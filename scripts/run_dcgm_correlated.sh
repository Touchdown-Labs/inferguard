#!/usr/bin/env bash
set -euo pipefail

: "${MODEL_NAME:?MODEL_NAME is required, e.g. /models/deepseek-v4}"
: "${ENDPOINT_URL:?ENDPOINT_URL is required, e.g. http://127.0.0.1:8000/v1/chat/completions}"
: "${TRACE_DIR:?TRACE_DIR is required, e.g. traces/isb1-dsv4-agent/coding-long}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
export PYTHONPATH="${REPO_ROOT}/src:${REPO_ROOT}:${PYTHONPATH:-}"

DCGM_IMAGE="${DCGM_IMAGE:-nvcr.io/nvidia/k8s/dcgm-exporter:4.5.2-4.8.1-distroless}"
DCGM_PORT="${DCGM_PORT:-9400}"
DCGM_METRICS_URL="${DCGM_METRICS_URL:-http://localhost:${DCGM_PORT}/metrics}"
VLLM_METRICS_URL="${VLLM_METRICS_URL:-http://localhost:8000/metrics}"
RESULTS_ROOT="${RESULTS_ROOT:-results/dcgm-correlated-$(date -u +%Y%m%dT%H%M%SZ)}"
CONCURRENCY="${CONCURRENCY:-1,4,8,16,32}"
OUTPUT_TOKENS="${OUTPUT_TOKENS:-512}"
WARMUP_SECONDS="${WARMUP_SECONDS:-30}"
DURATION_SECONDS="${DURATION_SECONDS:-300}"
CORRELATION_DURATION_SECONDS="${CORRELATION_DURATION_SECONDS:-${DURATION_SECONDS}}"
INTERVAL_SECONDS="${INTERVAL_SECONDS:-5}"
TIMEOUT="${TIMEOUT:-300}"
METRICS_INTERVAL="${METRICS_INTERVAL:-5}"
INFERGUARD_BIN="${INFERGUARD_BIN:-inferguard}"
PYTHON_BIN="${PYTHON_BIN:-python3}"
CONTAINER_RUNTIME="${CONTAINER_RUNTIME:-docker}"
DCGM_CONTAINER_NAME="${DCGM_CONTAINER_NAME:-inferguard-dcgm-exporter}"
BENCH_OUTPUT_DIR="${RESULTS_ROOT}/bench"
CORRELATED_OUTPUT_DIR="${RESULTS_ROOT}/dcgm-correlated"
CORRELATED_JSONL="${CORRELATED_OUTPUT_DIR}/dcgm-correlated-v1.jsonl"

phase() {
  printf '\n==> Phase: %s\n' "$1"
}

cleanup() {
  if [[ -n "${CORRELATOR_PID:-}" ]]; then
    kill "$CORRELATOR_PID" >/dev/null 2>&1 || true
    wait "$CORRELATOR_PID" >/dev/null 2>&1 || true
  fi
  if [[ "${STARTED_DCGM:-0}" == "1" ]]; then
    "$CONTAINER_RUNTIME" rm -f "$DCGM_CONTAINER_NAME" >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT

wait_for_metrics_url() {
  local label="$1"
  local url="$2"
  local attempt
  for attempt in $(seq 1 60); do
    if curl --fail --silent --max-time 2 "$url" >/dev/null; then
      return 0
    fi
    sleep 1
  done
  echo "ERROR: ${label} metrics endpoint did not become ready at ${url}" >&2
  return 1
}

mkdir -p "$RESULTS_ROOT" "$CORRELATED_OUTPUT_DIR"
phase "Environment summary"
cat <<EOF
MODEL_NAME=$MODEL_NAME
ENDPOINT_URL=$ENDPOINT_URL
TRACE_DIR=$TRACE_DIR
RESULTS_ROOT=$RESULTS_ROOT
DCGM_IMAGE=$DCGM_IMAGE
DCGM_METRICS_URL=$DCGM_METRICS_URL
VLLM_METRICS_URL=$VLLM_METRICS_URL
CONCURRENCY=$CONCURRENCY
OUTPUT_TOKENS=$OUTPUT_TOKENS
WARMUP_SECONDS=$WARMUP_SECONDS
DURATION_SECONDS=$DURATION_SECONDS
CORRELATION_DURATION_SECONDS=$CORRELATION_DURATION_SECONDS
INTERVAL_SECONDS=$INTERVAL_SECONDS
METRICS_INTERVAL=$METRICS_INTERVAL
EOF

phase "Pre-flight tools"
command -v "$INFERGUARD_BIN" >/dev/null 2>&1 || { echo "ERROR: inferguard binary not found: $INFERGUARD_BIN" >&2; exit 1; }
command -v "$PYTHON_BIN" >/dev/null 2>&1 || { echo "ERROR: python binary not found: $PYTHON_BIN" >&2; exit 1; }
command -v curl >/dev/null 2>&1 || { echo "ERROR: curl is required" >&2; exit 1; }
command -v "$CONTAINER_RUNTIME" >/dev/null 2>&1 || { echo "ERROR: container runtime not found: $CONTAINER_RUNTIME" >&2; exit 1; }

phase "Launch DCGM exporter"
"$CONTAINER_RUNTIME" rm -f "$DCGM_CONTAINER_NAME" >/dev/null 2>&1 || true
"$CONTAINER_RUNTIME" run -d --rm --gpus all --name "$DCGM_CONTAINER_NAME" -p "${DCGM_PORT}:9400" "$DCGM_IMAGE" >/dev/null
STARTED_DCGM=1
wait_for_metrics_url "DCGM" "$DCGM_METRICS_URL"
wait_for_metrics_url "vLLM" "$VLLM_METRICS_URL"

phase "Start dcgm-correlated/v1 sampler"
"$PYTHON_BIN" -m inferguard.harness.dcgm_correlate \
  --vllm-metrics-url "$VLLM_METRICS_URL" \
  --dcgm-metrics-url "$DCGM_METRICS_URL" \
  --output-dir "$CORRELATED_OUTPUT_DIR" \
  --duration-seconds "$CORRELATION_DURATION_SECONDS" \
  --interval-seconds "$INTERVAL_SECONDS" &
CORRELATOR_PID=$!

phase "Run InferGuard replay while correlation sampler is active"
"$INFERGUARD_BIN" bench replay \
  --endpoint "$ENDPOINT_URL" \
  --model "$MODEL_NAME" \
  --trace-dir "$TRACE_DIR" \
  --concurrency "$CONCURRENCY" \
  --output-tokens "$OUTPUT_TOKENS" \
  --warmup-seconds "$WARMUP_SECONDS" \
  --duration-seconds "$DURATION_SECONDS" \
  --timeout "$TIMEOUT" \
  --metrics-url "$VLLM_METRICS_URL" \
  --metrics-interval "$METRICS_INTERVAL" \
  --output-dir "$BENCH_OUTPUT_DIR" \
  --force

phase "Wait for correlation sampler"
wait "$CORRELATOR_PID"
CORRELATOR_PID=""

phase "Done"
echo "Bench output: $BENCH_OUTPUT_DIR"
echo "Correlated JSONL: $CORRELATED_JSONL"

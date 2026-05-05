#!/usr/bin/env bash
set -euo pipefail

: "${MODEL_NAME:?MODEL_NAME is required, e.g. /models/deepseek-v4}"
: "${ENDPOINT_URL:?ENDPOINT_URL is required, e.g. http://127.0.0.1:8000/v1/chat/completions}"

TRACE_DIR="${TRACE_DIR:-traces/isb1-dsv4-agent}"
OUTPUT_DIR="${OUTPUT_DIR:-runs/dsv4-smoke-$(date -u +%Y%m%dT%H%M%SZ)}"
CONCURRENCY="${CONCURRENCY:-1,4}"
OUTPUT_TOKENS="${OUTPUT_TOKENS:-256}"
ENDPOINT_BASE="${ENDPOINT_URL%/*}"
METRICS_URL="${METRICS_URL:-${ENDPOINT_BASE}/metrics}"

mkdir -p "$OUTPUT_DIR"

phase() {
  printf '\n==> %s\n' "$1"
}

phase "1. Environment summary"
cat <<EOF
MODEL_NAME=$MODEL_NAME
ENDPOINT_URL=$ENDPOINT_URL
TRACE_DIR=$TRACE_DIR
OUTPUT_DIR=$OUTPUT_DIR
CONCURRENCY=$CONCURRENCY
OUTPUT_TOKENS=$OUTPUT_TOKENS
METRICS_URL=$METRICS_URL
EOF

phase "2. Endpoint readiness checks"
if command -v curl >/dev/null 2>&1; then
  curl --fail --show-error --silent --max-time 10 "${ENDPOINT_BASE}/health" \
    > "$OUTPUT_DIR/health.json" || echo "health check best-effort failed; continuing"
  curl --fail --show-error --silent --max-time 20 "${ENDPOINT_BASE}/v1/models" \
    > "$OUTPUT_DIR/models.json"
else
  echo "curl not found; skipping HTTP readiness checks"
fi

phase "3. InferGuard disagg status smoke (best-effort)"
inferguard disagg status \
  --prefill "$METRICS_URL" \
  --decode "$METRICS_URL" \
  --json \
  > "$OUTPUT_DIR/disagg_status_smoke.json" \
  || echo "disagg status best-effort failed; continuing"

phase "4. InferGuard bench replay"
inferguard bench replay \
  --endpoint "$ENDPOINT_URL" \
  --model "$MODEL_NAME" \
  --trace-dir "$TRACE_DIR" \
  --concurrency "$CONCURRENCY" \
  --output-tokens "$OUTPUT_TOKENS" \
  --output-dir "$OUTPUT_DIR/bench" \
  --timeout 60

phase "5. InferGuard analyze"
inferguard analyze "$OUTPUT_DIR/bench" --format both

phase "6. Smoke complete"
echo "Report: $OUTPUT_DIR/bench/inferguard_report/report.md"

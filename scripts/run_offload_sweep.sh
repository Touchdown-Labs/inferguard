#!/usr/bin/env bash
set -euo pipefail

: "${MODEL_NAME:?MODEL_NAME is required, e.g. /models/deepseek-v4}"
: "${ENDPOINT_URL:?ENDPOINT_URL is required, e.g. http://127.0.0.1:8000/v1/chat/completions}"
: "${RIG_LABEL:?RIG_LABEL is required, e.g. h200, b200, b300, gb200}"
: "${OFFLOAD_LABEL:?OFFLOAD_LABEL is required, e.g. offload_off, offload_cpu_32gb}"

TRACE_DIR="${TRACE_DIR:-traces/isb1-dsv4-agent}"
RESULTS_ROOT="${RESULTS_ROOT:-results/offload-sweep-${RIG_LABEL}-$(date -u +%Y%m%dT%H%M%SZ)}"
CONCURRENCY="${CONCURRENCY:-1,4,8,16,32}"
OUTPUT_TOKENS="${OUTPUT_TOKENS:-512}"
WARMUP_SECONDS="${WARMUP_SECONDS:-60}"
DURATION_SECONDS="${DURATION_SECONDS:-600}"
TIMEOUT="${TIMEOUT:-300}"
REDACT_PROMPTS="${REDACT_PROMPTS:-0}"
INFERGUARD_BIN="${INFERGUARD_BIN:-inferguard}"
ENDPOINT_MODELS_URL="${ENDPOINT_URL%/v1*}/v1/models"
CONFIG_RESULTS_ROOT="$RESULTS_ROOT/$OFFLOAD_LABEL"
COMPARISON_PATH="$RESULTS_ROOT/cross-config-comparison.md"

WORKLOAD_CLASSES=(
  coding-long
  agent-chat
  multi-agent-coding
  tool-heavy
  session-resume
  prefix-reuse
  kv-pressure
)

phase() {
  printf '\n==> Phase: %s\n' "$1"
}

count_expected_cells() {
  local csv="$1"
  local rest="$csv"
  local count=1
  if [[ -z "$csv" ]]; then
    echo 0
    return
  fi
  while [[ "$rest" == *,* ]]; do
    count=$((count + 1))
    rest="${rest#*,}"
  done
  echo "$count"
}

count_captured_cells() {
  local summary_path="$1"
  if [[ ! -s "$summary_path" ]]; then
    echo 0
    return
  fi
  python3 - "$summary_path" <<'PY'
import json
import sys
from pathlib import Path

try:
    data = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
except Exception:
    print(0)
    raise SystemExit(0)

levels = data.get("concurrency", [])
if isinstance(levels, list):
    print(sum(1 for item in levels if isinstance(item, dict) and item.get("total", 0) > 0))
else:
    print(0)
PY
}

has_artifacts() {
  local dir="$1"
  [[ -d "$dir" ]] && find "$dir" -type f -print -quit | grep -q .
}

write_cross_config_comparison() {
  local results_root="$1"
  local comparison_path="$2"
  python3 - "$results_root" "$comparison_path" <<'PY'
import json
import sys
from pathlib import Path

results_root = Path(sys.argv[1])
comparison_path = Path(sys.argv[2])
rows = []
for report_path in sorted(results_root.glob("*/inferguard_report/report.json")):
    offload_label = report_path.parents[1].name
    try:
        report = json.loads(report_path.read_text(encoding="utf-8"))
    except Exception as exc:  # pragma: no cover - shell-facing guardrail
        rows.append([offload_label, "unreadable", "0", "0", "0", f"parse error: {exc}"])
        continue
    summary = report.get("run_summary", {})
    cells = report.get("cells", [])
    findings = report.get("findings", [])
    rows.append(
        [
            offload_label,
            str(summary.get("status", "unknown")),
            str(summary.get("total_cells", len(cells))),
            str(summary.get("successful_cells", "")),
            str(len(findings)),
            str(report_path.relative_to(results_root)),
        ]
    )

lines = [
    "# InferGuard offload sweep comparison",
    "",
    "| Offload config | Status | Cells | Successful cells | Findings | Report |",
    "|---|---|---:|---:|---:|---|",
]
if rows:
    lines.extend(f"| {' | '.join(row)} |" for row in rows)
else:
    lines.append("| _none_ | missing | 0 | 0 | 0 | _no reports found_ |")
lines.append("")
comparison_path.write_text("\n".join(lines), encoding="utf-8")
PY
}

mkdir -p "$CONFIG_RESULTS_ROOT"
EXPECTED_CELLS="$(count_expected_cells "$CONCURRENCY")"

phase "Environment summary"
cat <<EOF_SUMMARY
MODEL_NAME=$MODEL_NAME
ENDPOINT_URL=$ENDPOINT_URL
RIG_LABEL=$RIG_LABEL
OFFLOAD_LABEL=$OFFLOAD_LABEL
TRACE_DIR=$TRACE_DIR
RESULTS_ROOT=$RESULTS_ROOT
CONFIG_RESULTS_ROOT=$CONFIG_RESULTS_ROOT
CONCURRENCY=$CONCURRENCY
OUTPUT_TOKENS=$OUTPUT_TOKENS
WARMUP_SECONDS=$WARMUP_SECONDS
DURATION_SECONDS=$DURATION_SECONDS
TIMEOUT=$TIMEOUT
REDACT_PROMPTS=$REDACT_PROMPTS
INFERGUARD_BIN=$INFERGUARD_BIN
ENDPOINT_MODELS_URL=$ENDPOINT_MODELS_URL
METRICS_URL=${METRICS_URL:-}
EOF_SUMMARY

phase "Pre-flight endpoint readiness"
command -v "$INFERGUARD_BIN" >/dev/null 2>&1 || {
  echo "ERROR: inferguard binary not found: $INFERGUARD_BIN" >&2
  exit 1
}
command -v curl >/dev/null 2>&1 || {
  echo "ERROR: curl is required for endpoint pre-flight" >&2
  exit 1
}
if ! curl --fail --show-error --silent --max-time 20 "$ENDPOINT_MODELS_URL" > "$CONFIG_RESULTS_ROOT/models.json"; then
  echo "ERROR: endpoint pre-flight failed: $ENDPOINT_MODELS_URL" >&2
  exit 1
fi

phase "ISB-1 workload replay sweep for $OFFLOAD_LABEL"
declare -A STATUS_BY_CLASS=()
declare -A CAPTURED_BY_CLASS=()
artifact_classes=0

for workload_class in "${WORKLOAD_CLASSES[@]}"; do
  class_trace_dir="$TRACE_DIR/$workload_class"
  class_output_dir="$CONFIG_RESULTS_ROOT/$workload_class"
  bench_args=(
    bench replay
    --endpoint "$ENDPOINT_URL"
    --model "$MODEL_NAME"
    --trace-dir "$class_trace_dir"
    --concurrency "$CONCURRENCY"
    --output-tokens "$OUTPUT_TOKENS"
    --warmup-seconds "$WARMUP_SECONDS"
    --duration-seconds "$DURATION_SECONDS"
    --timeout "$TIMEOUT"
    --output-dir "$class_output_dir"
  )
  if [[ -n "${METRICS_URL:-}" ]]; then
    bench_args+=(--metrics-url "$METRICS_URL")
  fi
  if [[ "$REDACT_PROMPTS" == "1" ]]; then
    bench_args+=(--redact-prompts)
  fi

  phase "Replay $workload_class"
  if "$INFERGUARD_BIN" "${bench_args[@]}"; then
    STATUS_BY_CLASS["$workload_class"]="ok"
  else
    STATUS_BY_CLASS["$workload_class"]="failed"
    echo "WARNING: workload failed; continuing: $workload_class" >&2
  fi

  if has_artifacts "$class_output_dir"; then
    artifact_classes=$((artifact_classes + 1))
  fi
  CAPTURED_BY_CLASS["$workload_class"]="$(count_captured_cells "$class_output_dir/summary.json")"
done

phase "Analyze consolidated results for $OFFLOAD_LABEL"
if ! "$INFERGUARD_BIN" analyze "$CONFIG_RESULTS_ROOT"; then
  echo "WARNING: inferguard analyze failed for $CONFIG_RESULTS_ROOT" >&2
fi

phase "Write cross-config comparison"
write_cross_config_comparison "$RESULTS_ROOT" "$COMPARISON_PATH"
echo "Cross-config comparison: $COMPARISON_PATH"

phase "Offload config summary"
report_path="$CONFIG_RESULTS_ROOT/inferguard_report/report.md"
echo "Config report: $report_path"
printf '\n| Workload class | Status | Cells captured | Cells expected |\n'
printf '|---|---|---:|---:|\n'
for workload_class in "${WORKLOAD_CLASSES[@]}"; do
  printf '| %s | %s | %s | %s |\n' \
    "$workload_class" \
    "${STATUS_BY_CLASS[$workload_class]}" \
    "${CAPTURED_BY_CLASS[$workload_class]}" \
    "$EXPECTED_CELLS"
done

if (( artifact_classes >= 6 )); then
  echo "Offload config acceptable: $artifact_classes/7 workload classes produced artifacts."
  exit 0
fi

echo "Offload config failed: only $artifact_classes/7 workload classes produced artifacts." >&2
exit 1

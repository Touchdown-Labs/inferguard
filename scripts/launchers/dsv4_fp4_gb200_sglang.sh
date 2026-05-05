#!/usr/bin/env bash
set -euo pipefail

# Touchdown-planned SGLang GB200 DSv4-Flash launcher mirror.
#
# 🟡 PENDING upstream scheduler guard: keep this launcher gated until the GB200
# mixed decode + multi-prefill FlashMLA crash path is validated with SGLang
# issue #23743 and the mergeable scheduler-guard fix in PR #23741. SGLang
# DSv4 docs landed in #23725; this script mirrors the documented
# DeepSeek-V4/Flash parser + DeepEP direction without claiming upstream merge.

: "${MODEL_PATH:=deepseek-ai/DeepSeek-V4-Flash}"
: "${HOST:=0.0.0.0}"
: "${PORT:=30000}"
: "${TP:=4}"
: "${MAX_RUNNING_REQUESTS:=64}"
: "${CUDA_GRAPH_MAX_BS:=64}"
: "${MAX_TOTAL_TOKENS:=1048576}"
: "${SGLANG_DEEPEP_NUM_MAX_DISPATCH_TOKENS_PER_RANK:=4096}"
: "${SGLANG_ENABLE_SPEC_V2:=1}"
: "${ENABLE_LMCACHE:=0}"
: "${ENABLE_HICACHE:=0}"
: "${EXTRA_ARGS:=}"

export SGLANG_DEEPEP_NUM_MAX_DISPATCH_TOKENS_PER_RANK
export SGLANG_ENABLE_SPEC_V2

args=(
  python3 -m sglang.launch_server
  --model-path "$MODEL_PATH"
  --tp "$TP"
  --host "$HOST"
  --port "$PORT"
  --enable-metrics
  --enable-deepep
  --tool-call-parser deepseekv4
  --reasoning-parser deepseek-v4
  --max-running-requests "$MAX_RUNNING_REQUESTS"
  --cuda-graph-max-bs "$CUDA_GRAPH_MAX_BS"
  --max-total-tokens "$MAX_TOTAL_TOKENS"
)

if [[ "$ENABLE_LMCACHE" == "1" ]]; then
  # Cross-engine cache layer. Validate live before partner-facing claims.
  args+=(--enable-lmcache)
fi

if [[ "$ENABLE_HICACHE" == "1" ]]; then
  # SGLang-native ceiling mode; keep separately labeled from LMCache cells.
  args+=(--enable-hicache)
fi

if [[ -n "$EXTRA_ARGS" ]]; then
  # shellcheck disable=SC2206
  extra=( $EXTRA_ARGS )
  args+=("${extra[@]}")
fi

printf 'Launching SGLang DSv4 GB200 mirror (PENDING #23741/#23743 validation)\n' >&2
printf '  MODEL_PATH=%s TP=%s PORT=%s MAX_RUNNING_REQUESTS=%s\n' "$MODEL_PATH" "$TP" "$PORT" "$MAX_RUNNING_REQUESTS" >&2
exec "${args[@]}"

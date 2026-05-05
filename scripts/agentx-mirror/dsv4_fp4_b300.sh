#!/usr/bin/env bash
set -euo pipefail
set -x

# Agentic trace replay benchmark for DeepSeek-V4-Pro FP4 on B300 using vLLM v0.20 + deep_gemm_mega_moe + MTP config.
# Required env vars: MODEL, TP, CONC, RESULT_DIR

source "$(dirname "$0")/../../benchmark_lib.sh"

check_env_vars MODEL TP CONC RESULT_DIR

PORT=${PORT:-8888}
DURATION=${DURATION:-1800}
MAX_DELAY=${MAX_DELAY:-60}
ADVANCE_MIN=${ADVANCE_MIN:-0.0}
ADVANCE_MAX=${ADVANCE_MAX:-0.7}
IMAGE=${IMAGE:-vllm/vllm-openai:deepseekv4-cu130}
OFFLOADING=${OFFLOADING:-none}
TOTAL_CPU_DRAM_GB=${TOTAL_CPU_DRAM_GB:-0}
MAX_MODEL_LEN=${MAX_MODEL_LEN:-800000}
MTP_ARGS=${MTP_ARGS:-"--num-lookahead-slots 1 --speculative-config {\"method\":\"deepseek_mtp\",\"num_speculative_tokens\":1}"}

case "${OFFLOADING:-none}" in
  none) OFFLOAD_ARGS="" ;;
  cpu) OFFLOAD_ARGS="--kv_offloading_backend native --kv_offloading_size $TOTAL_CPU_DRAM_GB --disable-hybrid-kv-cache-manager" ;;
  *) echo "Error: unsupported OFFLOADING value '$OFFLOADING'" >&2; exit 1 ;;
esac

if [[ "$MODEL" != /* ]]; then hf download "$MODEL"; fi
nvidia-smi
resolve_trace_source
install_agentic_deps

export VLLM_ENGINE_READY_TIMEOUT_S=3600
SERVER_LOG="$RESULT_DIR/server.log"
mkdir -p "$RESULT_DIR"

export PYTHONNOUSERSITE=1
vllm serve $MODEL \
--host 0.0.0.0 \
--port $PORT \
--trust-remote-code \
--kv-cache-dtype fp4 \
--block-size 256 \
--no-enable-prefix-caching \
--enable-expert-parallel \
--data-parallel-size $TP \
--moe-backend deep_gemm_mega_moe \
--max-model-len $MAX_MODEL_LEN \
--gpu-memory-utilization 0.85 \
--max-num-seqs $CONC \
--max-num-batched-tokens 512 \
--compilation-config '{"cudagraph_mode":"FULL_AND_PIECEWISE","custom_ops":["all"]}' \
--attention_config.use_fp4_indexer_cache=True \
--tokenizer-mode deepseek_v4 \
--tool-call-parser deepseek_v4 \
--enable-auto-tool-choice \
--enable-expert-parallel \
$MTP_ARGS \
$OFFLOAD_ARGS > "$SERVER_LOG" 2>&1 &
SERVER_PID=$!

wait_for_server_ready --port "$PORT" --server-log "$SERVER_LOG" --server-pid "$SERVER_PID"
build_replay_cmd "$RESULT_DIR"
echo "$REPLAY_CMD" > "$RESULT_DIR/benchmark_command.txt"
$REPLAY_CMD 2>&1 | tee "$RESULT_DIR/benchmark.log" || true
write_agentic_result_json "$RESULT_DIR"
python3 "$AGENTIC_DIR/scripts/analyze_benchmark_distributions.py" "$RESULT_DIR/trace_replay" -o "$RESULT_DIR" 2>&1 || true

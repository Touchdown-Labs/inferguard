#!/usr/bin/env bash
set -euo pipefail

# InferGuard B200 DSv4-Pro launcher, aligned with upstream dsv4_fp4_b200_vllm.sh.
# DP_ATTENTION=true enables DP+EP with DeepGEMM MegaMOE; DP_ATTENTION=false is TP-only.
# Blackwell path enables FP4 indexer cache and FULL_AND_PIECEWISE cudagraph compilation.
# This script does not provision cloud resources or authenticate to any service.

MODEL_NAME="${MODEL_NAME:-deepseek-ai/DeepSeek-V4-Pro}"
HOST="${HOST:-0.0.0.0}"
PORT="${PORT:-8000}"
TP_SIZE="${TP_SIZE:-8}"
DP_ATTENTION="${DP_ATTENTION:-false}"
ENABLE_PREFIX_CACHING="${ENABLE_PREFIX_CACHING:-false}"
IMAGE="${IMAGE:-vllm/vllm-openai:deepseekv4-cu130}"
KV_CACHE_DTYPE="${KV_CACHE_DTYPE:-fp8}"
BLOCK_SIZE="${BLOCK_SIZE:-256}"
MAX_CUDAGRAPH_CAPTURE_SIZE="${MAX_CUDAGRAPH_CAPTURE_SIZE:-2048}"

export VLLM_ENGINE_READY_TIMEOUT_S="${VLLM_ENGINE_READY_TIMEOUT_S:-3600}"

PARALLEL_ARGS=(--tensor-parallel-size "${TP_SIZE}")
EP_ARGS=()
GMU_ARGS=()
MOE_ARGS=()
EP_SIZE="1"
if [ "${DP_ATTENTION}" = "true" ]; then
  EP_SIZE="${TP_SIZE}"
  PARALLEL_ARGS=(--data-parallel-size "${TP_SIZE}")
  EP_ARGS=(--enable-expert-parallel)
  GMU_ARGS=(--gpu-memory-utilization "${GPU_MEMORY_UTILIZATION:-0.85}")
  MOE_ARGS=(--moe-backend deep_gemm_mega_moe)
elif [ "${DP_ATTENTION}" != "false" ]; then
  echo "ERROR: DP_ATTENTION must be true or false; got ${DP_ATTENTION}." >&2
  exit 1
fi

PREFIX_CACHE_ARGS=(--no-enable-prefix-caching)
if [ "${ENABLE_PREFIX_CACHING}" = "true" ]; then
  PREFIX_CACHE_ARGS=(--enable-prefix-caching)
elif [ "${ENABLE_PREFIX_CACHING}" != "false" ]; then
  echo "ERROR: ENABLE_PREFIX_CACHING must be true or false; got ${ENABLE_PREFIX_CACHING}." >&2
  exit 1
fi

echo "==> Phase: InferGuard B200 DSv4-Pro vLLM launch"
echo "MODEL_NAME=${MODEL_NAME}"
echo "HOST=${HOST}"
echo "PORT=${PORT}"
echo "TP_SIZE=${TP_SIZE}"
echo "DP_ATTENTION=${DP_ATTENTION}"
echo "EP_SIZE=${EP_SIZE}"
echo "ENABLE_PREFIX_CACHING=${ENABLE_PREFIX_CACHING}"
echo "IMAGE=${IMAGE}"
echo "KV_CACHE_DTYPE=${KV_CACHE_DTYPE}"
echo "BLOCK_SIZE=${BLOCK_SIZE}"
echo "MAX_CUDAGRAPH_CAPTURE_SIZE=${MAX_CUDAGRAPH_CAPTURE_SIZE}"
echo "VLLM_ENGINE_READY_TIMEOUT_S=${VLLM_ENGINE_READY_TIMEOUT_S}"

echo "==> Phase: pre-flight — B200 rig sanity"
if ! command -v nvidia-smi >/dev/null 2>&1; then
  echo "ERROR: nvidia-smi is required for B200 rig pre-flight." >&2
  exit 1
fi
GPU_LIST="$(nvidia-smi -L)"
echo "${GPU_LIST}"
if echo "${GPU_LIST}" | grep -Eiq 'H100|H200|B300|GB200|GB300|A100|L40|RTX|MI[0-9]'; then
  echo "ERROR: Non-B200 GMI rig detected; refusing to launch this B200-only recipe." >&2
  exit 1
fi
if ! echo "${GPU_LIST}" | grep -Eiq 'B200'; then
  echo "ERROR: No B200 GPUs detected by nvidia-smi -L." >&2
  exit 1
fi
GPU_COUNT="$(echo "${GPU_LIST}" | grep -Ec '^GPU [0-9]+:')"
if [ "${GPU_COUNT}" -lt "${TP_SIZE}" ]; then
  echo "ERROR: TP_SIZE=${TP_SIZE} requires at least ${TP_SIZE} visible GPUs; found ${GPU_COUNT}." >&2
  exit 1
fi

echo "==> Phase: Launch vLLM OpenAI container"
docker run --rm --gpus all --ipc=host --shm-size=16g \
  -e "VLLM_ENGINE_READY_TIMEOUT_S=${VLLM_ENGINE_READY_TIMEOUT_S}" \
  -p "${PORT}:${PORT}" \
  --entrypoint vllm \
  "${IMAGE}" \
  serve "${MODEL_NAME}" --host "${HOST}" --port "${PORT}" \
    --kv-cache-dtype "${KV_CACHE_DTYPE}" \
    --block-size "${BLOCK_SIZE}" \
    "${PREFIX_CACHE_ARGS[@]}" \
    "${PARALLEL_ARGS[@]}" \
    "${EP_ARGS[@]}" \
    "${GMU_ARGS[@]}" \
    "${MOE_ARGS[@]}" \
    --compilation-config '{"cudagraph_mode":"FULL_AND_PIECEWISE","custom_ops":["all"]}' \
    --attention_config.use_fp4_indexer_cache=True \
    --tokenizer-mode deepseek_v4 \
    --tool-call-parser deepseek_v4 \
    --enable-auto-tool-choice \
    --max-cudagraph-capture-size "${MAX_CUDAGRAPH_CAPTURE_SIZE}" \
    --trust-remote-code

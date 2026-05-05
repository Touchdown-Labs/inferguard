#!/usr/bin/env bash
set -euo pipefail

# InferGuard H200 DSv4-Pro launcher, aligned with upstream dsv4_fp8_h200.sh.
# H200 recipe uses the cu129 image and omits the FP4 indexer cache flag; H200 has no FP4 path.
# Max-model-len is pinned at 800k per the verified upstream recipe.
# This script does not provision cloud resources or authenticate to any service.

MODEL_NAME="${MODEL_NAME:-deepseek-ai/DeepSeek-V4-Pro}"
HOST="${HOST:-0.0.0.0}"
PORT="${PORT:-8000}"
TP_SIZE="${TP_SIZE:-8}"
MAX_MODEL_LEN="${MAX_MODEL_LEN:-800000}"
GPU_MEMORY_UTILIZATION="${GPU_MEMORY_UTILIZATION:-0.95}"
IMAGE="${IMAGE:-vllm/vllm-openai:deepseekv4-cu129}"
KV_CACHE_DTYPE="${KV_CACHE_DTYPE:-fp8}"
BLOCK_SIZE="${BLOCK_SIZE:-256}"
MAX_NUM_SEQS="${MAX_NUM_SEQS:-512}"
MAX_NUM_BATCHED_TOKENS="${MAX_NUM_BATCHED_TOKENS:-512}"

export VLLM_ENGINE_READY_TIMEOUT_S="${VLLM_ENGINE_READY_TIMEOUT_S:-3600}"

echo "==> Phase: InferGuard H200 DSv4-Pro vLLM launch"
echo "MODEL_NAME=${MODEL_NAME}"
echo "HOST=${HOST}"
echo "PORT=${PORT}"
echo "TP_SIZE=${TP_SIZE}"
echo "MAX_MODEL_LEN=${MAX_MODEL_LEN}"
echo "GPU_MEMORY_UTILIZATION=${GPU_MEMORY_UTILIZATION}"
echo "IMAGE=${IMAGE}"
echo "KV_CACHE_DTYPE=${KV_CACHE_DTYPE}"
echo "BLOCK_SIZE=${BLOCK_SIZE}"
echo "MAX_NUM_SEQS=${MAX_NUM_SEQS}"
echo "MAX_NUM_BATCHED_TOKENS=${MAX_NUM_BATCHED_TOKENS}"
echo "VLLM_ENGINE_READY_TIMEOUT_S=${VLLM_ENGINE_READY_TIMEOUT_S}"

echo "==> Phase: pre-flight — H200 SXM5 141GB rig sanity"
if ! command -v nvidia-smi >/dev/null 2>&1; then
  echo "ERROR: nvidia-smi is required for H200 rig pre-flight." >&2
  exit 1
fi
GPU_LIST="$(nvidia-smi -L)"
echo "${GPU_LIST}"
if echo "${GPU_LIST}" | grep -Eiq 'H100|B200|B300|GB200|GB300|A100|L40|RTX|MI[0-9]'; then
  echo "ERROR: Non-H200 GMI rig detected; refusing to launch this H200-only recipe." >&2
  exit 1
fi
if ! echo "${GPU_LIST}" | grep -Eiq 'H200'; then
  echo "ERROR: No H200 GPUs detected by nvidia-smi -L." >&2
  exit 1
fi
if ! echo "${GPU_LIST}" | grep -Eiq '141GB|HBM3e|SXM5'; then
  echo "ERROR: H200 GPUs detected, but nvidia-smi -L did not show H200 SXM5/141GB markers." >&2
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
    --no-enable-prefix-caching \
    --enable-expert-parallel \
    --data-parallel-size "${TP_SIZE}" \
    --max-model-len "${MAX_MODEL_LEN}" \
    --gpu-memory-utilization "${GPU_MEMORY_UTILIZATION}" \
    --max-num-seqs "${MAX_NUM_SEQS}" \
    --max-num-batched-tokens "${MAX_NUM_BATCHED_TOKENS}" \
    --no-enable-flashinfer-autotune \
    --compilation-config '{"mode":0,"cudagraph_mode":"FULL_DECODE_ONLY"}' \
    --tokenizer-mode deepseek_v4 \
    --tool-call-parser deepseek_v4 \
    --enable-auto-tool-choice \
    --trust-remote-code

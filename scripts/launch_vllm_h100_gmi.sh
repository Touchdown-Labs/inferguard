#!/usr/bin/env bash
set -euo pipefail

# InferGuard-authored H100 DSv4 launcher.
# Hyperstack verification: "V4-Pro's ~960 GB FP4+FP8 mixed-precision checkpoint exceeds the 640 GB total VRAM of a single 8x H100-80G node."
# H100 launches therefore use DeepSeek-V4-Flash (284B-A13B, FP8) which fits comfortably.
# Active params 13B → fits in FP8 expert weights on Hopper without FP4 hardware.
# MAX_MODEL_LEN defaults to 32K even though V4-Flash supports 128K; agent workloads cap at 32K.
# This script does not provision cloud resources or authenticate to any service.

MODEL_NAME="${MODEL_NAME:-deepseek-ai/DeepSeek-V4-Flash}"
HOST="${HOST:-0.0.0.0}"
PORT="${PORT:-8000}"
TP_SIZE="${TP_SIZE:-8}"
MAX_MODEL_LEN="${MAX_MODEL_LEN:-32768}"
GPU_MEMORY_UTILIZATION="${GPU_MEMORY_UTILIZATION:-0.95}"
IMAGE="${IMAGE:-vllm/vllm-openai:deepseekv4-cu129}"
KV_CACHE_DTYPE="${KV_CACHE_DTYPE:-fp8}"
BLOCK_SIZE="${BLOCK_SIZE:-256}"
MAX_NUM_SEQS="${MAX_NUM_SEQS:-256}"
MAX_NUM_BATCHED_TOKENS="${MAX_NUM_BATCHED_TOKENS:-512}"

export VLLM_ENGINE_READY_TIMEOUT_S="${VLLM_ENGINE_READY_TIMEOUT_S:-3600}"

echo "==> Phase: InferGuard H100 DSv4-Flash vLLM launch"
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

echo "==> Phase: pre-flight — H100 SXM5 80GB rig sanity"
if ! command -v nvidia-smi >/dev/null 2>&1; then
  echo "ERROR: nvidia-smi is required for H100 rig pre-flight." >&2
  exit 1
fi
GPU_LIST="$(nvidia-smi -L)"
echo "${GPU_LIST}"
if echo "${GPU_LIST}" | grep -Eiq 'H200|B200|B300|GB200|GB300|A100|L40|RTX|MI[0-9]'; then
  echo "ERROR: Non-H100 GMI rig detected; refusing to launch this H100-only recipe." >&2
  exit 1
fi
if ! echo "${GPU_LIST}" | grep -Eiq 'H100'; then
  echo "ERROR: No H100 GPUs detected by nvidia-smi -L." >&2
  exit 1
fi
if ! echo "${GPU_LIST}" | grep -Eiq '80GB|HBM3|SXM5'; then
  echo "ERROR: H100 GPUs detected, but nvidia-smi -L did not show H100 SXM5/80GB markers." >&2
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
    --tensor-parallel-size "${TP_SIZE}" \
    --kv-cache-dtype "${KV_CACHE_DTYPE}" \
    --block-size "${BLOCK_SIZE}" \
    --no-enable-prefix-caching \
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

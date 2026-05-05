#!/usr/bin/env bash
set -euo pipefail

# Template only: fill in model, tensor parallelism, ports, and GMI host/container setup.
# This script does not provision cloud resources or authenticate to any service.

MODEL_NAME="${MODEL_NAME:?set MODEL_NAME to your local/private model path or verified HF repo}"
HOST="${HOST:-0.0.0.0}"
PORT="${PORT:-8000}"
TP_SIZE="${TP_SIZE:-1}"
GPU_MEMORY_UTILIZATION="${GPU_MEMORY_UTILIZATION:-0.90}"
MAX_MODEL_LEN="${MAX_MODEL_LEN:-131072}"

python -m vllm.entrypoints.openai.api_server \
  --host "${HOST}" \
  --port "${PORT}" \
  --model "${MODEL_NAME}" \
  --tensor-parallel-size "${TP_SIZE}" \
  --gpu-memory-utilization "${GPU_MEMORY_UTILIZATION}" \
  --max-model-len "${MAX_MODEL_LEN}"

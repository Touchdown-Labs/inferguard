#!/usr/bin/env bash
set -euo pipefail

# Template only: fill in model, tensor parallelism, ports, and GMI host/container setup.
# This script does not provision cloud resources or authenticate to any service.

MODEL_NAME="${MODEL_NAME:?set MODEL_NAME to your local/private model path or verified HF repo}"
HOST="${HOST:-0.0.0.0}"
PORT="${PORT:-8000}"
TP_SIZE="${TP_SIZE:-1}"
CONTEXT_LENGTH="${CONTEXT_LENGTH:-131072}"
MEM_FRACTION_STATIC="${MEM_FRACTION_STATIC:-0.88}"

python -m sglang.launch_server \
  --host "${HOST}" \
  --port "${PORT}" \
  --model-path "${MODEL_NAME}" \
  --tp-size "${TP_SIZE}" \
  --context-length "${CONTEXT_LENGTH}" \
  --mem-fraction-static "${MEM_FRACTION_STATIC}"

#!/usr/bin/env bash
set -euo pipefail

# GB200 DSv4-Pro disaggregated chooser.
# This is intentionally NOT a single `vllm serve` script: GB200 DSv4 disagg uses upstream
# InferenceX srt-slurm YAML recipes for multi-node Dynamo-vLLM prefill+decode workers.
# This script validates the selected upstream recipe and prints the srt_bench.sh pattern.

RECIPE_NAME="${1:-disagg-gb200-low-latency}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INFERENCEX_PATH="${INFERENCEX_PATH:-${SCRIPT_DIR}/../../../repos/inferencex}"
RECIPE_DIR="${INFERENCEX_PATH}/benchmarks/multi_node/srt-slurm-recipes/vllm/deepseek-v4/8k1k"
RECIPE_FILE="${RECIPE_DIR}/${RECIPE_NAME}.yaml"
IMAGE="${IMAGE:-vllm/vllm-openai:deepseekv4-arm64-cu130}"
MODEL="${MODEL:-deepseek-ai/DeepSeek-V4-Pro}"
ISL="${ISL:-8192}"
OSL="${OSL:-1024}"
CONC="${CONC:-1}"

VALID_RECIPES=(
  disagg-gb200-low-latency
  disagg-gb200-low-middle-curve
  disagg-gb200-mid-curve-megamoe
  disagg-gb200-max-tpt-megamoe
  disagg-gb200-high-tpt-megamoe
  disagg-gb200-2p1d-dep8-dep8-c4096-offload
  disagg-gb200-3p1d-dep8-dep16-c4096-offload
)

is_valid_recipe=false
for valid_recipe in "${VALID_RECIPES[@]}"; do
  if [ "${RECIPE_NAME}" = "${valid_recipe}" ]; then
    is_valid_recipe=true
    break
  fi
done

echo "==> Phase: InferGuard GB200 DSv4-Pro disagg recipe chooser"
echo "RECIPE_NAME=${RECIPE_NAME}"
echo "INFERENCEX_PATH=${INFERENCEX_PATH}"
echo "RECIPE_DIR=${RECIPE_DIR}"
echo "IMAGE=${IMAGE}"
echo "MODEL=${MODEL}"
echo "ISL=${ISL}"
echo "OSL=${OSL}"
echo "CONC=${CONC}"

echo "==> Phase: pre-flight — GB200 disaggregated rig sanity"
if command -v nvidia-smi >/dev/null 2>&1; then
  GPU_LIST="$(nvidia-smi -L || true)"
  if [ -n "${GPU_LIST}" ]; then
    echo "${GPU_LIST}"
    if echo "${GPU_LIST}" | grep -Eiq 'H100|H200|A100|L40|RTX|MI[0-9]'; then
      echo "ERROR: Non-GB200 rig detected; refusing to select a GB200 disagg recipe." >&2
      exit 1
    fi
    if ! echo "${GPU_LIST}" | grep -Eiq 'GB200|B200'; then
      echo "WARNING: nvidia-smi did not show GB200/B200 markers; continue only from a GB200 Slurm allocation." >&2
    fi
  fi
else
  echo "INFO: nvidia-smi not found; assuming this is a Slurm login/controller node."
fi

if [ "${is_valid_recipe}" != "true" ]; then
  echo "ERROR: Unknown GB200 DSv4 disagg recipe: ${RECIPE_NAME}" >&2
  echo "Valid recipe names:" >&2
  printf '  %s\n' "${VALID_RECIPES[@]}" >&2
  exit 1
fi

if [ ! -f "${RECIPE_FILE}" ]; then
  echo "ERROR: Recipe was valid by name but not found on disk:" >&2
  echo "  ${RECIPE_FILE}" >&2
  echo "Set INFERENCEX_PATH to an InferenceX checkout containing upstream srt-slurm recipes." >&2
  exit 1
fi

echo "==> Phase: validated upstream recipe"
echo "${RECIPE_FILE}"

echo "==> Phase: valid GB200 DSv4 disagg recipe names"
printf '  %s\n' "${VALID_RECIPES[@]}"

cat <<EOF
==> Phase: srt_bench.sh invocation pattern
GB200 DSv4 disagg uses upstream InferenceX srt-slurm YAML recipes with multi-node Dynamo-vLLM prefill+decode workers.
Run from the InferenceX checkout pinned to current upstream HEAD, then invoke the recipe with the same env-var shape upstream uses:

  cd "${INFERENCEX_PATH}"
  MODEL="${MODEL}" \\
  ISL="${ISL}" \\
  OSL="${OSL}" \\
  CONC="${CONC}" \\
  IMAGE="${IMAGE}" \\
  bash benchmarks/multi_node/srt_bench.sh "${RECIPE_FILE}"

Default DSv4-specialized ARM image for GB200: ${IMAGE}
EOF

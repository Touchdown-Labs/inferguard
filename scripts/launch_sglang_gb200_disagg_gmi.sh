#!/usr/bin/env bash
set -euo pipefail

# GB200 DSv4-Pro disaggregated SGLang chooser.
# GB200 DSv4 disagg uses upstream InferenceX srt-slurm YAML recipes for
# multi-node prefill+decode workers; this script validates the selected
# upstream SGLang recipe before invoking srt_bench.sh.
#
# Upstream Day 0 DSv4 Pro FP4 GB200 SGLang image from InferenceX@504048f1:
#   lmsysorg/sglang:deepseek-v4-grace-blackwell

MODEL_NAME="${MODEL_NAME:-/scratch/dsv4-pro}"
INFERENCEX_PATH="${INFERENCEX_PATH:-/path/to/InferenceX}"
RECIPE_NAME="${1:-conc512}"
RECIPE_DIR="${INFERENCEX_PATH}/benchmarks/multi_node/srt-slurm-recipes/sglang/deepseek-v4/8k1k"
RECIPE_FILE="${RECIPE_DIR}/${RECIPE_NAME}.yaml"
IMAGE="${IMAGE:-lmsysorg/sglang:deepseek-v4-grace-blackwell}"

VALID_RECIPES=(
  conc1
  conc512
  conc512-20
  conc1024
  conc2048
  conc16384
)

is_valid_recipe=false
for valid_recipe in "${VALID_RECIPES[@]}"; do
  if [ "${RECIPE_NAME}" = "${valid_recipe}" ]; then
    is_valid_recipe=true
    break
  fi
done

echo "==> Phase: InferGuard GB200 DSv4-Pro SGLang disagg recipe chooser"
echo "MODEL_NAME=${MODEL_NAME}"
echo "INFERENCEX_PATH=${INFERENCEX_PATH}"
echo "RECIPE_NAME=${RECIPE_NAME}"
echo "RECIPE_DIR=${RECIPE_DIR}"
echo "IMAGE=${IMAGE}"

echo "==> Phase: pre-flight — GB200 disaggregated rig sanity"
if command -v nvidia-smi >/dev/null 2>&1; then
  GPU_LIST="$(nvidia-smi -L || true)"
  if [ -n "${GPU_LIST}" ]; then
    echo "${GPU_LIST}"
    if echo "${GPU_LIST}" | grep -Eiq 'H100|H200|A100|L40|RTX|MI[0-9]'; then
      echo "ERROR: Non-GB200 rig detected; refusing to select a GB200 SGLang disagg recipe." >&2
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
  echo "ERROR: Unknown GB200 DSv4 SGLang disagg recipe: ${RECIPE_NAME}" >&2
  echo "Valid recipe names:" >&2
  printf '  %s
' "${VALID_RECIPES[@]}" >&2
  exit 1
fi

if [ ! -f "${RECIPE_FILE}" ]; then
  echo "ERROR: Recipe was valid by name but not found on disk:" >&2
  echo "  ${RECIPE_FILE}" >&2
  echo "Set INFERENCEX_PATH to an InferenceX checkout containing upstream SGLang srt-slurm recipes." >&2
  exit 1
fi

echo "==> Phase: validated upstream SGLang recipe"
echo "${RECIPE_FILE}"

echo "==> Phase: valid GB200 DSv4 SGLang disagg recipe names"
printf '  %s
' "${VALID_RECIPES[@]}"

echo "==> Phase: srt_bench.sh invocation"
cd "${INFERENCEX_PATH}"
bash benchmarks/multi_node/srt_bench.sh "${RECIPE_FILE}"

#!/usr/bin/env bash
#SBATCH --job-name=inferguard-bench
#SBATCH --nodes=2
#SBATCH --ntasks-per-node=1
#SBATCH --gpus-per-node=8
#SBATCH --cpus-per-task=64
#SBATCH --time=04:00:00
#SBATCH --partition=<EDIT>
#SBATCH --account=<EDIT>
#SBATCH --output=logs/%x-%j.out
#SBATCH --error=logs/%x-%j.err

# Generic InferGuard multi-node Slurm template.
# Copy this file, replace the <EDIT> placeholders, then submit the copy with sbatch.
# It uses a common topology: keep one vLLM OpenAI-compatible server alive inside
# the allocation, then run the InferGuard campaign against that endpoint with
# srun --overlap. Operators may replace the vLLM launch block with a site-local
# container, module, or torchrun recipe.

set -euo pipefail

phase() {
  printf '
==> Phase: %s
' "$1"
}

phase "operator environment"
# ---- Site setup: edit for your cluster. ----
# module purge
# module load cuda/<EDIT>
# module load nccl/<EDIT>
# module load python/<EDIT>
# source /path/to/conda.sh && conda activate <EDIT>
# source /path/to/inferguard-venv/bin/activate

export TOUCHDOWN_ROOT="${TOUCHDOWN_ROOT:-$PWD}"
export INFERGUARD_ROOT="${INFERGUARD_ROOT:-$TOUCHDOWN_ROOT/oss/inferguard}"
export MODEL_NAME="${MODEL_NAME:-<EDIT-model-or-local-path>}"
export RIG_LABEL="${RIG_LABEL:-slurm-multinode}"
export PORT="${PORT:-8000}"
export GPUS_PER_NODE="${GPUS_PER_NODE:-${SLURM_GPUS_ON_NODE:-8}}"
export TP_SIZE="${TP_SIZE:-$((SLURM_NNODES * GPUS_PER_NODE))}"
export MAX_MODEL_LEN="${MAX_MODEL_LEN:-32768}"
export CONCURRENCY="${CONCURRENCY:-1,4,8,16,32,64}"
export OUTPUT_TOKENS="${OUTPUT_TOKENS:-512}"
export WARMUP_SECONDS="${WARMUP_SECONDS:-60}"
export DURATION_SECONDS="${DURATION_SECONDS:-600}"
export RESULTS_ROOT="${RESULTS_ROOT:-$TOUCHDOWN_ROOT/results/inferguard-slurm-${SLURM_JOB_ID}}"
export TRACE_DIR="${TRACE_DIR:-$INFERGUARD_ROOT/traces/isb1-dsv4-agent}"
export INFERGUARD_BIN="${INFERGUARD_BIN:-inferguard}"

mkdir -p "$RESULTS_ROOT" logs

HEAD_NODE="$(scontrol show hostnames "$SLURM_JOB_NODELIST" | head -n 1)"
ENDPOINT_BASE="http://${HEAD_NODE}:${PORT}"
ENDPOINT_URL="${ENDPOINT_BASE}/v1/chat/completions"
ENDPOINT_MODELS_URL="${ENDPOINT_BASE}/v1/models"
export HEAD_NODE ENDPOINT_BASE ENDPOINT_URL ENDPOINT_MODELS_URL

cat <<SUMMARY | tee "$RESULTS_ROOT/slurm_job_env.txt"
SLURM_JOB_ID=$SLURM_JOB_ID
SLURM_JOB_NODELIST=$SLURM_JOB_NODELIST
SLURM_NNODES=$SLURM_NNODES
HEAD_NODE=$HEAD_NODE
MODEL_NAME=$MODEL_NAME
RIG_LABEL=$RIG_LABEL
PORT=$PORT
GPUS_PER_NODE=$GPUS_PER_NODE
TP_SIZE=$TP_SIZE
MAX_MODEL_LEN=$MAX_MODEL_LEN
ENDPOINT_URL=$ENDPOINT_URL
TRACE_DIR=$TRACE_DIR
RESULTS_ROOT=$RESULTS_ROOT
SUMMARY

phase "launch vLLM server across allocation"
# For a true multi-node tensor-parallel server, vLLM is launched through torchrun
# with external_launcher. If your cluster uses containers, replace the command
# inside bash -lc with the equivalent apptainer/docker/enroot invocation.
srun --overlap \
  --nodes="$SLURM_NNODES" \
  --ntasks="$SLURM_NNODES" \
  --ntasks-per-node=1 \
  --gpus-per-task="$GPUS_PER_NODE" \
  --cpus-per-task="$SLURM_CPUS_PER_TASK" \
  bash -lc '
    set -euo pipefail
    torchrun \
      --nnodes="$SLURM_NNODES" \
      --nproc-per-node="$GPUS_PER_NODE" \
      --node-rank="$SLURM_NODEID" \
      --master-addr="$HEAD_NODE" \
      --master-port="${MASTER_PORT:-29500}" \
      -m vllm.entrypoints.openai.api_server \
      --model "$MODEL_NAME" \
      --host 0.0.0.0 \
      --port "$PORT" \
      --tensor-parallel-size "$TP_SIZE" \
      --max-model-len "$MAX_MODEL_LEN" \
      --distributed-executor-backend external_launcher \
      --trust-remote-code
  ' \
  > "$RESULTS_ROOT/vllm_server.log" 2>&1 &
SERVER_SRUN_PID="$!"

cleanup() {
  phase "cleanup"
  kill "$SERVER_SRUN_PID" 2>/dev/null || true
  wait "$SERVER_SRUN_PID" 2>/dev/null || true
}
trap cleanup EXIT

phase "wait for /v1/models"
for attempt in $(seq 1 120); do
  if curl --fail --silent --show-error --max-time 5 "$ENDPOINT_MODELS_URL"       > "$RESULTS_ROOT/models.json"; then
    echo "Endpoint ready: $ENDPOINT_MODELS_URL"
    break
  fi
  if ! kill -0 "$SERVER_SRUN_PID" 2>/dev/null; then
    echo "ERROR: server launch exited before readiness" >&2
    tail -n 200 "$RESULTS_ROOT/vllm_server.log" >&2 || true
    exit 1
  fi
  sleep 10
  if [ "$attempt" -eq 120 ]; then
    echo "ERROR: timed out waiting for $ENDPOINT_MODELS_URL" >&2
    tail -n 200 "$RESULTS_ROOT/vllm_server.log" >&2 || true
    exit 1
  fi
done

phase "run InferGuard campaign against server"
# The campaign is intentionally overlapped with the server allocation. It runs
# from one task and sends HTTP requests to the endpoint above.
srun --overlap --nodes=1 --ntasks=1 --cpus-per-task=8 bash -lc '
  set -euo pipefail
  cd "$INFERGUARD_ROOT"
  "$INFERGUARD_BIN" --version || true
  MODEL_NAME="$MODEL_NAME"   ENDPOINT_URL="$ENDPOINT_URL"   RIG_LABEL="$RIG_LABEL"   TRACE_DIR="$TRACE_DIR"   RESULTS_ROOT="$RESULTS_ROOT/isb1-campaign"   CONCURRENCY="$CONCURRENCY"   OUTPUT_TOKENS="$OUTPUT_TOKENS"   WARMUP_SECONDS="$WARMUP_SECONDS"   DURATION_SECONDS="$DURATION_SECONDS"   INFERGUARD_BIN="$INFERGUARD_BIN"   bash scripts/run_isb1_campaign.sh
'

phase "done"
echo "Artifacts: $RESULTS_ROOT"

# InferGuard Slurm templates

This directory contains generic Slurm scaffolding for running InferGuard against an OpenAI-compatible endpoint inside an allocation.

## Files

- `example_inferguard_bench.sbatch` — copy/edit sbatch template for multi-node, non-disaggregated vLLM serving plus an overlapped InferGuard ISB-1 campaign.

## When to use this template

Use this directory when the target cluster is **not** one of the already-captured GMI launch paths, or when you want a generic starting point for:

- single allocation, multi-node Slurm jobs;
- tensor-parallel vLLM across nodes;
- campaign-against-server execution where the server stays alive while `run_isb1_campaign.sh` sends requests.

Use the existing GMI launchers instead when you are on the known GMI cells:

- `../launch_vllm_h100_gmi.sh`
- `../launch_vllm_h200_gmi.sh`
- `../launch_vllm_b200_gmi.sh`
- `../launch_vllm_gb200_disagg_gmi.sh`
- `../launch_sglang_gb200_disagg_gmi.sh`

Those scripts encode hardware-specific model/image/recipe assumptions. This Slurm template is intentionally generic and uses `<EDIT>` placeholders.

## Expected environment

The template expects the operator to provide or edit:

- Slurm partition/account lines in the copied sbatch file.
- Python environment with `inferguard`, `vllm`, `torchrun`, and `curl` available.
- `MODEL_NAME` pointing to a Hugging Face model ID or local model path.
- `TOUCHDOWN_ROOT` if the job starts outside the repository root.
- Optional sweep controls: `CONCURRENCY`, `OUTPUT_TOKENS`, `WARMUP_SECONDS`, `DURATION_SECONDS`.

The template derives:

- `TP_SIZE=$SLURM_NNODES * $GPUS_PER_NODE`
- `ENDPOINT_URL=http://<rank-0-node>:${PORT}/v1/chat/completions`
- `TRACE_DIR=$INFERGUARD_ROOT/traces/isb1-dsv4-agent`
- `RESULTS_ROOT=$TOUCHDOWN_ROOT/results/inferguard-slurm-${SLURM_JOB_ID}`

## Notes

- `srun --overlap` is required because the server step remains alive while the campaign step runs.
- Replace the vLLM launch block if your cluster mandates Apptainer, Enroot, Docker, custom NCCL wrappers, or a site-specific torchrun launcher.
- This directory does not implement Kubernetes, AWS Batch, or vendor-specific provisioning.

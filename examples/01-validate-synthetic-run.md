# Example 01: validate a synthetic run

This example proves the InferGuard bundle and validation flow on a laptop. It does **not** produce real GPU evidence.

## Prerequisites

```bash
pip install inferguard
```

From a source checkout, replace `inferguard` with `PYTHONPATH=src python3 -m inferguard.cli`.

## Run it

```bash
rm -rf /tmp/inferguard-doc-smoke

inferguard simulate-gpu \
  --results-root /tmp/inferguard-doc-smoke \
  --hardware b200 \
  --engine vllm \
  --model-profile dsv4-pro \
  --workload long_context_chat \
  --max-jobs 1

inferguard validate-completed \
  --results-root /tmp/inferguard-doc-smoke \
  --strict || true
```

`--strict` is included to show the publication gate. The command exits non-zero because synthetic evidence is not `live_complete`.

## Expected output

```text
inferguard validate-completed: status=synthetic_only jobs=1 live=0 synthetic=1 incomplete=0 missing=0
```

Generated files include:

```text
/tmp/inferguard-doc-smoke/
  matrix_plan.json
  expected_artifact_contract.json
  synthetic_gpu_mimic_summary.json
  validation_report.json
  validation_report.md
  sbatch/*.sbatch
```

In `validation_report.md`, expect:

```text
Status: synthetic_only
Claim status: synthetic
Synthetic markers: ... synthetic_gpu_mimic
```

## Gotchas

- `synthetic_only` is success for local plumbing, not a publishable benchmark result.
- Remove `--strict` if you want exit code `0` for a synthetic smoke test in a shell script.
- A real `live_complete` run needs request-profile rows, launch healthcheck, engine metrics, GPU metrics, and required contract artifacts.

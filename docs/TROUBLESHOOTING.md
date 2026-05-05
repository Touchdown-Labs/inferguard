# Troubleshooting

InferGuard is deliberately strict. Many "failures" are evidence-quality gates doing their job.

## `validate-completed --strict` exits non-zero

**Symptom**

```text
inferguard validate-completed: status=synthetic_only ...
# exit code 1 with --strict
```

**What it means**

Strict mode returns success only for `live_complete`. Synthetic bundles, incomplete live runs, missing contracts, and not-publishable runs return non-zero.

**Fix**

- For smoke tests, run without `--strict` or append `|| true` in documentation examples.
- For publication, add the missing request, launch, engine metrics, GPU metrics, and contract artifacts listed in `validation_report.md`.

## Synthetic run is not publishable live evidence

`simulate-gpu` intentionally stamps artifacts with `synthetic_gpu_mimic`. That is useful for testing bundle rendering, but the validator will classify it as `synthetic_only` unless real live evidence is present and the synthetic markers are removed from the publication path.

## No successful request-profile rows

**Symptom**

```text
reason=no_successful_request_profile_rows
status=live_incomplete
claim_status=not_proven
```

**Fix**

- Check that `--endpoint` points to `/v1/chat/completions`.
- Check the model name sent with `--model`.
- Inspect `request_profile/requests_profile.jsonl` for HTTP status and `error_type`.
- Increase `--timeout-seconds` for long prefill workloads.
- Start with `examples/02-profile-real-endpoint.md` and the local `serve-mimic` flow before testing a real GPU endpoint.

## Healthcheck failed or timed out

**Symptom**

```text
claim_id=launch_healthcheck
reason=launch_healthcheck_not_successful
```

**Fix**

- If the engine is already running, use `launch-engine --external-launch --endpoint-url ...`.
- Increase `--healthcheck-timeout-seconds` for large model load or CUDA graph capture.
- Confirm the endpoint accepts the model id in `launch/command.json`.
- Inspect `launch/stdout.log` and `launch/stderr.log`.

## Engine metrics timeline is empty

**Symptom**

```text
reason=no_live_engine_metric_sample
```

**Fix**

- Confirm the serving engine exposes Prometheus metrics.
- For vLLM/SGLang launches, pass the engine flags needed to enable metrics.
- Use the exact metrics URL with `collect-metrics --engine-metrics-url`, usually `http://host:port/metrics`.
- Keep collection running long enough to overlap real requests.

## DCGM GPU metrics are missing

**Symptom**

```text
reason=missing_required_dcgm_metrics
```

**Fix**

- Start DCGM exporter on the GPU host.
- Confirm `DCGM_FI_DEV_GPU_UTIL` and `DCGM_FI_DEV_FB_USED` are present in the scrape.
- Pass the exporter URL to `collect-metrics --dcgm-metrics-url`.
- On Slurm, make sure the exporter is reachable from the job network namespace.

## Slurm timeout or preemption interrupted the run

v0.7.1 registers JSONL streams, partial-result producers, and launched engine processes with shared signal cleanup. If Slurm sends SIGTERM, InferGuard should flush partial rows and write `partial_results.json` where supported.

**Fix**

- Look for `partial_results.json` in the command output directory.
- Increase Slurm wall time for first model-load runs.
- Split launch, request profile, and metrics collection into smaller scheduler steps if the allocation is tight.

## OOM during model launch

**Common causes**

- Model weights do not fit in single-node HBM.
- `--max-model-len` or concurrency creates too much KV pressure.
- GPU memory utilization is too aggressive for the engine.

**Fix**

- Check [`HARDWARE_COVERAGE.md`](HARDWARE_COVERAGE.md) before attempting DSv4-Pro on H100 single-node.
- Lower `--max-model-len`, concurrency, or `--gpu-memory-utilization` for vLLM.
- Use H200/B200/B300 templates for DSv4-Pro single-node, or wait for validated GB200/GB300 external lanes.

## `request-profile` token counts are estimated

If the endpoint does not return OpenAI `usage` fields, InferGuard estimates prompt and completion tokens. The row remains useful for latency, status, and failure analysis, but token-count fields will be `inferred` instead of `measured`.

## Endpoint URL rejected

InferGuard rejects endpoint URLs with userinfo, query strings, or fragments so secrets do not end up in artifacts.

Use:

```text
http://host:8000/v1/chat/completions
```

Do not use:

```text
http://token@host:8000/v1/chat/completions?api_key=...
```

Pass credentials with `--api-key` when supported.

## `diagnose-bottleneck` says not enough evidence

That is expected when the job lacks request rows, engine metrics, GPU metrics, or validation context. Run the earlier pipeline stages first:

```bash
inferguard request-profile ...
inferguard collect-metrics ...
inferguard validate-completed --results-root ...
inferguard diagnose-bottleneck --job-dir ...
```

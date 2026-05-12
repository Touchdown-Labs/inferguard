# AMD ROCm fixture TODO manifest

This directory is reserved for sanitized AMD ROCm fixtures. Do not add synthetic data and do not mark AMD support as live from fixture data alone.

## Support states

| State | Meaning |
|---|---|
| `not_started` | No implementation or proof exists. |
| `parser_only` | The signal can be parsed or represented, but no fixture proves it. |
| `fixture_backed` | Tests or saved fixtures prove the code path. |
| `live_validated` | Real runtime artifacts have passed through the tool. |
| `release_ready` | CLI, docs, tests, packaging/release checks, and rollback/failure notes are complete. |
| `not_applicable` | Correctly excluded for the detected mode. |

## Required fixture bundles

Each fixture bundle should live in a named subdirectory such as:

```text
tests/fixtures/amd_rocm/mi300x_vllm_smoke/
tests/fixtures/amd_rocm/mi350x_sglang_smoke/
```

A complete bundle should include sanitized versions of:

- `manifest.json`: GPU SKU, CDNA generation, ISA target, ROCm version, profiler tool version, engine, workload, and redaction notes.
- `rocminfo.txt`: hardware agent inventory proving `gfx942` or `gfx950`.
- `rocm-smi.json` or `rocm-smi.txt`: model, HBM, utilization, power, temperature, and XGMI fields when available.
- ROCm Compute Profiler CSV/JSON output: selected counters for kernel timing, occupancy, wavefront behavior, and memory traffic.
- rocprofiler or rocprofiler-sdk trace when available: HIP API timing and kernel dispatch timestamps.
- Engine logs and metrics from vLLM or SGLang on ROCm.
- InferGuard request trace or benchmark rows.
- Optional LMCache/cache telemetry if the run uses KV movement or offload.

## Minimum initial fixture target

To move the AMD path from `not_started` to `fixture_backed`, collect at least:

1. One CDNA3 bundle from MI300X or MI325X with `gfx942` identity evidence.
2. One CDNA4 bundle from MI350X or MI355X with `gfx950` identity evidence.
3. One ROCm profiler export with nonzero kernel timing and memory-related counters.
4. One engine metrics/log sample from vLLM or SGLang running on ROCm.

## Non-claims

- Fixture-backed parsing is not live validation.
- vLLM/SGLang ROCm compatibility is not enough to prove InferGuard AMD support.
- Missing ROCm counters should be represented explicitly as `not_applicable` when the metric is unavailable for the tool or hardware mode.

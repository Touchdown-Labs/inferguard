---
title: AMD CDNA hardware coverage
description: Planning matrix for ROCm and CDNA3/CDNA4 disaggregated inference profiling.
---

# AMD CDNA hardware coverage

This page is an additive planning reference for AMD ROCm lanes. It does not claim live AMD support. AMD lanes remain `not_started` until InferGuard has ROCm parser code and fixture artifacts, and they remain below `live_validated` until actual AMD GPU runs produce ROCm profiler and engine artifacts.

## Support state vocabulary

| State | Meaning |
|---|---|
| `not_started` | No implementation or proof exists. |
| `parser_only` | The signal can be parsed or represented, but no fixture proves it. |
| `fixture_backed` | Tests or saved fixtures prove the code path. |
| `live_validated` | Real runtime artifacts have passed through the tool. |
| `release_ready` | CLI, docs, tests, packaging/release checks, and rollback/failure notes are complete. |
| `not_applicable` | Correctly excluded for the detected mode. |

## Hardware map

| GPU | Architecture | ISA target | HBM | Compute units | HBM bandwidth | Wavefront | Current state | Proof required to advance |
|---|---|---|---:|---:|---:|---:|---|---|
| MI300X | CDNA3 | `gfx942` | 192 GiB HBM3 | 304 | 5.3 TB/s | 64 | `not_started` | `rocminfo`/`rocm-smi`, rocprofiler-compute output, engine logs, request trace, validation report from an MI300X run. |
| MI325X | CDNA3 | `gfx942` | 256 GiB HBM3E | 304 | 6 TB/s | 64 | `not_started` | Same as MI300X, captured on MI325X hardware. |
| MI350X | CDNA4 | `gfx950` | 288 GiB HBM3E | 256 | 8 TB/s | 64 | `not_started` | Same as MI300X, captured on MI350X hardware. |
| MI355X | CDNA4 | `gfx950` | 288 GiB HBM3E | 256 | 8 TB/s | 64 | `not_started` | Same as MI300X, captured on MI355X hardware. |

Source anchors for the architecture mapping:

- ROCm hardware specifications identify MI300X/MI325X as CDNA3 `gfx942` and MI350X/MI355X as CDNA4 `gfx950`.
- GPUOpen publishes CDNA ISA guide PDFs at <https://gpuopen.com/amd-isa-documentation>.
- GPUOpen publishes machine-readable AMD ISA XML specifications at <https://gpuopen.com/machine-readable-isa/>.

## Profiler and telemetry sources

| Source | Expected artifact shape | Useful fields | Current state | Notes |
|---|---|---|---|---|
| ROCm Compute Profiler | CSV or JSON export | kernel name, dispatch duration, occupancy, counters, memory traffic, wavefront metrics | `not_started` | Required for CDNA through CDNA4 metric-backed bottleneck evidence. |
| rocprofiler / rocprofiler-sdk trace | JSON/CSV/trace output | HIP API timing, kernel dispatch sequence, queue correlation, timestamps | `not_started` | Needed to align engine phases with GPU kernels. |
| `rocm-smi` | text or JSON snapshot | GPU model, VRAM used, temperature, power, utilization, XGMI where available | `not_started` | Hardware identity and health evidence. |
| `rocminfo` | text snapshot | ASIC target such as `gfx942` or `gfx950`, agent inventory | `not_started` | Required to distinguish CDNA3 vs CDNA4. |
| vLLM on ROCm logs/metrics | Prometheus plus logs | TTFT, TPOT, queue time, request counts, cache/offload settings | `not_started` | Engine evidence, not GPU proof by itself. |
| SGLang on ROCm logs/metrics | Prometheus plus logs | TTFT, TPOT, router/prefill/decode signals, cache settings | `not_started` | Engine evidence, not GPU proof by itself. |
| Disaggregated endpoint telemetry | InferGuard request rows, healthchecks, endpoint labels | prefill endpoint, decode endpoint, transfer path, request/session identity | `not_started` | Required for disaggregated inference attribution. |

## Metric families to normalize first

| Metric lane | ROCm source | InferGuard purpose | State |
|---|---|---|---|
| GPU identity | `rocminfo`, `rocm-smi` | Detect MI300X/MI325X/MI350X/MI355X and map to CDNA3/CDNA4. | `not_started` |
| HBM pressure | `rocm-smi`, profiler memory counters | Identify capacity pressure, memory-bound prefill, KV pressure, and OOM risk. | `not_started` |
| Kernel timing | rocprofiler / ROCm Compute Profiler | Separate prefill/decode/attention/collective bottlenecks. | `not_started` |
| Wavefront/CU occupancy | ROCm Compute Profiler | Distinguish occupancy limits from memory or network limits. | `not_started` |
| XGMI / interconnect | `rocm-smi` where exposed, system counters | Attribute multi-GPU or disaggregated transfer pressure. | `not_started` |
| Engine latency | vLLM/SGLang metrics | Preserve existing TTFT/TPOT/queue analysis on ROCm deployments. | `not_started` |
| Cache and transfer behavior | LMCache/engine logs and metrics | Connect KV cache movement to endpoint and GPU-side evidence. | `not_started` |

## Validation gates

A lane moves state only when the matching evidence exists:

1. `parser_only`: InferGuard can ingest the ROCm artifact format without live claims.
2. `fixture_backed`: `tests/fixtures/amd_rocm/` contains sanitized ROCm artifacts and tests assert normalized fields.
3. `live_validated`: a real MI300X, MI325X, MI350X, or MI355X run includes request trace, engine metrics/logs, ROCm profiler output, `rocm-smi`, `rocminfo`, and `inferguard validate-completed --strict` output.
4. `release_ready`: docs, CLI help, tests, packaging checks, known limitations, and rollback notes are complete.

## Non-claims

- These rows are not live AMD support claims.
- vLLM or SGLang ROCm compatibility alone is not InferGuard AMD validation.
- Synthetic fixtures are not live validation.
- NVIDIA DCGM metrics are not ROCm proof.

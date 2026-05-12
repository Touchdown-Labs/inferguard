---
title: InferGuard Profiler Bridge
description: No-bare-metal scaffold for vLLM, NVIDIA Nsight, and AMD ROCm profiler normalization.
---

# InferGuard Profiler Bridge

The Profiler Bridge is a no-bare-metal-first scaffold for importing vLLM metrics, NVIDIA Nsight artifacts, and AMD ROCm artifacts into one operator-facing report. It is parser and capture-plan support only until real hardware artifacts are collected.

## Non-claims

- Synthetic fixtures are not live NVIDIA or AMD validation.
- vLLM Prometheus metrics prove engine lanes, not GPU profiler support by themselves.
- Nsight and ROCm counters are not semantically identical. Reports keep raw counter names and mark cross-vendor comparisons `partial` unless live evidence proves a lane.
- vLLM deep profiling can slow inference, so steady benchmark runs must remain separate from deep-profile timeline or kernel runs.

## Package layout

- `src/inferguard/profilers/schema.py` defines normalized request metrics, kernel events, counter samples, roofline points, findings, and confidence states.
- `capture_plan.py` emits dry-run command templates and expected artifacts for vLLM steady metrics, Nsight Systems, Nsight Compute, rocprofv3, and rocprof-compute.
- `vllm_metrics.py` parses Prometheus text fixtures.
- `nvidia_nsight.py` parses `nsys stats` CSV kernel summaries and `ncu --csv` summaries.
- `amd_rocm.py` parses rocprofv3 kernel traces and rocprof-compute counter/roofline CSV files.
- `normalize.py`, `compare.py`, and `report.py` convert parsed artifacts into one report without making performance claims.

## Capture modes

| Mode | Purpose | Expected artifacts |
|---|---|---|
| `steady` | Engine benchmark and Prometheus scrape only. | `vllm.prom`, benchmark JSON. |
| `timeline` | First deep profile pass. | NVIDIA `nsys stats` CSV or AMD `rocprofv3` CSV plus vLLM metrics. |
| `kernel` | Focused kernel counters after timeline triage. | NVIDIA `ncu --csv` or AMD `rocprof-compute` PMC CSV. |
| `roofline` | Compute-vs-memory characterization when tool support exists. | AMD rocprof-compute roofline CSV or vendor-equivalent counter export. |

## Vendor annotation model

InferGuard uses one logical phase vocabulary:

- `server_startup`
- `warmup`
- `prefill`
- `decode`
- `kv_transfer`
- `scheduler_wait`
- `communication`
- `postprocess`

NVIDIA captures should use NVTX ranges. AMD captures should use ROCTx ranges. If neither annotation library is available, the bridge can still ingest raw kernel and counter artifacts, but phase confidence remains partial.

## Live acceptance gates

### NVIDIA H100/H200/B200/GB200/B300/GB300

1. Capture tool availability: `nvidia-smi`, `nsys`, `ncu`, CUDA driver/runtime versions.
2. Run a steady vLLM benchmark and save Prometheus `/metrics`.
3. Run an `nsys` timeline and export `nsys stats` CSV for kernels, memory, and NVTX ranges.
4. Optionally run `ncu --csv` for focused kernels after timeline triage.
5. Import artifacts into `NormalizedProfilerRun` and render a Profiler Bridge report.

### AMD CDNA3/CDNA4 MI300/MI325/MI350/MI355X

1. Capture tool availability: `rocprofv3`, `rocprofv3-avail`, `rocprof-compute`, `rocm-smi`, `hipcc`, ROCm version.
2. Run a steady vLLM benchmark and save Prometheus `/metrics`.
3. Run `rocprofv3` with runtime, kernel, memory-copy, and marker traces.
4. Run `rocprof-compute` counters or record why the metric set is unavailable.
5. For roofline mode, save rocprof-compute roofline CSV.
6. Import artifacts into `NormalizedProfilerRun` and render a Profiler Bridge report.

## Current support state

| Lane | State | Proof |
|---|---|---|
| vLLM Prometheus parser | `fixture_backed` | `tests/fixtures/profilers/vllm/prometheus_example.prom` |
| NVIDIA nsys CSV parser | `fixture_backed` | `tests/fixtures/profilers/nvidia/nsys_stats_kernel_sum.csv` |
| NVIDIA ncu CSV parser | `fixture_backed` | `tests/fixtures/profilers/nvidia/ncu_kernel_summary.csv` |
| AMD rocprofv3 CSV parser | `fixture_backed` | `tests/fixtures/profilers/amd/rocprofv3_kernel_trace.csv` |
| AMD rocprof-compute counter parser | `fixture_backed` | `tests/fixtures/profilers/amd/rocprof_compute_pmc_perf.csv` |
| AMD rocprof-compute roofline parser | `fixture_backed` | `tests/fixtures/profilers/amd/rocprof_compute_roofline.csv` |
| Live NVIDIA validation | `not_started` | Requires real Nsight plus vLLM artifacts. |
| Live AMD validation | `not_started` | Requires real ROCm plus vLLM artifacts. |

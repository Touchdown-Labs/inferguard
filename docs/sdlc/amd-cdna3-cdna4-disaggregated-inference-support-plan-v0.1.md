# AMD CDNA3/CDNA4 disaggregated inference support plan v0.1

Date: 2026-05-09

## Purpose

Plan InferGuard support for disaggregated inference profiling on AMD Instinct MI300X, MI325X, MI350X, and MI355X without overstating current support. This plan covers ROCm/CDNA artifact ingestion, fixture requirements, live validation gates, and release readiness.

## Required support states

| State | Meaning |
|---|---|
| `not_started` | No implementation or proof exists. |
| `parser_only` | The signal can be parsed or represented, but no fixture proves it. |
| `fixture_backed` | Tests or saved fixtures prove the code path. |
| `live_validated` | Real runtime artifacts have passed through the tool. |
| `release_ready` | CLI, docs, tests, packaging/release checks, and rollback/failure notes are complete. |
| `not_applicable` | Correctly excluded for the detected mode. |

## Current claim

InferGuard currently has no live AMD CDNA validation in this repo. AMD lanes must remain `not_started` until parser work lands, `fixture_backed` until sanitized ROCm fixtures and tests prove the code path, and below `live_validated` until real ROCm/AMD GPU artifacts pass through the tool.

## Hardware planning matrix

| GPU | CDNA generation | ISA target | HBM | CUs | Bandwidth | Wavefront | Current state | Live proof required |
|---|---|---|---:|---:|---:|---:|---|---|
| MI300X | CDNA3 | `gfx942` | 192 GiB HBM3 | 304 | 5.3 TB/s | 64 | `not_started` | MI300X run with `rocminfo`, `rocm-smi`, ROCm profiler output, engine logs/metrics, request trace, validation report. |
| MI325X | CDNA3 | `gfx942` | 256 GiB HBM3E | 304 | 6 TB/s | 64 | `not_started` | MI325X run with the same artifact set. |
| MI350X | CDNA4 | `gfx950` | 288 GiB HBM3E | 256 | 8 TB/s | 64 | `not_started` | MI350X run with the same artifact set. |
| MI355X | CDNA4 | `gfx950` | 288 GiB HBM3E | 256 | 8 TB/s | 64 | `not_started` | MI355X run with the same artifact set. |

References:

- ROCm hardware specifications map MI300X/MI325X to CDNA3 `gfx942` and MI350X/MI355X to CDNA4 `gfx950`.
- GPUOpen AMD ISA guides: <https://gpuopen.com/amd-isa-documentation>
- GPUOpen machine-readable ISA XML: <https://gpuopen.com/machine-readable-isa/>

## Lane-by-lane support matrix

| Lane | Scope | Current state | Required implementation | Fixture gate | Live validation gate |
|---|---|---|---|---|---|
| Hardware identity | `rocminfo`, `rocm-smi`, engine env | `not_started` | Add ROCm hardware parser that emits GPU model, ISA target, CDNA generation, HBM capacity, CUs, and wavefront size. | Sanitized MI300X and MI350X identity snapshots at minimum. | Real run proves `gfx942` and `gfx950` detection on AMD hosts. |
| ROCm profiler ingest | ROCm Compute Profiler CSV/JSON | `not_started` | Add parser for selected CSV/JSON fields and normalize kernel/counter rows into InferGuard metrics. | Minimal CDNA3 and CDNA4 profiler fixture files. | Real profiler export from a vLLM or SGLang inference run. |
| HIP/API timeline | rocprofiler / rocprofiler-sdk trace | `not_started` | Parse HIP API and kernel dispatch timestamps for request-phase correlation. | Sanitized trace with kernel dispatch and API calls. | Real trace aligned to prefill/decode windows. |
| HBM pressure | `rocm-smi`, profiler memory counters | `not_started` | Normalize VRAM used/free and memory traffic counters for KV pressure analysis. | Snapshot fixture with nonzero VRAM and memory counters. | Real long-context run showing HBM pressure or non-pressure. |
| CU / wavefront occupancy | ROCm Compute Profiler | `not_started` | Normalize occupancy, wavefront, and CU utilization counters when present. | Fixture with occupancy-like counters and documented missing-counter behavior. | Real run where analyzer can distinguish compute, memory, and queue bottlenecks. |
| XGMI/interconnect | `rocm-smi` and system topology where available | `not_started` | Ingest link/topology counters when exposed and mark missing counters as `not_applicable`. | Fixture with available and unavailable XGMI fields. | Multi-GPU or disaggregated run with transfer evidence. |
| vLLM on ROCm | vLLM metrics/logs on AMD | `not_started` | Reuse existing vLLM TTFT/TPOT/queue adapters and add ROCm hardware evidence binding. | Fixture containing vLLM ROCm metrics/log excerpts plus ROCm identity. | vLLM ROCm run with engine metrics and AMD profiler artifacts. |
| SGLang on ROCm | SGLang metrics/logs on AMD | `not_started` | Reuse existing SGLang adapters and add ROCm hardware evidence binding. | Fixture containing SGLang ROCm metrics/log excerpts plus ROCm identity. | SGLang ROCm run with engine metrics and AMD profiler artifacts. |
| Disaggregated attribution | Prefill/decode endpoints, transfer/cache telemetry | `not_started` | Attach ROCm GPU evidence to endpoint roles and request/session labels. | Fixture with prefill and decode endpoint logs plus ROCm identity. | Disaggregated run with endpoint telemetry, ROCm profiler artifacts, and request trace. |
| LMCache/KV movement on AMD | LMCache plus engine logs/metrics on ROCm | `not_started` | Treat cache evidence as engine/cache proof and require ROCm artifacts for AMD GPU proof. | Fixture with LMCache evidence plus ROCm identity. | Live AMD run showing cache behavior and GPU-side evidence. |
| Diagnostics/reporting | Analyze/report output | `not_started` | Add AMD-specific language that never equates ROCm parser support with live AMD validation. | Golden report fixture or assertion tests. | `inferguard validate-completed --strict` accepts complete AMD live artifact bundle. |
| Docs and release gate | Reference docs, CLI docs, changelog | `parser_only` for planning docs only | Keep docs explicit about support states and non-claims. | Link/docs checks pass. | Release notes include validated GPU SKUs and missing lanes. |

## Implementation plan

### Phase 1: Parser contracts

1. Define ROCm artifact manifest fields under `tests/fixtures/amd_rocm/README.md`.
2. Add ROCm identity parser for `rocminfo` and `rocm-smi` snapshots.
3. Add ROCm Compute Profiler CSV/JSON parser for a small, documented counter subset.
4. Add missing-counter handling that reports `not_applicable`, not failure, when a metric is absent for a tool version or mode.

Exit state: `parser_only`.

### Phase 2: Fixtures and tests

1. Collect sanitized CDNA3 and CDNA4 identity snapshots.
2. Collect sanitized ROCm profiler artifacts from at least one inference-like workload.
3. Add tests that assert GPU model, ISA target, CDNA generation, HBM capacity, and profiler metric normalization.
4. Add report tests that verify AMD lanes do not claim live validation from fixtures alone.

Exit state: `fixture_backed`.

### Phase 3: Live single-node validation

1. Run vLLM or SGLang on MI300X or MI325X with InferGuard request tracing.
2. Capture `rocminfo`, `rocm-smi`, ROCm profiler artifacts, engine logs/metrics, request rows, healthcheck, and validation output.
3. Repeat on MI350X or MI355X to prove CDNA4 `gfx950` behavior.

Exit state: `live_validated` for the specific GPU and engine lanes that ran.

### Phase 4: Disaggregated validation

1. Run a prefill/decode split deployment on AMD hardware.
2. Capture endpoint labels, transfer/cache telemetry, ROCm profiler artifacts per endpoint role, and request/session identity.
3. Verify analyzer output attributes queue, prefill, decode, transfer, cache, HBM, and interconnect evidence without conflating engine metrics with GPU proof.

Exit state: `live_validated` for the specific disaggregated lanes that ran.

### Phase 5: Release readiness

1. Update CLI help and docs with exactly validated AMD SKUs.
2. Add known limitations for missing ROCm counters, unsupported profiler versions, and unavailable XGMI fields.
3. Run package, docs, and targeted parser/report tests.
4. Add rollback notes for disabling AMD parser paths if ROCm artifact formats change.

Exit state: `release_ready` only for lanes with full docs, tests, packaging checks, and failure notes.

## Blockers

- No ROCm profiler fixture artifacts are present in this repo.
- No `rocminfo` or `rocm-smi` AMD host snapshots are present in this repo.
- No actual MI300X, MI325X, MI350X, or MI355X InferGuard run artifacts are present in this repo.
- No disaggregated AMD endpoint telemetry is present in this repo.

## Exact next command

After obtaining access to an AMD ROCm host and choosing an output directory, collect the first identity and profiler bundle, then import it as a sanitized fixture:

```bash
mkdir -p /tmp/inferguard-amd-rocm-mi300x && \
  rocminfo > /tmp/inferguard-amd-rocm-mi300x/rocminfo.txt && \
  rocm-smi --showall --json > /tmp/inferguard-amd-rocm-mi300x/rocm-smi.json && \
  rocprof-compute profile --name inferguard-mi300x-smoke --path /tmp/inferguard-amd-rocm-mi300x -- <vllm-or-sglang-inference-command>
```

Then add sanitized copies under `tests/fixtures/amd_rocm/mi300x_smoke/` and write parser tests to move the lane from `not_started` to `fixture_backed`.

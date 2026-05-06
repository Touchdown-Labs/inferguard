# LMCache Compatibility

InferGuard treats LMCache support as mode-specific evidence, not a single yes/no flag. LMCache can run embedded in an engine process, as a standalone multiprocess service, through controller-backed P2P sharing, or as part of disaggregated prefill. These modes expose different metrics and require different proof.

## Architecture Priority

InferGuard's priority is the current LMCache architecture:

1. **Primary target: standalone MP.** LMCache runs as `lmcache server`; vLLM connects with `LMCacheMPConnector`; telemetry comes from `lmcache_mp_*`, LMCache HTTP health/status endpoints, logs, and optional OTel/trace replay.
2. **Compatibility target: embedded/in-process.** LMCache runs inside the engine through `LMCacheConnectorV1` or the vLLM LMCache offload flag path; telemetry commonly appears as production `lmcache:*` metrics and inline engine logs.
3. **Detection-only until fixtures exist: P2P, disaggregated prefill, controller/internal API, logs, OTel, and trace replay.** These are important, but they should not displace MP-first implementation work.

The old `LMCacheConnector` v0-style string is not a priority. InferGuard should flag it as stale/unsupported unless the operator explicitly documents an older pinned stack.

## Support Levels

| Surface | Typical launch shape | Evidence InferGuard can use today | Support level |
| --- | --- | --- | --- |
| Standalone MP | `lmcache server` plus vLLM `LMCacheMPConnector` | LMCache `/metrics` with `lmcache_mp_*`, vLLM `/metrics`, launch/config artifacts | Partial, highest priority |
| Embedded LMCache | vLLM with `LMCacheConnectorV1` or `--kv-offloading-backend lmcache` | Engine `/metrics`, production `lmcache:*` metrics, launch/config artifacts | Partial, compatibility priority |
| P2P sharing | multiple engines, `enable_p2p`, controller, NIXL | production `lmcache:*` P2P metrics when present; logs/controller evidence are not first-class yet | Planned |
| Disaggregated prefill | prefiller/decoder roles using NIXL | launch/config artifacts and external metrics; PD proof packet is not first-class yet | Planned |
| Controller / internal API | `lmcache_controller` or internal API server | not collected as a structured packet yet | Planned |
| Logs | engine and LMCache logs | not parsed as structured evidence yet | Planned |
| OTel traces / `.lct` replay | MP tracing and trace recording | not collected yet | Planned |

## What `lmcache-compat` Does Today

`inferguard lmcache-compat` compares available Prometheus text against known LMCache and vLLM metric families. It reports whether each family is:

- `populated`: present with non-zero data;
- `zero`: present but all values are zero;
- `missing`: absent from the input;
- `partial`: some required families are present and others are not.

Use it when you have one or both of:

- engine metrics from vLLM/SGLang/Dynamo-compatible Prometheus endpoints;
- LMCache metrics from a standalone MP server or embedded production endpoint.

Example:

```bash
inferguard lmcache-compat \
  --engine-metrics-file vllm.prom \
  --lmcache-metrics-file lmcache.prom \
  --expect-mode mp \
  --fail-on missing-required
```

Use `--l2-configured` only when the run actually configured an MP L2 adapter.
Without that flag, L2 families are reported as `not_applicable` so an L1-only
lab is not treated as a failed L2 proof.

## Metric Surfaces

### Embedded / Production `lmcache:*`

The embedded and production surface commonly includes:

- request counters such as `lmcache:num_retrieve_requests`, `lmcache:num_store_requests`, and `lmcache:num_lookup_requests`;
- token counters such as `lmcache:num_requested_tokens`, `lmcache:num_hit_tokens`, `lmcache:num_lookup_tokens`, and `lmcache:num_lookup_hits`;
- hit-rate gauges/histograms;
- retrieve/store latency and speed histograms;
- local CPU, remote backend, memory-management, health, and chunk-statistics metrics;
- P2P transfer metrics such as `lmcache:num_p2p_requests`, `lmcache:num_p2p_transferred_tokens`, `lmcache:p2p_time_to_transfer`, and `lmcache:p2p_transfer_speed`.

Prometheus exporters may normalize colons to underscores depending on the scrape path. InferGuard preserves unknown LMCache-like metric names so new upstream metrics are not discarded.

### Standalone MP `lmcache_mp_*`

Standalone MP mode uses `lmcache server` and exposes `lmcache_mp_*` metrics from the LMCache server endpoint. Important families include:

- StorageManager read/write counters;
- L1 read/write/eviction counters;
- L1 chunk lifecycle histograms;
- real-reuse histograms with `cache_salt`;
- L2 store/prefetch counters and throughput histograms;
- lookup requested/hit token counters with `model_name` and `cache_salt`;
- L0 GPU block lifecycle histograms;
- L0-L1 throughput histograms;
- engine loaded-chunk counters;
- observable gauges for active prefetch jobs, L1 memory, and in-flight L2 work.

MP runs often produce a mix of populated, zero, and missing families. For example, an L1-only run should not be expected to populate L2 throughput. A run that populates StorageManager/L1 counters but never emits lookup token counters is an integration or workload question, not automatic proof that caching failed.

## Mode Detection Rules

InferGuard should interpret the packet conservatively:

- `lmcache_mp_*` present: likely standalone MP.
- `lmcache:*` or `lmcache_` present without `lmcache_mp_*`: likely embedded/production surface.
- P2P metrics or P2P connection logs present: P2P candidate.
- prefiller/decoder connector roles or PD config present: disaggregated-prefill candidate.
- controller-only API responses without engine/cache metrics: controller-only packet, not cache performance proof.

Do not claim full LMCache compatibility from one metric prefix. A complete packet should include launch/config evidence and the relevant metrics/logs for the mode under test.

## Required Evidence By Mode

### Embedded

- launch command or config showing `LMCacheConnectorV1` or LMCache offload flags;
- consistent `PYTHONHASHSEED` across participating processes;
- engine `/metrics` output;
- `lmcache:*` or normalized LMCache metrics;
- logs showing first-request store and repeated-request retrieve when available.

### Standalone MP

- `lmcache server` command and config;
- vLLM connector config showing `LMCacheMPConnector`;
- LMCache healthcheck;
- vLLM healthcheck;
- LMCache `/metrics`;
- vLLM `/metrics`;
- LMCache server logs;
- optional OTel/trace replay artifacts if tracing is in scope.

### P2P

- at least two engine launch commands;
- controller launch command;
- P2P config with instance IDs, peer init/lookup ports, controller URLs, and transfer channel;
- NIXL/RDMA/TCP mode;
- consistent `PYTHONHASHSEED`;
- peer connection logs;
- cross-engine retrieval logs;
- P2P metrics when exposed.

### Disaggregated Prefill

- prefiller and decoder launch commands;
- producer/consumer connector roles;
- NIXL config and ports;
- proxy/router behavior if used;
- transfer success evidence;
- TTFT comparison against baseline.

## Known Gaps

Current InferGuard support is not 100% LMCache compatible. The highest-priority gaps are MP-first:

1. Complete MP schema/report coverage for every documented `lmcache_mp_*` family.
2. Add an MP L2 live fixture.
3. Add detector rules for MP mode mismatch, missing MP metrics, zero-hit-after-warmup, hash-seed risk, missing lookup counters, L1 pressure, L2 stalls, and unobservable EventBus drop risk.
4. Add structured log parsing for MP store/retrieve evidence.
5. Add P2P mode detection and P2P metric normalization.
6. Add controller and internal API collection.
7. Add live compatibility fixtures for embedded, P2P, PD, and trace replay.

Until those are complete, InferGuard should describe LMCache findings as evidence levels:

- `supported`: enough telemetry exists for the claim;
- `partial`: telemetry proves some behavior but not the full claim;
- `missing_signal`: required telemetry is absent;
- `inferred_without_engine_metrics`: workload shape suggests a result but live engine/cache evidence is missing.

## Modal MP Lab Reference

The 2026-05-06 Modal lab validated standalone MP telemetry, not P2P:

- LMCache server ran separately.
- vLLM used `LMCacheMPConnector`.
- LMCache and vLLM healthchecks passed.
- The latest loaded metrics contained 136 `lmcache_mp` series, 117 of them non-zero.
- StorageManager, L1, L1 lifecycle, and L0 lifecycle families populated.
- Lookup token counters, real-reuse histograms, L2 families, throughput families, and some gauges did not populate in that L1-only workload/config path.
- `diagnose-bottleneck` now reads `lmcache_compat_report.json` and emits specific missing-signal rules, such as `lmcache_mp_lookup_counters_missing`, instead of only a generic insufficient-evidence result.

This is exactly the kind of packet `lmcache-compat` is intended to make inspectable before anyone makes a customer or upstream claim.

# LMCache Compatibility

InferGuard treats LMCache support as mode-specific evidence, not a single yes/no flag. LMCache can run embedded in an engine process, as a standalone multiprocess service, through controller-backed P2P sharing, or as part of disaggregated prefill. These modes expose different metrics and require different proof.

## Architecture Priority

InferGuard's priority is the current LMCache architecture:

1. **Primary target: standalone MP.** LMCache runs as `lmcache server`; vLLM connects with `LMCacheMPConnector`; telemetry comes from `lmcache_mp_*`, LMCache HTTP health/status endpoints, logs, and optional OTel/trace replay.
2. **Compatibility target: embedded/in-process.** LMCache runs inside the engine through `LMCacheConnectorV1` or the vLLM LMCache offload flag path; telemetry commonly appears as production `lmcache:*` metrics and inline engine logs.
3. **Detection/evidence-only until fixtures exist: P2P, disaggregated prefill, controller/internal API, logs, OTel, and trace recording.** HTTP, log, OTel, and `.lct` inputs are now accepted as packet evidence, but they still need live golden fixtures and detector rules before they can support customer-facing claims by themselves.

The old `LMCacheConnector` v0-style string is not a priority. InferGuard should flag it as stale/unsupported unless the operator explicitly documents an older pinned stack.

## Progress

The upstream tracker for this effort is
`/Users/chen/Projects/Touchdown-Labs/docs/sdlc/188-2026-05-07-lmcache-inferguard-observability-source-of-truth.md`.
As of that tracker, LMCache observability coverage remains **58 / 100**. This
page documents parser, packet, report, and diagnosis behavior that exists in
InferGuard; it does not claim live-complete coverage. The next score movement
requires one clean live vLLM + standalone LMCache MP packet with metrics, HTTP,
logs, trace recording, fixture replay, and tests.

## Support Levels

| Surface | Typical launch shape | Evidence InferGuard can use today | Support level |
| --- | --- | --- | --- |
| Standalone MP | `lmcache server` plus vLLM `LMCacheMPConnector` | LMCache `/metrics` with `lmcache_mp_*`, vLLM `/metrics`, launch/config artifacts | Partial, highest priority |
| Embedded vLLM LMCache | vLLM with `LMCacheConnectorV1`, `LMCacheConnectorV1Dynamic`, or `--kv-offloading-backend lmcache` | Engine `/metrics`, production `lmcache:*` metrics, launch/config artifacts, inline vLLM/LMCache logs | Partial, compatibility priority |
| Embedded SGLang LMCache | SGLang `--enable-lmcache` using `LMCacheLayerwiseConnector` through SGLang's radix cache | SGLang `/metrics`, aggregate `sglang:cache_hit_rate`, HiCache/storage metrics when present, LMCache config/log evidence | Partial, compatibility priority |
| P2P sharing | multiple engines, `enable_p2p`, controller, NIXL | production `lmcache:*` P2P metrics when present; logs can be parsed as conservative packet evidence and surfaced by diagnosis | Parser/report partial; live proof missing |
| Disaggregated prefill | prefiller/decoder roles using NIXL | launch/config artifacts and NIXL/PD log hints can be parsed as conservative packet evidence and surfaced by diagnosis | Parser/report partial; live proof missing |
| CacheBlend | blend-mode lookups/retrieve/store with `lmcache_blend_*` and `cb.*` spans | `lmcache_blend_*` metrics are normalized, CacheBlend OTel spans are parsed, and report/diagnosis can surface CacheBlend finding codes | Parser/report partial; live proof missing |
| Lookup-hash JSONL | `lookup_hashes_*.jsonl` with redacted key-shape metadata | privacy-bounded parser redacts raw hashes and preserves request/model/chunk-shape summaries; packet/report plumbing accepts lookup-hash evidence | Parser/report partial; live proof missing |
| Controller / internal API | `lmcache_controller` or internal API server | not collected as a structured packet yet | Planned |
| Logs | engine and LMCache logs | copied into packets and parsed for conservative LMCache hints | Partial |
| OTel spans | MP tracing exported to operator-supplied JSONL | parsed into LMCache OTel evidence for `mp.store`, `mp.retrieve`, and `mp.lookup_prefetch` | Partial |
| Trace recording `.lct` | MP `--trace-level storage` binary trace recording | parsed as LMCache trace evidence; malformed traces are recorded without aborting packet creation | Partial |
| Trace replay metadata | `lmcache trace info` / replay JSON, JSONL, and CSV summaries | replay info, JSON, JSONL, and `trace_replay_ops.csv` evidence can be parsed and surfaced in packet/report/diagnosis flows | Parser/report partial; live proof missing |

## What `lmcache-compat` Does Today

`inferguard lmcache-compat` compares available Prometheus text against known LMCache and vLLM metric families. It reports whether each family is:

- `populated`: present with non-zero data;
- `zero`: present but all values are zero;
- `missing`: absent from the input;
- `partial`: some required families are present and others are not.

Use it when you have one or both of:

- engine metrics from vLLM/SGLang/Dynamo-compatible Prometheus endpoints;
- LMCache metrics from a standalone MP server or embedded production endpoint.
- Optional LMCache HTTP, `.lct`, and OTel evidence JSON files produced by
  `collect-lmcache` or equivalent local parsing.

For MP runs, prefer packet collection first:

```bash
inferguard collect-lmcache \
  --output-dir modal-out/lmcache-packet \
  --engine-metrics-file vllm.prom \
  --lmcache-metrics-file lmcache.prom \
  --lmcache-http-base-url http://localhost:7000 \
  --lmcache-http-thread-name eviction \
  --lmcache-log-file lmcache.log \
  --lmcache-trace-file lmcache-trace.lct \
  --lmcache-otel-file lmcache-otel.json \
  --expect-mode mp \
  --mp-trace-recording-enabled \
  --mp-tracing-enabled
```

`collect-lmcache` fetches safe read-only MP HTTP routes from the base URL and
records destructive routes such as cache clearing and metrics reset as skipped
evidence rather than invoking them.

Example:

```bash
inferguard lmcache-compat \
  --engine-metrics-file vllm.prom \
  --lmcache-metrics-file lmcache.prom \
  --lmcache-http-evidence-file lmcache_http_evidence.json \
  --lmcache-trace-evidence-file lmcache_trace_evidence.json \
  --lmcache-otel-evidence-file lmcache_otel_evidence.json \
  --expect-mode mp \
  --fail-on missing-required
```

Use `--l2-configured` only when the run actually configured an MP L2 adapter.
Without that flag, L2 families are reported as `not_applicable` so an L1-only
lab is not treated as a failed L2 proof.

For MP runs, pass the observability settings from the launch command when they
are known:

```bash
inferguard lmcache-compat \
  --lmcache-metrics-file lmcache.prom \
  --expect-mode mp \
  --mp-prometheus-port 9090 \
  --mp-event-bus-queue-size 10000 \
  --mp-metrics-sample-rate 0.01 \
  --mp-tracing-enabled
```

The JSON report includes an `lmcache_mp_observability` section with
`service_instance_ids` from Prometheus `target_info`, `cache_salt` cardinality,
L2 adapter labels, EventBus tail-drop risk, sampled-histogram sparsity, and
whether metrics/tracing/logging were disabled by config.

`diagnose-bottleneck` reads `metrics/lmcache_compat_report.json` and now
promotes user-facing LMCache finding codes for MP logs, CacheBlend, P2P, PD,
trace replay, and lookup-hash surfaces when those findings are present in the
report. It also reads `metrics/lmcache_log_evidence.json` from collected
packets and can emit conservative log-backed diagnoses such as
`lmcache_log_p2p_evidence_present`,
`lmcache_log_pd_evidence_present`, and `lmcache_log_stale_connector`. These are
`inferred` unless paired with measured Prometheus/HTTP/trace evidence.

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

For vLLM embedded mode, the current source-backed connector strings are:

- `LMCacheConnectorV1`;
- `LMCacheConnectorV1Dynamic` with
  `kv_connector_module_path="lmcache.integration.vllm.lmcache_connector_v1"`;
- `--kv-offloading-backend lmcache` / `kv_offloading_backend="lmcache"` as
  launch/config evidence for the vLLM LMCache offload path;
- legacy `LMCacheConnector`, which InferGuard should treat as stale/pinned
  evidence unless the operator documents an old stack.

For SGLang embedded mode, current mainline source evidence points to:

- `python -m sglang.launch_server --enable-lmcache`;
- SGLang `LMCRadixCache`;
- LMCache `LMCacheLayerwiseConnector`;
- SGLang metrics such as `sglang:cache_hit_rate`, queue gauges, HiCache
  host-token gauges, KV-transfer histograms, and storage metrics.

No current-mainline SGLang MP connector contract has been proven yet. InferGuard
must not mark SGLang MP as supported until source and a live fixture prove it.
SGLang HiCache-only metrics are not LMCache proof; InferGuard keeps them as
SGLang cache/storage context unless `--enable-lmcache`,
`LMCacheLayerwiseConnector`, `LMCRadixCache`, or `lmcache:*` evidence is also
present.

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

MP metrics are sampled in several places. Lifecycle and throughput histograms
default to a 1% sample rate, while counters count all events. Missing sampled
histograms should be explained separately from missing always-counted counters.
EventBus is also bounded; if EventBus self-metrics are absent, InferGuard flags
tail-drop observability risk instead of pretending drops are impossible.

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

Important source-backed caveat: current vLLM `LMCacheMPConnector` does not
export connector-specific Prometheus metrics through vLLM because its
`build_prom_metrics()` implementation returns `None`. For MP, the required
cache observability source is the standalone LMCache server, not the vLLM
connector metrics surface.

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

1. Add a clean full MP golden fixture with LMCache MP metrics, HTTP evidence,
   logs, and optional `.lct` / OTel evidence.
2. Add an MP L2 live fixture.
3. Calibrate detector rules for MP mode mismatch, missing MP metrics,
   zero-hit-after-warmup, hash-seed risk, missing lookup counters, L1 pressure,
   L2 stalls, EventBus drop risk, and trace/OTel evidence gaps.
4. Expand structured log parsing for MP store/retrieve lifecycle proof.
5. Validate embedded vLLM and SGLang connector classification against live
   fixtures. Fixture-backed parser support exists for vLLM
   `LMCacheConnectorV1Dynamic`/`kv_offloading_backend=lmcache`, stale
   `LMCacheConnector`, SGLang `--enable-lmcache`/`LMCacheLayerwiseConnector`/
   `LMCRadixCache`, and HiCache-only separation.
6. Add P2P mode detection and P2P metric normalization.
7. Add controller and internal API collection.
8. Add live compatibility fixtures for embedded, P2P, PD, OTel, and trace
   recording.

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

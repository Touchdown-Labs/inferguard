# LMCache Coverage Plan

This is the working tracker for getting InferGuard to full LMCache observability
coverage. "Full coverage" means InferGuard can collect, normalize, report, and
diagnose every LMCache signal class that matters for Touchdown AI Spend Recovery,
with real fixtures from live runs.

It does not mean every optional metric must be non-zero in every run. It means
InferGuard can tell the operator which LMCache mode is running, which evidence is
present, which evidence is missing, and what that implies.

## Current State

Scoring source manifest:

- Active upstream tracker for this plan:
  `/Users/chen/Projects/Touchdown-Labs/docs/sdlc/195-2026-05-07-lmcache-vllm-inferguard-100-coverage-ssot.md`.
  It supersedes and consolidates docs 188/189/190.
- Source-of-truth score from that tracker: **68 / 100**. Do not raise this
  score until a live Modal/H100 artifact has been replayed through
  `collect-lmcache`, `lmcache-compat`, `observability-coverage`, and
  `diagnose-bottleneck`, imported as a compact sanitized fixture, and pinned by
  passing tests.
- InferGuard tracker commit used for this score: see SDLC 195 for the current
  checked repo refs before moving any score.
- Latest InferGuard implementation included in the score: parser/report/runner
  support is present, and Packet A is live-validated under
  `tests/fixtures/lmcache_live/packet_a/`.
- LMCache repo used for source verification: `/Users/chen/Projects/LMCache`.
- LMCache upstream ref used for source verification: `upstream/dev` at
  `5ff3fe35`.
- LMCache local branch state when scored: `dev...upstream/dev [behind 7]`.
- Official public baseline: `https://docs.lmcache.ai/mp/observability.html`.
- Local doc/source baseline:
  - `docs/source/mp/observability.rst`
  - `docs/source/mp/http_api.rst`
  - `docs/source/mp/configuration.rst`
  - `docs/source/mp/tracing_and_debugging.rst`
  - `docs/source/mp/architecture.rst`
  - `lmcache/v1/mp_observability/`
  - `tests/v1/mp_observability/`
  - `examples/observability/grafana/provisioning/dashboards/lmcache.json`
- RepoPrompt context: LMCache window `10`, context
  `44277818-F58D-4891-A5F3-97AC341DB0B2`. The selection has been reset to the
  explicit MP observability source set listed above.
- vLLM repo used for bridge verification: `/Users/chen/Projects/vllm`.
  - Upstream ref fetched: `upstream/main` at
    `5a0a8fc1ea7542394ff315138bd5677b7b53bca1`
    (`[Docs] add cache directory security guidance (#38920)`).
  - Local fork branch during review:
    `ocwc/simple-cpu-offload-metrics` at
    `6509008424f243d874a91e76d34d8c67456a9855`
    (`feat(kv-offload): expose SimpleCPU offload metrics`).
  - RepoPrompt workspace: `/Users/chen/Projects/vllm`, window `8`.
- SGLang repo used for bridge verification: `/Users/chen/Projects/sglang`.
  - Upstream ref fetched: `upstream/main` at
    `2e642ea1872d12e3d838bd3350d4d64f792042ec`
    (`[diffusion] chore: align LTX-2 with official (#24313)`).
  - Local fork branch during review: `kv-transfer-telemetry` at
    `f26a73ea3407c620dd1c28d84b904bd3e1c8af50`
    (`feat(pd): expose KV transfer size in load metrics`).
  - RepoPrompt workspace: `/Users/chen/Projects/sglang`, window `8`.

## Progress Scoreboard

Current LMCache coverage: **68 / 100 points complete**.

This score is intentionally conservative. Parser support without real live
fixtures counts as partial progress, not complete support. A surface only gets
full credit when InferGuard has code, tests, real artifacts, and user-facing
diagnosis or reporting.

Scoring rules:

- Public LMCache docs define the customer-facing baseline.
- LMCache source defines emerging/hidden requirements, but source-only metrics
  do not earn full support credit until InferGuard has fixture coverage.
- Parser and compatibility-report support earns partial credit.
- Real artifacts and golden tests are required for full credit.
- Diagnosis credit requires user-facing findings, not just metric presence.

| Workstream | Weight | Done | Status | Source basis | What is complete | What is still needed |
| --- | ---: | ---: | --- | --- | --- | --- |
| LMCache MP Prometheus coverage | 20 | 15 | partial | Official MP Observability doc plus `lmcache/v1/mp_observability/subscribers/metrics/` | Parses and reports documented MP metric families; supports mode detection, L1, L2, lookup, lifecycle, throughput, gauges, EventBus families, and source-discovered L1/L2 failure counters | Add live L2 fixture, live nonzero lookup-token fixture, and sampled throughput/lifecycle fixture |
| Embedded / in-process LMCache metrics | 12 | 7 | partial | InferGuard aliases plus LMCache single-process `lmcache.` namespace guidance | Parses `lmcache:*` and `lmcache_*`; added production request/token/health/remote/P2P/chunk aliases; preserves unknown metrics | Add live embedded fixture and stale connector tests |
| HTTP API evidence | 8 | 6 | partial | `docs/source/mp/http_api.rst` and public HTTP API docs | Parses saved LMCache MP health/status evidence and now packet-captures safe read-only MP HTTP routes including `/conf`, `/threads`, `/periodic-threads`, `/periodic-threads/{thread_name}`, and `/periodic-threads-health`; destructive routes are explicitly skipped | Add live fixtures for the full HTTP endpoint set and add source-backed quota/version/internal API packet evidence |
| Trace recording `.lct` evidence | 8 | 5 | partial | MP Observability and Tracing/Debugging docs; `lmcache/v1/mp_observability/trace/` | Captures and summarizes length-prefixed records, supports real msgpack `.lct` records plus legacy JSON fixtures, parses trace-info/replay JSON/JSONL/CSV summaries, and handles malformed traces | Validate against a real live LMCache `.lct` trace from `--trace-level storage` plus replay output from the same run |
| OTel span evidence | 8 | 5 | partial | MP Observability tracing section and Grafana dashboard span names | Parses JSONL and OTLP JSON span exports for `mp.store`, `mp.retrieve`, `mp.lookup_prefetch`, root `request`, and CacheBlend `cb.*` spans; included in reports | Add real collector export fixture for MP and CacheBlend spans |
| Log evidence | 8 | 3 | partial | MP logging docs and existing InferGuard log parser | Existing conservative LMCache log parsing exists and diagnosis can surface log-only P2P, PD, lifecycle, and stale-connector evidence as inferred findings | Expand MP lifecycle, hash-seed, P2P, PD, and zero-hit-after-warmup log detectors |
| Diagnosis rules | 16 | 6 | early | InferGuard `diagnose-bottleneck` behavior and Touchdown playbook needs | Compatibility/coverage reports LMCache-specific findings for low MP hit rate, empty `cache_salt`, EventBus observability/loss, L1 eviction/failure pressure, L2 failures, trace-enabled-without-trace evidence, and OTel-enabled-without-spans; `diagnose-bottleneck` can surface them and now passes through new user-facing CacheBlend/P2P/PD/trace-replay/lookup-hash/log finding codes when parser/report lanes emit them | Add live thresholds from real runs, log-backed zero-hit-after-restart detector, first-class CacheBlend/P2P/PD parser-backed detectors, and stronger remediation text |
| Live golden fixtures | 10 | 3 | partial | Existing Modal real-shaped slice plus synthetic tests | Modal real-shaped MP metric slice exists; synthetic tests cover new evidence parsers | Capture clean full MP packet, embedded packet, L2 packet, OTel packet, and `.lct` packet |
| vLLM / SGLang bridge | 6 | 5 | partial | InferGuard vLLM/SGLang parsers and LMCache connector docs/source | vLLM prefix/external/CPU-offload and SGLang queue/HiCache/KV-transfer parsing exists; compatibility reports now emit architecture labels for `vllm_mp_lmcache`, `vllm_embedded_lmcache`, `sglang_embedded_lmcache`, and `sglang_mp_lmcache_candidate` | Add live vLLM+LMCache MP connector fixture and SGLang external-cache fixture |
| Docs / release readiness | 4 | 3 | partial | InferGuard docs and CLI reference | Coverage plan exists, is linked in docs nav, and now reflects the expanded HTTP/trace/OTel implementation and remaining live-proof gates | Refresh generated CLI reference and add a live-packet runbook after the Modal packet is captured |

### Detailed Ledger: LMCache MP Prometheus Coverage

The **15 / 20** MP Prometheus score is based on the official MP Observability
metric list plus source-discovered metrics in
`lmcache/v1/mp_observability/subscribers/metrics/`.

| Sub-area | Weight | Done | Source | InferGuard evidence | Missing for full credit |
| --- | ---: | ---: | --- | --- | --- |
| StorageManager counters: `sm_read_*`, `sm_write_*` | 2 | 2 | Official docs | Parsed, normalized, reported, and tested | None |
| L1 counters and memory: `l1_read_keys`, `l1_write_keys`, `l1_evicted_keys`, `l1_memory_usage_bytes` | 2 | 2 | Official docs | Parsed, normalized, reported, and tested | None |
| Lookup hit-rate: `lookup_requested_tokens`, `lookup_hit_tokens`, `model_name`, `cache_salt` | 2 | 1.5 | Official docs | Parser/report/tests exist | Live nonzero lookup-token fixture |
| L2 counters and `l2_name` labels | 2 | 1.5 | Official docs | Parser/report/tests exist | Live L2-configured fixture |
| L1/L0 lifecycle and real-reuse histograms | 2 | 1.5 | Official docs | Parser/report/tests exist | Live sampled fixture proving nonzero histograms |
| L0-L1 and L1-L2 throughput histograms | 2 | 1.5 | Official docs | Parser/report/tests exist | Live sampled throughput fixture |
| Engine counter: `num_chunks_loaded` | 1 | 1 | Official docs | Parser/report/tests exist | None |
| Observable gauges: `active_prefetch_jobs`, in-flight L2, in-flight load bytes | 1 | 1 | Official docs | Parser/report/tests exist | None |
| Resource and label handling: `service.instance.id`, `cache_salt`, `model_name`, L2 labels | 1 | 1 | Official docs | Compatibility report tracks these | None |
| EventBus self-metrics and L1/L2 failure counters | 1 | 1 | LMCache source | EventBus self-metrics and `l1_allocation_failure`, `l1_read_failure`, `l2_prefetch_failure` aliases parse and have targeted tests | None |
| Real MP fixture coverage | 2 | 0.5 | Modal real-shaped slice | Real-shaped MP scrape exists | Clean full fixture with metrics, HTTP, logs, optional trace/OTel |
| Diagnostic mapping | 2 | 1.5 | InferGuard report behavior | Missing-family reporting plus first LMCache-specific detector pack exists | Tune thresholds and recommendations against live packets |

Percent by category:

- **Collection/parsing:** about **78%** complete.
- **Compatibility/coverage reporting:** about **80%** complete.
- **Real live validation:** about **40%** complete.
- **Actionable diagnostics:** about **45%** complete.
- **Public docs/release readiness:** about **55%** complete.

The next score-moving milestone is **74 / 100**: C1, the live Packet B lifecycle gate.
To reach it, finish:

1. Use the local-source Modal packaging path that produced the accepted Packet A
   proof.
2. Run the full repo packet runner from `/Users/chen/Projects/inferguard`:
   `INFERGUARD_LMCACHE_LOCAL_SOURCE=/Users/chen/Projects/LMCache modal run scripts/lmcache_mp_modal_packet_lab.py::run_packet_b`.
3. Import compact sanitized Packet B fixtures and pin sampled lifecycle/L0-L1
   expectations with passing tests.

Do not move the score for runner/docs/parser changes alone.

### RepoPrompt Index Procedure

When refreshing this score, do not use a stale broad RepoPrompt selection. Build
an explicit LMCache MP observability selection with:

```bash
rp-cli -w 10 -e 'call manage_selection {"op":"set","paths":["docs/source/mp/observability.rst","docs/source/mp/http_api.rst","docs/source/mp/configuration.rst","docs/source/mp/tracing_and_debugging.rst","docs/source/mp/architecture.rst","lmcache/v1/mp_observability","tests/v1/mp_observability","examples/observability/grafana/provisioning/dashboards/lmcache.json"],"mode":"full","view":"files","strict":true}'
rp-cli -w 10 -e 'context --tree --files'
```

Then copy the selected source list and LMCache `upstream/dev` commit into the
source manifest above before changing score values.

## Architecture Map: Old Embedded vs New MP

InferGuard needs to support two LMCache generations at the same time, but the
priority is the new standalone MP architecture. The old architecture is still
important because many customer deployments will have copied vLLM/SGLang
examples that run LMCache inside the serving process.

| Lane | Connector / launch shape | Process boundary | Primary telemetry surface | InferGuard support target | Current status |
| --- | --- | --- | --- | --- | --- |
| Old vLLM embedded / in-process | `LMCacheConnectorV1` through vLLM `--kv-transfer-config`; `LMCacheConnectorV1Dynamic` with `kv_connector_module_path="lmcache.integration.vllm.lmcache_connector_v1"`; legacy `LMCacheConnector` should be treated as stale unless pinned | LMCache engine is initialized inside the vLLM worker process through `lmcache/integration/vllm/vllm_v1_adapter.py` | vLLM `/metrics`, embedded LMCache `lmcache:*` or exporter-normalized `lmcache_*`, vLLM logs containing LMCache store/retrieve lines, optional embedded internal API | Detect embedded mode, parse old metric namespace, detect connector name, explain that MP-only endpoints and `lmcache_mp_*` are not expected | Partial: aliases exist; live fixture and connector-specific stale/current detection still needed |
| Old SGLang embedded / in-process | `lmcache.integration.sglang.sglang_adapter.LMCacheConnector` or `LMCacheLayerwiseConnector` from SGLang launch/config | LMCache engine is initialized inside the SGLang server/worker process | SGLang metrics when enabled, SGLang queue/cache/HiCache/KV-transfer counters, LMCache logs/config evidence, possible KV events | Detect SGLang+LMCache evidence separately from vLLM; parse SGLang cache pressure and queue signals; avoid claiming MP support unless a standalone LMCache server is present | Partial: SGLang metric families parse; live SGLang+LMCache fixture and connector proof still needed |
| New vLLM MP | Standalone `lmcache server`; vLLM attaches with `LMCacheMPConnector`, for example `--kv-transfer-config '{"kv_connector":"LMCacheMPConnector","kv_role":"kv_both"}'`; newer vLLM offload flags may wrap this path | LMCache runs as a separate process and vLLM talks to it over ZMQ; HTTP/Prometheus/OTel live on the LMCache process | LMCache MP `/metrics` with `lmcache_mp_*`, MP HTTP API, EventBus metrics/logs, `.lct` trace recording, OTel spans, plus vLLM `/metrics` | This is the primary 100% target: collect LMCache MP evidence and correlate it with the engine that drove traffic | Best-covered structurally; live full packet and detectors still needed |
| New SGLang MP candidate | SGLang-to-MP support is not yet treated as confirmed mainline coverage in this tracker; local LMCache source has SGLang embedded adapters and separate MP infrastructure, and an upstream branch exists for SGLang MP work | Expected shape is SGLang process talking to a standalone LMCache MP server, but this must be validated from current source/docs before scoring | Same LMCache MP surfaces as vLLM MP, plus SGLang engine metrics/logs | Track as planned/emerging until current mainline docs/source prove the exact connector and launch contract | Planned: do not claim 100% until source and fixture prove it |

Source anchors in the LMCache repo:

- vLLM embedded connector: `lmcache/integration/vllm/lmcache_connector_v1.py`
  exposes `LMCacheConnectorV1Dynamic`, backed by
  `lmcache/integration/vllm/vllm_v1_adapter.py`.
- vLLM MP connector: `lmcache/integration/vllm/lmcache_mp_connector_0180.py`
  exposes `LMCacheMPConnector`, backed by
  `lmcache/integration/vllm/vllm_multi_process_adapter.py`.
- SGLang embedded connector:
  `lmcache/integration/sglang/sglang_adapter.py` exposes
  `LMCacheConnector` and `LMCacheLayerwiseConnector`.
- Public vLLM mode docs: `docs/source/getting_started/quickstart.rst`
  explicitly split vLLM into MP mode via `LMCacheMPConnector` and in-process
  mode via `LMCacheConnectorV1`.
- Public dynamic connector docs:
  `docs/source/api_reference/dynamic_connector.rst` explain
  `LMCacheConnectorV1`, `LMCacheConnectorV1Dynamic`, and why old connector
  updates may require vLLM-side synchronization.
- Public MP docs: `docs/source/mp/index.rst`,
  `docs/source/mp/configuration.rst`, `docs/source/mp/http_api.rst`, and
  `docs/source/mp/observability.rst` define the new standalone architecture and
  telemetry surface.

Source anchors in the vLLM repo:

- Current vLLM embedded wrapper:
  `vllm/distributed/kv_transfer/kv_connector/v1/lmcache_connector.py`
  exposes `LMCacheConnectorV1`. It lazy-loads either vLLM's vendored/native
  LMCache adapter when `use_native=true`, or the latest installed LMCache
  package's `lmcache.integration.vllm.vllm_v1_adapter.LMCacheConnectorV1Impl`
  by default.
- Current vLLM MP wrapper:
  `vllm/distributed/kv_transfer/kv_connector/v1/lmcache_mp_connector.py`
  exposes `LMCacheMPConnector`. It imports
  `lmcache.integration.vllm.vllm_multi_process_adapter` when available and
  falls back to vLLM's `lmcache_integration` implementation.
- Current vLLM MP connector telemetry gap:
  `LMCacheMPConnector.build_prom_metrics()` returns `None`. Therefore, as of
  the fetched vLLM refs, MP observability must be collected from the standalone
  LMCache MP server (`lmcache_mp_*`, HTTP, EventBus, trace, OTel), not from
  vLLM connector Prometheus metrics.
- Current vLLM generic connector telemetry:
  `vllm/distributed/kv_transfer/kv_connector/v1/metrics.py` defines the generic
  `KVConnectorStats`, `KVConnectorLogging`, and `KVConnectorPromMetrics`
  extension points. Connectors only export Prometheus metrics when they
  implement `build_prom_metrics()`.
- Current vLLM offload telemetry:
  `vllm/distributed/kv_transfer/kv_connector/v1/offloading/metrics.py`
  exports `vllm:kv_offload_total_bytes`,
  `vllm:kv_offload_total_time`, and `vllm:kv_offload_size` by
  `transfer_type`. This is adjacent to LMCache but is not proof that LMCache MP
  is working.

Source anchors in the SGLang repo:

- Current SGLang LMCache integration:
  `python/sglang/srt/mem_cache/storage/lmcache/README.md` documents
  `python -m sglang.launch_server --model-path MODEL --enable-lmcache` with
  `LMCACHE_CONFIG_FILE`.
- Current SGLang LMCache implementation:
  `python/sglang/srt/mem_cache/storage/lmcache/lmc_radix_cache.py` defines
  `LMCRadixCache`, imports
  `lmcache.integration.sglang.sglang_adapter.LMCacheLayerwiseConnector`, and
  stores/retrieves KV through SGLang's radix-cache lifecycle.
- Current SGLang launch flag:
  `python/sglang/srt/server_args.py` defines `enable_lmcache` and the
  `--enable-lmcache` CLI flag.
- Current SGLang metrics:
  `python/sglang/srt/observability/metrics_collector.py` exports
  `sglang:cache_hit_rate`, scheduler queue gauges, KV-transfer histograms
  (`kv_transfer_latency_ms`, `kv_transfer_total_mb`,
  `kv_transfer_speed_gb_s`), HiCache host-token gauges, and storage metrics
  (`sglang:prefetched_tokens_total`, `sglang:backuped_tokens_total`,
  `sglang:prefetch_pgs`, `sglang:backup_pgs`,
  `sglang:prefetch_bandwidth`, `sglang:backup_bandwidth`).
- No current-mainline SGLang MP connector contract was proven in this pass.
  Treat SGLang+LMCache as embedded/layerwise until a source-backed MP connector
  and live fixture are added.

## Old Architecture Signal Checklist

These signals are required for backward compatibility. They are not the new
primary target, but InferGuard must not misclassify them as broken MP.

### vLLM Embedded LMCache

Mode evidence:

- Connector strings:
  - `LMCacheConnectorV1` means current embedded vLLM path.
  - `LMCacheConnectorV1Dynamic` means current embedded vLLM path loaded from the
    LMCache package by module path.
  - `LMCacheConnector` without `V1` should be flagged as stale or pinned legacy
    evidence, not as the modern vLLM path.
- Process evidence:
  - LMCache log lines are inline with vLLM engine logs.
  - No standalone LMCache MP `/api/healthcheck` or `lmcache_mp_*` scrape is
    expected unless the deployment also runs MP.

Metric evidence:

- Embedded LMCache namespace:
  - `lmcache:num_retrieve_requests`;
  - `lmcache:num_store_requests`;
  - `lmcache:num_lookup_requests`;
  - `lmcache:num_requested_tokens`;
  - `lmcache:num_hit_tokens`;
  - `lmcache:num_lookup_tokens`;
  - `lmcache:num_lookup_hits`;
  - `lmcache:num_vllm_hit_tokens`;
  - `lmcache:is_healthy`;
  - `lmcache:storage_event_count`;
  - remote backend read/write byte, latency, ping, and error counters;
  - P2P transfer metrics when P2P sharing is configured;
  - chunk-statistics metrics or HTTP evidence when the internal API server is
    enabled.
- vLLM bridge namespace:
  - local prefix cache metrics such as `vllm:prefix_cache_*`;
  - external prefix cache metrics such as `vllm:external_prefix_cache_*`;
  - prompt-token source metrics if vLLM exposes them;
  - KV offload or simple CPU-offload metrics when the vLLM build includes them.

Required InferGuard behavior:

- Report mode as `vllm_embedded_lmcache`.
- Compute LMCache hit rate from embedded token counters when present.
- Say MP observability is `not_applicable`, not missing, unless an MP endpoint
  was explicitly supplied.
- Detect hash-seed risk when `PYTHONHASHSEED` is absent or inconsistent across
  processes.
- Preserve unknown `lmcache:*` families so new LMCache releases are not hidden.

### SGLang Embedded LMCache

Mode evidence:

- Connector classes:
  - `lmcache.integration.sglang.sglang_adapter.LMCacheConnector`;
  - `lmcache.integration.sglang.sglang_adapter.LMCacheLayerwiseConnector`.
- Process evidence:
  - LMCache is initialized through SGLang adapter code.
  - SGLang metrics must be enabled separately; lack of `lmcache_mp_*` is normal
    for embedded mode.

Metric evidence:

- SGLang queue and scheduler pressure:
  - `sglang:num_running_reqs`;
  - `sglang:num_queue_reqs`;
  - related wait/latency counters where exposed.
- SGLang cache evidence:
  - aggregate cache hit rate such as `sglang:cache_hit_rate`;
  - HiCache L1/L2/L3 hit, miss, and transfer counters where exposed;
  - KV-transfer counters where exposed.
- LMCache-adjacent evidence:
  - LMCache config path/env;
  - store/retrieve/hit-token log lines;
  - KV events if configured through SGLang.

Required InferGuard behavior:

- Report mode as `sglang_embedded_lmcache` when SGLang and LMCache adapter
  evidence are both present.
- Report SGLang cache/queue pressure separately from LMCache MP health.
- Do not infer MP just because L2/HiCache terms appear; MP requires a
  standalone LMCache server evidence source.
- Add a live SGLang fixture before claiming more than partial support.

## New Architecture Signal Checklist

This is the priority path for current LMCache work and for Touchdown AI Spend
Recovery engagements.

### vLLM With LMCache MP

Mode evidence:

- `lmcache server` process is running.
- vLLM uses `LMCacheMPConnector`.
- The LMCache MP HTTP API responds on its HTTP port.
- The LMCache MP Prometheus endpoint emits `lmcache_mp_*`.
- ZMQ host/port appears in either LMCache config, vLLM
  `kv_connector_extra_config`, or logs.

Metric and evidence requirements:

- All canonical MP HTTP endpoints listed below are either collected or marked
  intentionally skipped when they mutate state.
- All canonical MP Prometheus metric families listed below are parsed.
- Sampled histograms are classified separately from always-on counters.
- L2 families are `not_applicable` when no L2 adapter is configured.
- EventBus self-metrics are treated as first-class because tail-drop can hide
  observability evidence.
- vLLM `/metrics` is collected so InferGuard can compare engine-side external
  cache claims against LMCache-side lookup/store/retrieve evidence.

Required InferGuard behavior:

- Report mode as `vllm_mp_lmcache`.
- Compute LMCache MP lookup hit rate from `lookup_hit_tokens /
  lookup_requested_tokens`.
- Report missing cache-salt, empty cache-salt, or high-cardinality cache-salt as
  separate findings.
- Diagnose L1 pressure, L2 backlog, throughput regressions, and EventBus drops
  from MP-native evidence.

### SGLang With LMCache MP

This is a planned lane, not a completed claim. The tracker should only move it
from candidate to supported after source and fixtures confirm the current
mainline connector contract.

Required before scoring as supported:

- Current LMCache source/docs show the exact SGLang MP connector or launch
  contract.
- A live SGLang run proves traffic reaches a standalone LMCache MP server.
- InferGuard packet includes both SGLang engine metrics and LMCache MP HTTP /
  Prometheus evidence.
- The report can distinguish SGLang local/HiCache hits from LMCache MP L1/L2
  hits.

### Canonical LMCache MP HTTP Endpoints To Support

These are the real MP HTTP endpoints confirmed from
`lmcache/v1/multiprocess/http_apis/` plus inherited compatible routes from
`lmcache/v1/internal_api_server/common/`. The shared `/run_script` route exists
in the common package but is explicitly excluded from MP by
`_MP_INCOMPATIBLE_MODULES`, so InferGuard should not require it for MP coverage.

| Method | Path | Source | Status | Missing proof | Exact next command |
| --- | --- | --- | --- | --- | --- |
| GET | `/` | `root_api.py` | parser_only | Live MP packet liveness capture. | `curl -fsS "$LMCACHE_HTTP/" -o "$PACKET_DIR/lmcache_root.txt"` |
| GET | `/api/healthcheck` | `healthcheck_api.py` | fixture_backed | Live MP packet health proof. | `curl -fsS "$LMCACHE_HTTP/api/healthcheck" -o "$PACKET_DIR/lmcache-health.json"` |
| GET | `/api/status` | `status_api.py` | fixture_backed | Live MP packet status proof. | `curl -fsS "$LMCACHE_HTTP/api/status" -o "$PACKET_DIR/lmcache-status.json"` |
| POST | `/api/clear-cache` | `cache_api.py` | destructive_skipped | Skipped endpoint recorded in packet manifest. | `printf '%s\n' 'POST /api/clear-cache destructive_skipped' >> "$PACKET_DIR/skipped_endpoints.txt"` |
| GET | `/conf` | `conf_api.py` | parser_only | Live config capture with parsed fields. | `curl -fsS "$LMCACHE_HTTP/conf" -o "$PACKET_DIR/lmcache-conf.json"` |
| GET | `/version` | `version_api.py` | fixture_backed | Live MP packet endpoint proof. | `curl -fsS "$LMCACHE_HTTP/version" -o "$PACKET_DIR/lmcache-version.txt"` |
| GET | `/lmc_version` | `version_api.py` | fixture_backed | Live MP packet endpoint proof. | `curl -fsS "$LMCACHE_HTTP/lmc_version" -o "$PACKET_DIR/lmcache-lmc-version.txt"` |
| GET | `/commit_id` | `version_api.py` | fixture_backed | Live MP packet endpoint proof. | `curl -fsS "$LMCACHE_HTTP/commit_id" -o "$PACKET_DIR/lmcache-commit-id.txt"` |
| GET | `/env` | inherited `env_api.py` | missing | Opt-in redacted capture policy and fixture. | `curl -fsS "$LMCACHE_HTTP/env" -o "$PACKET_DIR/lmcache_env.raw.json"` |
| GET | `/loglevel` | inherited `loglevel_api.py` | missing | Verify non-mutating form; never set level by default. | `curl -fsS "$LMCACHE_HTTP/loglevel" -o "$PACKET_DIR/lmcache_loglevel.json"` |
| GET | `/metrics` | inherited `metrics_api.py` | fixture_backed | Live MP and embedded metric packets. | `curl -fsS "$LMCACHE_METRICS" -o "$PACKET_DIR/lmcache.prom"` |
| POST | `/metrics/reset` | inherited `metrics_api.py` | destructive_skipped | Skipped endpoint recorded in packet manifest. | `printf '%s\n' 'POST /metrics/reset destructive_skipped' >> "$PACKET_DIR/skipped_endpoints.txt"` |
| GET | `/threads` | inherited `thread_api.py` | parser_only | Live thread dump summary. | `curl -fsS "$LMCACHE_HTTP/threads" -o "$PACKET_DIR/lmcache-threads.json"` |
| GET | `/periodic-threads` | inherited `periodic_thread_api.py` | parser_only | Live periodic thread capture. | `curl -fsS "$LMCACHE_HTTP/periodic-threads" -o "$PACKET_DIR/lmcache-periodic-threads.json"` |
| GET | `/periodic-threads/{thread_name}` | inherited `periodic_thread_api.py` | parser_only | Discovered or operator-provided live thread row. | `curl -fsS "$LMCACHE_HTTP/periodic-threads/$THREAD_NAME" -o "$PACKET_DIR/lmcache-periodic-thread-$THREAD_NAME.json"` |
| GET | `/periodic-threads-health` | inherited `periodic_thread_api.py` | parser_only | Live periodic thread health capture. | `curl -fsS "$LMCACHE_HTTP/periodic-threads-health" -o "$PACKET_DIR/lmcache-periodic-threads-health.json"` |
| PUT | `/api/quota/{cache_salt}` | `quota_api.py` | destructive_skipped | Skipped endpoint recorded; do not mutate quota. | `printf '%s\n' 'PUT /api/quota/{cache_salt} destructive_skipped' >> "$PACKET_DIR/skipped_endpoints.txt"` |
| GET | `/api/quota/{cache_salt}` | `quota_api.py` | parser_only | Per-salt quota live fixture. | `curl -fsS "$LMCACHE_HTTP/api/quota/$CACHE_SALT" -o "$PACKET_DIR/lmcache-quota-$CACHE_SALT.json"` |
| DELETE | `/api/quota/{cache_salt}` | `quota_api.py` | destructive_skipped | Skipped endpoint recorded; do not mutate quota. | `printf '%s\n' 'DELETE /api/quota/{cache_salt} destructive_skipped' >> "$PACKET_DIR/skipped_endpoints.txt"` |
| GET | `/api/quota` | `quota_api.py` | fixture_backed | Live MP packet quota proof. | `curl -fsS "$LMCACHE_HTTP/api/quota" -o "$PACKET_DIR/lmcache-quota.json"` |

### Canonical LMCache MP Metrics To Support

Metric names below use the OpenTelemetry source name. In Prometheus, dots become
underscores and counters usually gain a `_total` suffix. InferGuard should
accept both exact scraped names and the OTel-to-Prometheus form.

| Family | Metrics | Source | Status | Missing proof | Exact next command |
| --- | --- | --- | --- | --- | --- |
| StorageManager counters | `lmcache_mp.sm_read_requests`, `lmcache_mp.sm_read_succeed_keys`, `lmcache_mp.sm_read_failed_keys`, `lmcache_mp.sm_write_requests`, `lmcache_mp.sm_write_succeed_keys`, `lmcache_mp.sm_write_failed_keys` | Official docs and `sm.py` | fixture_backed | Live MP packet with nonzero read/write evidence. | `inferguard lmcache-compat --lmcache-metrics-file "$PACKET_DIR/lmcache.prom" --output "$PACKET_DIR/lmcache_compat_report.json" --expect-mode mp` |
| L1 counters | `lmcache_mp.l1_read_keys`, `lmcache_mp.l1_write_keys`, `lmcache_mp.l1_evicted_keys` | Official docs and `l1.py` | fixture_backed | Live MP packet with L1 read/write/eviction evidence. | `inferguard observability-coverage --lmcache-metrics-file "$PACKET_DIR/lmcache.prom" --output "$PACKET_DIR/observability_coverage.json" --expect-lmcache-mode mp` |
| L1 memory gauge | `lmcache_mp.l1_memory_usage_bytes` | Official docs and L1 gauge registration | fixture_backed | Multi-scrape timeline proving plateau or continued growth. | `inferguard collect-metrics --engine lmcache --endpoint "$LMCACHE_METRICS" --samples 6 --interval-seconds 10 --output-dir "$PACKET_DIR/l1-memory-timeline"` |
| L1 failure counters | `lmcache_mp.l1_allocation_failure`, `lmcache_mp.l1_read_failure` | Source `l1_failures.py` | fixture_backed | Real failure packet. | `inferguard lmcache-compat --lmcache-metrics-file "$PACKET_DIR/lmcache_l1_failure.prom" --output "$PACKET_DIR/l1_failure_report.json" --expect-mode mp` |
| L1 lifecycle histograms | `lmcache_mp.l1_chunk_lifetime_seconds`, `lmcache_mp.l1_chunk_idle_before_evict_seconds`, `lmcache_mp.l1_chunk_reuse_gap_seconds`, `lmcache_mp.l1_chunk_evict_reuse_gap_seconds` | Official docs and `l1_lifecycle.py` | fixture_backed | Live sample-rate 1.0 packet. | `inferguard lmcache-compat --lmcache-metrics-file "$PACKET_DIR/lmcache_lifecycle.prom" --output "$PACKET_DIR/lifecycle_report.json" --expect-mode mp` |
| Real reuse histograms | `lmcache_mp.real_reuse_gap_seconds`, `lmcache_mp.real_reuse_gap_chunks` | Official docs and `sm_lifecycle.py` | parser_only | Repeated-prefix packet with nonzero reuse buckets. | `inferguard lmcache-compat --lmcache-metrics-file "$PACKET_DIR/lmcache_reuse.prom" --output "$PACKET_DIR/reuse_report.json" --expect-mode mp` |
| L2 counters | `lmcache_mp.l2_store_tasks`, `lmcache_mp.l2_store_keys`, `lmcache_mp.l2_store_completed`, `lmcache_mp.l2_store_succeeded_keys`, `lmcache_mp.l2_store_failed_keys`, `lmcache_mp.l2_load_completed`, `lmcache_mp.l2_prefetch_lookups`, `lmcache_mp.l2_prefetch_lookup_keys`, `lmcache_mp.l2_prefetch_hit_keys`, `lmcache_mp.l2_prefetch_load_tasks`, `lmcache_mp.l2_prefetch_load_keys`, `lmcache_mp.l2_prefetch_loaded_keys`, `lmcache_mp.l2_prefetch_failed_keys` | Official docs and `l2.py` | fixture_backed | Live L2-configured packet. | `inferguard lmcache-compat --lmcache-metrics-file "$PACKET_DIR/lmcache_l2.prom" --output "$PACKET_DIR/l2_report.json" --l2-configured --expect-mode mp` |
| L2 failure counter | `lmcache_mp.l2_prefetch_failure` | Source `l2_failures.py` | fixture_backed | Real failed L2 fixture. | `inferguard diagnose-bottleneck --job-dir "$JOB_DIR" --output-dir "$PACKET_DIR/diagnose-l2-failures"` |
| Lookup hit-rate counters | `lmcache_mp.lookup_requested_tokens`, `lmcache_mp.lookup_hit_tokens` | Official docs and `lookup.py` | fixture_backed | Warmup/replay packet with nonzero requested and hit tokens. | `inferguard diagnose-bottleneck --job-dir "$JOB_DIR" --output-dir "$PACKET_DIR/diagnose-lookup"` |
| L0 lifecycle histograms | `lmcache_mp.l0_block_lifetime_seconds`, `lmcache_mp.l0_block_idle_before_evict_seconds`, `lmcache_mp.l0_block_reuse_gap_seconds` | Official docs and `l0_lifecycle.py` | fixture_backed | Live GPU-block lifecycle scrape. | `inferguard lmcache-compat --lmcache-metrics-file "$PACKET_DIR/lmcache_l0_lifecycle.prom" --output "$PACKET_DIR/l0_lifecycle_report.json" --expect-mode mp` |
| L0-L1 throughput histograms | `lmcache_mp.l0_l1_store_throughput_gbs`, `lmcache_mp.l0_l1_load_throughput_gbs` | Official docs and `l0_l1_throughput.py` | parser_only | Live L0-L1 throughput packet. | `inferguard observability-coverage --lmcache-metrics-file "$PACKET_DIR/lmcache_l0_l1.prom" --output "$PACKET_DIR/l0_l1_throughput_coverage.json" --expect-lmcache-mode mp` |
| L1-L2 throughput histograms | `lmcache_mp.l2_store_throughput_gbs`, `lmcache_mp.l2_load_throughput_gbs` | Official docs and `l2_throughput.py` | parser_only | Live L2 throughput packet. | `inferguard observability-coverage --lmcache-metrics-file "$PACKET_DIR/lmcache_l2.prom" --output "$PACKET_DIR/l2_throughput_coverage.json" --l2-configured --expect-lmcache-mode mp` |
| Engine counter | `lmcache_mp.num_chunks_loaded` | Official docs and `engine.py` | parser_only | Live retrieve proof with chunks loaded populated. | `inferguard lmcache-compat --lmcache-metrics-file "$PACKET_DIR/lmcache_loaded.prom" --output "$PACKET_DIR/chunks_loaded_report.json" --expect-mode mp` |
| Observable gauges | `lmcache_mp.active_prefetch_jobs`, `lmcache_mp.num_inflight_l2_stores`, `lmcache_mp.num_inflight_l2_loads`, `lmcache_mp.inflight_load_memory_usage_bytes` | Official docs and gauge registration | parser_only | Multi-scrape pressure/backlog timeline. | `inferguard collect-metrics --engine lmcache --endpoint "$LMCACHE_METRICS" --samples 6 --interval-seconds 10 --output-dir "$PACKET_DIR/l2-gauge-timeline"` |
| EventBus self-metrics | `lmcache_mp.event_bus.queue_depth`, `lmcache_mp.event_bus.drain_lag_seconds`, `lmcache_mp.event_bus.dropped_events_total`, `lmcache_mp.event_bus.subscriber_exceptions` | Source `event_bus.py` | fixture_backed | Clean and failing live EventBus packets. | `inferguard lmcache-compat --lmcache-metrics-file "$PACKET_DIR/lmcache_eventbus.prom" --output "$PACKET_DIR/eventbus_report.json" --expect-mode mp` |
| CacheBlend counters | `lmcache_blend.lookup_requests`, `lmcache_blend.lookup_fingerprint_hits`, `lmcache_blend.lookup_storage_hits`, `lmcache_blend.lookup_stale_chunks`, `lmcache_blend.lookup_no_gpu_context_errors`, `lmcache_blend.retrieve_requests`, `lmcache_blend.retrieve_chunks`, `lmcache_blend.retrieve_failures`, `lmcache_blend.store_pre_computed_requests`, `lmcache_blend.store_pre_computed_chunks`, `lmcache_blend.store_pre_computed_failures`, `lmcache_blend.store_final_requests`, `lmcache_blend.store_final_chunks`, `lmcache_blend.store_final_failures`, `lmcache_blend.fingerprints_registered`, `lmcache_blend.chunks_evicted` | Source `cb_server.py` | fixture_backed | Live CacheBlend packet. | `inferguard lmcache-compat --lmcache-metrics-file "$PACKET_DIR/cacheblend.prom" --output "$PACKET_DIR/cacheblend_report.json" --expect-mode mp` |

What shipped before `edccffd`:

- LMCache MP Prometheus compatibility reporting for `lmcache_mp_*`.
- Embedded/in-process LMCache metric normalization for `lmcache:*` and
  `lmcache_*`.
- `collect-lmcache` evidence packet basics.
- `lmcache-compat` compatibility reports.
- `observability-coverage` reports across LMCache, vLLM, and SGLang.
- MP coverage reporting for StorageManager, lookup tokens, L1, L2, lifecycle,
  throughput, gauges, and EventBus families.
- Architecture detection for `vllm_mp_lmcache`, `vllm_embedded_lmcache`,
  `sglang_embedded_lmcache`, and `sglang_mp_lmcache_candidate`.
- First LMCache MP diagnostic findings for low hit rate, empty `cache_salt`,
  EventBus loss/unobservability, L1 eviction/failure pressure, and L2 failures.

What `edccffd` added:

- Structured LMCache MP HTTP health/status evidence parsing.
- LMCache trace recording `.lct` evidence parsing.
- LMCache OTel JSONL span evidence parsing for `mp.store`, `mp.retrieve`, and
  `mp.lookup_prefetch`.
- CLI flags to pass those evidence files into `collect-lmcache`,
  `lmcache-compat`, and `observability-coverage`.
- More embedded/production LMCache metric aliases:
  - request counters;
  - token counters;
  - health;
  - remote backend read/write/ping;
  - P2P;
  - chunk statistics.
- Targeted tests for HTTP, trace, OTel, packet capture, compatibility,
  coverage, and metric alias parsing.

Latest verification:

```bash
uv run pytest \
  tests/test_lmcache_http.py \
  tests/test_lmcache_trace.py \
  tests/test_lmcache_otel.py \
  tests/test_lmcache_packet.py \
  tests/test_observability_coverage.py \
  tests/test_lmcache_metrics_adapter.py \
  tests/test_collect_metrics.py
```

Result: `44 passed`.

What the latest implementation added:

- Normalized LMCache MP source-discovered failure counters:
  `lmcache_mp_l1_allocation_failure_total`,
  `lmcache_mp_l1_read_failure_total`, and
  `lmcache_mp_l2_prefetch_failure_total`.
- `detected_architecture` in compatibility reports, separating the LMCache
  server mode from the engine integration path.
- `diagnostic_findings` in compatibility reports, with evidence and recommended
  operator action.
- `diagnose-bottleneck` promotion of those findings into a specific rule-fired
  result when a job directory contains `metrics/lmcache_compat_report.json`.

Latest focused verification:

```bash
uv run pytest \
  tests/test_lmcache_metrics_adapter.py \
  tests/test_observability_coverage.py \
  tests/test_lmcache_packet.py \
  tests/test_diagnose_bottleneck.py
```

Result: `17 passed, 18 skipped`.

## Definition Of 100 Percent

InferGuard reaches "100 percent LMCache coverage" when the rows below are all
`done` with real fixture evidence.

| Area | Required capability | Status | Missing proof | Exact next command |
| --- | --- | --- | --- | --- |
| Mode detection | Distinguish `vllm_embedded_lmcache`, `vllm_mp_lmcache`, `sglang_embedded_lmcache`, `sglang_mp_lmcache_candidate`, P2P candidate, disaggregated-prefill candidate, and controller-only packets | partial | Live packets for every mode, especially P2P, PD, embedded SGLang, and SGLang MP candidate. | `inferguard observability-coverage --engine-metrics-file "$PACKET_DIR/engine.prom" --lmcache-metrics-file "$PACKET_DIR/lmcache.prom" --output "$PACKET_DIR/mode_coverage.json"` |
| MP Prometheus | Parse/report all documented `lmcache_mp_*` families | partial | Live L2, nonzero lookup, and sampled lifecycle/throughput packets. | `inferguard lmcache-compat --lmcache-metrics-file "$PACKET_DIR/lmcache.prom" --output "$PACKET_DIR/lmcache_compat_report.json" --expect-mode mp` |
| Embedded Prometheus | Parse/report production `lmcache:*` and exporter-normalized `lmcache_*` families | partial | Live embedded vLLM and SGLang fixtures. | `inferguard observability-coverage --engine-metrics-file "$PACKET_DIR/vllm_embedded.prom" --output "$PACKET_DIR/vllm_embedded_coverage.json" --expect-lmcache-mode embedded` |
| HTTP API | Parse health/status evidence and explain unhealthy/unreachable states | partial | Live full safe-endpoint packet. | `inferguard collect-lmcache --output-dir "$PACKET_DIR" --lmcache-health-file "$PACKET_DIR/lmcache-health.json" --lmcache-status-file "$PACKET_DIR/lmcache-status.json"` |
| Trace recording | Capture and summarize `.lct` storage trace artifacts | partial | Live `.lct` from `--trace-level storage`. | `inferguard collect-lmcache --output-dir "$PACKET_DIR/trace" --lmcache-trace-file "$PACKET_DIR/trace/lmcache-trace.lct"` |
| OTel tracing | Capture and summarize MP store/retrieve/lookup spans | partial | Real OTel collector export. | `inferguard collect-lmcache --output-dir "$PACKET_DIR/otel" --lmcache-otel-file "$PACKET_DIR/otel/lmcache-otel.jsonl"` |
| Logs | Parse MP, embedded, P2P, and PD operational logs into structured evidence | partial | Live MP, embedded, P2P, and PD log packets. | `inferguard collect-lmcache --output-dir "$PACKET_DIR/logs" --engine-log-file "$PACKET_DIR/vllm.log" --lmcache-log-file "$PACKET_DIR/lmcache.log"` |
| Diagnostics | Convert evidence into specific findings, not just coverage rows | missing | Calibrated rules from live packets. | `inferguard diagnose-bottleneck --job-dir "$JOB_DIR" --output-dir "$PACKET_DIR/diagnose-bottleneck"` |
| Live fixtures | Golden artifacts from real LMCache runs for each supported mode | partial | Packet A is accepted; sanitized fixture imports remain for Packet B-F, L2, CacheBlend, P2P/PD, embedded vLLM, and embedded SGLang. | `INFERGUARD_LMCACHE_LOCAL_SOURCE=/Users/chen/Projects/LMCache modal run scripts/lmcache_mp_modal_packet_lab.py::run_packet_b` |
| vLLM bridge | Verify vLLM connector metrics line up with LMCache MP evidence | partial | Live vLLM + LMCache MP connector packet and mismatch detector. | `inferguard observability-coverage --engine-metrics-file "$PACKET_DIR/vllm.prom" --lmcache-metrics-file "$PACKET_DIR/lmcache.prom" --external-cache-configured --output "$PACKET_DIR/vllm_mp_coverage.json"` |
| SGLang bridge | Verify SGLang + external cache/LMCache-adjacent evidence where applicable | partial | Live SGLang embedded fixture and source-backed MP contract. | `inferguard observability-coverage --engine-metrics-file "$PACKET_DIR/sglang_lmcache.prom" --expected-engine sglang --output "$PACKET_DIR/sglang_lmcache_coverage.json" --expect-lmcache-mode embedded` |
| Documentation | User-facing docs match the current CLI and support level | partial | CLI examples and release notes after live fixture gates. | `uv run mkdocs build` |

## Phase 1: Lock The Live MP Baseline

Goal: prove InferGuard can inspect one real LMCache MP run end to end.

- [x] Add MP metric compatibility report.
- [x] Add MP evidence packet collection.
- [x] Add HTTP, trace, and OTel evidence inputs.
- [x] Run a clean LMCache MP Packet A lab from the full repo packet runner and save artifacts:
  - [x] vLLM `/metrics`.
  - [x] LMCache MP `/metrics`.
  - [x] LMCache `/api/healthcheck`.
  - [x] LMCache `/api/status`.
  - [x] LMCache `/threads`.
  - [x] LMCache `/periodic-threads`.
  - [x] LMCache `/periodic-threads-health`.
  - [x] vLLM logs.
  - [x] LMCache logs.
  - [x] `.lct` trace when `--trace-level storage` is enabled.
  - [ ] OTel JSONL or exported spans when tracing is enabled.
- [x] Add Packet A artifacts as compact live fixtures.
- [x] Add tests that prove Packet A reports:
  - [x] detected mode is `mp`;
  - [x] required MP counters are present;
  - [x] sampled families are classified separately from always-counted counters;
  - [ ] L2 families are `not_applicable` unless L2 is configured.

Acceptance criteria:

- B1 uses `cd /Users/chen/Projects/inferguard && uv run pytest -q tests/test_lmcache_live_fixtures.py tests/test_lmcache_mp_modal_packet_lab.py`.
- Packet B uses `cd /Users/chen/Projects/inferguard && INFERGUARD_LMCACHE_LOCAL_SOURCE=/Users/chen/Projects/LMCache modal run scripts/lmcache_mp_modal_packet_lab.py::run_packet_b`.
- A developer can run one command against the fixture and see exactly what
  populated, what stayed zero, and what was missing.
- The report does not overclaim when a sampled histogram or L2 family is absent.

## Phase 2: Add Real Diagnostic Findings

Goal: move from "coverage matrix" to "actionable AI Spend Recovery diagnosis."

- [ ] Add LMCache MP detector rules:
  - [ ] `lmcache_mp_lookup_counters_missing`.
  - [ ] `lmcache_mp_low_hit_rate_after_warmup`.
  - [ ] `lmcache_mp_l1_memory_no_plateau`.
  - [ ] `lmcache_mp_l1_eviction_pressure`.
  - [ ] `lmcache_mp_l2_store_backlog`.
  - [ ] `lmcache_mp_l2_load_backlog`.
  - [ ] `lmcache_mp_l2_throughput_low`.
  - [ ] `lmcache_mp_cache_salt_empty_or_missing`.
  - [ ] `lmcache_mp_cache_salt_cardinality_high`.
  - [ ] `lmcache_mp_eventbus_drop_unobservable`.
  - [ ] `lmcache_mp_trace_enabled_without_spans`.
  - [ ] `lmcache_mp_trace_recording_enabled_without_lct`.
- [ ] Add embedded LMCache detector rules:
  - [ ] `lmcache_embedded_zero_hit_rate_after_replay`.
  - [ ] `lmcache_embedded_hashseed_risk`.
  - [ ] `lmcache_embedded_remote_backend_errors`.
  - [ ] `lmcache_embedded_p2p_transfer_slow`.
- [ ] Map each detector to:
  - [ ] required input artifacts;
  - [ ] threshold defaults;
  - [ ] user-facing explanation;
  - [ ] recommended next action;
  - [ ] whether it is safe to show in customer reports.

Acceptance criteria:

- `inferguard diagnose-bottleneck` can emit LMCache-specific findings from a
  real MP packet.
- Each finding has enough evidence to paste into Slack or a customer audit note.

## Phase 3: Complete Embedded / In-Process Coverage

Goal: keep compatibility with older and embedded LMCache architectures without
letting them distract from MP-first work.

- [x] Parse major production `lmcache:*` aliases.
- [x] Preserve unknown LMCache metric names in raw extras.
- [ ] Capture a live embedded fixture using vLLM with LMCache in-process.
- [ ] Add fixture tests for:
  - [ ] request counters;
  - [ ] token counters;
  - [ ] hit-rate counters;
  - [ ] remote backend counters;
  - [ ] P2P metrics if exposed;
  - [ ] chunk statistics.
- [ ] Add stale connector detection:
  - [ ] `LMCacheConnectorV1` is supported;
  - [ ] `LMCacheConnectorV1Dynamic` is supported when the module path points to
    `lmcache.integration.vllm.lmcache_connector_v1`;
  - [ ] old `LMCacheConnector` is flagged as stale unless explicitly pinned.
- [ ] Add embedded mode labels:
  - [ ] `vllm_embedded_lmcache`;
  - [ ] `sglang_embedded_lmcache`.

Acceptance criteria:

- InferGuard can say "this is embedded LMCache, not MP" and give a useful
  coverage report without mixing the two architectures.

## Phase 4: P2P And Disaggregated Prefill

Goal: support LMCache modes that matter for larger customer architectures.

- [ ] P2P evidence:
  - [ ] controller URL/config capture;
  - [ ] peer instance IDs;
  - [ ] peer ports;
  - [ ] NIXL/RDMA/TCP transfer mode;
  - [ ] cross-engine retrieve proof;
  - [ ] P2P metrics;
  - [ ] P2P connection failure logs.
- [ ] Disaggregated prefill evidence:
  - [ ] prefiller launch/config;
  - [ ] decoder launch/config;
  - [ ] producer/consumer roles;
  - [ ] NIXL ports/config;
  - [ ] transfer bytes/errors;
  - [ ] TTFT before/after comparison.
- [ ] Add explicit support levels:
  - [ ] `supported`;
  - [ ] `partial`;
  - [ ] `missing_signal`;
  - [ ] `inferred_without_engine_metrics`.

Acceptance criteria:

- InferGuard does not confuse MP, P2P, and PD.
- Reports say what was proven and what was only inferred.

## Phase 5: vLLM And SGLang Bridge Coverage

Goal: connect LMCache evidence to the engine that is actually serving traffic.

- [ ] vLLM:
  - [x] Parse local prefix cache metrics.
  - [x] Parse external prefix cache metrics when present.
  - [x] Parse CPU offload metric aliases.
  - [ ] Add live vLLM + LMCache MP connector fixture.
  - [ ] Validate vLLM CPU offload metrics against current upstream names.
  - [ ] Add detector for mismatch between vLLM external cache claims and
    LMCache MP evidence.
- [ ] SGLang:
  - [x] Parse queue and aggregate cache hit rate.
  - [x] Parse HiCache L1/L2/L3 counters.
  - [x] Parse KV transfer families when present.
  - [ ] Capture live SGLang embedded LMCache fixture.
  - [ ] Confirm current mainline SGLang MP connector/launch contract before
    scoring SGLang MP as supported.
  - [ ] Capture live SGLang MP fixture only after that contract is confirmed.
  - [ ] Confirm whether SGLang exposes request-level prefix hit/query counters.
  - [ ] Add SGLang-specific queue and KV transfer diagnostics.

Acceptance criteria:

- A customer packet can answer: "Is the engine using the cache path we think it
  is using, and is that path helping cost per useful task?"

## Phase 6: Docs, CLI, And Release

Goal: make the coverage usable by engineers who were not in this session.

- [ ] Update `docs/guides/lmcache-compatibility.md` to match current support:
  - [x] HTTP evidence is no longer "raw only";
  - [x] `.lct` evidence is no longer "missing";
  - [x] OTel evidence is no longer "missing";
  - [x] diagnosis now documents pass-through handling for CacheBlend, P2P, PD,
    trace-replay, lookup-hash, and log finding codes;
  - [ ] live detector gaps remain explicit.
- [x] Update `docs/guides/observability-coverage-matrix.md`.
- [x] Update `docs/reference/cli.md` after CLI help changes.
- [ ] Add one "run this on Modal output" example:
  - [ ] collect packet;
  - [ ] run compatibility;
  - [ ] run coverage;
  - [ ] run diagnosis.
- [ ] Release checklist:
  - [ ] run targeted tests;
  - [ ] run full test suite;
  - [ ] build docs;
  - [ ] bump package version if publishing PyPI;
  - [ ] publish release notes.

Acceptance criteria:

- The public docs do not claim 100 percent support until live fixtures and
  detectors exist.
- The CLI examples map directly to the Modal lab artifact names.

## Immediate Next Work

Do these in order:

1. Use the local-source Modal packaging runner path.
2. Run Packet B lifecycle from the full repo runner:
   `cd /Users/chen/Projects/inferguard && INFERGUARD_LMCACHE_LOCAL_SOURCE=/Users/chen/Projects/LMCache modal run scripts/lmcache_mp_modal_packet_lab.py::run_packet_b`.
3. Import compact sanitized Packet B fixture slices and pin sampled lifecycle/L0-L1 expectations.
4. Add the first detector pack:
   - missing lookup counters;
   - zero hit rate after replay;
   - missing cache salt;
   - EventBus tail-drop observability gap;
   - trace enabled without spans;
   - trace recording enabled without `.lct`.
5. Keep the LMCache docs at **68 / 100** until Packet B lands, is imported as
   a compact fixture, and passes the closeout tests.
6. Send Kuntai a concrete question backed by the fixture.

## Kuntai Follow-Up Template

Use this only after a live fixture is captured.

```text
We ran vLLM + LMCache MP through InferGuard and captured the LMCache MP
Prometheus endpoint, HTTP status, and optional trace evidence. The interesting
thing we saw is: <specific finding from fixture>.

InferGuard can now classify MP vs embedded LMCache and report which MP
observability families are populated, zero, or missing. The gap we keep hitting
is: <specific missing signal>.

Would a small upstream PR for <metric/log/span/HTTP field> be useful to you?
The goal would be to make cache behavior easier to verify automatically in
customer deployments, especially around <cache_salt/EventBus/L2/lookup counters>.
```

## Worker Docs/CLI Checklist - 2026-05-07

This section is the source-backed operator checklist for "100% LMCache
observability." It is documentation-only accounting; it does not raise the
current **68 / 100** score unless a new live packet or fixture is added.

Source links used for this checklist:

- LMCache MP observability:
  <https://docs.lmcache.ai/mp/observability.html>
- LMCache MP HTTP API:
  <https://docs.lmcache.ai/mp/http_api.html>
- LMCache MP tracing and replay:
  <https://docs.lmcache.ai/mp/tracing_and_debugging.html>
- LMCache production metrics reference:
  <https://docs.lmcache.ai/production/observability/metrics.html>
- LMCache production vLLM metrics endpoint:
  <https://docs.lmcache.ai/production/observability/vllm_endpoint.html>
- LMCache chunk statistics:
  <https://docs.lmcache.ai/production/observability/chunk_statistics.html>
- vLLM `LMCacheMPConnector` API:
  <https://docs.vllm.ai/en/v0.20.1/api/vllm/distributed/kv_transfer/kv_connector/v1/lmcache_mp_connector/>

Status language for all rows below:

- `fixture_backed`: InferGuard parser/report path has synthetic or saved
  fixture proof, but live proof may still be missing.
- `parser_only`: InferGuard can represent or parse the signal, but no fixture
  or live artifact proves it.
- `live_validated`: real LMCache runtime artifact has been replayed through
  InferGuard. In this tracker, the accepted Packet A/B1 fixture is
  `live_validated`; Packet B lifecycle is the next command before any other row
  can move the score.
- `not_applicable`: correctly excluded for the detected mode.
- `destructive_skipped`: endpoint or operation exists but InferGuard must record
  it as skipped rather than call it.

### Required Workload Packets

| SSoT row | Runner packet / lane | Required artifacts | Status | Missing proof | Exact command |
| --- | --- | --- | --- | --- | --- |
| B1 | Packet A: vLLM + standalone LMCache MP, L1-only, repeated-prefix warmup/replay | vLLM `/metrics`, LMCache `/metrics`, safe MP HTTP endpoints, vLLM log, LMCache log, `.lct` trace when enabled, packet manifest, compat report, coverage report, diagnosis output | live_validated | Accepted live fixture: `tests/fixtures/lmcache_live/packet_a/`; Modal run `https://modal.com/apps/ocwc22/main/ap-cH4YAMKOZxmsVOf58YzHPo`. | `cd /Users/chen/Projects/inferguard && uv run pytest -q tests/test_lmcache_live_fixtures.py tests/test_lmcache_mp_modal_packet_lab.py` |
| C1 | Packet B: sampled lifecycle and reuse/eviction pressure | Packet A plus nonzero L1/L0 lifecycle, real-reuse, L1 eviction, and L0-L1 throughput evidence | parser_only for live throughput/lifecycle; fixture_backed structurally | Live sampled scrape with nonzero lifecycle and throughput buckets. | `cd /Users/chen/Projects/inferguard && INFERGUARD_LMCACHE_LOCAL_SOURCE=/Users/chen/Projects/LMCache modal run scripts/lmcache_mp_modal_packet_lab.py::run_packet_b` |
| D1 | Packet C: MP with L2 configured | Packet A plus L2 config, L2 labels, store/load counters, throughput, prefetch, and in-flight gauges | parser_only for throughput/gauges; fixture_backed for core L2 counters | Live L2 scrape with nonzero store/load and backlog/throughput evidence. | `cd /Users/chen/Projects/inferguard && modal run scripts/lmcache_mp_modal_packet_lab.py::run_packet_c` |
| E1 | Packet D: MP OTel tracing | OTel collector export, `mp.store`, `mp.retrieve`, `mp.lookup_prefetch`, request/root spans, compat/coverage evidence | fixture_backed parser; live collector proof missing | Real collector export from the Modal packet, not hand-authored JSONL. | `cd /Users/chen/Projects/inferguard && modal run scripts/lmcache_mp_modal_packet_lab.py::run_packet_d` |
| E2 | Packet E: trace replay | `.lct`, `lmcache trace info`, replay JSON/JSONL/CSV, config digest linkage, compat/coverage evidence | fixture_backed parsers | Live replay output tied to the same `.lct` trace. | `cd /Users/chen/Projects/inferguard && modal run scripts/lmcache_mp_modal_packet_lab.py::run_packet_e` |
| F1 | Packet F: `cache_salt` and `IsolatedLRU` | launch proof for `IsolatedLRU`, cache_salt request path, lookup-hash JSONL with redaction, quota evidence | fixture_backed parser; live upstream-version proof missing | Live salt/isolation packet accepted by the installed LMCache/vLLM versions. | `cd /Users/chen/Projects/inferguard && modal run scripts/lmcache_mp_modal_packet_lab.py::run_packet_f` |
| G1 | Diagnostic calibration from Packets A-C | Packet A-C compact fixtures, diagnosis output, calibrated LMCache thresholds | missing / fixture_backed mixed | Thresholds tuned from live A-C timelines, not synthetic fixtures. | `inferguard diagnose-bottleneck --job-dir "$JOB_DIR" --output-dir "$PACKET_DIR/diagnose-bottleneck"` |
| H1 | Live embedded vLLM LMCache | vLLM launch/config showing `LMCacheConnectorV1` or current dynamic V1, vLLM `/metrics`, embedded `lmcache:*` metrics, logs | fixture_backed structurally | Live embedded vLLM fixture and stale connector negative case. | `inferguard observability-coverage --engine-metrics-file "$PACKET_DIR/vllm_embedded.prom" --output "$PACKET_DIR/vllm_embedded_coverage.json" --expect-lmcache-mode embedded` |
| H2 | Live SGLang `--enable-lmcache` embedded/layerwise | SGLang launch/config, SGLang metrics/logs, `LMCacheLayerwiseConnector` / `LMCRadixCache` evidence | parser_only | Live SGLang fixture proving adapter traffic. | `inferguard observability-coverage --engine-metrics-file "$PACKET_DIR/sglang_lmcache.prom" --expected-engine sglang --output "$PACKET_DIR/sglang_lmcache_coverage.json" --expect-lmcache-mode embedded` |
| H3 | Advanced CacheBlend, P2P, and 1p1d PD packets | CacheBlend metrics/spans, two-engine P2P transfer evidence, prefiller/decoder role and NIXL/proxy evidence | parser_only / fixture_backed mixed | Live compact fixtures for each advanced lane. | `inferguard collect-lmcache --output-dir "$PACKET_DIR/pd" --engine-log-file "$PACKET_DIR/pd/engine.log" --lmcache-log-file "$PACKET_DIR/pd/lmcache.log"` |
| I1 | Release/readiness | all compact fixtures, targeted and full tests, docs build, release notes, upstream question log | partial | Fixture import, tests, docs build, and release note evidence after B1-H3. | `uv run mkdocs build` |

### MP Metric Family Checklist

The MP source names below follow LMCache's OTel spelling. Prometheus scrapes
must also accept the underscore form and `_total` suffixes for counters.

| Metric family | Required metrics | Status | Missing proof | Exact command |
| --- | --- | --- | --- | --- |
| StorageManager counters | `lmcache_mp.sm_read_requests`, `sm_read_succeed_keys`, `sm_read_failed_keys`, `sm_write_requests`, `sm_write_succeed_keys`, `sm_write_failed_keys` | fixture_backed | Live Packet A nonzero reads/writes. | `inferguard lmcache-compat --lmcache-metrics-file "$PACKET_DIR/lmcache.prom" --output "$PACKET_DIR/lmcache_compat_report.json" --expect-mode mp` |
| L1 counters and memory | `lmcache_mp.l1_read_keys`, `l1_write_keys`, `l1_evicted_keys`, `l1_memory_usage_bytes` | fixture_backed | Live Packet A timeline. | `inferguard collect-metrics --engine lmcache --endpoint "$LMCACHE_METRICS" --samples 6 --interval-seconds 10 --output-dir "$PACKET_DIR/l1-memory-timeline"` |
| L1 failures | `lmcache_mp.l1_allocation_failure`, `l1_read_failure` | fixture_backed | Real failure packet. | `inferguard lmcache-compat --lmcache-metrics-file "$PACKET_DIR/lmcache_l1_failure.prom" --output "$PACKET_DIR/l1_failure_report.json" --expect-mode mp` |
| L1 lifecycle histograms | `lmcache_mp.l1_chunk_lifetime_seconds`, `l1_chunk_idle_before_evict_seconds`, `l1_chunk_reuse_gap_seconds`, `l1_chunk_evict_reuse_gap_seconds` | fixture_backed | Live sample-rate 1.0 scrape. | `inferguard lmcache-compat --lmcache-metrics-file "$PACKET_DIR/lmcache_lifecycle.prom" --output "$PACKET_DIR/lifecycle_report.json" --expect-mode mp` |
| StorageManager real reuse | `lmcache_mp.real_reuse_gap_seconds`, `real_reuse_gap_chunks` | parser_only | Repeated-prefix packet with nonzero reuse buckets. | `inferguard lmcache-compat --lmcache-metrics-file "$PACKET_DIR/lmcache_reuse.prom" --output "$PACKET_DIR/reuse_report.json" --expect-mode mp` |
| L2 counters | `lmcache_mp.l2_store_tasks`, `l2_store_keys`, `l2_store_completed`, `l2_store_succeeded_keys`, `l2_store_failed_keys`, `l2_load_completed`, `l2_prefetch_lookups`, `l2_prefetch_lookup_keys`, `l2_prefetch_hit_keys`, `l2_prefetch_load_tasks`, `l2_prefetch_load_keys`, `l2_prefetch_loaded_keys`, `l2_prefetch_failed_keys` | fixture_backed | Live L2 packet. | `inferguard lmcache-compat --lmcache-metrics-file "$PACKET_DIR/lmcache_l2.prom" --output "$PACKET_DIR/l2_report.json" --l2-configured --expect-mode mp` |
| L2 failure | `lmcache_mp.l2_prefetch_failure` | fixture_backed | Real failed L2 packet. | `inferguard diagnose-bottleneck --job-dir "$JOB_DIR" --output-dir "$PACKET_DIR/diagnose-l2-failures"` |
| Lookup hit rate | `lmcache_mp.lookup_requested_tokens`, `lookup_hit_tokens` with `model_name` and `cache_salt` | fixture_backed | Live warmup/replay with nonzero denominator and hits. | `inferguard diagnose-bottleneck --job-dir "$JOB_DIR" --output-dir "$PACKET_DIR/diagnose-lookup"` |
| L0 lifecycle | `lmcache_mp.l0_block_lifetime_seconds`, `l0_block_idle_before_evict_seconds`, `l0_block_reuse_gap_seconds` | fixture_backed | Live GPU-block lifecycle scrape. | `inferguard lmcache-compat --lmcache-metrics-file "$PACKET_DIR/lmcache_l0_lifecycle.prom" --output "$PACKET_DIR/l0_lifecycle_report.json" --expect-mode mp` |
| L0-L1 throughput | `lmcache_mp.l0_l1_store_throughput_gbs`, `l0_l1_load_throughput_gbs` | parser_only | Live throughput histogram. | `inferguard observability-coverage --lmcache-metrics-file "$PACKET_DIR/lmcache_l0_l1.prom" --output "$PACKET_DIR/l0_l1_throughput_coverage.json" --expect-lmcache-mode mp` |
| L1-L2 throughput | `lmcache_mp.l2_store_throughput_gbs`, `l2_load_throughput_gbs` | parser_only | Live L2 throughput histogram. | `inferguard observability-coverage --lmcache-metrics-file "$PACKET_DIR/lmcache_l2.prom" --output "$PACKET_DIR/l2_throughput_coverage.json" --l2-configured --expect-lmcache-mode mp` |
| Engine counter | `lmcache_mp.num_chunks_loaded` | parser_only | Live retrieve proof. | `inferguard lmcache-compat --lmcache-metrics-file "$PACKET_DIR/lmcache_loaded.prom" --output "$PACKET_DIR/chunks_loaded_report.json" --expect-mode mp` |
| Observable gauges | `lmcache_mp.active_prefetch_jobs`, `num_inflight_l2_stores`, `num_inflight_l2_loads`, `inflight_load_memory_usage_bytes` | parser_only | Multi-scrape live backlog timeline. | `inferguard collect-metrics --engine lmcache --endpoint "$LMCACHE_METRICS" --samples 6 --interval-seconds 10 --output-dir "$PACKET_DIR/l2-gauge-timeline"` |
| EventBus self-metrics | queue depth, drain lag, dropped events, subscriber exceptions | fixture_backed | Clean and failing live EventBus packets. | `inferguard lmcache-compat --lmcache-metrics-file "$PACKET_DIR/lmcache_eventbus.prom" --output "$PACKET_DIR/eventbus_report.json" --expect-mode mp` |
| CacheBlend counters | lookup, retrieve, pre-computed store, final store, fingerprint registration, chunk eviction, stale/no-context/failure counters | fixture_backed | Live CacheBlend packet. | `inferguard lmcache-compat --lmcache-metrics-file "$PACKET_DIR/cacheblend.prom" --output "$PACKET_DIR/cacheblend_report.json" --expect-mode mp` |

### Production Embedded Metric Family Checklist

These families come from the LMCache production metrics reference. InferGuard
must accept both `lmcache:*` and exporter-normalized `lmcache_*` spellings.

| Metric family | Required metrics | Status | Missing proof | Exact command |
| --- | --- | --- | --- | --- |
| Core request | `num_retrieve_requests`, `num_store_requests`, `num_lookup_requests` | fixture_backed | Live embedded vLLM and SGLang packets. | `inferguard observability-coverage --engine-metrics-file "$PACKET_DIR/vllm_embedded.prom" --output "$PACKET_DIR/vllm_embedded_coverage.json" --expect-lmcache-mode embedded` |
| Token | `num_requested_tokens`, `num_hit_tokens`, `num_stored_tokens`, `num_lookup_tokens`, `num_lookup_hits`, `num_vllm_hit_tokens`, `num_prompt_tokens` | fixture_backed | Repeated-request embedded hit packet. | `inferguard lmcache-compat --lmcache-metrics-file "$PACKET_DIR/embedded_lmcache.prom" --output "$PACKET_DIR/embedded_tokens_report.json" --expect-mode embedded` |
| Hit rate | `retrieve_hit_rate`, `lookup_hit_rate`, `request_cache_hit_rate`, `lookup_0_hit_requests` | fixture_backed | Live zero-hit and hit-after-warmup cases. | `inferguard diagnose-bottleneck --job-dir "$JOB_DIR" --output-dir "$PACKET_DIR/diagnose-embedded-hit-rate"` |
| Performance and latency | `time_to_retrieve`, `time_to_store`, `time_to_lookup`, `retrieve_speed`, `store_speed`, slow-retrieval counters | parser_only | Live latency/speed scrape. | `inferguard collect-metrics --engine lmcache --endpoint "$ENGINE_METRICS" --output-dir "$PACKET_DIR/embedded-latency"` |
| Detailed profiling | retrieve/store process, GPU transfer, put, remote blocking, connector batched-get histograms | parser_only | Live profiling-enabled scrape. | `inferguard lmcache-compat --lmcache-metrics-file "$PACKET_DIR/embedded_profile.prom" --output "$PACKET_DIR/embedded_profile_report.json" --expect-mode embedded` |
| Cache usage and lifecycle | local/remote cache usage, local storage usage, request cache lifespan | fixture_backed | Live embedded usage timeline. | `inferguard collect-metrics --engine lmcache --endpoint "$ENGINE_METRICS" --samples 6 --interval-seconds 10 --output-dir "$PACKET_DIR/embedded-usage"` |
| Remote backend and network | remote read/write request and byte counters, get/put latency, ping latency/errors/success/error code | parser_only | Live remote backend success/failure packet. | `inferguard lmcache-compat --lmcache-metrics-file "$PACKET_DIR/embedded_backend.prom" --output "$PACKET_DIR/embedded_backend_report.json" --expect-mode embedded` |
| Local CPU backend | evict count, evicted keys, eviction failures, hot cache count, keys-in-request count | parser_only | Live local CPU backend fixture. | `inferguard lmcache-compat --lmcache-metrics-file "$PACKET_DIR/embedded_cpu.prom" --output "$PACKET_DIR/embedded_cpu_report.json" --expect-mode embedded` |
| Memory management | active objects, pinned objects, forced unpin, pin monitor object count | parser_only | Live memory-management fixture. | `inferguard lmcache-compat --lmcache-metrics-file "$PACKET_DIR/embedded_memory.prom" --output "$PACKET_DIR/embedded_memory_report.json" --expect-mode embedded` |
| P2P transfer | P2P request/token counters, transfer time, transfer speed | parser_only | Two-engine P2P packet. | `inferguard collect-lmcache --output-dir "$PACKET_DIR/p2p" --lmcache-metrics-file "$PACKET_DIR/p2p/lmcache.prom" --lmcache-log-file "$PACKET_DIR/p2p/lmcache.log"` |
| Health/internal | `lmcache_is_healthy`, blocking failure count, KV queue size, remote put tasks, storage event counts | fixture_backed for aliases; live proof missing | Live healthy/unhealthy and queue/backlog packets. | `inferguard lmcache-compat --lmcache-metrics-file "$PACKET_DIR/embedded_health.prom" --output "$PACKET_DIR/embedded_health_report.json" --expect-mode embedded` |
| Chunk statistics | enabled, total requests/chunks, unique chunks, reuse rate, Bloom filter size/fill, file count/current file size | fixture_backed | Live chunk-statistics packet. | `inferguard lmcache-compat --lmcache-metrics-file "$PACKET_DIR/embedded_chunks.prom" --output "$PACKET_DIR/embedded_chunks_report.json" --expect-mode embedded` |

### CLI Closeout Commands

After any live packet, run the same four InferGuard steps before changing the
score:

```bash
inferguard collect-lmcache \
  --output-dir "$PACKET_DIR/lmcache-packet" \
  --engine-metrics-file "$PACKET_DIR/vllm.prom" \
  --lmcache-metrics-file "$PACKET_DIR/lmcache.prom" \
  --lmcache-health-file "$PACKET_DIR/lmcache-health.json" \
  --lmcache-status-file "$PACKET_DIR/lmcache-status.json" \
  --engine-log-file "$PACKET_DIR/vllm.log" \
  --lmcache-log-file "$PACKET_DIR/lmcache.log" \
  --lmcache-trace-file "$PACKET_DIR/lmcache-trace.lct" \
  --lmcache-trace-replay-output "$PACKET_DIR/trace-replay" \
  --lmcache-otel-file "$PACKET_DIR/lmcache-otel.jsonl" \
  --lmcache-lookup-hash-path "$PACKET_DIR/lookup-hashes" \
  --expect-mode mp \
  --json

inferguard lmcache-compat \
  --engine-metrics-file "$PACKET_DIR/vllm.prom" \
  --lmcache-metrics-file "$PACKET_DIR/lmcache.prom" \
  --lmcache-http-evidence-file "$PACKET_DIR/lmcache-packet/lmcache_http_evidence.json" \
  --lmcache-log-evidence-file "$PACKET_DIR/lmcache-packet/lmcache_log_evidence.json" \
  --lmcache-trace-evidence-file "$PACKET_DIR/lmcache-packet/lmcache_trace_evidence.json" \
  --lmcache-trace-replay-evidence-file "$PACKET_DIR/lmcache-packet/lmcache_trace_replay_evidence.json" \
  --lmcache-otel-evidence-file "$PACKET_DIR/lmcache-packet/lmcache_otel_evidence.json" \
  --lmcache-lookup-hash-evidence-file "$PACKET_DIR/lmcache-packet/lmcache_lookup_hash_evidence.json" \
  --expect-mode mp \
  --fail-on missing-required \
  --json

inferguard observability-coverage \
  --engine-metrics-file "$PACKET_DIR/vllm.prom" \
  --lmcache-metrics-file "$PACKET_DIR/lmcache.prom" \
  --lmcache-http-evidence-file "$PACKET_DIR/lmcache-packet/lmcache_http_evidence.json" \
  --lmcache-log-evidence-file "$PACKET_DIR/lmcache-packet/lmcache_log_evidence.json" \
  --lmcache-trace-evidence-file "$PACKET_DIR/lmcache-packet/lmcache_trace_evidence.json" \
  --lmcache-trace-replay-evidence-file "$PACKET_DIR/lmcache-packet/lmcache_trace_replay_evidence.json" \
  --lmcache-otel-evidence-file "$PACKET_DIR/lmcache-packet/lmcache_otel_evidence.json" \
  --lmcache-lookup-hash-evidence-file "$PACKET_DIR/lmcache-packet/lmcache_lookup_hash_evidence.json" \
  --expected-engine vllm \
  --expect-lmcache-mode mp \
  --json

inferguard diagnose-bottleneck \
  --job-dir "$JOB_DIR" \
  --output-dir "$PACKET_DIR/diagnose-bottleneck"
```

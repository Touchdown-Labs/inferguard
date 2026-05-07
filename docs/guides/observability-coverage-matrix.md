# Observability Coverage Matrix

This page is InferGuard's local coverage matrix for LMCache, vLLM, and SGLang.
The upstream source of truth is the Touchdown tracker linked below. This page
tracks what the CLI can parse or collect today,
which artifact records the evidence, and what remains before a surface can be
treated as complete proof.

Status meanings:

- `supported`: current parser or collector coverage is explicit and fixture-tested
  for the named surface.
- `partial`: InferGuard records useful evidence, but the surface is incomplete,
  raw-only, mode-dependent, or not enough to prove runtime behavior alone.
- `missing`: no current parser or collector handles the surface as first-class
  evidence.

## Progress

The upstream tracker is
`/Users/chen/Projects/Touchdown-Labs/docs/sdlc/188-2026-05-07-lmcache-inferguard-observability-source-of-truth.md`.
Current LMCache coverage remains **58 / 100**. This matrix records structural
parser, packet, report, and diagnosis surfaces that exist now. Live validation
is still pending for the Modal Packet A gate, so these rows must not be read as
100% LMCache compatibility.

## Matrix

| Runtime | Surface | Status | Artifact name | Current parser or CLI entrypoint | What remains |
| --- | --- | --- | --- | --- | --- |
| LMCache | Embedded / in-process Prometheus (`lmcache:*`, `lmcache_`) | partial | `engine_metrics_timeline.jsonl`, `metrics_summary.json`, `lmcache_compat_report.json`, optional `lmcache_metrics.prom`, `observability_coverage.json` when requested | `inferguard.collect_metrics.normalize.normalize_engine_sample("lmcache", ...)`, `inferguard.disagg.metrics_schema.parse_lmcache_prometheus`, `inferguard lmcache-compat`, `inferguard observability-coverage`, `inferguard collect-lmcache` | Add live embedded fixture with launch/config, repeated-request store/retrieve evidence, and explicit stale-connector failure case. Current parser preserves unknown LMCache metrics but does not prove compatibility from metrics alone. |
| LMCache | MP Prometheus (`lmcache_mp_*`) | supported | `lmcache_metrics.prom`, `engine_metrics_timeline.jsonl`, `metrics_summary.json`, `lmcache_compat_report.json`, `packet_manifest.json`, `observability_coverage.json` when requested | `parse_lmcache_prometheus`, `parse_lmcache_snapshot`, `normalize_engine_sample`, `build_compat_report`, `inferguard lmcache-compat`, `inferguard observability-coverage`, `inferguard collect-metrics --lmcache-metrics-url`, `inferguard collect-lmcache` | Add more live MP fixtures for L2-configured runs, nonzero lookup-token runs, and sampled throughput/lifecycle sparsity. Keep missing sampled histograms distinct from missing always-counted counters. |
| LMCache | MP HTTP status / health | partial | `lmcache_health.txt`, `lmcache_status.txt`, `lmcache_http_evidence.json`, `packet_manifest.json`, generic `launch/healthcheck.json` | `inferguard collect-lmcache --lmcache-health-url --lmcache-status-url`, `inferguard lmcache-compat --lmcache-http-evidence-file`, `inferguard observability-coverage --lmcache-http-evidence-file`, `inferguard.lmcache_http.parse_lmcache_http_payloads` | Add live fixtures for `/api/healthcheck`, `/api/status`, `/threads`, `/periodic-threads`, `/periodic-threads/{thread_name}`, and `/periodic-threads-health`. Parser support exists, but live endpoint coverage is still incomplete. |
| LMCache | Logs | partial | `engine.log`, `lmcache.log`, `lmcache_log_evidence.json`, `packet_manifest.json`, `bottleneck_diagnosis.json` when copied under a job `metrics/` directory | `inferguard.lmcache_logs.parse_lmcache_logs`, `inferguard collect-lmcache --engine-log-file --lmcache-log-file`, `inferguard diagnose-bottleneck` | Extend beyond conservative hints into mode-specific failure checks: zero-hit-after-warmup, hash-seed mismatch across processes, P2P connection failures, PD sender/receiver mismatch, and MP store/retrieve lifecycle proof. Log-only diagnosis remains inferred. |
| LMCache | OTel spans | partial | `lmcache_otel.jsonl`, `lmcache_otel_evidence.json`, `packet_manifest.json`, `lmcache_compat_report.json`, `observability_coverage.json` when requested | `inferguard collect-lmcache --lmcache-otel-file`, `inferguard lmcache-compat --lmcache-otel-evidence-file`, `inferguard observability-coverage --lmcache-otel-evidence-file`, `inferguard.lmcache_otel.parse_lmcache_otel_jsonl` | Add real OTel export fixture and detector for tracing enabled without spans. Current parser covers MP spans, root `request`, and CacheBlend `cb.*` spans. |
| LMCache | Trace recording `.lct` | partial | `lmcache_trace.lct`, `lmcache_trace_evidence.json`, `packet_manifest.json`, `lmcache_compat_report.json`, `observability_coverage.json` when requested | `inferguard collect-lmcache --lmcache-trace-file`, `inferguard lmcache-compat --lmcache-trace-evidence-file`, `inferguard observability-coverage --lmcache-trace-evidence-file`, `inferguard.lmcache_trace.parse_lmcache_trace_file` | Validate against a real LMCache `.lct` msgpack trace from `--trace-level storage`. Malformed traces are handled, but live trace proof is still pending. |
| LMCache | CacheBlend metrics/spans | partial | `lmcache_metrics.prom`, `lmcache_otel.jsonl`, `lmcache_compat_report.json`, `observability_coverage.json`, `bottleneck_diagnosis.json` | `parse_lmcache_prometheus`, `inferguard.lmcache_otel.parse_lmcache_otel_jsonl`, `inferguard lmcache-compat`, `inferguard observability-coverage`, `inferguard diagnose-bottleneck` | Add compact fixtures from a real CacheBlend run and live CacheBlend packet. |
| LMCache | Lookup-hash JSONL | partial | `lookup_hashes_*.jsonl`, `lmcache_lookup_hash_evidence.json`, `packet_manifest.json`, `lmcache_compat_report.json`, `bottleneck_diagnosis.json` | `inferguard.lmcache_lookup_hash.parse_lmcache_lookup_hash_jsonl`, `inferguard collect-lmcache --lmcache-lookup-hash-path`, `inferguard diagnose-bottleneck` | Add live lookup-hash packet and validate rotation/config fields from a real MP run. |
| LMCache | Trace replay metadata | partial | `lmcache_trace_replay_evidence.json`, `packet_manifest.json`, `lmcache_compat_report.json`, `bottleneck_diagnosis.json` | `inferguard.lmcache_trace.parse_lmcache_trace_replay_file`, `inferguard.lmcache_trace.parse_lmcache_trace_replay_dir`, `inferguard collect-lmcache --lmcache-trace-replay-output` | Add live replay proof tied to the same `.lct` trace and config digest. |
| LMCache | P2P / PD log evidence | partial | `lmcache_log_evidence.json`, `packet_manifest.json`, `bottleneck_diagnosis.json` when copied under a job `metrics/` directory | `inferguard.lmcache_logs.parse_lmcache_logs`, `inferguard collect-lmcache --engine-log-file --lmcache-log-file`, `inferguard diagnose-bottleneck` | Add metric/config correlation, connection-failure detectors, PD role/proxy/NIXL proof packets, and live two-engine P2P plus prefiller/decoder fixtures. |
| vLLM | Prometheus prefix cache | supported | `engine_metrics_timeline.jsonl`, `metrics_summary.json`, optional `raw_samples.jsonl`, `observability_coverage.json` when requested | `inferguard.disagg.adapters._parse_vllm`, `normalize_engine_sample("vllm", ...)`, `inferguard observability-coverage`, `inferguard collect-metrics`, `inferguard disagg status` | Keep support for both locked metric spellings (`vllm:prefix_cache_*` and `*_total`) as upstream evolves. Add a fixture where local prefix hits are nonzero and external prefix is absent to lock local-only behavior. |
| vLLM | Prometheus external prefix cache | supported | `engine_metrics_timeline.jsonl`, `metrics_summary.json`, `lmcache_compat_report.json` when LMCache packet/report is requested, `observability_coverage.json` when requested | `_parse_vllm`, `normalize_engine_sample("vllm", ...)`, `build_compat_report`, `inferguard observability-coverage --external-cache-configured` | Add live fixture with nonzero `external_prefix_cache_hits` and `prompt_tokens_by_source{source="external_kv_transfer"}`. Current real-shaped fixture proves detection even when external hits are zero. |
| vLLM | Prometheus CPU offload metrics | supported | `engine_metrics_timeline.jsonl`, `metrics_summary.json`, `observability_coverage.json` when requested | `_parse_vllm`, `normalize_engine_sample("vllm", ...)`, `inferguard observability-coverage --cpu-offload-configured` | Validate provisional KV-offload alias names against live vLLM versions and keep `simple_cpu_offload_*` plus labeled `kv_offload_total_*` fixtures. |
| SGLang | Prometheus prefix cache | partial | `engine_metrics_timeline.jsonl`, `metrics_summary.json`, `observability_coverage.json` when requested | `normalize_engine_sample("sglang", ...)` for `sglang:cache_hit_rate`; `_parse_sglang` for HiCache families; `inferguard observability-coverage --expected-engine sglang` | Add explicit SGLang prefix-cache hit/query fixture if upstream exposes one beyond aggregate `cache_hit_rate`. HiCache L1/L2/L3 counters are parsed, but they are not the same as request-level prefix-cache proof. |
| SGLang | Prometheus queue | supported | `engine_metrics_timeline.jsonl`, `metrics_summary.json`, `observability_coverage.json` when requested | `_parse_sglang`, `normalize_engine_sample("sglang", ...)`, `inferguard collect-metrics`, `inferguard disagg status`, `inferguard observability-coverage --expected-engine sglang` | Add an overload fixture with nonzero queue and a failure-classification test if queue pressure should drive a user-facing diagnosis. |
| SGLang | Prometheus KV transfer, if present | supported | `engine_metrics_timeline.jsonl`, `metrics_summary.json`, `observability_coverage.json` when requested | `_parse_sglang`, connector label detection on `sglang:kv_transfer_*`, `inferguard observability-coverage --disaggregated-or-external-cache` | Validate against live SGLang deployments using Mooncake/NIXL labels. Current parser only reports the generic KV-transfer family when present; it should not infer transfer support when the family is absent. |
| SGLang | Embedded LMCache evidence | partial | `engine_metrics_timeline.jsonl`, `metrics_summary.json`, `observability_coverage.json`, optional LMCache packet artifacts | `normalize_engine_sample("sglang", ...)`, `_parse_sglang`, LMCache embedded metric parser when `lmcache:*` is present | Capture live SGLang `--enable-lmcache` fixture. Current SGLang mainline evidence is embedded/layerwise, not proven MP. |
| SGLang | LMCache MP evidence | missing | none | none yet | Confirm a current-mainline SGLang MP connector/launch contract before adding support. Do not mark SGLang MP supported from SGLang HiCache/L2 naming alone. |

## Current Fixture Coverage

| Fixture or test | Surface locked | Current expectation |
| --- | --- | --- |
| `tests/fixtures/lmcache_metrics/full.prom` with `tests/test_lmcache_metrics_adapter.py` | LMCache embedded-style Prometheus aliases | passing |
| `tests/fixtures/lmcache_metrics/with_v1_connector.prom` with `tests/test_collect_metrics.py` | LMCache embedded connector detection | passing |
| `tests/fixtures/lmcache_metrics/mp.prom` with `tests/test_lmcache_metrics_adapter.py` and `tests/test_collect_metrics.py` | LMCache MP counters, lookup tokens, L1, L2, EventBus | passing |
| `tests/fixtures/lmcache_metrics/mp_modal_real_slice.prom` with `tests/test_lmcache_metrics_adapter.py` and `tests/test_collect_metrics.py` | Real-shaped LMCache MP storage/L0 plus vLLM external prefix scrape | passing |
| `tests/fixtures/lmcache_metrics/variant_unknown.prom` with `tests/test_lmcache_metrics_adapter.py` | Unknown LMCache metrics retained in `raw_metrics_extra` | passing |
| `tests/test_lmcache_logs.py` inline fixtures | LMCache log store/retrieve/prefetch/P2P/PD/config hints | passing |
| `tests/test_lmcache_packet.py` inline fixtures | `collect-lmcache` packet artifacts and partial-first failure behavior | passing |
| `tests/test_observability_coverage.py` inline fixtures | Cross-runtime vLLM, SGLang, and LMCache coverage-report rows plus CLI JSON output | passing |
| `tests/fixtures/vllm.txt` with `tests/test_disagg_adapters.py` and `tests/test_collect_metrics.py` | vLLM queue, local prefix cache, CPU prefix cache, KV transfer, TTFT/TPOT | passing |
| `tests/fixtures/vllm_simple_cpu_offload.prom` with `tests/test_disagg_adapters.py` and `tests/test_collect_metrics.py` | vLLM simple CPU offload and labeled KV offload transfer metrics | passing |
| `tests/fixtures/sglang.txt` with `tests/test_disagg_adapters.py` and `tests/test_collect_metrics.py` | SGLang queue, aggregate prefix hit rate, KV transfer, connector labels | passing |
| `tests/fixtures/sglang_hicache.txt` with `tests/test_disagg_adapters.py` | SGLang HiCache L1/L2/L3 counters | passing |

## Fixture Plan

These are the focused fixtures that should be added next. They should fail
before parser or report work begins and pass only when the named surface is
implemented.

| Planned fixture | Expected initial state | Target behavior |
| --- | --- | --- |
| `tests/fixtures/lmcache_health/healthy.json` and `unhealthy.json` | partially covered by parser tests; needs live endpoint fixtures | `collect-lmcache` emits parsed health fields and marks unhealthy status as a packet warning or failure reason. |
| `tests/fixtures/lmcache_traces/sample.lct` and `malformed.lct` | parser exists; needs real `.lct` fixture | Packet manifest includes trace artifact, parser summarizes storage events, malformed trace is recorded as not proven without aborting packet creation. |
| `tests/fixtures/lmcache_otel/basic.jsonl` | parser exists; needs real OTel export fixture | Report maps operator-supplied spans to LMCache evidence without mixing them into Touchdown telemetry. |
| `tests/fixtures/lmcache_metrics/mp_l2_live.prom` | failing only if L2 parser/report coverage regresses | `lmcache-compat --l2-configured` reports L2 counters/throughput as populated when live L2 metrics are present. |
| `tests/fixtures/vllm_external_prefix_nonzero.prom` | failing only if external-prefix normalization regresses | Metrics summary records external prefix queries, hits, and `prompt_tokens_external_kv_transfer` as measured. |
| `tests/fixtures/sglang_prefix_cache.prom` | failing until exact upstream request-level SGLang prefix metrics are known | SGLang prefix-cache group reports concrete hit/query fields, not only aggregate `cache_hit_rate`. |
| `tests/fixtures/sglang_lmcache_embedded.prom` | failing until live SGLang `--enable-lmcache` fixture exists | Coverage report marks SGLang embedded LMCache separately from vLLM embedded and LMCache MP. |
| `tests/fixtures/sglang_queue_overload.prom` | failing until queue diagnosis is expected | SGLang queue group is measured and downstream diagnosis can flag queue pressure from nonzero queued requests. |
| `tests/fixtures/sglang_kv_transfer_nixl.prom` | failing only if connector label detection regresses | SGLang KV-transfer bytes/errors and connector label are measured when present. |

## Targeted Test Set

Run this set after changing observability parsers, fixtures, or packet/report
logic:

```bash
uv run pytest \
  tests/test_disagg_adapters.py \
  tests/test_collect_metrics.py \
  tests/test_lmcache_metrics_adapter.py \
  tests/test_lmcache_logs.py \
  tests/test_lmcache_packet.py \
  tests/test_observability_coverage.py \
  tests/test_launch_engine_lmcache.py
```

Run CLI reference generation or broader docs validation separately if nav,
command names, or public help text changes.

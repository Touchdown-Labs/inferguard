# Observability Coverage Matrix

This page is the source of truth for InferGuard observability coverage across
LMCache, vLLM, and SGLang. It tracks what the CLI can parse or collect today,
which artifact records the evidence, and what remains before a surface can be
treated as complete proof.

Status meanings:

- `supported`: current parser or collector coverage is explicit and fixture-tested
  for the named surface.
- `partial`: InferGuard records useful evidence, but the surface is incomplete,
  raw-only, mode-dependent, or not enough to prove runtime behavior alone.
- `missing`: no current parser or collector handles the surface as first-class
  evidence.

## Matrix

| Runtime | Surface | Status | Artifact name | Current parser or CLI entrypoint | What remains |
| --- | --- | --- | --- | --- | --- |
| LMCache | Embedded / in-process Prometheus (`lmcache:*`, `lmcache_`) | partial | `engine_metrics_timeline.jsonl`, `metrics_summary.json`, `lmcache_compat_report.json`, optional `lmcache_metrics.prom`, `observability_coverage.json` when requested | `inferguard.collect_metrics.normalize.normalize_engine_sample("lmcache", ...)`, `inferguard.disagg.metrics_schema.parse_lmcache_prometheus`, `inferguard lmcache-compat`, `inferguard observability-coverage`, `inferguard collect-lmcache` | Add live embedded fixture with launch/config, repeated-request store/retrieve evidence, and explicit stale-connector failure case. Current parser preserves unknown LMCache metrics but does not prove compatibility from metrics alone. |
| LMCache | MP Prometheus (`lmcache_mp_*`) | supported | `lmcache_metrics.prom`, `engine_metrics_timeline.jsonl`, `metrics_summary.json`, `lmcache_compat_report.json`, `packet_manifest.json`, `observability_coverage.json` when requested | `parse_lmcache_prometheus`, `parse_lmcache_snapshot`, `normalize_engine_sample`, `build_compat_report`, `inferguard lmcache-compat`, `inferguard observability-coverage`, `inferguard collect-metrics --lmcache-metrics-url`, `inferguard collect-lmcache` | Add more live MP fixtures for L2-configured runs, nonzero lookup-token runs, and sampled throughput/lifecycle sparsity. Keep missing sampled histograms distinct from missing always-counted counters. |
| LMCache | MP HTTP status / health | partial | `lmcache_health.txt`, `lmcache_status.txt`, `packet_manifest.json`, generic `launch/healthcheck.json` | `inferguard collect-lmcache --lmcache-health-url --lmcache-status-url`; generic OpenAI health via `inferguard.launch_engine.healthcheck.run_healthcheck` | Add structured parser for LMCache MP health/status payloads, success/failure classification, and fixtures for healthy, unhealthy, and unreachable status endpoints. Today these URLs are captured raw and listed in the packet manifest. |
| LMCache | Logs | partial | `engine.log`, `lmcache.log`, `lmcache_log_evidence.json`, `packet_manifest.json` | `inferguard.lmcache_logs.parse_lmcache_logs`, `inferguard collect-lmcache --engine-log-file --lmcache-log-file` | Extend beyond conservative hints into mode-specific failure checks: zero-hit-after-warmup, hash-seed mismatch across processes, P2P connection failures, PD sender/receiver mismatch, and MP store/retrieve lifecycle proof. |
| LMCache | OTel traces | missing | none | none for LMCache OTel; agent traces only document an OTel relationship separately | Add an operator-supplied OTel trace input, schema mapping, fixture, and report section. Do not conflate this with Touchdown telemetry or `agent-trace/v1`. |
| LMCache | Trace recording `.lct` | missing | none | CLI records MP trace-recording config flags in `lmcache-compat` / `collect-lmcache`, but does not ingest `.lct` files | Add `.lct` artifact capture, parser or replay adapter, passing trace fixture, malformed/unsupported trace fixture, and compatibility report rows for trace coverage. |
| vLLM | Prometheus prefix cache | supported | `engine_metrics_timeline.jsonl`, `metrics_summary.json`, optional `raw_samples.jsonl`, `observability_coverage.json` when requested | `inferguard.disagg.adapters._parse_vllm`, `normalize_engine_sample("vllm", ...)`, `inferguard observability-coverage`, `inferguard collect-metrics`, `inferguard disagg status` | Keep support for both locked metric spellings (`vllm:prefix_cache_*` and `*_total`) as upstream evolves. Add a fixture where local prefix hits are nonzero and external prefix is absent to lock local-only behavior. |
| vLLM | Prometheus external prefix cache | supported | `engine_metrics_timeline.jsonl`, `metrics_summary.json`, `lmcache_compat_report.json` when LMCache packet/report is requested, `observability_coverage.json` when requested | `_parse_vllm`, `normalize_engine_sample("vllm", ...)`, `build_compat_report`, `inferguard observability-coverage --external-cache-configured` | Add live fixture with nonzero `external_prefix_cache_hits` and `prompt_tokens_by_source{source="external_kv_transfer"}`. Current real-shaped fixture proves detection even when external hits are zero. |
| vLLM | Prometheus CPU offload metrics | supported | `engine_metrics_timeline.jsonl`, `metrics_summary.json`, `observability_coverage.json` when requested | `_parse_vllm`, `normalize_engine_sample("vllm", ...)`, `inferguard observability-coverage --cpu-offload-configured` | Validate provisional KV-offload alias names against live vLLM versions and keep `simple_cpu_offload_*` plus labeled `kv_offload_total_*` fixtures. |
| SGLang | Prometheus prefix cache | partial | `engine_metrics_timeline.jsonl`, `metrics_summary.json`, `observability_coverage.json` when requested | `normalize_engine_sample("sglang", ...)` for `sglang:cache_hit_rate`; `_parse_sglang` for HiCache families; `inferguard observability-coverage --expected-engine sglang` | Add explicit SGLang prefix-cache hit/query fixture if upstream exposes one beyond aggregate `cache_hit_rate`. HiCache L1/L2/L3 counters are parsed, but they are not the same as request-level prefix-cache proof. |
| SGLang | Prometheus queue | supported | `engine_metrics_timeline.jsonl`, `metrics_summary.json`, `observability_coverage.json` when requested | `_parse_sglang`, `normalize_engine_sample("sglang", ...)`, `inferguard collect-metrics`, `inferguard disagg status`, `inferguard observability-coverage --expected-engine sglang` | Add an overload fixture with nonzero queue and a failure-classification test if queue pressure should drive a user-facing diagnosis. |
| SGLang | Prometheus KV transfer, if present | supported | `engine_metrics_timeline.jsonl`, `metrics_summary.json`, `observability_coverage.json` when requested | `_parse_sglang`, connector label detection on `sglang:kv_transfer_*`, `inferguard observability-coverage --disaggregated-or-external-cache` | Validate against live SGLang deployments using Mooncake/NIXL labels. Current parser only reports the generic KV-transfer family when present; it should not infer transfer support when the family is absent. |

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
| `tests/fixtures/lmcache_health/healthy.json` and `unhealthy.json` | failing until structured health/status parser exists | `collect-lmcache` emits parsed health fields and marks unhealthy status as a packet warning or failure reason. |
| `tests/fixtures/lmcache_traces/sample.lct` and `malformed.lct` | failing until `.lct` capture/parser exists | Packet manifest includes trace artifact, parser summarizes storage events, malformed trace is recorded as not proven without aborting packet creation. |
| `tests/fixtures/lmcache_otel/basic.jsonl` | failing until LMCache OTel input exists | Report maps operator-supplied spans to LMCache evidence without mixing them into Touchdown telemetry. |
| `tests/fixtures/lmcache_metrics/mp_l2_live.prom` | failing only if L2 parser/report coverage regresses | `lmcache-compat --l2-configured` reports L2 counters/throughput as populated when live L2 metrics are present. |
| `tests/fixtures/vllm_external_prefix_nonzero.prom` | failing only if external-prefix normalization regresses | Metrics summary records external prefix queries, hits, and `prompt_tokens_external_kv_transfer` as measured. |
| `tests/fixtures/sglang_prefix_cache.prom` | failing until exact upstream request-level SGLang prefix metrics are known | SGLang prefix-cache group reports concrete hit/query fields, not only aggregate `cache_hit_rate`. |
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

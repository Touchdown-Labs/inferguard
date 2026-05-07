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

| Runtime | Surface | Status | Artifact name | Current parser or CLI entrypoint | Missing proof | Exact next command |
| --- | --- | --- | --- | --- | --- | --- |
| LMCache | Embedded / in-process Prometheus (`lmcache:*`, `lmcache_`) | partial | `engine_metrics_timeline.jsonl`, `metrics_summary.json`, `lmcache_compat_report.json`, optional `lmcache_metrics.prom`, `observability_coverage.json` when requested | `normalize_engine_sample("lmcache", ...)`, `parse_lmcache_prometheus`, `lmcache-compat`, `observability-coverage`, `collect-lmcache` | Live embedded fixture with launch/config, repeated-request store/retrieve evidence, and stale-connector failure case. | `inferguard observability-coverage --engine-metrics-file "$PACKET_DIR/vllm_embedded.prom" --output "$PACKET_DIR/vllm_embedded_coverage.json" --expect-lmcache-mode embedded` |
| LMCache | MP Prometheus (`lmcache_mp_*`) | supported | `lmcache_metrics.prom`, `engine_metrics_timeline.jsonl`, `metrics_summary.json`, `lmcache_compat_report.json`, `packet_manifest.json`, `observability_coverage.json` when requested | `parse_lmcache_prometheus`, `parse_lmcache_snapshot`, `normalize_engine_sample`, `build_compat_report`, `lmcache-compat`, `observability-coverage`, `collect-metrics`, `collect-lmcache` | Live L2-configured, nonzero lookup-token, and sampled throughput/lifecycle fixtures. | `inferguard lmcache-compat --lmcache-metrics-file "$PACKET_DIR/lmcache.prom" --output "$PACKET_DIR/lmcache_compat_report.json" --expect-lmcache-mode mp` |
| LMCache | MP HTTP status / health | partial | `lmcache_health.txt`, `lmcache_status.txt`, `lmcache_http_evidence.json`, `packet_manifest.json`, generic `launch/healthcheck.json` | `collect-lmcache`, `lmcache-compat --lmcache-http-evidence-file`, `observability-coverage --lmcache-http-evidence-file`, `parse_lmcache_http_payloads` | Live fixtures for health, status, threads, periodic threads, per-thread detail, and periodic thread health. | `inferguard collect-lmcache --output-dir "$PACKET_DIR" --lmcache-health-file "$PACKET_DIR/lmcache-health.json" --lmcache-status-file "$PACKET_DIR/lmcache-status.json"` |
| LMCache | Logs | partial | `engine.log`, `lmcache.log`, `lmcache_log_evidence.json`, `packet_manifest.json`, `bottleneck_diagnosis.json` | `parse_lmcache_logs`, `collect-lmcache --engine-log-file --lmcache-log-file`, `diagnose-bottleneck` | Mode-specific checks for zero-hit-after-warmup, hashseed mismatch, P2P failures, PD role mismatch, and MP store/retrieve lifecycle. | `inferguard collect-lmcache --output-dir "$PACKET_DIR/logs" --engine-log-file "$PACKET_DIR/vllm.log" --lmcache-log-file "$PACKET_DIR/lmcache.log"` |
| LMCache | OTel spans | partial | `lmcache_otel.jsonl`, `lmcache_otel_evidence.json`, `packet_manifest.json`, `lmcache_compat_report.json`, `observability_coverage.json` | `collect-lmcache --lmcache-otel-file`, `lmcache-compat --lmcache-otel-evidence-file`, `observability-coverage --lmcache-otel-evidence-file`, `parse_lmcache_otel_jsonl` | Real OTel collector export and tracing-enabled-without-spans detector. | `inferguard collect-lmcache --output-dir "$PACKET_DIR/otel" --lmcache-otel-file "$PACKET_DIR/otel/lmcache-otel.jsonl"` |
| LMCache | Trace recording `.lct` | partial | `lmcache_trace.lct`, `lmcache_trace_evidence.json`, `packet_manifest.json`, `lmcache_compat_report.json`, `observability_coverage.json` | `collect-lmcache --lmcache-trace-file`, `lmcache-compat --lmcache-trace-evidence-file`, `observability-coverage --lmcache-trace-evidence-file`, `parse_lmcache_trace_file` | Real `.lct` msgpack trace from `--trace-level storage`. | `inferguard collect-lmcache --output-dir "$PACKET_DIR/trace" --lmcache-trace-file "$PACKET_DIR/trace/lmcache-trace.lct"` |
| LMCache | CacheBlend metrics/spans | partial | `lmcache_metrics.prom`, `lmcache_otel.jsonl`, `lmcache_compat_report.json`, `observability_coverage.json`, `bottleneck_diagnosis.json` | `parse_lmcache_prometheus`, `parse_lmcache_otel_jsonl`, `lmcache-compat`, `observability-coverage`, `diagnose-bottleneck` | Compact fixtures from a real CacheBlend run and live CacheBlend packet. | `inferguard lmcache-compat --lmcache-metrics-file "$PACKET_DIR/cacheblend.prom" --output "$PACKET_DIR/cacheblend_report.json" --expect-lmcache-mode mp` |
| LMCache | Lookup-hash JSONL | partial | `lookup_hashes_*.jsonl`, `lmcache_lookup_hash_evidence.json`, `packet_manifest.json`, `lmcache_compat_report.json`, `bottleneck_diagnosis.json` | `parse_lmcache_lookup_hash_jsonl`, `collect-lmcache --lmcache-lookup-hash-path`, `diagnose-bottleneck` | Live lookup-hash packet and real rotation/config fields. | `inferguard collect-lmcache --output-dir "$PACKET_DIR/lookup-hash" --lmcache-lookup-hash-path "$PACKET_DIR/lookup-hashes"` |
| LMCache | Trace replay metadata | partial | `lmcache_trace_replay_evidence.json`, `packet_manifest.json`, `lmcache_compat_report.json`, `bottleneck_diagnosis.json` | `parse_lmcache_trace_replay_file`, `parse_lmcache_trace_replay_dir`, `collect-lmcache --lmcache-trace-replay-output` | Live replay proof tied to the same `.lct` trace and config digest. | `inferguard collect-lmcache --output-dir "$PACKET_DIR/trace-replay" --lmcache-trace-replay-output "$PACKET_DIR/trace-replay"` |
| LMCache | P2P / PD log evidence | partial | `lmcache_log_evidence.json`, `packet_manifest.json`, `bottleneck_diagnosis.json` | `parse_lmcache_logs`, `collect-lmcache --engine-log-file --lmcache-log-file`, `diagnose-bottleneck` | Metric/config correlation, connection-failure detectors, PD role/proxy/NIXL proof packets, and live two-engine P2P plus prefiller/decoder fixtures. | `inferguard collect-lmcache --output-dir "$PACKET_DIR/p2p" --engine-log-file "$PACKET_DIR/p2p/engine.log" --lmcache-log-file "$PACKET_DIR/p2p/lmcache.log"` |
| vLLM | Prometheus prefix cache | supported | `engine_metrics_timeline.jsonl`, `metrics_summary.json`, optional `raw_samples.jsonl`, `observability_coverage.json` | `_parse_vllm`, `normalize_engine_sample("vllm", ...)`, `observability-coverage`, `collect-metrics`, `disagg status` | Fixture where local prefix hits are nonzero and external prefix is absent. | `inferguard observability-coverage --engine-metrics-file "$PACKET_DIR/vllm.prom" --output "$PACKET_DIR/vllm_prefix_coverage.json"` |
| vLLM | Prometheus external prefix cache | supported | `engine_metrics_timeline.jsonl`, `metrics_summary.json`, `lmcache_compat_report.json`, `observability_coverage.json` | `_parse_vllm`, `normalize_engine_sample("vllm", ...)`, `build_compat_report`, `observability-coverage --external-cache-configured` | Live fixture with nonzero external prefix hits and external KV transfer prompt tokens. | `inferguard observability-coverage --engine-metrics-file "$PACKET_DIR/vllm.prom" --lmcache-metrics-file "$PACKET_DIR/lmcache.prom" --external-cache-configured --output "$PACKET_DIR/vllm_external_prefix_coverage.json"` |
| vLLM | Prometheus CPU offload metrics | supported | `engine_metrics_timeline.jsonl`, `metrics_summary.json`, `observability_coverage.json` | `_parse_vllm`, `normalize_engine_sample("vllm", ...)`, `observability-coverage --cpu-offload-configured` | Current-upstream KV-offload alias validation. | `inferguard observability-coverage --engine-metrics-file "$PACKET_DIR/vllm_cpu_offload.prom" --cpu-offload-configured --output "$PACKET_DIR/vllm_cpu_offload_coverage.json"` |
| SGLang | Prometheus prefix cache | partial | `engine_metrics_timeline.jsonl`, `metrics_summary.json`, `observability_coverage.json` | `normalize_engine_sample("sglang", ...)`, `_parse_sglang`, `observability-coverage --expected-engine sglang` | Request-level SGLang prefix hit/query fixture if upstream exposes one. | `inferguard observability-coverage --engine-metrics-file "$PACKET_DIR/sglang_prefix.prom" --expected-engine sglang --output "$PACKET_DIR/sglang_prefix_coverage.json"` |
| SGLang | Prometheus queue | supported | `engine_metrics_timeline.jsonl`, `metrics_summary.json`, `observability_coverage.json` | `_parse_sglang`, `normalize_engine_sample("sglang", ...)`, `collect-metrics`, `disagg status`, `observability-coverage --expected-engine sglang` | Overload fixture with nonzero queue and failure-classification test. | `inferguard observability-coverage --engine-metrics-file "$PACKET_DIR/sglang_queue.prom" --expected-engine sglang --output "$PACKET_DIR/sglang_queue_coverage.json"` |
| SGLang | Prometheus KV transfer, if present | supported | `engine_metrics_timeline.jsonl`, `metrics_summary.json`, `observability_coverage.json` | `_parse_sglang`, connector label detection on `sglang:kv_transfer_*`, `observability-coverage --disaggregated-or-external-cache` | Live SGLang deployments using Mooncake/NIXL labels. | `inferguard observability-coverage --engine-metrics-file "$PACKET_DIR/sglang_kv_transfer.prom" --expected-engine sglang --disaggregated-or-external-cache --output "$PACKET_DIR/sglang_kv_transfer_coverage.json"` |
| SGLang | Embedded LMCache evidence | partial | `engine_metrics_timeline.jsonl`, `metrics_summary.json`, `observability_coverage.json`, optional LMCache packet artifacts | `normalize_engine_sample("sglang", ...)`, `_parse_sglang`, LMCache embedded metric parser | Live SGLang `--enable-lmcache` fixture. | `inferguard observability-coverage --engine-metrics-file "$PACKET_DIR/sglang_lmcache.prom" --expected-engine sglang --output "$PACKET_DIR/sglang_lmcache_coverage.json" --expect-lmcache-mode embedded` |
| SGLang | LMCache MP evidence | missing | none | none yet | Current-mainline SGLang MP connector/launch contract plus live proof. | `inferguard observability-coverage --engine-metrics-file "$PACKET_DIR/sglang.prom" --lmcache-metrics-file "$PACKET_DIR/lmcache.prom" --expected-engine sglang --output "$PACKET_DIR/sglang_mp_candidate_coverage.json" --expect-lmcache-mode mp` |

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

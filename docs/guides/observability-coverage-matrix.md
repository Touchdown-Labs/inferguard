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
- `live_validated`: real runtime artifacts have been replayed through
  `collect-lmcache`, `lmcache-compat`, `observability-coverage`, and
  `diagnose-bottleneck`, imported as compact fixtures, and pinned by tests.

## Progress

The active upstream tracker is
`/Users/chen/Projects/Touchdown-Labs/docs/sdlc/195-2026-05-07-lmcache-vllm-inferguard-100-coverage-ssot.md`.
It supersedes docs 188/189/190. Original vLLM + LMCache + InferGuard CLI
coverage is release-ready after the I1 local docs/test gates and the final real
H100 smoke passed. Accepted runtime evidence covers Packet A-F MP, G1
diagnostics, H1 embedded vLLM, and H3 embedded CacheBlend/vLLM. The final H100
receipts are Packet B / LC1 at
`/Users/chen/Projects/inferguard/modal-out/pulls/20260510T230559Z` and Packet H3
at `/Users/chen/Projects/inferguard/modal-out/pulls/20260510T232009Z`. H2/SGLang,
Mooncake, P2P/PD expansion, and DLM/llm-d are paused backend-expansion lanes, not
blockers for the original vLLM + LMCache CLI finish line.

Coverage accounting is split deliberately:

| Scope | Current state | Evidence | Missing proof |
| --- | --- | --- | --- |
| Original vLLM + LMCache + InferGuard CLI | `release_ready` / 100/100 | accepted fixtures, local gates, final Packet B and H3 H100 receipts | none for original scope |
| LMCache MP observability with vLLM | `release_ready` | Packet A-F fixtures plus Packet B H100 receipt with `detected_mode=mp`, `failure_reasons=[]`, and required lifecycle/lookup/reuse families populated | none for original MP acceptance scope |
| embedded CacheBlend / vLLM | `live_validated` | Packet H3 H100 receipt with `detected_mode=embedded_cacheblend`, `cb.*` spans, and `lmcache_blend_*` metrics | none for H3 acceptance scope |
| continuous low-level GPU hardware telemetry | `not_proven` | H100 identity captured by `nvidia-smi`; application telemetry captured | DCGM/NVML sampler evidence for GPU util, HBM, NVLink, PCIe, and sustained power |

Keep accepted live fixtures pinned under `tests/fixtures/lmcache_live/` and run
the I1 local gate before updating release claims:

```bash
cd /Users/chen/Projects/inferguard
uv run --with pytest --with pytest-asyncio --with aiohttp --with msgpack pytest -q \
  tests/test_lmcache_metrics_adapter.py \
  tests/test_observability_coverage.py \
  tests/test_lmcache_mp_modal_packet_lab.py \
  tests/test_lmcache_packet.py \
  tests/test_collect_metrics.py \
  tests/test_diagnose_bottleneck.py \
  tests/test_lmcache_otel.py \
  tests/test_lmcache_trace.py \
  tests/test_lmcache_lookup_hash.py \
  tests/test_lmcache_live_fixtures.py \
  tests/test_lmcache_embedded_advanced_modal_packet_lab.py
uv run mkdocs build
```

Source refresh for the Worker Docs/CLI checklist on 2026-05-07 used:

- LMCache MP observability:
  <https://docs.lmcache.ai/mp/observability.html>
- LMCache MP HTTP API:
  <https://docs.lmcache.ai/mp/http_api.html>
- LMCache production metrics:
  <https://docs.lmcache.ai/production/observability/metrics.html>
- LMCache production vLLM metrics endpoint:
  <https://docs.lmcache.ai/production/observability/vllm_endpoint.html>
- LMCache trace recording/replay:
  <https://docs.lmcache.ai/mp/tracing_and_debugging.html>
- vLLM `LMCacheMPConnector`:
  <https://docs.vllm.ai/en/v0.20.1/api/vllm/distributed/kv_transfer/kv_connector/v1/lmcache_mp_connector/>

Source refresh for the SGLang backend-expansion lane on 2026-05-12 used LMCache
SGLang quickstart and KV-cache-events docs. The documented SGLang embedded launch
contract is `python -m sglang.launch_server --model-path <model> --host 0.0.0.0
--port 30000 --enable-lmcache` with `LMCACHE_CONFIG_FILE=<path>`. The documented
KV event path uses LMCache `enable_kv_events: true` plus SGLang
`--kv-events-config '{"publisher": "zmq", "topic": "kv-events"}'`. InferGuard
redacts raw token IDs and block hashes from normalized/report artifacts.

SGLang + LMCache embedded support is existing runtime support in LMCache/SGLang,
not an InferGuard feature and not an MP claim. InferGuard reports it separately
as `sglang_lmcache_embedded_support`: `source_backed` when launch/source evidence
is present, and only artifact-backed for a specific run when SGLang metrics plus
LMCache embedded metrics are captured. The source-backed contract is
`--enable-lmcache` plus `LMCACHE_CONFIG_FILE` or equivalent LMCache environment
configuration; LMCache's SGLang adapter owns the runtime lookup/retrieve/store
path. InferGuard now also emits `sglang_lmcache_version_provenance`, which records the specific source/version ledger for this claim: LMCache `f3bba133` (Yuwei An, 2025-06-23) for SGLang config/adapter introduction, SGLang `9a7ced4` (Yuwei An, 2025-09-06) for the `--enable-lmcache` launch surface, and LMCache PR #3002 (opened 2026-04-11, merged 2026-05-11) for env-only config validation. Current GitHub recon is recorded in
`docs/sdlc/sglang-lmcache-support-reconciliation-report-v0.1.md`.

SGLang + LMCache MP observability is tracked separately from embedded SGLang
LMCache. It is source-backed by open upstream PRs
<https://github.com/sgl-project/sglang/pull/24089> and
<https://github.com/LMCache/LMCache/pull/3166>, and fixture-tested in InferGuard
only. The PR-backed SGLang launch evidence is `--enable-lmcache` plus
`--lmcache-mp-host` and `--lmcache-mp-port`; InferGuard does not invent an MP
enable flag. This lane is not live validated, not merged upstream, not
performance validated, and not production support.

InferGuard is source-available under `BUSL-1.1`; parser support below is not a
hosted-service license grant or a performance/customer-readiness claim.

Status language for coverage accounting remains conservative: `supported` means
the parser or collector path exists and is fixture-tested, not that the lane is
100% done. A lane reaches customer-proof only after it is also
`live_validated` in the source-of-truth tracker.

## Matrix

| Runtime | Surface | Status | Artifact name | Current parser or CLI entrypoint | Missing proof | Exact next command |
| --- | --- | --- | --- | --- | --- | --- |
| LMCache | Embedded / in-process Prometheus (`lmcache:*`, `lmcache_`) | partial | `engine_metrics_timeline.jsonl`, `metrics_summary.json`, `lmcache_compat_report.json`, optional `lmcache_metrics.prom`, `observability_coverage.json` when requested | `normalize_engine_sample("lmcache", ...)`, `parse_lmcache_prometheus`, `lmcache-compat`, `observability-coverage`, `collect-lmcache` | Live embedded fixture with launch/config, repeated-request store/retrieve evidence, and stale-connector failure case. | `inferguard observability-coverage --engine-metrics-file "$PACKET_DIR/vllm_embedded.prom" --output "$PACKET_DIR/vllm_embedded_coverage.json" --expect-lmcache-mode embedded` |
| LMCache | MP Prometheus L0 allocation boundary from PR #3255 | live_validated | `lmcache_metrics.prom`, `lmcache_compat_report.json`, `observability_coverage.json`, optional `l0_block_boundary_events.jsonl` / `l0_block_boundary_evidence.json` | `parse_lmcache_prometheus`, `build_compat_report`, `observability-coverage`, boundary JSONL parser | Downstream Modal H100 Packet B proof accepted for PR3255 allocation/boundary observability; broader LMCache performance and vLLM-source-change claims are not applicable. | `inferguard observability-coverage --lmcache-metrics-file "$PACKET_DIR/lmcache_metrics_loaded.prom" --lmcache-l0-boundary-evidence-file "$PACKET_DIR/l0_block_boundary_evidence.json" --expect-lmcache-mode mp --output "$PACKET_DIR/observability_coverage.json"` |
| LMCache | MP Prometheus (`lmcache_mp_*`) | supported | `lmcache_metrics.prom`, `engine_metrics_timeline.jsonl`, `metrics_summary.json`, `lmcache_compat_report.json`, `packet_manifest.json`, `observability_coverage.json` when requested | `parse_lmcache_prometheus`, `parse_lmcache_snapshot`, `normalize_engine_sample`, `build_compat_report`, `lmcache-compat`, `observability-coverage`, `collect-metrics`, `collect-lmcache` | Live L2-configured, nonzero lookup-token, and sampled throughput/lifecycle fixtures. | `inferguard lmcache-compat --lmcache-metrics-file "$PACKET_DIR/lmcache.prom" --output "$PACKET_DIR/lmcache_compat_report.json" --expect-mode mp` |
| LMCache | MP HTTP status / health | partial | `lmcache_health.txt`, `lmcache_status.txt`, `lmcache_http_evidence.json`, `packet_manifest.json`, generic `launch/healthcheck.json` | `collect-lmcache`, `lmcache-compat --lmcache-http-evidence-file`, `observability-coverage --lmcache-http-evidence-file`, `parse_lmcache_http_payloads` | Live fixtures for health, status, threads, periodic threads, per-thread detail, and periodic thread health. | `inferguard collect-lmcache --output-dir "$PACKET_DIR" --lmcache-health-file "$PACKET_DIR/lmcache-health.json" --lmcache-status-file "$PACKET_DIR/lmcache-status.json"` |
| LMCache | Logs | partial | `engine.log`, `lmcache.log`, `lmcache_log_evidence.json`, `packet_manifest.json`, `bottleneck_diagnosis.json` | `parse_lmcache_logs`, `collect-lmcache --engine-log-file --lmcache-log-file`, `diagnose-bottleneck` | Mode-specific checks for zero-hit-after-warmup, hashseed mismatch, P2P failures, PD role mismatch, and MP store/retrieve lifecycle. | `inferguard collect-lmcache --output-dir "$PACKET_DIR/logs" --engine-log-file "$PACKET_DIR/vllm.log" --lmcache-log-file "$PACKET_DIR/lmcache.log"` |
| LMCache | OTel spans | partial | `lmcache_otel.jsonl`, `lmcache_otel_evidence.json`, `packet_manifest.json`, `lmcache_compat_report.json`, `observability_coverage.json` | `collect-lmcache --lmcache-otel-file`, `lmcache-compat --lmcache-otel-evidence-file`, `observability-coverage --lmcache-otel-evidence-file`, `parse_lmcache_otel_jsonl` | Real OTel collector export and tracing-enabled-without-spans detector. | `inferguard collect-lmcache --output-dir "$PACKET_DIR/otel" --lmcache-otel-file "$PACKET_DIR/otel/lmcache-otel.jsonl"` |
| LMCache | Trace recording `.lct` | partial | `lmcache_trace.lct`, `lmcache_trace_evidence.json`, `packet_manifest.json`, `lmcache_compat_report.json`, `observability_coverage.json` | `collect-lmcache --lmcache-trace-file`, `lmcache-compat --lmcache-trace-evidence-file`, `observability-coverage --lmcache-trace-evidence-file`, `parse_lmcache_trace_file` | Real `.lct` msgpack trace from `--trace-level storage`. | `inferguard collect-lmcache --output-dir "$PACKET_DIR/trace" --lmcache-trace-file "$PACKET_DIR/trace/lmcache-trace.lct"` |
| LMCache | CacheBlend metrics/spans | live_validated | `lmcache_blend_metrics.prom`, `lmcache_otel.jsonl`, `lmcache_compat_report.json`, `observability_coverage.json`, `bottleneck_diagnosis.json` | `parse_lmcache_prometheus`, `parse_lmcache_otel_jsonl`, `lmcache-compat`, `observability-coverage`, `diagnose-bottleneck` | H3 embedded CacheBlend/vLLM fixture is accepted; P2P/PD remain backend expansion. | `inferguard lmcache-compat --lmcache-metrics-file "$PACKET_DIR/lmcache_blend_metrics.prom" --expect-mode auto --fail-on missing-required --json` |
| LMCache | Lookup-hash JSONL | partial | `lookup_hashes_*.jsonl`, `lmcache_lookup_hash_evidence.json`, `packet_manifest.json`, `lmcache_compat_report.json`, `bottleneck_diagnosis.json` | `parse_lmcache_lookup_hash_jsonl`, `collect-lmcache --lmcache-lookup-hash-path`, `diagnose-bottleneck` | Live lookup-hash packet and real rotation/config fields. | `inferguard collect-lmcache --output-dir "$PACKET_DIR/lookup-hash" --lmcache-lookup-hash-path "$PACKET_DIR/lookup-hashes"` |
| LMCache | Trace replay metadata | partial | `lmcache_trace_replay_evidence.json`, `packet_manifest.json`, `lmcache_compat_report.json`, `bottleneck_diagnosis.json` | `parse_lmcache_trace_replay_file`, `parse_lmcache_trace_replay_dir`, `collect-lmcache --lmcache-trace-replay-output` | Live replay proof tied to the same `.lct` trace and config digest. | `inferguard collect-lmcache --output-dir "$PACKET_DIR/trace-replay" --lmcache-trace-replay-output "$PACKET_DIR/trace-replay"` |
| LMCache | P2P / PD log evidence | partial | `lmcache_log_evidence.json`, `packet_manifest.json`, `bottleneck_diagnosis.json` | `parse_lmcache_logs`, `collect-lmcache --engine-log-file --lmcache-log-file`, `diagnose-bottleneck` | Metric/config correlation, connection-failure detectors, PD role/proxy/NIXL proof packets, and live two-engine P2P plus prefiller/decoder fixtures. | `inferguard collect-lmcache --output-dir "$PACKET_DIR/p2p" --engine-log-file "$PACKET_DIR/p2p/engine.log" --lmcache-log-file "$PACKET_DIR/p2p/lmcache.log"` |
| vLLM | Prometheus prefix cache | supported | `engine_metrics_timeline.jsonl`, `metrics_summary.json`, optional `raw_samples.jsonl`, `observability_coverage.json` | `_parse_vllm`, `normalize_engine_sample("vllm", ...)`, `observability-coverage`, `collect-metrics`, `disagg status` | Fixture where local prefix hits are nonzero and external prefix is absent. | `inferguard observability-coverage --engine-metrics-file "$PACKET_DIR/vllm.prom" --output "$PACKET_DIR/vllm_prefix_coverage.json"` |
| vLLM | Prometheus external prefix cache | supported | `engine_metrics_timeline.jsonl`, `metrics_summary.json`, `lmcache_compat_report.json`, `observability_coverage.json` | `_parse_vllm`, `normalize_engine_sample("vllm", ...)`, `build_compat_report`, `observability-coverage --external-cache-configured` | Live fixture with nonzero external prefix hits and external KV transfer prompt tokens. | `inferguard observability-coverage --engine-metrics-file "$PACKET_DIR/vllm.prom" --lmcache-metrics-file "$PACKET_DIR/lmcache.prom" --external-cache-configured --output "$PACKET_DIR/vllm_external_prefix_coverage.json"` |
| vLLM | Prometheus CPU offload metrics | supported | `engine_metrics_timeline.jsonl`, `metrics_summary.json`, `observability_coverage.json` | `_parse_vllm`, `normalize_engine_sample("vllm", ...)`, `observability-coverage --cpu-offload-configured` | Current-upstream KV-offload alias validation. | `inferguard observability-coverage --engine-metrics-file "$PACKET_DIR/vllm_cpu_offload.prom" --cpu-offload-configured --output "$PACKET_DIR/vllm_cpu_offload_coverage.json"` |
| Cross-layer | KV cache CPU↔GPU offload summary | partial | `observability_coverage.json` field `kv_cache_offload` | `observability-coverage` summarizes native vLLM CPU offload bytes/time and LMCache MP L0↔L1 throughput separately | Live long-context chat/tool-agent packet with nonzero LMCache `lmcache_mp_l0_l1_*_throughput_gbs` and vLLM latency/prefix-cache metrics. | `inferguard observability-coverage --engine-metrics-file "$PACKET_DIR/vllm.prom" --lmcache-metrics-file "$PACKET_DIR/lmcache.prom" --external-cache-configured --output "$PACKET_DIR/kv_offload_coverage.json"` |
| SGLang | Prometheus native `/metrics` queue/cache/tokens/latency | supported | `engine_metrics_timeline.jsonl`, `metrics_summary.json`, `observability_coverage.json` | `normalize_engine_sample("sglang", ...)`, `_parse_sglang`, `observability-coverage --expected-engine sglang` | Fixture-tested parser support; live SGLang + LMCache validation remains separate. | `inferguard observability-coverage --engine-metrics-file "$PACKET_DIR/sglang.prom" --expected-engine sglang --output "$PACKET_DIR/sglang_coverage.json"` |
| SGLang | Prometheus prefix cache | partial | `engine_metrics_timeline.jsonl`, `metrics_summary.json`, `observability_coverage.json` | `normalize_engine_sample("sglang", ...)`, `_parse_sglang`, `observability-coverage --expected-engine sglang` | Request-level SGLang prefix hit/query fixture if upstream exposes one. | `inferguard observability-coverage --engine-metrics-file "$PACKET_DIR/sglang_prefix.prom" --expected-engine sglang --output "$PACKET_DIR/sglang_prefix_coverage.json"` |
| SGLang | Prometheus queue | supported | `engine_metrics_timeline.jsonl`, `metrics_summary.json`, `observability_coverage.json` | `_parse_sglang`, `normalize_engine_sample("sglang", ...)`, `collect-metrics`, `disagg status`, `observability-coverage --expected-engine sglang` | Overload fixture with nonzero queue and failure-classification test. | `inferguard observability-coverage --engine-metrics-file "$PACKET_DIR/sglang_queue.prom" --expected-engine sglang --output "$PACKET_DIR/sglang_queue_coverage.json"` |
| SGLang | Prometheus KV transfer, if present | supported | `engine_metrics_timeline.jsonl`, `metrics_summary.json`, `observability_coverage.json` | `_parse_sglang`, connector label detection on `sglang:kv_transfer_*`, `observability-coverage --disaggregated-or-external-cache` | Live SGLang deployments using Mooncake/NIXL labels. | `inferguard observability-coverage --engine-metrics-file "$PACKET_DIR/sglang_kv_transfer.prom" --expected-engine sglang --disaggregated-or-external-cache --output "$PACKET_DIR/sglang_kv_transfer_coverage.json"` |
| SGLang | Embedded LMCache evidence | partial | `engine_metrics_timeline.jsonl`, `metrics_summary.json`, `observability_coverage.json` field `sglang_lmcache_embedded_support`, optional LMCache packet artifacts | `normalize_engine_sample("sglang", ...)`, `_parse_sglang`, LMCache embedded metric parser, `launch-engine` argv support for documented `--enable-lmcache`; `observability-coverage` separates embedded support from MP observability. | Source-backed and fixture-tested for documented embedded mode; pending live validation. Demo `chunk_size: 8` values from docs remain demo-only, not recommended production defaults. | `inferguard observability-coverage --engine-metrics-file "$PACKET_DIR/sglang_lmcache.prom" --expected-engine sglang --output "$PACKET_DIR/sglang_lmcache_coverage.json" --expect-lmcache-mode embedded` |
| SGLang | KV events via LMCache `enable_kv_events` | partial | `sglang_kv_events_evidence`, `observability_coverage.json` | `observability-coverage --sglang-kv-events-evidence-file` redacts raw `token_ids`, `block_hashes`, and parent hashes while retaining counts. | Source-backed and parser-tested; pending live SGLang/LMCache KV-event capture. | `inferguard observability-coverage --engine-metrics-file "$PACKET_DIR/sglang.prom" --sglang-kv-events-evidence-file "$PACKET_DIR/sglang-kv-events.jsonl" --expected-engine sglang --output "$PACKET_DIR/sglang_kv_events_coverage.json"` |
| SGLang | LMCache MP observability evidence | partial | `launch/command.json`, `observability_coverage.json`, `lmcache_compat_report.json`, `lmcache_metrics.prom` | `launch-engine` argv support for PR-backed `--enable-lmcache --lmcache-mp-host --lmcache-mp-port`; `observability-coverage` emits `sglang_lmcache_mp_observability` with `source_backed_fixture_tested` support status when SGLang metrics, LMCache MP metrics, and MP launch/source evidence are present. | Live SGLang + LMCache MP GPU run artifacts; upstream PRs #24089/#3166 remain open and unmerged, so no production/performance claim. | `inferguard observability-coverage --engine-metrics-file "$PACKET_DIR/sglang.prom" --lmcache-metrics-file "$PACKET_DIR/lmcache.prom" --expected-engine sglang --output "$PACKET_DIR/sglang_mp_candidate_coverage.json" --expect-lmcache-mode mp` |

## 100% Checklist Matrix

This is the docs/CLI coverage checklist that must be green before the score can
reach 100/100. The states intentionally use the stricter SDLC taxonomy.

| Lane | Current state | Required evidence | Missing proof | Exact next command |
| --- | --- | --- | --- | --- |
| MP architecture | release_ready | `LMCacheMPConnector` launch/config, standalone `lmcache server`, ZMQ config, vLLM `/metrics`, LMCache HTTP and `/metrics`, final Packet B real-H100 receipt | No missing proof for the original MP acceptance scope; keep fixtures and Packet B receipt auditable. | `cd /Users/chen/Projects/inferguard && uv run pytest -q tests/test_lmcache_live_fixtures.py tests/test_lmcache_mp_modal_packet_lab.py` |
| MP HTTP safe endpoints | parser_only / fixture_backed mixed | `/`, `/api/healthcheck`, `/api/status`, `/conf`, `/version`, `/lmc_version`, `/commit_id`, `/api/quota`, `/threads`, `/periodic-threads`, `/periodic-threads/{thread_name}`, `/periodic-threads-health` | Live endpoint packet; `/env` and `/loglevel` opt-in redaction/safety policy. | `curl -fsS "$LMCACHE_HTTP/api/status" -o "$PACKET_DIR/lmcache-status.json"` |
| MP destructive endpoint guard | destructive_skipped | `POST /api/clear-cache`, `POST /metrics/reset`, quota mutation routes recorded but not called | Packet manifest row proving skipped status. | `printf '%s\n' 'POST /api/clear-cache destructive_skipped' >> "$PACKET_DIR/skipped_endpoints.txt"` |
| MP Prometheus metric families | fixture_backed / parser_only mixed | StorageManager, L1, L1 failures, L1 lifecycle, real reuse, L2, L2 failures, lookup hit rate, L0 lifecycle, L0-L1 throughput, L1-L2 throughput, engine counter, observable gauges, EventBus, CacheBlend | Packet A is accepted for the L1-only MP baseline; live nonzero lookup, L2, sampled lifecycle/throughput, EventBus clean/failure, and CacheBlend packets remain. | `inferguard lmcache-compat --lmcache-metrics-file "$PACKET_DIR/lmcache.prom" --output "$PACKET_DIR/lmcache_compat_report.json" --expect-mode mp` |
| Embedded production metric families | fixture_backed / parser_only mixed | Core request, token, hit rate, performance/latency, profiling, cache usage/lifecycle, remote backend/network, local CPU backend, memory management, P2P, health/internal, chunk statistics | Live embedded vLLM and SGLang fixtures with backend/P2P/chunk-stat surfaces. | `inferguard lmcache-compat --lmcache-metrics-file "$PACKET_DIR/embedded_lmcache.prom" --output "$PACKET_DIR/embedded_report.json" --expect-mode embedded` |
| Trace recording `.lct` | fixture_backed | `.lct` file from `--trace-level storage`, trace header, storage operation records | Live `.lct` from the same Packet A run. | `inferguard collect-lmcache --output-dir "$PACKET_DIR/trace" --lmcache-trace-file "$PACKET_DIR/trace/lmcache-trace.lct"` |
| Trace replay metadata | fixture_backed | `lmcache trace info`, replay JSON, replay JSONL, replay CSV, config digest comparison | Live replay output tied to same `.lct`. | `inferguard collect-lmcache --output-dir "$PACKET_DIR/trace-replay" --lmcache-trace-replay-output "$PACKET_DIR/trace-replay"` |
| OTel spans | fixture_backed | `mp.store`, `mp.retrieve`, `mp.lookup_prefetch`, root `request`, CacheBlend `cb.*` spans | Real collector export, not hand-authored JSONL. | `inferguard collect-lmcache --output-dir "$PACKET_DIR/otel" --lmcache-otel-file "$PACKET_DIR/otel/lmcache-otel.jsonl"` |
| Logs | fixture_backed structurally | store/retrieve/prefetch/startup, P2P, PD, hashseed, stale connector, lifecycle lines | Live MP, embedded, P2P, and PD logs converted to compact fixtures. | `inferguard collect-lmcache --output-dir "$PACKET_DIR/logs" --engine-log-file "$PACKET_DIR/vllm.log" --lmcache-log-file "$PACKET_DIR/lmcache.log"` |
| Lookup-hash JSONL | fixture_backed | redacted hashes, request/model/chunk metadata, rotation/config evidence | Live lookup-hash directory from Packet A. | `inferguard collect-lmcache --output-dir "$PACKET_DIR/lookup-hash" --lmcache-lookup-hash-path "$PACKET_DIR/lookup-hashes"` |
| P2P and PD | parser_only | P2P transfer metrics/logs, peer evidence, PD role/config/proxy/NIXL logs, request profile | Live two-engine P2P and 1p1d PD packets. | `inferguard collect-lmcache --output-dir "$PACKET_DIR/pd" --engine-log-file "$PACKET_DIR/pd/engine.log" --lmcache-log-file "$PACKET_DIR/pd/lmcache.log"` |
| Diagnostics | missing / fixture_backed mixed | mode-aware findings for hit rate, cache salt, L1/L2 pressure, EventBus loss, trace gaps, CacheBlend, P2P, PD, stale connector | Calibrated thresholds from live packets. | `inferguard diagnose-bottleneck --job-dir "$JOB_DIR" --output-dir "$PACKET_DIR/diagnose-bottleneck"` |
| Release readiness | release_ready | docs, CLI reference, fixture tests, docs build, release notes, rollback notes, upstream question log | Keep local docs/test receipts attached to the release note. | `uv run mkdocs build` |

## Metric Family Closeout

| Source | Family coverage required | Current state | Missing proof | Exact next command |
| --- | --- | --- | --- | --- |
| LMCache MP observability | StorageManager, L1, lifecycle, real reuse, L2, lookup, L0, throughput, engine, gauges | release_ready for original vLLM+LMCache CLI MP acceptance; backend-expansion surfaces remain separate | No missing proof for original MP acceptance; separate L2/EventBus/failure/p2p expansion packets are optional backend-expansion work. | `inferguard observability-coverage --lmcache-metrics-file "$PACKET_DIR/lmcache.prom" --output "$PACKET_DIR/observability_coverage.json" --expect-lmcache-mode mp` |
| LMCache MP source additions | EventBus, L1 allocation/read failure, L2 prefetch failure, CacheBlend counters | fixture_backed | Clean/failure EventBus, L1/L2 failure, and CacheBlend live packets. | `inferguard lmcache-compat --lmcache-metrics-file "$PACKET_DIR/lmcache_eventbus.prom" --output "$PACKET_DIR/eventbus_report.json" --expect-mode mp` |
| LMCache production metrics | Core request, token, hit rate, performance/latency, profiling, cache usage/lifecycle, remote/backend/network, local CPU, memory, P2P, health/internal, chunk statistics | fixture_backed / parser_only mixed | Live embedded and backend/P2P/chunk-stat fixtures. | `inferguard observability-coverage --engine-metrics-file "$PACKET_DIR/vllm_embedded.prom" --output "$PACKET_DIR/vllm_embedded_coverage.json" --expect-lmcache-mode embedded` |
| vLLM bridge | local prefix, external prefix, prompt-token source, KV CPU offload caveat, connector identity | release_ready for original vLLM+LMCache CLI bridge | Packet B H100 proves the vLLM + LMCache MP connector path for the acceptance scope; native vLLM CPU offload remains a caveat, not LMCache proof. | `inferguard observability-coverage --engine-metrics-file "$PACKET_DIR/vllm.prom" --lmcache-metrics-file "$PACKET_DIR/lmcache.prom" --external-cache-configured --output "$PACKET_DIR/vllm_mp_coverage.json"` |
| SGLang bridge | queue/cache/HiCache/KV-transfer plus embedded LMCache adapter evidence and MP observability candidate classification | partial | Live SGLang `--enable-lmcache`; live SGLang + LMCache MP artifacts for the PR #24089/#3166 host/port path before any `live_validated` claim. | `inferguard observability-coverage --engine-metrics-file "$PACKET_DIR/sglang_lmcache.prom" --expected-engine sglang --output "$PACKET_DIR/sglang_lmcache_coverage.json" --expect-lmcache-mode embedded` |

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
| `tests/fixtures/lmcache_live/packet_a_missing_prometheus/` with `tests/test_lmcache_diagnostic_cli.py` | Non-scoreable Packet A failure mode; `lmcache-compat`, `observability-coverage`, `collect-lmcache`, and `diagnose-bottleneck` expose missing B1 Prometheus families without moving score | passing |
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
  tests/test_lmcache_diagnostic_cli.py \
  tests/test_observability_coverage.py \
  tests/test_launch_engine_lmcache.py
```

Run CLI reference generation or broader docs validation separately if nav,
command names, or public help text changes.

# LMCache Coverage Plan

This is the working tracker for getting InferGuard to full LMCache observability
coverage. "Full coverage" means InferGuard can collect, normalize, report, and
diagnose every LMCache signal class that matters for Touchdown AI Spend Recovery,
with real fixtures from live runs.

It does not mean every optional metric must be non-zero in every run. It means
InferGuard can tell the operator which LMCache mode is running, which evidence is
present, which evidence is missing, and what that implies.

## Current State

Latest pushed InferGuard commit:

- `edccffd feat: add LMCache evidence coverage`

## Progress Scoreboard

Current LMCache coverage: **48 / 100 points complete**.

This score is intentionally conservative. Parser support without real live
fixtures counts as partial progress, not complete support. A surface only gets
full credit when InferGuard has code, tests, real artifacts, and user-facing
diagnosis or reporting.

| Workstream | Weight | Done | Status | What is complete | What is still needed |
| --- | ---: | ---: | --- | --- | --- |
| LMCache MP Prometheus coverage | 20 | 14 | partial | Parses and reports documented MP metric families; supports mode detection, L1, L2, lookup, lifecycle, throughput, gauges, EventBus families | Add live L2 fixture, live nonzero lookup-token fixture, and sampled throughput/lifecycle fixture |
| Embedded / in-process LMCache metrics | 12 | 7 | partial | Parses `lmcache:*` and `lmcache_*`; added production request/token/health/remote/P2P/chunk aliases; preserves unknown metrics | Add live embedded fixture and stale connector tests |
| HTTP health/status evidence | 8 | 5 | partial | Parses saved LMCache MP health/status evidence; included in packet, compat, and coverage reports | Add live HTTP fixtures for healthy, unhealthy, unreachable, and richer `/api/status` payloads |
| Trace recording `.lct` evidence | 8 | 4 | partial | Captures and summarizes `.lct`-style length-prefixed records; handles malformed traces | Validate against real LMCache `.lct` msgpack trace from `--trace-level storage` |
| OTel span evidence | 8 | 4 | partial | Parses JSONL spans for `mp.store`, `mp.retrieve`, `mp.lookup_prefetch`; included in reports | Add real OTel export fixture and tracing-enabled/no-spans detector |
| Log evidence | 8 | 3 | partial | Existing conservative LMCache log parsing exists | Expand MP lifecycle, hash-seed, P2P, PD, and zero-hit-after-warmup log detectors |
| Diagnosis rules | 16 | 2 | early | Compatibility/coverage can report missing families and evidence gaps | Add LMCache-specific `diagnose-bottleneck` detectors with thresholds and recommendations |
| Live golden fixtures | 10 | 3 | partial | Modal real-shaped MP metric slice exists; synthetic tests cover new evidence parsers | Capture clean full MP packet, embedded packet, L2 packet, OTel packet, `.lct` packet |
| vLLM / SGLang bridge | 6 | 4 | partial | vLLM prefix/external/CPU-offload and SGLang queue/HiCache/KV-transfer parsing exists | Add live vLLM+LMCache MP connector fixture and SGLang external-cache fixture |
| Docs / release readiness | 4 | 2 | partial | Coverage plan exists and is linked in docs nav | Update existing LMCache docs to reflect new HTTP/trace/OTel support and refresh CLI reference |

Percent by category:

- **Collection/parsing:** about **65%** complete.
- **Compatibility/coverage reporting:** about **70%** complete.
- **Real live validation:** about **30%** complete.
- **Actionable diagnostics:** about **15%** complete.
- **Public docs/release readiness:** about **45%** complete.

The next meaningful milestone is **60 / 100**. To reach it, finish:

1. A clean live LMCache MP packet with metrics, HTTP, logs, and summary output.
2. Golden fixture tests from that packet.
3. First detector pack for missing lookup counters, zero hit rate, cache salt,
   EventBus observability, and tracing artifacts.

What shipped before `edccffd`:

- LMCache MP Prometheus compatibility reporting for `lmcache_mp_*`.
- Embedded/in-process LMCache metric normalization for `lmcache:*` and
  `lmcache_*`.
- `collect-lmcache` evidence packet basics.
- `lmcache-compat` compatibility reports.
- `observability-coverage` reports across LMCache, vLLM, and SGLang.
- MP coverage reporting for StorageManager, lookup tokens, L1, L2, lifecycle,
  throughput, gauges, and EventBus families.

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

## Definition Of 100 Percent

InferGuard reaches "100 percent LMCache coverage" when the rows below are all
`done` with real fixture evidence.

| Area | Required capability | Status |
| --- | --- | --- |
| Mode detection | Distinguish MP, embedded, P2P candidate, disaggregated-prefill candidate, and controller-only packets | partial |
| MP Prometheus | Parse/report all documented `lmcache_mp_*` families | partial |
| Embedded Prometheus | Parse/report production `lmcache:*` and exporter-normalized `lmcache_*` families | partial |
| HTTP API | Parse health/status evidence and explain unhealthy/unreachable states | partial |
| Trace recording | Capture and summarize `.lct` storage trace artifacts | partial |
| OTel tracing | Capture and summarize MP store/retrieve/lookup spans | partial |
| Logs | Parse MP, embedded, P2P, and PD operational logs into structured evidence | partial |
| Diagnostics | Convert evidence into specific findings, not just coverage rows | missing |
| Live fixtures | Golden artifacts from real LMCache runs for each supported mode | partial |
| vLLM bridge | Verify vLLM connector metrics line up with LMCache MP evidence | partial |
| SGLang bridge | Verify SGLang + external cache/LMCache-adjacent evidence where applicable | partial |
| Documentation | User-facing docs match the current CLI and support level | partial |

## Phase 1: Lock The Live MP Baseline

Goal: prove InferGuard can inspect one real LMCache MP run end to end.

- [x] Add MP metric compatibility report.
- [x] Add MP evidence packet collection.
- [x] Add HTTP, trace, and OTel evidence inputs.
- [ ] Run a clean LMCache MP lab and save artifacts:
  - [ ] vLLM `/metrics`.
  - [ ] LMCache MP `/metrics`.
  - [ ] LMCache `/api/healthcheck`.
  - [ ] LMCache `/api/status`.
  - [ ] vLLM logs.
  - [ ] LMCache logs.
  - [ ] `.lct` trace when `--trace-level storage` is enabled.
  - [ ] OTel JSONL or exported spans when tracing is enabled.
- [ ] Add those artifacts as golden fixtures or compressed fixture slices.
- [ ] Add tests that prove the live packet reports:
  - [ ] detected mode is `mp`;
  - [ ] required MP counters are present;
  - [ ] sampled families are classified separately from always-counted counters;
  - [ ] L2 families are `not_applicable` unless L2 is configured.

Acceptance criteria:

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
  - [ ] old `LMCacheConnector` is flagged as stale unless explicitly pinned.

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
  - [ ] Capture live SGLang external-cache fixture.
  - [ ] Confirm whether SGLang exposes request-level prefix hit/query counters.
  - [ ] Add SGLang-specific queue and KV transfer diagnostics.

Acceptance criteria:

- A customer packet can answer: "Is the engine using the cache path we think it
  is using, and is that path helping cost per useful task?"

## Phase 6: Docs, CLI, And Release

Goal: make the coverage usable by engineers who were not in this session.

- [ ] Update `docs/guides/lmcache-compatibility.md` to match current support:
  - [ ] HTTP evidence is no longer "raw only";
  - [ ] `.lct` evidence is no longer "missing";
  - [ ] OTel evidence is no longer "missing";
  - [ ] detector gaps remain explicit.
- [ ] Update `docs/guides/observability-coverage-matrix.md`.
- [ ] Update `docs/reference/cli.md` after CLI help changes.
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

1. Capture a clean live MP fixture from Modal or local H100.
2. Add the live fixture slices to tests.
3. Add the first detector pack:
   - missing lookup counters;
   - zero hit rate after replay;
   - missing cache salt;
   - EventBus tail-drop observability gap;
   - trace enabled without spans;
   - trace recording enabled without `.lct`.
4. Update the two existing LMCache docs so they no longer lag the code.
5. Send Kuntai a concrete question backed by the fixture.

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

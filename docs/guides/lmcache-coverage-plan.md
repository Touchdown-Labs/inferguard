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

- InferGuard tracker commit used for this score: `7ba414c`.
- Latest InferGuard implementation commit included in the score:
  `edccffd feat: add LMCache evidence coverage`.
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

## Progress Scoreboard

Current LMCache coverage: **48 / 100 points complete**.

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
| LMCache MP Prometheus coverage | 20 | 14 | partial | Official MP Observability doc plus `lmcache/v1/mp_observability/subscribers/metrics/` | Parses and reports documented MP metric families; supports mode detection, L1, L2, lookup, lifecycle, throughput, gauges, EventBus families | Add live L2 fixture, live nonzero lookup-token fixture, sampled throughput/lifecycle fixture, and source-discovered L1/L2 failure counters |
| Embedded / in-process LMCache metrics | 12 | 7 | partial | InferGuard aliases plus LMCache single-process `lmcache.` namespace guidance | Parses `lmcache:*` and `lmcache_*`; added production request/token/health/remote/P2P/chunk aliases; preserves unknown metrics | Add live embedded fixture and stale connector tests |
| HTTP API evidence | 8 | 5 | partial | `docs/source/mp/http_api.rst` and public HTTP API docs | Parses saved LMCache MP health/status evidence; included in packet, compat, and coverage reports | Add live fixtures for `/api/healthcheck`, `/api/status`, `/threads`, `/periodic-threads`, `/periodic-threads/{thread_name}`, and `/periodic-threads-health` |
| Trace recording `.lct` evidence | 8 | 4 | partial | MP Observability and Tracing/Debugging docs; `lmcache/v1/mp_observability/trace/` | Captures and summarizes `.lct`-style length-prefixed records; handles malformed traces | Validate against real LMCache `.lct` msgpack trace from `--trace-level storage` and add replay-summary checks |
| OTel span evidence | 8 | 4 | partial | MP Observability tracing section and Grafana dashboard span names | Parses JSONL spans for `mp.store`, `mp.retrieve`, `mp.lookup_prefetch`; included in reports | Add real OTel export fixture and tracing-enabled/no-spans detector |
| Log evidence | 8 | 3 | partial | MP logging docs and existing InferGuard log parser | Existing conservative LMCache log parsing exists | Expand MP lifecycle, hash-seed, P2P, PD, and zero-hit-after-warmup log detectors |
| Diagnosis rules | 16 | 2 | early | InferGuard `diagnose-bottleneck` behavior and Touchdown playbook needs | Compatibility/coverage can report missing families and evidence gaps | Add LMCache-specific detectors with thresholds, evidence, and recommendations |
| Live golden fixtures | 10 | 3 | partial | Existing Modal real-shaped slice plus synthetic tests | Modal real-shaped MP metric slice exists; synthetic tests cover new evidence parsers | Capture clean full MP packet, embedded packet, L2 packet, OTel packet, and `.lct` packet |
| vLLM / SGLang bridge | 6 | 4 | partial | InferGuard vLLM/SGLang parsers and LMCache connector docs/source | vLLM prefix/external/CPU-offload and SGLang queue/HiCache/KV-transfer parsing exists | Add live vLLM+LMCache MP connector fixture and SGLang external-cache fixture |
| Docs / release readiness | 4 | 2 | partial | InferGuard docs and CLI reference | Coverage plan exists and is linked in docs nav | Update existing LMCache docs to reflect new HTTP/trace/OTel support and refresh CLI reference |

### Detailed Ledger: LMCache MP Prometheus Coverage

The **14 / 20** MP Prometheus score is based on the official MP Observability
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
| EventBus self-metrics and L1/L2 failure counters | 1 | 0.5 | LMCache source | EventBus self-metrics parsed; failure counters not yet parsed | Add `l1_allocation_failure`, `l1_read_failure`, and `l2_prefetch_failure` aliases/tests |
| Real MP fixture coverage | 2 | 0.5 | Modal real-shaped slice | Real-shaped MP scrape exists | Clean full fixture with metrics, HTTP, logs, optional trace/OTel |
| Diagnostic mapping | 2 | 0.5 | InferGuard report behavior | Missing-family reporting exists | LMCache-specific detector pack |

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

### RepoPrompt Index Procedure

When refreshing this score, do not use a stale broad RepoPrompt selection. Build
an explicit LMCache MP observability selection with:

```bash
rp-cli -w 10 -e 'call manage_selection {"op":"set","paths":["docs/source/mp/observability.rst","docs/source/mp/http_api.rst","docs/source/mp/configuration.rst","docs/source/mp/tracing_and_debugging.rst","docs/source/mp/architecture.rst","lmcache/v1/mp_observability","tests/v1/mp_observability","examples/observability/grafana/provisioning/dashboards/lmcache.json"],"mode":"full","view":"files","strict":true}'
rp-cli -w 10 -e 'context --tree --files'
```

Then copy the selected source list and LMCache `upstream/dev` commit into the
source manifest above before changing score values.

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
  - [ ] LMCache `/threads`.
  - [ ] LMCache `/periodic-threads`.
  - [ ] LMCache `/periodic-threads-health`.
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

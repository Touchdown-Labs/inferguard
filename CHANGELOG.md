# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Added source-backed, fixture-tested SGLang backend-expansion support for native metrics, documented embedded LMCache launch flags, and redacted KV-event evidence parsing. SGLang embedded LMCache and KV events remain pending live validation.
- Added source-backed, fixture-tested SGLang + LMCache MP observability classification and launch-command plumbing for the open PR-backed `--enable-lmcache`, `--lmcache-mp-host`, and `--lmcache-mp-port` path. SGLang LMCache MP remains pending live validation, not merged upstream, not performance validated, and not production support.

## [0.7.4] - 2026-05-11

### Added

- Added downstream reporting support for LMCache PR #3255 L0 allocation counters, including allocation record and allocated-block totals.
- Added ingestion and reporting for redacted L0 boundary JSONL evidence without recording raw tokens or raw block IDs.

### Docs

- Recorded Modal H100 downstream proof for vLLM + LMCache PR3255 source plus updated InferGuard CLI.
- Documented release scope boundaries: no vLLM source changes, no performance-improvement claim, and full LMCache coverage remains evidence-gated rather than claimed complete.
- Closed I1 release-readiness documentation for original vLLM + LMCache +
  InferGuard CLI coverage: refreshed CLI references for accepted MP Packet A-F,
  G1 diagnostics, H1 embedded vLLM, and H3 embedded CacheBlend/vLLM; added
  rollback guidance for private vLLM/LMCache overlays and accepted fixture
  rollback; and kept H2/SGLang, Mooncake, P2P/PD, and DLM/llm-d paused as
  backend-expansion lanes outside the active release finish line.

## [0.7.3] - 2026-05-08

### Changed

- Relicensed InferGuard from Apache-2.0 to Business Source License 1.1 (`BUSL-1.1`) with Apache-2.0 as the Change License.
- Added a BSL Additional Use Grant that permits use in a team's own repos, CI/CD, staging, internal tools, and internal production inference-diagnostics workflows, while reserving paid/hosted competing commercial offerings for separate commercial licensing.
- Updated PyPI package metadata, license classifier, README badge, NOTICE, and active CLI documentation to stop advertising Apache-2.0/OSS for the current release line.
- Bumped package metadata and runtime `inferguard.__version__` to `0.7.3`.

## [0.7.1] - 2026-05-04

### Fixed

- Hardened `validate-completed` live-complete quorum: a live job now requires at least one successful `request_profile/requests_profile.jsonl` row, a successful `launch/healthcheck.json`, and non-empty engine + GPU metric timelines before it can emit `status=live_complete`.
- Corrected the `not_publishable` kill path so per-job `claim_status` downgrades to `not_proven`, matching PRD §5 instead of leaking `synthetic`.
- Removed non-canonical public `claim_status` labels (`downgraded`, `partial`, and `inferred_without_engine_metrics`) from InferGuard outputs; detailed causes now live in `reason`, `claim_reason`, or `claim_caveat`.
- Guarded `compute-cost` and `find-cliffs` so `measured` output is only emitted when an existing validation report has `status=live_complete`; otherwise measured math is capped at `inferred` with an explicit `claim_reason`.
- Passed `--data-parallel-size` through the vLLM launcher argv so DSv4-Pro DP=8 launch recipes are represented in `launch/command.json`.
- Moved launch-engine subprocesses into their own process group and updated shared SIGTERM/SIGINT cleanup to terminate registered process groups, preventing orphan vLLM/SGLang workers.
- Fixed `test_agent_trace` to assert the correct proxy behavior: when streaming usage chunks are not requested, output tokens are estimated from streamed text rather than copied from `max_tokens`.

### Tests / CI

- Added validator regressions for empty request-profile JSONL and failed healthcheck artifacts blocking `live_complete`.
- Added claim-status discipline tests that scan source literals and emitted validation/cost/cliff artifacts for the PRD §5 enum.
- Added regressions for cost/cliff measured-output downgrades when `validation_report.status != live_complete`.
- Added vLLM DP argv and process-group SIGTERM cleanup regression tests.
- Added release workflow gates for pytest and `pyproject.toml` ↔ `inferguard.__version__` matching.
- Import/fix-up commit for the v0.7.1 baseline: `dbc128d`.

## [0.7.0] - 2026-05-04

### Added

- Added `inferguard.io` crash-safe artifact helpers for atomic JSON/text writes, tolerant JSON object loading, JSONL stream flushing, partial-results registration, and child-process cleanup registration.
- Added shared SIGINT/SIGTERM shutdown handling that flushes registered JSONL streams, writes `partial_results.json`, terminates registered engine subprocesses with SIGTERM then SIGKILL grace, and exits with standard 130/143 codes.

### Changed

- Stream `request-profile` JSONL rows incrementally as each request sample is collected instead of buffering all rows until run completion.
- Migrated runtime JSON summary/artifact writes from truncate-on-open `Path.write_text(json.dumps(...))` patterns to atomic replace writes across CLI, benchmark, analyzer, profiler, launcher, metrics, bundle, diagnosis, classification, cliff, and telemetry paths.
- Hardened `validate-completed`, `report-completed`, `find-cliffs`, and `compute-cost` readers so missing or truncated JSON downgrades claim status instead of crashing the operator workflow.
- Reconciled package metadata and runtime version strings to `0.7.0` for the P0 reliability release.

### Fixed

- Preserved live profiling artifacts under Slurm SIGTERM/SIGINT preemption by registering JSONL streams, partial-results summaries, and spawned engine child processes with shared shutdown cleanup.
- Prevented torn final JSON artifacts from replacing prior readable summaries when a process dies mid-write.
- Prevented `validate-completed` from raising through on malformed artifact contracts, labels, or job summary JSON; invalid inputs now produce downgraded/not-publishable reports.

### Tests

- Added regression coverage for atomic write failure preservation, SIGTERM partial-results emission and child cleanup, request-profile KeyboardInterrupt streaming preservation, and truncated-JSON tolerant readers across validation/report/cliff/cost consumers.

## [0.6.0] - 2026-05-04

### Added

- `inferguard validate-completed` publishability gate with `inferguard-validation-report/v1`, claim-keyed downgrade matrix, locked stdout summary, label overrides, JSON/Markdown artifacts, and strict non-`live_complete` exit semantics.
- `inferguard request-profile` per-request truth layer with TTFT/TPOT/E2E rows, request summaries, OpenAI-compatible streaming/non-streaming support, closed-loop and Poisson arrival modes, and `inferguard-request-profile/v1` plus `inferguard-request-profile-summary/v1` schemas.
- `inferguard collect-metrics` engine + GPU normalized timeline collector for vLLM, SGLang, LMCache, Dynamo-SGLang, and DCGM exporter evidence, including raw sample retention and `inferguard-engine-metrics-timeline/v1`, `dcgm-correlated/v1`, `inferguard-metrics-summary/v1`, and `inferguard-raw-prom-samples/v1` schemas.
- `inferguard launch-engine` vLLM/SGLang/LMCache launcher with command capture, healthcheck artifacts, external-launch validation mode, engine version capture, and `inferguard-launch-command/v1`, `inferguard-healthcheck/v1`, `inferguard-engine-version/v1`, and `inferguard-launch-outcome/v1` schemas.
- `inferguard diagnose-bottleneck` with eight verdicts: prefill-bound, decode-bound, KV-bound, queue-bound, network-bound, host-bound, model-launch-bound, and not-enough-evidence. Emits `inferguard-bottleneck-diagnosis/v1`.
- `inferguard classify-failures` 12-class failure triage with ranked evidence and `inferguard-failure-classification/v1` output.
- `inferguard report-completed` refusal-gated operator recommendation report with `inferguard-operator-recommendation/v1`; it refuses or marks claims not proven when live evidence is missing.
- `inferguard find-cliffs` capacity envelope analysis across six cliffs with `inferguard-capacity-cliffs/v1` output.
- `inferguard compute-cost` cost-per-useful-task report, safe concurrency envelope, SLO/useful-task flags, and `inferguard-cost/v1` output.
- `inferguard agentx-ingest` plus `inferguard ingest-agentx` alias to convert AgentX result CSVs into canonical InferGuard request-profile, metrics timeline, and `inferguard-agentx-ingest-summary/v1` artifacts.
- Release trust gates: `scripts/scan_no_stubs.py`, `scripts/scan_release_bundle.py`, `.github/workflows/release-gate.yml`, and `.github/workflows/release-tag-gate.yml`.

### Changed

- Exposed the Phase B/C library modules through the published Typer CLI so `pip install inferguard==0.6.0` provides the same core workflow previously reachable only through the internal monorepo argparse wrapper.
- Reconciled package metadata and runtime version strings to `0.6.0` for tag-gated releases.

### Added — CI/CD + deployment safety cluster (2026-05-03)

- Add S-79 canary quality regression evidence on `bench replay --canary-eval-set <path-or-dataset>` with `canary_quality_regression` findings carrying `{baseline_accuracy, canary_accuracy, accuracy_delta, eval_sample_count, p_value}`.
- Add S-80 blue/green rollout comparison on `bench compare --blue-green`, emitting `blue_green_p99_regression` when candidate p99 TTFT/TPOT regresses >1.5× with p<0.05.
- Add S-82 tokenizer mismatch preflight mode via `inferguard preflight --detect-tokenizer-mismatch`, emitting `tokenizer_mismatch_silent_drift` when client/server prompt-token counts diverge >1%.
- Add S-83 prompt-template/tool-parser schema validation via `bench replay --tool-call-schema <path>`, emitting `prompt_template_tool_parser_regression` on >5% compliance-rate drops.
- Operator brief now renders CI/CD rollout evidence in Quality regression, Blue/green comparison, Output structure/tool-parser, and tokenizer/config drift sections.
- SPEC.md: v1.0.10 → v1.0.11 for the batched CI/CD deployment-safety audit trail.

### Added — Platform-engineer v2 backlog scenarios (2026-05-03)

- Add S-09 partial GPU degradation detection in `harness/dcgm_correlate.py`: SM activity divergence vs cluster median, temperature divergence, ECC/XID error events. Emits `gpu_partial_degradation` finding with `{gpu_index, gpu_uuid, divergence_metric, divergence_value}`. Operator brief renders new "Hardware health" section.
- Add S-11 OOM giant-prefill chaos injection on `bench replay`: `--inject-giant-prefill-tokens N --allow-chaos`. Single oversized request injected mid-run, before/during/after batch state captured. Emits `oom_giant_prefill_blast_radius` finding with `{killed_batch_count, killed_in_flight_count, engine_recovery_seconds, engine}` for vLLM vs SGLang behavior distinction.
- Add S-14 idle GPU amortization curve: `bench replay --idle-active-mix-mode --active-window-seconds N --idle-window-seconds M` for realistic non-pegged traffic. Analyzer emits `cost_per_token_by_utilization` (4-bucket: 0-25/25-50/50-75/75-100%) + `customer_idle_amortization` + `idle_amortization_penalty` vs 90% target. New `cost_idle_underutilization_high` finding when GPU util <50% for >60% of run AND penalty >1.5×. Operator brief: new "Cost economics" depth section.
- Add S-26 retry storm scenario type: `bench kvcast --mode retry-storm --burst-multiplier N --burst-window-seconds M --baseline-rps N`. Burst-injection pattern measures queue depth recovery, success rate during burst, post-burst restoration time, preemption count. Emits `retry_storm_engine_overload` finding with `{burst_peak_qps, queue_depth_max, recovery_seconds, preemption_count}`.
- Deepen S-01 cold-start ramp metadata to 3-phase decomposition: `model_load_seconds`, `cudagraph_capture_seconds`, `first_60s_p99_ttft_seconds`. Operator brief renders new "Cold-start decomposition" section with per-phase cliff detection.
- Deepen S-03 engine crash recovery metadata: `in_flight_request_loss_count`, `customer_error_signature`, `successful_retry_count_post_recovery`. Operator brief renders new "Crash recovery" section showing full picture beyond recovery time.
- SPEC.md: v1.0.7 → v1.0.10. Three sequential audit-trail entries (v1.0.8 = S-09/S-11, v1.0.9 = S-14, v1.0.10 = S-26 + S-01/S-03 deepen) with full schema documentation.
- Tests: 287 → 297 passed (+10 platform-scenario tests).

### Added — Platform-engineer P1/P2 scenario coverage (2026-05-02)

- Add S-21 per-customer KV footprint accounting in daemon snapshots, native bench customer tagging, metrics timelines, operator-brief "KV by customer" table, and `kv_footprint_imbalance` finding.
- Add S-13 per-customer × workload cost decomposition in operator briefs.
- Add S-07 cache-lineage scaffolding via `--track-cache-lineage` and `prefix_eviction_cross_customer`; full engine block-ID/vLLM-internal lineage remains 🟡 PENDING upstream instrumentation.
- Add S-05 `bench kvcast --mode multi-tenant-storm` with `--customers` and `--sla-tiers`, plus noisy-neighbor finding coverage.
- Add S-01 `bench cold-start` and S-03 `--inject-crash-after-seconds` / `--allow-chaos` scaffolds; full SGLang #23743 chaos reproduction remains 🟡 PENDING version-gated expansion.

### Added — Runbook 08 GB200 execution readiness (2026-05-02)

- Add `inferguard preflight` for read-only HMA/offload compatibility checks before paid GB200 benchmark traffic.
- Add `scripts/run_runbook_08.sh` plus `scripts/dryrun_runbook_08.sh`; dry-run starts local mock vLLM/SGLang OpenAI-compatible endpoints, executes the Runbook 08 sequence with shrunken workloads, and emits Private Repro Packet zips.
- Add `demo/mock_openai_server.py` for offline OpenAI-compatible `/v1/chat/completions`, `/v1/models`, and `/metrics` validation.
- Add `scripts/launchers/dsv4_fp4_gb200_sglang.sh`, gated as 🟡 PENDING SGLang #23741/#23743 validation and citing SGLang docs #23725.
- Extend operator briefs with explicit cost summary and cache-mode cost comparison rows (`$ / completed session` at `--cost-per-gpu-hour × --gpus`).
- Accept both endpoint base URLs and explicit `/metrics` URLs in `disagg status` scrapes so runbook paste commands do not request `/metrics/metrics`.

### Added — `inferguard profile live` MVP (2026-05-02)

- Add top-level `inferguard profile live` command for observing existing `/metrics` traffic without generating requests.
- Stream profile-local findings for high/critical KV usage, rising preemptions, queue backlog, low prefix-hit-rate deltas, offload churn, and metrics unavailable.
- Write `profile.jsonl`, `profile_summary.json`, and `profile.md` with `inferguard-profile-sample/v1` and `inferguard-profile-summary/v1` contracts documented in `docs/SPEC.md`.

### Added — Tier 1 vLLM prefix-cache + HMA finding (2026-05-01)

- Add vLLM prefix-cache, CPU prefix-cache, and KV-offload byte/time fields to `VLLM_FIELD_MAP` and `DisaggSnapshot`.
- Promote native bench metrics timelines into analyzer cache-hit-rate metrics.
- Add `hma_offload_incompatible` as a `FindingCode` surfaced in `report.json` and operator brief artifacts.
- Bump `docs/SPEC.md` to v1.0.4 and reconcile Dynamo / LMCache adapter coverage with code.

### Fixed — vLLM `deepseek_v4` reasoning parser bypass (2026-04-30)

- Drop `--reasoning-parser deepseek_v4` from `launch_vllm_{h100,h200,b200}_gmi.sh`.
- Upstream vLLM parser is missing `reasoning_start_str`/`reasoning_end_str` —
  produces 0 output tokens. Verified via AgentX testing branch
  (`chore/agentx-v0.1-testing` commit `8af1760d`, `docs/AGENTIC_TEST_RESULTS.md`).
- Safe for InferGuard: our `bench/client.py` reads `delta.content`, not
  `delta.reasoning_content`. Other `deepseek_v4` flags (`--tokenizer-mode`,
  `--tool-call-parser`, `--enable-auto-tool-choice`) retained.
- See `docs/sdlc/88-…` for full rationale.

### Added — Tier 1 SA-shape parity (2026-04-30)

- Sync GB200 launchers + runbook to upstream `504048f1` (Day 0 DSv4 Pro FP4 GB200 SGLang).
- Add `launch_sglang_gb200_disagg_gmi.sh` chooser.
- Extend vLLM GB200 chooser with 2 `*-c4096-offload` variants.
- Native bench `config.json` now emits `inferguard-bench-config/v1` and captures GMI topology env vars in a `topology` block.
- `inferguard analyze` now emits `inferguard-analyze/v1.1` with throughput, per-GPU throughput, QPS, interactivity, full percentile ladders, workload-shape stats, and per-cell topology.
- New `--emit-agentx-shape <PATH>` flag writes per-cell AgentX / InferenceX-shaped `agg_*.json` files with `_schema_version: inferguard-agentx-export/v1`.

### Added (from main — 4-rig DSv4 truth verification, 2026-04-30)
- `scripts/launch_vllm_h100_gmi.sh` — InferGuard-authored H100 DSv4 vLLM launch template (now defaults to **DSv4-Flash**; see "Changed" below). No upstream InferenceX DSv4 H100 cell exists; this script is derived from `dsv4_fp8_h200.sh` minus EP/DP-attention paths.
- `scripts/launch_vllm_h200_gmi.sh` — H200 single-node DSv4-Pro launcher. Mirrors upstream `dsv4_fp8_h200.sh` flag set: `--data-parallel-size 8 --enable-expert-parallel --max-model-len 800000`, image `vllm/vllm-openai:deepseekv4-cu129`, four `deepseek_v4` flags, NO FP4 indexer cache (Hopper has no FP4 path).
- `scripts/launch_vllm_b200_gmi.sh` — B200 single-node DSv4-Pro launcher. Mirrors upstream `dsv4_fp4_b200_vllm.sh`: TP/DP-attention toggle (`DP_ATTENTION` env), `--attention_config.use_fp4_indexer_cache=True`, `--max-cudagraph-capture-size 2048`, optional `--moe-backend deep_gemm_mega_moe` on dp-attn path, image `vllm/vllm-openai:deepseekv4-cu130`.
- `scripts/launch_vllm_gb200_disagg_gmi.sh` — thin chooser that points at the 5 upstream srt-slurm recipes (DSv4 GB200 disagg requires Dynamo-vLLM with multi-node prefill+decode workers; we don't replicate that). Validates recipe name against the 5 that actually exist.

## [0.5.0] - 2026-04-30 (production-grade)

### Added
- Production-grade v0.5 harness layer wired into the CLI package, following the canonical design doc at `docs/designs/2026-04-30-inferguard-harness-architecture.md`.
- NeoCloud environment detection in `inferguard.harness.env` for Modal, Crusoe Slinky/CMK, CoreWeave CKS/SUNK, Lambda 1-Click signals, Fireworks target metadata, RadixArk/SGLang, and GMI deployment modes.
- Multi-node daemon fan-in in `inferguard.harness.cluster_daemon` with leader/follower modes, rank labels, shared bearer-token auth, heartbeat/stale tracking, five-minute follower buffering, replay on reconnect, and merged Prometheus metrics.
- `inferguard daemon start --leader` and `inferguard daemon start --follower <leader-url>` CLI flags for cluster fan-in deployments.
- DCGM × vLLM correlator in `inferguard.harness.dcgm_correlate` that emits `dcgm-correlated/v1` JSONL with `gpu_uuid` / `gpu_index` labels, aligned five-second sampling, null-row empty-scrape behavior, and vLLM aggregate broadcast fields.
- Normative schema document `docs/schemas/dcgm-correlated-v1.md`.
- Production LangGraph callback hook: `LangGraphCallback` records model-call, tool-call, and branch nodes into redacted `agent-trace/v1` JSONL.
- Agent-trace graph integrity validator `validate_trace_integrity()` for unique node IDs, valid parent references, one trace ID, summary ordering, node-count consistency, and monotonic timestamps.
- Privacy hardening: value-level telemetry redaction, secure consent-token storage under `~/.config/inferguard/secrets/consent.token` with mode `0o600`, local payload separation under `~/.config/inferguard/uploads-pending/`, and stricter payload audit behavior.
- Broader privacy test fixture coverage for `aiohttp`, `urllib`, `urllib3`, raw sockets, and subprocess network tools (`curl`, `wget`, `http`, `grpc-cli`) in addition to `httpx` / `requests`.
- Production runbooks under the repo root:
  - `docs/runbooks/05-2026-04-30-coreweave-gb200-disagg.md`.
  - `docs/runbooks/06-2026-04-30-modal-multi-node-bench.md`.
  - `docs/runbooks/07-2026-04-30-crusoe-slinky-cmk-bench.md`.
- SDLC and changelog audit entries for the production-quality push: `docs/sdlc/79-2026-04-30-v0.5-production-quality-push.md` and `docs/changelog/70-2026-04-30-v0.5-production-quality-push.md`.

### Added (from `bench/gmi-dsv4-offload-coverage` branch — v0.5 offload coverage)
- LMCache adapter (`LMCACHE_FIELD_MAP` + engine detection) covering hit rate, eviction count, tier-usage bytes (cpu/local_disk/remote), remote bytes sent/received, queue depth. New `tests/fixtures/lmcache.txt`.
- vLLM v0.12 KV offloading connector metrics extending `VLLM_FIELD_MAP` (DMA throughput, async queue depth, eviction count). Metric names inferred from research; need live-endpoint validation.
- NVIDIA Dynamo KVBM field map populated (was empty `DYNAMO_FIELD_MAP = {}`) with block-residency seconds, L1/L2/L3 block counts, evictions, promotions. New `tests/fixtures/dynamo_kvbm.txt`. Metric names need live-endpoint validation.
- SGLang HiCache field extensions (L1/L2/L3 hit counts + lookups + tier bytes). New `tests/fixtures/sglang_hicache.txt`. Metric names need live-endpoint validation.
- `tests/fixtures/mock_vllm_server.py` flags: `enable_lmcache`, `enable_dynamo_kvbm`, `enable_sglang_hicache` (default off). Lets the integration test suite exercise the new metric paths locally without breaking existing tests.
- `scripts/run_offload_sweep.sh` — CPU+GPU offload config sweep wrapper. Operator passes `OFFLOAD_LABEL` per config, runs the 7-class ISB-1 campaign within one engine configuration, then runs again for the next config. Final phase emits `cross-config-comparison.md`.
- `tests/test_integration_offload_sweep_e2e.py` — subprocess-driven kink test using the extended mock for two `OFFLOAD_LABEL` values.

### Changed
- `docs/SPEC.md` is now v1.0.3 and adds §14 Multi-node fan-in, §15 NeoCloud environment detection, and §16 DCGM correlation.
- `docs/HARNESS.md` now describes the v0.5 harness as production-grade for the shipped capabilities and includes a per-provider capability matrix for Modal, Crusoe, CoreWeave, Lambda, Fireworks, RadixArk, and GMI.
- `README.md` now lists five production-grade v0.5 capabilities with explicit status badges.
- `docs/telemetry/v0/POSTURE.md` now documents secure storage paths and the broader outbound-call privacy fixture coverage.
- `scripts/run_dcgm_correlated.sh` now delegates correlation to the Python helper instead of carrying brittle shell/Python join logic.
- Telemetry sanitizer now redacts sensitive string values, not only sensitive keys.
- The consent token is now stored separately from payload JSON.
- The v0.5 release notes now distinguish production-ready LangGraph support from still-stubbed non-LangGraph framework hooks.

### Fixed
- Closed the production-readiness investigation's confirmed H2 blocker with real multi-node rank fan-in and leader-side merge.
- Closed the confirmed H4 blocker with tested DCGM/vLLM correlation and null-safe empty-scrape behavior.
- Closed the confirmed H5 blocker with provider-specific Modal, Crusoe, CoreWeave, Lambda, Fireworks, RadixArk/SGLang, and expanded GMI detection.
- Closed the LangGraph portion of H7 with a real callback hook and documented CrewAI, AutoGen, Claude Code, and Cursor SDK as explicit v0.5 stubs that raise `NotImplementedError`.
- Closed the H8 privacy-hardening risk with broader no-network guards, safer consent-token storage, value-level redaction, and local-payload audit docs.
- Replaced vague harness claims with provider/runbook-specific production guidance and explicit non-claims.

### Deferred
- Real PipelineDP library integration remains deferred to v0.6+.
- Hosted ingest server, dashboards, cross-customer aggregation, and autonomous Ops agents remain deferred to hosted releases.
- CrewAI, AutoGen, Claude Code, and Cursor SDK hooks remain deferred beyond v0.5.
- Ray Serve LLM compatibility tests and KV-block-id ingestion remain deferred.

### Caveats (v0.5 branch)
- LMCache + DSv4 unsupported upstream per LMCache issue #3156 (CSA + HCA hybrid attention not handled). Adapter is built to be ready when LMCache adds support.
- Metric names for v0.12 connector + Dynamo KVBM + SGLang HiCache are inferred from research docs; first live-endpoint test on GMI will tell us if any need adjustment.

### Filed for v0.6 (post-GMI-campaign follow-up)
- **Open-loop Poisson arrival mode** for `bench replay` and `bench kvcast`. New flags: `--arrival-mode {closed-loop,poisson}` (default `closed-loop` to preserve current behavior), `--arrival-rate-rps`, `--arrival-burst-multiplier`. Adds new per-request fields (`queue_depth_at_submit`, `time_in_queue_seconds`, `arrival_lambda_rps_at_submit`) under sibling schema `inferguard-bench-metric/v2`. New summary aggregates: `arrival_mode`, `peak_queue_depth`, `head_of_line_blocking_rate`. Production traffic shape is closer to Poisson than closed-loop; this surfaces queue/HOL behavior the current closed-loop firing hides. See `docs/research/39-2026-04-30-cpu-gpu-agentic-stress-scope-decision.md` §5 for full sketch.

## [0.4.0] - 2026-04-29
### Added
- `scripts/run_isb1_campaign.sh` — paste-executable orchestrator that runs all 7 priority ISB-1 workload classes × concurrency sweep on one rig and writes a consolidated results bundle, then invokes `inferguard analyze` for a top-level report.
- Cost model in `inferguard analyze`: `--cost-per-gpu-hour`, `--gpus`, `--cost-currency` flags compute per-cell `cost` blocks (gpu_hours, compute_cost, completed_sessions, cost_per_completed_session, cost_per_completed_request, cost_per_million_input_tokens, cost_per_million_output_tokens) and a top-level `run_summary.cost`. Schema: `inferguard-cost/v1`.
- Live engine `/metrics` scrape during native bench: `--metrics-url`, `--metrics-interval`, `--metrics-engine` on `bench replay`, `bench kvcast`, `bench kv-stress`. Writes `metrics_timeline.jsonl` with `inferguard-metrics-timeline/v1` records and promotes `kv_pressure_label` from `inferred_without_engine_metrics` to `measured` for requests overlapped by an in-window scrape.
- SVG plot rendering: `--plots` on `inferguard analyze` produces `plots/ttft_vs_concurrency.svg`, `plots/throughput_per_gpu.svg`, and `plots/cost_per_task.svg`. Matplotlib is an optional dep — install via `pip install 'inferguard[plot]'`. New module `inferguard.analyze.plots` exposes `render_plots`, `plot_ttft_vs_concurrency`, `plot_throughput_per_gpu`, `plot_cost_per_task`.
- Schema additions: `inferguard-cost/v1` and `inferguard-metrics-timeline/v1` documented in `docs/SCHEMAS.md`.

### Changed
- `summary.json` now includes `metrics_timeline_present` and `metrics_scrape_interval_seconds` fields when a live metrics scrape was attempted.

## [0.3.0] - 2026-04-29
### Changed
- Reconciled InferGuard SPEC v1.0.1 and schema docs with implemented OSS behavior: path tracing remains aggregate-only, recent-events records use `at`/`endpoints`, and analyzer finding codes distinguish emitted vs reserved values.
- Extended OSS layer lint coverage to `bench/`, `schemas/`, `utils/`, and `analyze/`, and softened Dynamo / llm-d support wording to detected adapter-pending.
- Documented Wave 1 analyzer field preservation and recursive trace-pack loading in `docs/SPEC.md`.

### Added
- ISB-1 DSv4 Agent Trace Pack v1 under `traces/isb1-dsv4-agent/` for priority long-context coding, multi-agent, tool-heavy, session-resume, prefix-reuse, and KV-pressure workloads.
- Bare-metal DSv4 smoke script at `scripts/run_dsv4_smoke.sh` and GMI DSv4 bare-metal bench runbook v2.
- D-task batch coverage: D-1, D-2, D-3, D-8, D-9, D-10, D-11, and D-12.
- Native bench artifact schema identifiers: `inferguard-bench/v1` and `inferguard-bench-summary/v1`.
- `inferguard bench kvcast` with explicit `cold-pressure`, `prefix-reuse`, and `mixed-agent` modes for synthetic cache-stress runs.
- `--redact-prompts`, `--requests-per-level`, `--duration-seconds`, and `--warmup-seconds` options for native benchmark commands.
- First functional InferGuard Bench CLI: `inferguard bench replay` and `inferguard bench kv-stress` for OpenAI-compatible streaming chat endpoints.
- Native bench artifact set: `run.json`, `config.json`, `requests.jsonl`, `metrics.jsonl`, `summary.json`, and `report.md`.
- Trace JSONL validation, synthetic KV/KVCast generation, streaming TTFT measurement from first non-empty generated content token, first-SSE/content-token telemetry, and explicit estimated token-source labels.
- Analyzer support for native InferGuard bench `summary.json` outputs.
- GMI bare-metal launch templates for vLLM and SGLang.

## [0.2.0] - 2026-04-23
### Added
- Initial public release of `inferguard disagg status` CLI + `inferguard-mcp` server.
- Cross-engine adapters for vLLM, SGLang, NVIDIA Dynamo, and llm-d.
- Three MCP tools: `disagg_status(prefill_url, decode_url, transfer_url?)`, `path_trace(sample_size=10)`, `recent_events(minutes=10)`.
- Six read-only detectors: connector_mismatch, prefill_decode_imbalance, kv_transfer_errors_present, kv_transfer_stall, endpoint_unreachable, engine_unidentified.

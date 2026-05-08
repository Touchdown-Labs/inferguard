# LC1/C1 long-context agent KV/offload benchmark integration spec v0.1

Status: implementation-ready
Repo: /Users/chen/Projects/inferguard
Scope: grow the existing LMCache MP Modal packet lab and coverage reports. Do not create a parallel harness.

## Source of truth reviewed

Authoritative SDLC SSoT:
/Users/chen/Projects/Touchdown-Labs/docs/sdlc/195-2026-05-07-lmcache-vllm-inferguard-100-coverage-ssot.md

Current score remains 68/100 until a live artifact lands. C1/LC1 only counts after a real Modal H100 run is captured, passed through:

1. inferguard collect-lmcache
2. inferguard lmcache-compat
3. inferguard observability-coverage
4. inferguard diagnose-bottleneck

Then the reports plus compact sanitized fixture must land under tests/fixtures/lmcache_live/** and be pinned by passing tests.

## Classification

AUTO:
- Add/adjust unit tests first for Packet B/C1 long-context agent workload metadata.
- Extend existing Packet B in scripts/lmcache_mp_modal_packet_lab.py.
- Extend observability coverage and compatibility assertions for L0 block gap evidence.
- Add import/sanitization tests for the accepted C1 live fixture contract.
- Run local test subset and release scans through RepoPrompt agent/local macOS tooling.

REVIEW:
- Before Modal spend, review command plan, env overrides, and expected artifact list.
- Review any fixture imported from Modal for secrets and raw prompt leakage.
- Review whether upstream LMCache actually emits lmcache_mp_l0_block_* on the tested ref.

MANUAL:
- Modal H100 live run, only after local tests and runner dry-run pass.
- Updating the SDLC score after live artifact acceptance.

## Existing anchors found

1. Existing Modal packet runner:
   - scripts/lmcache_mp_modal_packet_lab.py
   - Packet specs at lines 420-507.
   - Packet B currently maps to C1-style lifecycle work:
     packet_id=b, workload=reuse_eviction, output_slug=packet-b-lifecycle-reuse-eviction.
   - Traffic generation is _drive_traffic, lines 1028-1127.
   - Workload manifest is _write_workload_manifest, lines 933-985.
   - Packet B evidence is _write_packet_b_lifecycle_evidence, lines 1139-1171.
   - Required Packet B families already include l0_lifecycle and l0_l1_throughput via PACKET_B_REQUIRED_TELEMETRY, lines 99-107.
   - Pipeline commands already call collect-lmcache, lmcache-compat, observability-coverage, and diagnose-bottleneck in _run_inferguard_packet, lines 1205-1382.
   - Modal entrypoints already expose run_packet_b and packet selection, lines 1629-1689.

2. Existing coverage report:
   - src/inferguard/observability_coverage.py
   - build_observability_coverage_report merges engine + LMCache compat and emits kv_cache_offload plus coverage_gaps.
   - compat path: src/inferguard/compat.py already knows lmcache_mp l0_lifecycle and l0_l1_throughput families.

3. Existing acceptance gate:
   - tests/test_lmcache_live_fixtures.py
   - _assert_packet_b_c1_acceptance already enforces packet_b C1 artifacts, measured evidence, no missing required families, and populated l1_lifecycle, real_reuse, l0_l1_throughput.
   - It does not yet force the workload to be a long-context agent trace or explicitly require l0_lifecycle in compat rows.

4. Existing agent traces:
   - traces/isb1-dsv4-agent/**
   - Candidate trace files include agent-chat, coding-long, kv-pressure, multi-agent-coding, prefix-reuse, session-resume, and tool-heavy.

## Required design change

Grow Packet B into LC1/C1 instead of adding another runner.

Packet B should become:
- packet_id: b
- sdlc row: C1 / LC1
- workload: long_context_agent_kv_offload or keep reuse_eviction only as a legacy mode label while adding workload_profile=long_context_agent_kv_offload
- output_slug: packet-b-lifecycle-reuse-eviction can remain for continuity, but summary must say LC1/C1 long-context agent KV/offload benchmark.
- traffic source: use compact sanitized prompts derived from traces/isb1-dsv4-agent/coding-long, kv-pressure, multi-agent-coding, prefix-reuse, session-resume, or tool-heavy.
- no raw prompts in fixture manifests. Record prompt_chars, trace id, phase, prefix_group, synthetic redaction status, cache_salt, request index.

The current Packet B failed acceptance because lmcache_mp_l0_block_* was absent. The implementation must make that absence first-class evidence:

- If l0 block metrics are absent, packet-b-lifecycle-evidence.json must keep claim_status=blocked or not_measured and include missing_required_families containing l0_lifecycle.
- If l0 block metrics are present, claim_status=measured and missing_required_families=[].
- observability_coverage.json and lmcache_compat_report.json must expose l0_lifecycle and l0_l1_throughput family statuses.
- diagnose-bottleneck should surface the L0 gap as an operator-facing bottleneck/failure reason when C1 is blocked.

## TDD plan

RED 1: tests/test_lmcache_mp_modal_packet_lab.py
- Add a test that Packet B manifest describes LC1/C1 long-context agent KV/offload, not just generic reuse_eviction.
- Assert Packet B request_count remains bounded for cost.
- Assert _write_workload_manifest includes:
  - sdlc_row_id=C1
  - benchmark_id=LC1
  - workload_profile=long_context_agent_kv_offload
  - trace_source under traces/isb1-dsv4-agent
  - required_packet_b_telemetry includes l0_lifecycle and l0_l1_throughput
  - raw_prompts_recorded is false

RED 2: tests/test_lmcache_live_fixtures.py
- Strengthen _assert_packet_b_c1_acceptance to require:
  - manifest row_id=C1, packet_id=b, benchmark_id=LC1
  - workload_profile=long_context_agent_kv_offload
  - l0_lifecycle compat row populated, in addition to l1_lifecycle, real_reuse, l0_l1_throughput
  - no raw prompts or credentials in traffic_requests.jsonl

RED 3: tests/test_observability_coverage.py or tests/test_lmcache_metrics_adapter.py
- Add fixture metrics containing lmcache_mp_l0_block_* and lmcache_mp_l0_l1_*_throughput_gbs.
- Assert compat and coverage mark lmcache_mp l0_lifecycle and l0_l1_throughput populated.
- Add negative test: when L1 lifecycle/reuse is present but L0 block metrics absent, report contains an explicit upstream/operator question or coverage gap for l0_lifecycle missing.

GREEN implementation:
- Modify PacketSpec with C1 metadata fields:
  sdlc_row_id, benchmark_id, workload_profile, trace_source, requires_l0_block_metrics.
- Update PACKETS['b'] with LC1/C1 metadata while preserving packet_id b and existing Modal command path.
- Update _write_workload_manifest to emit the C1 metadata and phase plan.
- Update _drive_traffic to use sanitized long-context agent request templates. Do not store raw prompts in fixtures.
- Update _write_packet_b_lifecycle_evidence to include benchmark_id, workload_profile, trace_source, l0 status, and explicit blocked reason when lmcache_mp_l0_block_* is absent.
- Update _write_summary_and_index so Packet B summary says LC1/C1 and includes blocked/measured status.
- Update acceptance tests to require l0_lifecycle in compat rows.

Refactor:
- Keep Packet A stable.
- Keep packets C-F stable.
- Avoid new runner files unless a tiny helper module is needed for sanitized trace prompt construction.

## Modal/H100 run gate

Do not run Modal until all local tests pass:

- tests/test_lmcache_mp_modal_packet_lab.py
- tests/test_lmcache_live_fixtures.py
- tests/test_observability_coverage.py
- tests/test_lmcache_artifact_contract.py
- scripts/scan_no_stubs.py src scripts tests

When ready, run exactly the existing harness:

modal run scripts/lmcache_mp_modal_packet_lab.py --packet b

Recommended cost bounds before first H100 run:

- INFERGUARD_PACKET_B_VLLM_GPU_MEMORY_UTILIZATION=0.65
- INFERGUARD_PACKET_B_VLLM_MAX_MODEL_LEN=8192
- request_count stays at 48 unless local dry-run shows a lower value can still expose L0/L1 lifecycle.

After Modal returns /out path, pull artifacts from Modal volume into ./modal-out/packet-b-lifecycle-reuse-eviction/<timestamp>/ and run the existing pipeline if the runner did not already complete it.

## Acceptance artifact import

Import a compact sanitized fixture under:

tests/fixtures/lmcache_live/packet_b/

Required files are already defined by PACKET_B_REQUIRED_FILES in tests/test_lmcache_live_fixtures.py. Add benchmark metadata to fixture_manifest.json:

- row_id: C1
- benchmark_id: LC1
- packet_id: b
- source: live_modal_h100
- acceptance_status: accepted only when all required L0/L1 families are populated
- modal_run_id or Modal path
- raw_prompts_recorded: false

If lmcache_mp_l0_block_* is still absent, do not mark accepted and do not move score. Keep the Modal output as blocked evidence only.

## Immediate next action

Implement RED tests in the existing test files, then update scripts/lmcache_mp_modal_packet_lab.py and compat/coverage handling until the local subset passes. Only then spend H100 time.
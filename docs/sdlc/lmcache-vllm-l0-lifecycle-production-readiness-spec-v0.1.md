# LMCache/vLLM L0 lifecycle production-readiness spec v0.1

Date: 2026-05-09
Owner: Touchdown Labs / InferGuard
Repo scope: /Users/chen/Projects/inferguard plus private local forks /Users/chen/Projects/vllm and /Users/chen/Projects/LMCache

## Goal

Make the accepted Packet B Modal/H100 LC1/C1 result production-traceable for InferGuard CLI observability across LMCache MP KV-cache offload, CPU/GPU memory pressure, long-context chat, tool-use, chat, and coding workloads.

This is not a new harness. It extends the existing Packet B Modal runner and the existing InferGuard CLI chain:

collect-lmcache -> lmcache-compat -> observability-coverage -> diagnose-bottleneck -> sanitized live fixture gate

## Current accepted evidence

Final accepted Modal/H100 run:
- Modal URL: https://modal.com/apps/ocwc22/main/ap-fnSk3mvREgoyqPpx3QuogL
- Local artifact: /Users/chen/Projects/inferguard/modal-out/packet-b-lifecycle-reuse-eviction/20260508T173047Z
- vLLM private branch: ocwc/lmcache-mp-l0-lifecycle at 2536687198bf69fbbe385decdbe3bb8b3aaaf816
- LMCache private branch: ocwc/l0-boundary-evidence at 06a73b21580a53c13f37e9999fd001009d0881e3
- InferGuard branch: ocwc/packet-b-l0-lifecycle-overlay at 63ac91ff3389811cc14bd9218d7b6225c419bd97

Accepted populated metrics:
- lmcache_mp_l0_block_allocated_blocks_total = 11692.0
- lmcache_mp_l0_block_allocation_records_total = 336.0
- lmcache_mp_lookup_requested_tokens_total = 177152.0
- lmcache_mp_lookup_hit_tokens_total = 98816.0
- lmcache_mp_l1_memory_usage_bytes = 7.92723456e+08
- missing_required_families = []
- l0 boundary evidence = 1680 events / 58460 total reported blocks

Accepted status:
- Packet B artifact status: candidate_measured
- claim_status: measured
- fixture imported under tests/fixtures/lmcache_live/packet_b/
- fixture tests pass

## Required updates now

1. InferGuard docs must record that C1 moved from blocked to measured for Packet B LC1/C1 only.
2. Touchdown-Labs SSoT must be updated from the previous 68/100 blocked state to reflect accepted Packet B live H100 evidence.
3. Do not overclaim global 100% compatibility beyond the measured use case. State precisely:
   - Packet B LC1/C1 is measured for current long-context agent KV/offload workload.
   - InferGuard now has accepted telemetry coverage for required families in the sanitized fixture.
   - Production readiness still needs release hardening, upstream/private fork packaging, and repeatability/CI gating before public open-source PRs.
4. Keep private fork work private. Do not open upstream PRs yet.
5. Do not rerun Modal/H100 unless a new code change affects the runtime telemetry path.
6. Commit only allowlisted docs/spec/status changes. Leave unrelated dirty files untouched:
   - /Users/chen/Projects/inferguard/docs/getting-started/quick-start.md
   - /Users/chen/Projects/inferguard/uv.lock
   - /Users/chen/Projects/inferguard/AGENTS.md
   - /Users/chen/Projects/inferguard/modal-out/
   - unrelated Touchdown-Labs dirty files

## Acceptance checks for this update

Run after docs/status updates:
- cd /Users/chen/Projects/inferguard && uv run pytest tests/test_lmcache_live_fixtures.py -q
- cd /Users/chen/Projects/inferguard && uv run pytest tests/test_lmcache_mp_modal_packet_lab.py -q
- cd /Users/chen/Projects/inferguard && uv run pytest tests/test_observability_coverage.py -q

Docs review must confirm:
- No claim that all possible LMCache/vLLM deployments are 100% covered.
- No claim that upstream vLLM/LMCache PRs are open or merged.
- Clear distinction between measured Packet B LC1/C1 and remaining productionization.
- Modal run URL and artifact path are present.
- Private fork commit SHAs are present.

## Output contract

Return:
- files updated
- commits and push status
- final score/status language used in SSoT
- tests run and results
- remaining dirty files untouched

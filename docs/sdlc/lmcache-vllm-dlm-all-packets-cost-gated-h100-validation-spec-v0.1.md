# LMCache/vLLM/DLM all-packets cost-gated H100 validation spec v0.1

Date: 2026-05-09
Owner: Touchdown Labs / InferGuard
Implementation repo: /Users/chen/Projects/inferguard
Private forks:
- /Users/chen/Projects/vllm, branch ocwc/lmcache-mp-l0-lifecycle
- /Users/chen/Projects/LMCache, branch ocwc/l0-boundary-evidence
Control SSoT: /Users/chen/Projects/Touchdown-Labs/docs/sdlc/195-2026-05-07-lmcache-vllm-inferguard-100-coverage-ssot.md

## Goal

Get complete evidence-backed coverage for the current InferGuard LMCache/vLLM workstream without wasting H100 spend.

Coverage scope requested:
- InferGuard CLI chain across all packets
- LMCache MP architecture with vLLM LMCacheMPConnector
- KV-cache offload lifecycle
- CPU/GPU/offload/throughput metrics where exposed
- telemetry/log/trace/HTTP surfaces
- diagnostics and observability coverage reports
- DLM-related coverage if supported by repo code; if DLM is absent/undefined in current repo, mark as not_started or not_applicable with exact evidence, do not hallucinate support

## Non-goals / guardrails

- Do not create a parallel harness unless the existing runner cannot express the packet.
- Do not run H100 repeatedly. Run local/synthetic gates first. Run each H100 packet at most once per telemetry-path code state.
- Do not rerun Packet B unless runtime telemetry code changed after accepted run ap-fnSk3mvREgoyqPpx3QuogL.
- Do not claim global 100% unless every matrix lane has evidence. Use states: not_started, parser_only, fixture_backed, live_validated, release_ready, not_applicable.
- Do not open upstream PRs yet.
- Do not edit unrelated dirty files.

## Baseline accepted evidence

Already accepted:
- B1 Packet A: live_validated.
- C1 Packet B LC1: live_validated from Modal/H100 run https://modal.com/apps/ocwc22/main/ap-fnSk3mvREgoyqPpx3QuogL.
- Local artifact for Packet B: /Users/chen/Projects/inferguard/modal-out/packet-b-lifecycle-reuse-eviction/20260508T173047Z.
- Packet B populated lmcache_mp_l0_block_* and passed CLI -> sanitized fixture gate.
- SSoT score before this all-packets pass: 74 / 100.

Do not rerun Packet B unless necessary. Use the imported fixture as proof.

## Required matrix

Validate or explicitly classify every row below:

1. Packet A / B1 — MP L1 smoke
   - Expected state: live_validated already.
   - Action: verify fixture/test remains green. Do not rerun H100.

2. Packet B / C1 / LC1 — sampled lifecycle / long-context agent KV offload
   - Expected state: live_validated already.
   - Action: verify fixture/test remains green. Do not rerun H100.

3. Packet C / D1 — MP lifecycle + L2
   - Expected state before work: runner_exists or fixture_backed, needs live validation if runner exists.
   - Action: inspect existing runner support. Run local gates. If H100 is required and packet has a defined runner, run exactly once. Import sanitized fixture only if accepted.

4. Packet D / E1 — OTel / trace export
   - Expected state before work: runner_exists or fixture_backed, needs live validation if runner exists.
   - Action: inspect existing runner support. Prefer local collector simulation if accepted by tests; otherwise run exactly once on H100 only if live artifact required.

5. Packet E / E2 — salt / namespace / isolation or equivalent collision-safety lane
   - Expected state before work: runner_exists or fixture_backed.
   - Action: validate with local tests first, H100 only if required for metric proof.

6. Packet F / F1 — traces / HTTP / diagnostics surface completeness
   - Expected state before work: runner_exists or fixture_backed.
   - Action: validate all CLI surfaces and import fixture if accepted.

7. G1 — diagnose-bottleneck calibration
   - Action: calibrate from accepted live Packet A-C timelines if enough evidence exists. If Packet C remains unvalidated, leave G1 blocked and state why.

8. H1-H3 — embedded / advanced LMCache-vLLM lanes
   - Include old embedded LMCacheConnectorV1, dynamic embedded LMCacheConnectorV1Dynamic or current upstream equivalent, stale LMCacheConnector negative guard, SGLang/CacheBlend/P2P/PD where repo has support.
   - Action: classify each as not_started/parser_only/fixture_backed/live_validated/not_applicable with evidence.

9. I1 — release readiness
   - Action: docs, CLI reference, release notes, rollback/failure notes. Mark release_ready only if all are complete.

10. DLM
   - Search repo for DLM. If DLM has code/tests/docs, include it in the matrix and validate through the same CLI chain. If absent or ambiguous, mark not_started with exact search evidence and create a prompt/spec for future DLM integration rather than claiming support.

## Cost-gated execution protocol

1. Inspect current repo status and existing packet runner capabilities.
2. Run local focused tests before any H100:
   - uv run pytest tests/test_lmcache_live_fixtures.py -q
   - uv run pytest tests/test_lmcache_mp_modal_packet_lab.py -q
   - uv run pytest tests/test_observability_coverage.py -q
3. Identify which packets genuinely require new H100 runs.
4. Run H100 packets sequentially, one at a time, stopping on first systemic runtime blocker.
5. For every accepted packet:
   - collect-lmcache
   - lmcache-compat
   - observability-coverage
   - diagnose-bottleneck
   - sanitize/import fixture
   - run fixture tests
6. For every blocked packet:
   - save a blocked report with exact missing telemetry family, command, artifact path, and next patch target.
7. Update SSoT score only for accepted live_validated or release_ready evidence.

## Allowlisted files

InferGuard allowlist:
- docs/sdlc/lmcache-vllm-dlm-all-packets-cost-gated-h100-validation-spec-v0.1.md
- docs/sdlc/*packet*validation*report*.md
- docs/sdlc/*lmcache*coverage*report*.md
- scripts/lmcache_mp_modal_packet_lab.py only if a test-first fix is required
- src/inferguard/** only if a test-first fix is required
- tests/test_lmcache_*.py, tests/test_observability_coverage.py only if needed
- tests/fixtures/lmcache_live/** only for accepted sanitized fixtures

Touchdown-Labs allowlist:
- docs/sdlc/195-2026-05-07-lmcache-vllm-inferguard-100-coverage-ssot.md

Private fork allowlist:
- vLLM/LMCache files only if a failing local test proves a runtime telemetry bug.

## Output contract

Return:
- packet-by-packet matrix with state and evidence
- H100 runs performed, URLs, local artifact paths, why each was needed
- tests run and results
- fixtures imported or blocked reports saved
- SSoT score before/after and exact wording
- commits pushed per repo/branch
- dirty files intentionally left untouched
- exact next move for any remaining gap

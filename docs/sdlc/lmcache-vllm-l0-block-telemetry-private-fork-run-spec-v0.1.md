# LMCache/vLLM L0 block telemetry private-fork run spec v0.1

Date: 2026-05-08
Status: active implementation spec
Owner: Touchdown Labs / InferGuard
Repos in scope:
- /Users/chen/Projects/inferguard
- /Users/chen/Projects/LMCache
- /Users/chen/Projects/vllm
Repos explicitly out of scope for writes:
- /Users/chen/Projects/Touchdown-Labs, except reading SDLC SSoT 195 for requirements

## Objective

Make Packet B / LC1 prove LMCache MP L0 lifecycle for vLLM LMCacheMPConnector traffic by producing populated `lmcache_mp_l0_block_*` telemetry, then run exactly one cost-gated Modal/H100 validation through InferGuard.

This is private-fork work first. Do not open upstream PRs yet. Push to our fork branch only after local tests and the single Modal validation are complete.

## Current known state

- InferGuard score remains 68 / 100.
- Packet B live Modal/H100 run completed but strict C1 acceptance is blocked.
- Blocker: `lmcache_mp_l0_block_*` absent for LMCacheMPConnector traffic.
- Existing Packet B artifact already proves the InferGuard pipeline works and that other LMCache MP surfaces populate:
  - lookup requested/hit tokens
  - real-reuse counts
  - L1 lifecycle counts
  - L1 allocation failures
  - L0 to L1 throughput
  - diagnostic artifact chain
- Required fix is in the runtime/fork layer, not a parallel InferGuard harness.

## Classification

AUTO:
- inspect existing private fork branches/remotes/status
- locate current vLLM LMCacheMPConnector telemetry patch and LMCache metric definitions
- add focused tests first
- patch private fork code
- run local unit/static gates
- run exactly one Modal/H100 Packet B validation after local gates pass
- import sanitized fixture only if acceptance criteria are satisfied
- commit/push private fork branch and InferGuard fixture/docs updates if accepted

REVIEW:
- opening upstream PRs
- changing public-facing score from 68 to 74 unless live artifact and sanitized fixture pass
- editing Touchdown-Labs docs beyond a post-acceptance SSoT update

MANUAL:
- upstream maintainer review and merge decisions
- any GitHub PR creation to vLLM or LMCache

## Implementation constraints

1. Use existing InferGuard Packet B runner.
2. Do not invent a parallel benchmark harness.
3. Do not blindly rerun H100. Local gates must pass first.
4. Run Modal/H100 exactly once for this iteration.
5. Do not touch unrelated dirty files.
6. Do not print or persist secrets/env file contents.
7. Treat metric names as insufficient. Acceptance requires populated samples.

## Expected branch discipline

- LMCache default branch is `dev`; create or update a private branch from current local state or latest upstream/dev if safe.
- vLLM branch currently exists as `ocwc/lmcache-mp-l0-lifecycle`; continue it unless inspection shows the fix belongs in LMCache instead.
- InferGuard changes should be made on a branch such as `ocwc/packet-b-l0-lifecycle-acceptance` if code/fixtures/docs change.

## Root-cause investigation steps

1. Inspect `/Users/chen/Projects/vllm`:
   - current branch and remotes
   - current `ocwc/lmcache-mp-l0-lifecycle` diff
   - LMCacheMPConnector files under vLLM distributed KV transfer
   - any existing tests around connector metrics or block allocation deltas
2. Inspect `/Users/chen/Projects/LMCache`:
   - metric registration for `lmcache_mp_l0_block_*`
   - MP connector/server paths that know L0 block allocation, store, load, eviction, free/reuse lifecycle
   - Prometheus exporter behavior and sample labels
3. Inspect `/Users/chen/Projects/inferguard`:
   - Packet B runner
   - compat/coverage parser requirements for L0 lifecycle
   - fixture import script/tests
4. Decide minimal patch location:
   - prefer the runtime component that actually owns L0 block lifecycle truth
   - do not synthesize metrics in InferGuard
   - bridge vLLM connector deltas to LMCache telemetry only if those deltas represent actual L0 block lifecycle state

## TDD/local gates

Before production patch:
- write a failing test that proves MP connector traffic produces or exposes populated `lmcache_mp_l0_block_*` samples or equivalent source data
- run the focused test and verify expected failure

After patch:
- run focused test and verify pass
- run relevant existing vLLM/LMCache focused tests
- run InferGuard gates:
  - `pytest tests/test_lmcache_mp_modal_packet_lab.py -q`
  - `pytest tests/test_observability_coverage.py -q`
  - `pytest tests/test_lmcache_live_fixtures.py -q`

## Modal/H100 command

Run exactly once after local gates pass:

```bash
INFERGUARD_LMCACHE_LOCAL_SOURCE=/Users/chen/Projects/LMCache \
/Users/chen/.local/share/uv/tools/modal/bin/python3 \
  scripts/lmcache_mp_modal_packet_lab.py --packet b
```

If the chosen fix is in the vLLM fork, update the existing Modal runner in InferGuard to mount/install the local vLLM fork for the run before dispatch. Do this through the existing runner path and tests, not a side harness.

## Acceptance criteria

Accepted C1 requires all of:
- Modal/H100 Packet B completes
- artifact chain exists:
  - `lmcache-packet/packet_manifest.json`
  - `lmcache_compat_report.json`
  - `observability_coverage.json`
  - `diagnose-bottleneck/bottleneck_diagnosis.json`
  - `agent_kv_offload_report.json`
  - `packet-b-lifecycle-evidence.json`
  - `workload_manifest.json`
- `lmcache_mp_l0_block_*` family is present and populated with non-zero/sample lifecycle evidence
- InferGuard coverage reports `l0_lifecycle` accepted/populated, not missing/zero
- sanitized fixture imported under `tests/fixtures/lmcache_live/**`
- fixture test passes

If accepted:
- import sanitized fixture
- move C1 from 68 to 74 in the InferGuard-facing docs/score artifacts and then update Touchdown-Labs SSoT in a separate docs-only commit
- commit and push private fork branches
- do not open PR yet

If blocked:
- save blocked report with exact missing family and source patch attempted
- do not import accepted fixture
- do not move score
- do not rerun H100 blindly

## Output contract for implementation agent

Return:
- repo branches and commits before/after
- files changed
- tests run with exact commands and results
- Modal run URL and local artifact path if executed
- whether `lmcache_mp_l0_block_*` populated
- whether fixture imported and C1 moved
- remaining unrelated dirty files

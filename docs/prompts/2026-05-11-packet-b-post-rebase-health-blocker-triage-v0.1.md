# InferGuard Packet B post-rebase health blocker triage v0.1

Created: 2026-05-11
Owner: Touchdown Labs
Runtime: RepoPrompt Agent Mode, engineer role
Classification:
- AUTO: inspect existing Modal runner logs/artifacts, local source diffs, healthcheck code paths, startup command/env, recent LMCache/vLLM rebase deltas; run local/static tests; write diagnosis and patch plan.
- REVIEW: decide whether a fix belongs in InferGuard runner, LMCache branch, or vLLM overlay.
- MANUAL: launching another H100 run only after a specific low-risk fix is identified.

## Objective
Diagnose why the post-rebase Packet B / standalone LMCache MP Modal H100 release smoke failed with:

```text
RuntimeError: LMCache HTTP did not become healthy at http://127.0.0.1:8080/api/healthcheck
```

Do not launch another H100 run in this triage pass. Use existing logs, runner code, and source diffs to identify the likely cause and exact patch/test plan.

## Context
The post-rebase H100 smoke is documented in:
- InferGuard OSS SDLC report: `/Users/chen/Projects/inferguard/docs/sdlc/post-rebase-real-h100-release-smoke-report-v0.1.md`
- Touchdown-Labs control-plane note: `/Users/chen/Projects/Touchdown-Labs/docs/sdlc/203-2026-05-11-inferguard-post-rebase-modal-h100-release-smoke-control-plane.md`

Packet B failed at Modal run:
- `https://modal.com/apps/ocwc22/main/ap-YPfI7S59z2PU0TW1mNOJxJ`

Current relevant heads after push:
- InferGuard branch `ocwc/packet-b-l0-lifecycle-overlay`, latest pushed commit includes docs only: `97b7ab4 docs: record post-rebase H100 smoke`
- LMCache branch `ocwc/l0-boundary-evidence`, expected head: `f2a6a037c2af2f91dae958ec9f94aacd1f34984b`
- vLLM branch `ocwc/simple-cpu-offload-metrics`, expected head: `171fd54c4c3005c2f50f1feaefe4a5dd5a29ebf0`

Known state:
- Local InferGuard gates passed before H100.
- Packet H3 H100 smoke passed after rebase.
- Packet B had no local artifact because LMCache HTTP health never became ready.
- Do not claim release-smoke parity until Packet B passes.

## Required steps
1. Inspect InferGuard runner code for Packet B:
   - `/Users/chen/Projects/inferguard/scripts/lmcache_mp_modal_packet_lab.py`
   - any helper modules it imports for healthcheck/startup/pull.
2. Inspect LMCache branch diffs vs `upstream/dev`, especially:
   - `lmcache/integration/vllm/vllm_multi_process_adapter.py`
   - `lmcache/v1/mp_observability/subscribers/metrics/l0_lifecycle.py`
   - `lmcache/v1/multiprocess/server.py`
   - tests for MP observability/lifecycle.
3. Inspect whether upstream LMCache changed the HTTP health endpoint, host/port binding, startup command, required env vars, or process lifecycle after the rebase.
4. Inspect whether the Modal run output is retrievable locally or through Modal CLI logs for `ap-YPfI7S59z2PU0TW1mNOJxJ`. If logs are available, extract only the relevant startup/traceback lines.
5. Run local non-H100 tests only:
   - InferGuard focused tests that do not launch Modal.
   - LMCache unit tests for the modified files if dependencies are available.
   - Static grep/source inspection if dependencies are missing.
6. Classify the likely fix target:
   - `inferguard_runner_fix`
   - `lmcache_branch_fix`
   - `vllm_overlay_fix`
   - `modal_environment_fix`
   - `unknown_needs_rerun_logs`
7. Write a triage report under `/Users/chen/Projects/inferguard/docs/sdlc/packet-b-post-rebase-health-blocker-triage-v0.1.md` with:
   - evidence ledger;
   - likely root cause;
   - exact patch plan;
   - exact tests to run before the next H100 launch;
   - exact H100 rerun command once fixed;
   - PR implication for LMCache/vLLM/InferGuard.
8. Do not stage, commit, push, or open PRs.

## Final output contract
Return:
- likely root cause or `unknown_needs_rerun_logs`;
- fix target;
- report path;
- next command;
- whether to message Kuntia now or after Packet B is green;
- whether to PR LMCache/vLLM now or wait.

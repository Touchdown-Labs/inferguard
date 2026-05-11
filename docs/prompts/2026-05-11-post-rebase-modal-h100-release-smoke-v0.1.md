# InferGuard post-rebase Modal H100 release smoke + SDLC documentation v0.1

Created: 2026-05-11T04:44:09+0000
Owner: Touchdown Labs
Runtime: RepoPrompt Agent Mode, engineer role
Classification:
- AUTO: run focused local gates; run existing Modal H100 smoke runners; pull/inspect artifacts; run InferGuard compatibility/report verification; write SDLC report.
- REVIEW: decide whether the new artifacts supersede fixtures or only serve as release-smoke receipts.
- MANUAL: none unless Modal auth/credits fail or a live runner requires missing secrets.

## Objective
After LMCache was rebased onto `upstream/dev` and vLLM was rebased onto `upstream/main`, run the cost-gated real H100 Modal smoke again for the InferGuard LMCache/vLLM runtime families. Verify the artifacts still pass through InferGuard, then document the receipts in an OSS SDLC markdown file.

This is a release smoke, not a new scoring exercise unless it finds a regression.

## Repos
- InferGuard: `/Users/chen/Projects/inferguard`
- LMCache: `/Users/chen/Projects/LMCache`, branch expected `ocwc/l0-boundary-evidence`, post-rebase HEAD from prior review `f2a6a037`
- vLLM: `/Users/chen/Projects/vllm`, branch expected `ocwc/simple-cpu-offload-metrics`, post-rebase HEAD from prior review `171fd54c4`
- Touchdown-Labs docs: `/Users/chen/Projects/Touchdown-Labs`

If current heads differ, record the actual heads and continue only if worktrees are safe. Do not stage, commit, push, or open PRs.

## Source-backed evidence rules
Use statuses: `source_backed`, `artifact_backed`, `fixture_tested`, `measured`, `live_validated`, `release_ready`, `not_proven`, `blocked`, `not_applicable`.

Allowed claim wording:
`LMCache MP observability with vLLM is 100% covered for the InferGuard CLI acceptance scope. That does not mean continuous DCGM/NVML hardware telemetry is covered.`

Do not claim DCGM/NVML GPU utilization, HBM bandwidth, NVLink, PCIe, or sustained power telemetry unless a sampler emits accepted samples.

## Required workflow
1. From `/Users/chen/Projects/inferguard`, record:
   - `git status --short --branch`
   - `git rev-parse HEAD`
   - `git log --oneline -5`
2. From LMCache and vLLM, record current branch/head/status. Confirm they are still the post-rebase branches or record drift.
3. Run local focused gates first from InferGuard:
   - `uv run pytest tests/test_lmcache_live_fixtures.py -q`
   - `uv run pytest tests/test_lmcache_mp_modal_packet_lab.py -q`
   - `uv run pytest tests/test_observability_coverage.py -q`
   - `uv run pytest tests/test_lmcache_embedded_advanced_modal_packet_lab.py -q`
   - `uv run mkdocs build`
   If any fail, stop before launching H100 and write a blocked report.
4. Run exactly one H100 smoke per runtime family using existing runners:
   - Packet B / LMCache MP:
     `INFERGUARD_LMCACHE_LOCAL_SOURCE=/Users/chen/Projects/LMCache modal run scripts/lmcache_mp_modal_packet_lab.py --packet b`
   - Packet H3 / embedded CacheBlend:
     `modal run scripts/lmcache_embedded_advanced_modal_packet_lab.py --packet h3-cacheblend`
   If a runner has an existing documented flag/env var to point at local vLLM or LMCache, use it and record it. Do not invent a parallel harness.
5. Capture for each run:
   - exact command
   - Modal app/run URL or app ID
   - Modal output path
   - local artifact path under `/Users/chen/Projects/inferguard/modal-out/pulls/...`
   - GPU identity from `nvidia-smi`
   - driver/CUDA/NCCL/Python/runtime versions when available
   - model, max model length, GPU memory utilization, connector, ports, offload/cache config
   - telemetry files generated
   - required metric families and whether populated
   - compat/coverage/diagnose outputs
   - fixture decision: imported / not imported, with reason
6. Pull artifacts if the Modal runner does not already pull them. Use existing repo scripts only.
7. Verify artifacts through existing InferGuard commands/tests. At minimum, locate generated summaries/reports and confirm:
   - Packet B detected mode `mp` and `failure_reasons=[]`
   - Packet B has populated `lmcache_mp_l0_block_*`/L0 lifecycle evidence
   - Packet H3 detected mode `embedded_cacheblend` or `vllm_embedded_cacheblend` equivalent and `failure_reasons=[]`
   - Packet H3 has non-empty `lmcache_otel.jsonl`, `cb.*` spans, and `lmcache_blend_*` metrics
8. Write a new OSS SDLC markdown report under `/Users/chen/Projects/inferguard/docs/sdlc/` with a dated filename, e.g. `post-rebase-real-h100-release-smoke-report-v0.1.md` if not taken. Include:
   - baseline
   - delta since the rebase review
   - current progress / status matrix
   - evidence ledger with commands, run URLs, local paths, artifacts, and test output
   - hardware telemetry caveat
   - remaining work
   - next PR implications for InferGuard, LMCache, vLLM
9. Also write/update a Touchdown-Labs control-plane SDLC note under `/Users/chen/Projects/Touchdown-Labs/docs/sdlc/` referencing the InferGuard OSS SDLC file and the prior review report `/Users/chen/Projects/Touchdown-Labs/docs/sdlc/202-2026-05-11-inferguard-lmcache-vllm-rebase-pr-gap-review.md`.
10. Run verification after doc writes:
    - `uv run mkdocs build` from InferGuard
    - `git diff -- docs/sdlc` from InferGuard
    - `git status --short --branch` for all four repos

## Important boundaries
- Do not stage, commit, push, or open PRs.
- Preserve unrelated dirty files.
- Import a new fixture only if the new artifact improves/supersedes prior accepted evidence. Otherwise document as release-smoke receipt only.
- If Modal auth, cloud quota, or H100 execution fails, write a blocked SDLC report with exact failure output and do not pretend verification happened.

## Final response contract
Return a concise terminal-readable summary with:
- local gates result
- Modal run result for Packet B
- Modal run result for Packet H3
- artifact paths and run URLs
- verification result
- OSS SDLC report path
- Touchdown-Labs control-plane report path
- coverage status and caveats
- blockers/remaining work

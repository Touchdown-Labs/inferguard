# Final real H100 release smoke spec v0.1

## Objective
Run one cost-gated real Modal/H100 validation pass after the vLLM + LMCache + InferGuard CLI scope reached 100/100, to prove the release state still works on real hardware before demo/publishing.

This is a release smoke, not a new scoring exercise. The score remains 100/100 unless the run exposes a regression.

## Scope
Active scope only:
- vLLM + LMCache + InferGuard CLI
- Long-context chat/coding/tool-use observability
- LMCache MP KV cache/offload diagnostics
- Embedded CacheBlend / OTel diagnostics

Paused and out of scope for this smoke:
- H2/SGLang, currently paused at sgl_kernel
- Mooncake, no runnable local runtime/source contract
- DLM/llm-d, detection-only/no validated field map
- P2P/PD expansion lanes

## Cost gate
Do not run every historical packet unless local evidence proves a regression. Use the smallest real H100 smoke that covers both runtime families:

1. Packet B / LC1 MP lifecycle smoke
   - proves LMCache MP + vLLM fork path still emits lmcache_mp_l0_block_*
   - proves collect-lmcache -> lmcache-compat -> observability-coverage -> diagnose-bottleneck still works on H100

2. Packet H3 / embedded_cacheblend smoke only if the runner has an existing smoke mode or focused command
   - proves CacheBlend runtime starts on H100
   - proves lmcache_otel.jsonl is non-empty
   - proves cb.* spans and lmcache_blend_* metrics are captured

If H3 has no cheap focused smoke command, do not invent a new harness. Reuse the existing runner, or stop with a documented command-level blocker.

## Local prerequisites before H100
Run focused local gates first:
- uv run pytest tests/test_lmcache_live_fixtures.py -q
- uv run pytest tests/test_lmcache_mp_modal_packet_lab.py -q
- uv run pytest tests/test_observability_coverage.py -q
- uv run pytest tests/test_lmcache_embedded_advanced_modal_packet_lab.py -q if present/applicable

If local gates fail, patch locally with TDD and do not launch H100.

## H100 execution rules
- Use existing Modal runner(s), not a parallel harness.
- Use exactly one H100 run per runtime family unless a command fails before workload execution due to local runner/config error.
- Sanitize logs and artifacts before committing.
- Do not expose credentials, API keys, tokens, or connection strings. Redact as [REDACTED].
- Import a new fixture only if the artifact improves or supersedes existing accepted evidence.
- If the run matches existing accepted evidence but does not improve it, record a short smoke report only.

## Acceptance
Packet B smoke acceptance requires:
- Modal/H100 run URL or app id recorded
- local artifact path recorded
- lmcache_mp_l0_block_* populated
- lmcache_compat_report.json present and compatible
- observability_coverage.json present and passing required families
- diagnose-bottleneck output present

H3 smoke acceptance requires, if run:
- Modal/H100 run URL or app id recorded
- local artifact path recorded
- lmcache_otel.jsonl exists and is non-empty
- cb.* spans present
- lmcache_blend_* metrics present
- compat classification is embedded_cacheblend, not MP/mixed

## Deliverables
- Commit any allowlisted smoke report/doc updates to InferGuard branch.
- Update Touchdown SSoT only if the smoke changes status or adds a clean final release-smoke receipt.
- Leave unrelated dirty files untouched.
- Do not open PRs.

## Final report
Report:
- Whether the real H100 smoke passed
- Modal run URL(s)
- local artifact path(s)
- exact commands run
- tests passed
- commits pushed
- any regression or blocker

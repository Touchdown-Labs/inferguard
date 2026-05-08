# InferGuard Packet B Modal/H100 Live Validation Run Spec v0.1

Date: 2026-05-08
Repo: `/Users/chen/Projects/inferguard`
Run target: existing LMCache MP Modal Packet B
Commit baseline: `d854ee1beee3d2e870262a471b5e44b9a412de90`
Status: ready-to-run, cost-gated by explicit founder request

## Purpose

Run the existing Packet B Modal/H100 path once to validate real LMCache MP observability for long-context agent KV/offload coverage. This validates InferGuard as a vendor-neutral diagnostic CLI that complements LMCache/vLLM and reports real CPU/GPU/KV/offload metrics without pretending to be the cache engine.

## Scope

Use the existing harness only:

- `scripts/lmcache_mp_modal_packet_lab.py`
- Packet id: `b`
- CLI chain already invoked by the packet runner:
  - `inferguard collect-lmcache`
  - `inferguard lmcache-compat`
  - `inferguard observability-coverage`
  - `inferguard diagnose-bottleneck`

Do not create a new harness. Do not run unrelated packets unless Packet B tooling requires a quick local sanity check.

## Local gate before H100 spend

Run these first:

```bash
pytest tests/test_lmcache_mp_modal_packet_lab.py -q
pytest tests/test_observability_coverage.py -q
pytest tests/test_lmcache_live_fixtures.py -q
```

If these fail, stop and fix locally before spending Modal/H100.

## H100 run command

Prefer existing documented command path from the repo. Current expected path:

```bash
python scripts/lmcache_mp_modal_packet_lab.py --packet b
```

or, if repo instructions require Modal CLI directly:

```bash
modal run scripts/lmcache_mp_modal_packet_lab.py --packet b
```

Use the command that the repo currently supports. Capture exact command, app/run id, output path, and artifact directory.

## Acceptance policy

The SSoT score can move from 68/100 only if all are true:

1. Real Modal/H100 artifact is captured under `./modal-out/` or equivalent.
2. The artifact has completed InferGuard CLI chain outputs:
   - `lmcache-packet/packet_manifest.json`
   - `lmcache_compat_report.json`
   - `observability_coverage.json`
   - `diagnose-bottleneck/bottleneck_diagnosis.json`
   - `agent_kv_offload_report.json`
3. Packet B/C1 has populated L0 lifecycle metrics from `lmcache_mp_l0_block_*`.
4. Compact sanitized fixture is imported into `tests/fixtures/lmcache_live/**`.
5. Fixture tests pass.
6. No raw prompts, messages, API keys, env secrets, or credentials are preserved in fixture-bound artifacts.

## If L0 block metrics are absent

Do not rerun blindly. Treat as blocked evidence:

- `claim_status=not_proven`
- `acceptance_status=blocked`
- `blocked_reason=lmcache_mp_l0_block_metrics_absent`
- `operator_facing_code=lmcache_mp_l0_lifecycle_missing`

Report the exact missing metric family and stop. Do not update the score.

## Sanitization rules

Never print or summarize env values from:

- `modal-out/**/env.txt`
- `modal-out/**/00-env.txt`
- any `.env` or token-bearing files

For fixture import, include only compact evidence required by tests. Redact secrets as `[REDACTED]`.

## Output contract for the run agent

Return:

- local test results
- exact Modal/H100 command used
- Modal app/run id if available
- artifact directory path
- whether `lmcache_mp_l0_block_*` was populated
- InferGuard CLI chain artifact status
- sanitized fixture path if imported
- fixture test results if imported
- SSoT score update status
- blocker summary if not accepted

## Changelog

- v0.1 — 2026-05-08 — First live Packet B Modal/H100 validation run spec after LC1/C1 local TDD commit.

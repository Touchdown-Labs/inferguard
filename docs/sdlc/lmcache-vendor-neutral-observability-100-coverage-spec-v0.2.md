# InferGuard LMCache Vendor-Neutral Observability 100% Coverage Spec v0.2

Date: 2026-05-08
Repo: `/Users/chen/Projects/inferguard`
Status: implementation-in-progress
Owner system: Hermes / RepoPrompt agent stack
Authoritative SSoT: `/Users/chen/Projects/Touchdown-Labs/docs/sdlc/195-2026-05-07-lmcache-vllm-inferguard-100-coverage-ssot.md`
Previous focused spec: `docs/sdlc/lc1-c1-long-context-agent-kv-offload-spec-v0.1.md`

## Purpose

Get InferGuard to 100% LMCache plus vLLM observability coverage as a vendor-neutral diagnostic CLI. The CLI must extend and integrate with LMCache and vLLM evidence. It must not recreate LMCache, replace LMCache, or build a parallel benchmark harness.

The immediate scoring row remains LC1/C1: grow the existing Modal Packet B runner into a long-context agent KV/offload benchmark with explicit L0/L1 lifecycle, GPU/CPU/offload, and operator-facing blocked evidence when LMCache does not emit required L0 block metrics.

## Non-negotiables

1. Use the existing InferGuard pipeline.
   - `scripts/lmcache_mp_modal_packet_lab.py`
   - `inferguard collect-lmcache`
   - `inferguard lmcache-compat`
   - `inferguard observability-coverage`
   - `inferguard diagnose-bottleneck`

2. Preserve Packet B continuity.
   - Keep `packet_id = "b"`.
   - Keep current Modal command path.
   - Extend Packet B into LC1/C1. Do not create a new harness.

3. Stay vendor-neutral.
   - InferGuard diagnoses and validates evidence from LMCache/vLLM.
   - InferGuard does not claim to be the cache engine.
   - InferGuard reports missing upstream telemetry as blocked/not_measured/not_proven, not as success.

4. Do not move the SSoT score from 68/100 unless the live-artifact rule is satisfied.
   - Real Modal/H100 run captured under `./modal-out/` or equivalent.
   - Passed through collect-lmcache -> lmcache-compat -> observability-coverage -> diagnose-bottleneck.
   - Compact sanitized fixture imported into `tests/fixtures/lmcache_live/**`.
   - Pinned by passing tests.

5. Cost control.
   - No Modal/H100 spend until local TDD tests and dry-run artifact generation pass.
   - Packet B remains bounded and demo-oriented.
   - If required telemetry is absent, capture blocked evidence and stop. Do not rerun H100 blindly.

6. No prompt or secret leakage.
   - Do not persist raw long-context prompts.
   - `traffic_requests.jsonl` must be metadata-only.
   - Env files and Modal artifacts must be sanitized before fixture import.

## Coverage surfaces

### LMCache MP and KV cache/offload

Required diagnostic surfaces:

- LMCache MP lookup/reuse:
  - requested tokens
  - hit tokens
  - reuse tokens
  - reuse ratio

- LMCache L1 lifecycle:
  - L1 stored tokens/blocks
  - L1 usage/pressure
  - L1 eviction evidence
  - real reuse after pressure

- LMCache L0 lifecycle, required for C1 acceptance:
  - `lmcache_mp_l0_block_*`
  - block lifetime
  - idle-before-evict
  - reuse gap
  - status must be populated for score movement

- LMCache L0 <-> L1 transfer:
  - `lmcache_mp_l0_l1_*_throughput_gbs`
  - store/load direction where available
  - throughput populated vs missing/zero distinction

- LMCache L2 / remote / DLM-next readiness:
  - L2 counts/bytes/hit/miss, when present
  - backend identity, when present
  - remote/P2P path evidence, when present
  - explicit not_present/not_configured when not part of current run

### vLLM / serving runtime

Required diagnostic surfaces:

- GPU pressure:
  - utilization
  - memory usage
  - KV pressure if exposed

- CPU/offload pressure:
  - native vLLM CPU offload setting/evidence
  - CPU swap/offload evidence when exposed
  - distinction between vLLM native CPU offload and LMCache external KV serving

- Runtime request behavior:
  - request count
  - latency/timing metadata
  - phases: warm, pressure, retest
  - no raw prompt persistence

### New architecture / NP analytics observability

Interpret NP analytics observability as the next diagnostic layer on top of the vendor-neutral evidence contract:

- Normalize packet evidence into concise operator-facing analytics.
- Separate measured facts from inferred facts.
- Preserve evidence provenance for each claim.
- Emit failure/blocker codes that a demo operator can explain quickly.
- Keep artifacts small enough to import as fixtures and review in CI.

For LC1/C1, NP analytics output is represented by:

- `agent_kv_offload_report.json`
- `observability_coverage.json`
- `diagnose-bottleneck/bottleneck_diagnosis.json`
- `lmcache_compat_report.json`

### DLM next

DLM is the next extension after Packet B/C1, not a reason to fork the harness.

DLM-ready design requirements:

- Add fields only through the same compat/coverage/report surfaces.
- Report DLM/remote/distributed cache evidence as vendor-neutral families.
- If DLM metrics are absent, report not_present or not_configured, not failure, unless the packet explicitly requires DLM.
- Future DLM packet should reuse the same Modal packet lab and CLI chain.

### Meshmark with Modal CLI to H100

Meshmark/Modal H100 execution is the live acceptance layer, not a separate local truth source.

Acceptance path:

1. Local tests pass.
2. Existing Packet B Modal command path is used.
3. Modal H100 run captures artifacts under `modal-out/` or equivalent.
4. InferGuard CLI chain processes the run artifacts.
5. Sanitized compact fixture is imported.
6. Fixture test passes.
7. Only then update the SSoT score.

## AUTO / REVIEW / MANUAL classification

### AUTO

- Add Packet B LC1/C1 metadata to `PacketSpec` and `PACKETS["b"]`.
- Extend `workload_manifest.json` with LC1 metadata.
- Ensure traffic request logs are metadata-only.
- Add `agent_kv_offload_report.json` artifact.
- Add explicit L0 lifecycle missing diagnostic code.
- Strengthen local tests.
- Run local pytest subsets.

### REVIEW

- Review generated blocked evidence to ensure it does not overclaim.
- Review sanitized fixture import before accepting C1.
- Review SSoT update after live artifact lands.

### MANUAL / COST-GATED

- Modal/H100 live run.
- Repeated H100 reruns after absent `lmcache_mp_l0_block_*`.
- Any credential or account configuration.

## Immediate implementation sequence

1. RED: Packet B metadata tests.
2. GREEN: Add PacketSpec LC1 fields and Packet B metadata.
3. RED: Workload manifest and traffic sanitization tests.
4. GREEN: Metadata-only request logging and temp traffic driver path.
5. RED: L0 lifecycle populated/missing evidence tests.
6. GREEN: blocked/not_proven lifecycle evidence.
7. RED: `agent_kv_offload_report.json` test.
8. GREEN: report writer and required artifact entry.
9. RED: compat/coverage diagnostic tests for missing `lmcache_mp_l0_block_*`.
10. GREEN: compat diagnostic and diagnose priority.
11. RED/GREEN: fixture acceptance contract strengthened for future live Packet B.
12. Local validation.
13. Modal/H100 only if local validation is clean.

## Success criteria before Modal spend

- Focused tests pass locally:
  - `tests/test_lmcache_mp_modal_packet_lab.py`
  - `tests/test_observability_coverage.py`
  - `tests/test_lmcache_live_fixtures.py`
  - `tests/test_diagnose_bottleneck.py`

- Packet B generated artifacts explicitly show one of:
  - `candidate_measured` with populated L0 lifecycle, or
  - `blocked` / `not_proven` with `lmcache_mp_l0_lifecycle_missing`.

- No raw prompt or secret-like values are written to fixture-bound artifacts.

## Score policy

The score remains 68/100 until C1 satisfies the SSoT live-artifact rule. Local parser/test/spec changes improve readiness but do not increase score.

## Changelog

- v0.2 — 2026-05-08 — Expanded LC1/C1 focused spec into the full vendor-neutral LMCache/vLLM observability coverage frame, including NP analytics, DLM-next readiness, and Meshmark/Modal H100 acceptance gates.
- v0.1 — 2026-05-08 — Focused LC1/C1 Packet B implementation spec.

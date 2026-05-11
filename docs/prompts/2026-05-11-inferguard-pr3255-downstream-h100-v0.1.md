# InferGuard PR3255 downstream consumer + Modal H100 verification v0.1

Date: 2026-05-11
Owner: Touchdown Labs / InferGuard
Status: execution spec

## User instruction

Since LMCache PR #3255 exists, update the InferGuard CLI repo to consume the new LMCache MP observability surface without requiring any vLLM changes, then test again on Modal H100.

User phrasing: "So since we made this PR, without any changes to vllm ... we update our InferGuard cli repo to match this and test this on Modal H100 to verify again."

## Classification

- InferGuard CLI parser/report update: AUTO
- Local tests and docs/claim ledger update: AUTO
- One Modal H100 smoke using existing runners: AUTO because user explicitly requested it
- Any vLLM code change: REVIEW, default NO
- Any new upstream PR beyond InferGuard local branch: REVIEW
- Any broad LMCache PR scope expansion: REVIEW

## Non-negotiable direction

Do **not** modify vLLM.

LMCache PR #3255 makes LMCache MP the source of truth for these signals. InferGuard should consume LMCache evidence downstream.

Correct boundary:

```text
vLLM LMCacheMPConnector traffic
  -> LMCache MP adapter/server
  -> LMCache observability subscriber
  -> LMCache metrics/evidence files
  -> InferGuard compat/coverage/diagnose/report CLI
```

vLLM does not need to export copied LMCache metrics for this task.

## Source context

LMCache PR #3255:
- URL: https://github.com/LMCache/LMCache/pull/3255
- Scope: L0 GPU KV block allocation observability for vLLM -> LMCache MP.
- New OTel/Prometheus counters:
  - `lmcache_mp.l0_block_allocation_records`
  - `lmcache_mp.l0_block_allocated_blocks`
- Optional redacted boundary evidence schema:
  - `inferguard-l0-block-boundary-event/v1`
- Boundary stages expected:
  - vLLM adapter before queue submit
  - LMCache server receive / EventBus publish
  - L0 lifecycle subscriber processing
- Boundary evidence must not include token IDs or raw block IDs.

Existing InferGuard context:
- The repo already supports LMCache MP modes and older `lmcache_mp_l0_block_*`/lifecycle evidence in Packet B-style flows.
- This task updates the CLI to recognize PR #3255's explicit allocation counters and optional JSONL evidence as first-class downstream evidence.
- Prior docs distinguish that vLLM `LMCacheMPConnector.build_prom_metrics()` returns `None`; MP observability comes from standalone LMCache server metrics, not vLLM metrics.

## Evidence standard

Claim status vocabulary:
- `fixture_tested`: parser/report behavior proven by sanitized fixture only.
- `measured`: live Modal H100 artifact produced the metric/evidence and InferGuard accepted it.
- `blocked`: runner or dependency prevented verification.
- `not_proven`: expected but no artifact.
- `not_applicable`: vLLM-side metric bridge not required for this task.

Rules:
- Synthetic fixtures do not prove H100 behavior.
- H100 smoke proves LMCache/vLLM app telemetry only if artifacts contain the required metrics/evidence and InferGuard reports accept them.
- Do not claim DCGM/NVML hardware utilization, HBM, NVLink, PCIe, or power telemetry unless a sampler produced accepted samples.
- Do not claim performance improvement. This is observability verification.

## Implementation scope

Update InferGuard CLI/reporting so PR #3255 evidence is first-class in:

- LMCache metrics adapter / parser
- LMCache compatibility report
- observability coverage report
- diagnose-bottleneck or operator summary if currently used for LMCache gaps
- docs/coverage matrix or SDLC report as needed
- sanitized fixtures and tests

Expected support:

1. Recognize metric families:
   - `lmcache_mp.l0_block_allocation_records`
   - `lmcache_mp.l0_block_allocated_blocks`

2. Recognize optional boundary JSONL:
   - schema/version: `inferguard-l0-block-boundary-event/v1`
   - fields may include source component, stage, timestamp, request id, block count, metric update count
   - fields must exclude raw tokens and raw block IDs

3. Report statuses:
   - `populated`: metric family exists and sample value > 0, or boundary records present with valid stages
   - `zero`: metric family exists but samples are zero and no positive boundary evidence
   - `missing`: metric family absent and boundary evidence absent
   - `blocked`: runner/config prevents collection or evidence file absent when explicitly requested

4. Keep old accepted LMCache MP evidence behavior intact.

## TDD plan

### RED 1: metrics recognition

Add/extend a fixture with PR #3255 metric names:

```text
# HELP lmcache_mp_l0_block_allocation_records ...
# TYPE lmcache_mp_l0_block_allocation_records counter
lmcache_mp_l0_block_allocation_records{model_name="Qwen/Qwen3-8B"} 3
# HELP lmcache_mp_l0_block_allocated_blocks ...
# TYPE lmcache_mp_l0_block_allocated_blocks counter
lmcache_mp_l0_block_allocated_blocks{model_name="Qwen/Qwen3-8B"} 128
```

Note: if the parser canonicalizes dots to underscores or vice versa, preserve both raw family and normalized family in the report.

Failing assertion before implementation:
- compat/coverage does not currently mark PR3255 L0 allocation counters as populated.

### GREEN 1

Implement recognition and status output with minimal code.

### RED 2: boundary evidence JSONL

Add sanitized fixture lines for `inferguard-l0-block-boundary-event/v1` with adapter/server/subscriber stages.

Failing assertions before implementation:
- boundary file is ignored or not surfaced in coverage/compat.

### GREEN 2

Parse boundary evidence and expose accepted/redacted status.

### RED 3: negative evidence

Add tests for:
- metric family missing
- metric family present but zero
- malformed boundary evidence
- boundary evidence containing forbidden token/raw-block fields should be rejected or flagged

### GREEN 3

Implement missing/zero/malformed/redaction status behavior.

### REFACTOR gate

Run focused suite:

```bash
uv run pytest tests/test_lmcache_metrics_adapter.py -q
uv run pytest tests/test_observability_coverage.py -q
uv run pytest tests/test_lmcache_packet.py -q
uv run pytest tests/test_diagnose_bottleneck.py -q
uv run pytest tests/test_lmcache_live_fixtures.py -q
uv run pytest tests/test_lmcache_mp_modal_packet_lab.py -q
uv run mkdocs build
```

If some exact test files do not exist, run the nearest existing LMCache/observability tests and report substitutions.

## Modal H100 smoke

Run only after local focused gates pass.

Use existing runner. Default command:

```bash
INFERGUARD_LMCACHE_LOCAL_SOURCE=/Users/chen/Projects/LMCache \
  modal run scripts/lmcache_mp_modal_packet_lab.py --packet b
```

Required H100 acceptance evidence:

- Modal run URL or app id
- local artifact path under `/Users/chen/Projects/inferguard/modal-out/`
- `packet_manifest.json`
- `lmcache_compat_report.json`
- `observability_coverage.json`
- `diagnose-bottleneck/bottleneck_diagnosis.json`
- PR3255 metrics present and classified:
  - `lmcache_mp.l0_block_allocation_records` or normalized equivalent
  - `lmcache_mp.l0_block_allocated_blocks` or normalized equivalent
- boundary evidence present if `INFERGUARD_L0_BLOCK_BOUNDARY_EVIDENCE_PATH` is enabled by the runner
- detected mode remains `mp`
- failure reasons remain `[]`

If the existing Packet B runner only emits older `lmcache_mp_l0_block_*` names, update the runner/config to enable PR3255 boundary evidence from local LMCache source, but do not modify vLLM.

## Docs/report updates

Add or update a dated SDLC report under `docs/sdlc/` recording:

- local test commands and results
- exact changed files
- Modal command
- Modal URL/app id
- local artifact path
- metric families observed
- boundary evidence status
- claim ledger:
  - InferGuard parser support for PR3255 metrics: fixture_tested or measured
  - Modal H100 PR3255 evidence: measured only if artifact contains new metrics/evidence
  - vLLM changes: not_applicable
  - DCGM/NVML hardware telemetry: not_proven unless sampled

Update coverage docs if status changes.

## Forbidden changes

- Do not edit vLLM.
- Do not add InferGuard code to LMCache PR #3255.
- Do not broaden LMCache PR #3255.
- Do not claim performance improvement.
- Do not stage unrelated dirty files.
- Do not import raw prompts/secrets into fixtures.
- Do not force-push any repo.

## Commit policy

Commit only after:

- focused tests pass
- H100 smoke either passes or is recorded as blocked with exact error
- docs/claim ledger updated
- unrelated dirty work preserved

Suggested commit message:

```text
feat: consume LMCache PR3255 L0 allocation evidence
```

## Final output contract

Return founder-facing summary with:

- changed files
- local tests run and pass/fail
- Modal H100 run URL/app id
- local artifact path
- whether PR3255 metrics/evidence were measured or blocked
- statement that no vLLM changes were made
- commit SHA and push status if committed

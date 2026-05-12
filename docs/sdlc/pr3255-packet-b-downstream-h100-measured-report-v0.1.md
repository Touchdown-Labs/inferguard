# PR3255 downstream Packet B H100 measured report v0.1

Date: 2026-05-11
Branch: `ocwc/packet-b-l0-lifecycle-overlay`

## Scope

InferGuard was updated to consume LMCache PR #3255 downstream evidence without vLLM changes.

## Changed files

- `src/inferguard/compat.py`
- `src/inferguard/observability_coverage.py`
- `src/inferguard/cli.py`
- `scripts/lmcache_mp_modal_packet_lab.py`
- `tests/test_lmcache_metrics_adapter.py`
- `tests/test_observability_coverage.py`
- `docs/prompts/2026-05-11-inferguard-pr3255-downstream-h100-v0.1.md`
- `docs/sdlc/pr3255-packet-b-downstream-h100-measured-report-v0.1.md`

Pre-existing dirty files intentionally left untouched: `docs/getting-started/quick-start.md`, `uv.lock`, `docs/prompts/inferguard-rebase-smoke-verification-v0.1.md`.

## Local verification

- `uv run pytest tests/test_lmcache_metrics_adapter.py -q -k pr3255` — passed, 3 passed / 67 deselected.
- `uv run pytest tests/test_lmcache_metrics_adapter.py tests/test_observability_coverage.py tests/test_lmcache_packet.py tests/test_diagnose_bottleneck.py tests/test_lmcache_live_fixtures.py tests/test_lmcache_mp_modal_packet_lab.py -q` — passed, 127 passed / 65 skipped.
- `uv run mkdocs build` — passed.
- After runner boundary-evidence wiring: `uv run pytest tests/test_lmcache_metrics_adapter.py tests/test_observability_coverage.py tests/test_lmcache_mp_modal_packet_lab.py -q` — passed, 120 passed.

## Modal H100 Packet B run

Command:

```bash
INFERGUARD_LMCACHE_LOCAL_SOURCE=/Users/chen/Projects/LMCache modal run scripts/lmcache_mp_modal_packet_lab.py --packet b
```

Modal run URL/app id:

- `https://modal.com/apps/ocwc22/main/ap-Vz0QD1FjLH33nKUYSOcEBR`

Local artifact path:

- `/Users/chen/Projects/inferguard/modal-out/pulls/20260511T224306Z/20260511T224306Z`

Required artifacts present:

- `lmcache-packet/packet_manifest.json`
- `lmcache_compat_report.json`
- `observability_coverage.json`
- `diagnose-bottleneck/bottleneck_diagnosis.json`
- `l0_block_boundary_events.jsonl`
- `l0_block_boundary_evidence.json`

Observed PR3255 metric families in `lmcache_metrics_loaded.prom`:

```text
lmcache_mp_l0_block_allocation_records_total{instance_id="84",model_name="Qwen/Qwen3-8B"} 336.0
lmcache_mp_l0_block_allocated_blocks_total{instance_id="84",model_name="Qwen/Qwen3-8B"} 11692.0
```

Compat report status:

- `detected_mode`: `mp`
- `failure_reasons`: `[]`
- `lmcache_mp/l0_allocation_counters`: `populated`
- `lmcache_l0_boundary/redacted_jsonl`: `populated`

Boundary evidence status:

- Schema: `inferguard-l0-block-boundary-event/v1`
- `claim_status`: `measured`
- `accepted_count`: 1008
- `rejected_count`: 0
- `raw_tokens_recorded`: false
- `raw_block_ids_recorded`: false
- Stage counts:
  - `report_block_allocation_mq_submit`: 336
  - `report_block_allocation_received`: 336
  - `l0_lifecycle_subscriber_processed`: 336

Observability coverage status:

- `detected_lmcache_mode`: `mp`
- `lmcache_l0_boundary` surface: `complete`

## Claim ledger

| Claim | Status | Evidence |
|---|---:|---|
| InferGuard parser/report support for PR3255 L0 allocation counters | `measured` | Local tests plus Modal artifact `lmcache_compat_report.json` accepted `l0_allocation_counters` as `populated`. |
| InferGuard optional PR3255 boundary JSONL support | `measured` | Local tests plus Modal artifact accepted 1008 redacted v1 rows with zero rejections. |
| Modal H100 PR3255 downstream evidence | `measured` | H100 run `ap-Vz0QD1FjLH33nKUYSOcEBR`, local artifact path above. |
| vLLM changes | `not_applicable` | No vLLM files modified for this task. Existing runner overlays the local connector as before; this task did not edit vLLM. |
| DCGM/NVML hardware telemetry | `not_proven` | No sampler-produced accepted DCGM/NVML samples were claimed. |
| Performance improvement | `not_proven` | No performance improvement claimed; this was observability verification only. |

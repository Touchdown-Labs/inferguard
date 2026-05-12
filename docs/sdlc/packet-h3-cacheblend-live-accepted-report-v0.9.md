# Packet H3 CacheBlend Live Accepted Report v0.9

Date: 2026-05-10
Status: accepted by local artifact reclassification

## Artifact

- Modal run: `https://modal.com/apps/ocwc22/main/ap-wlmFK2sEYs6VH11zdeFuHf`
- Local pull: `modal-out/pulls/h3-cacheblend-20260510T221217Z/20260510T221217Z`
- Fixture: `tests/fixtures/lmcache_live/packet_h3/`

## Root cause

The artifact had valid CacheBlend runtime evidence, but `lmcache-compat --expect-mode auto --fail-on missing-required` treated `lmcache_blend_*` metrics as MP-like. That produced `detected_mode=mixed` / `vllm_mp_lmcache` and required MP-only families (`storage_manager`, `lookup_tokens`, `l1_counters`, `l1_memory`) that are not required for embedded CacheBlend.

## Fix

- Classify CacheBlend as `embedded_cacheblend` / `vllm_embedded_cacheblend` when embedded LMCache metrics plus `lmcache_blend_*` metrics or measured `cb.*` OTel spans are present.
- Make MP families not applicable for H3 CacheBlend.
- Require CacheBlend-specific lookup/retrieve metrics plus measured cb.* OTel evidence.
- Preserve A-F/G1/H1 MP strictness.

## Verification

- `uv run pytest tests/test_lmcache_metrics_adapter.py -k 'cacheblend_vllm_artifact_shape or cacheblend_requires_metrics'`
- `uv run pytest tests/test_lmcache_live_fixtures.py tests/test_lmcache_metrics_adapter.py tests/test_observability_coverage.py -q` → `92 passed`
- `uv run --with pytest --with pytest-asyncio --with aiohttp --with msgpack pytest -q tests/test_lmcache_metrics_adapter.py tests/test_observability_coverage.py tests/test_lmcache_mp_modal_packet_lab.py tests/test_lmcache_packet.py tests/test_collect_metrics.py tests/test_diagnose_bottleneck.py tests/test_lmcache_otel.py tests/test_lmcache_trace.py tests/test_lmcache_lookup_hash.py` → `153 passed, 65 skipped`
- `uv run mkdocs build` → green

## Local artifact pipeline

- `lmcache-compat`: `detected_mode=embedded_cacheblend`, `failure_reasons=0`
- `observability-coverage`: `detected_lmcache_mode=embedded_cacheblend`
- `diagnose-bottleneck`: measured compat evidence preserved; verdict remains `not_enough_evidence` because this local job contains only the H3 compat/log evidence, not a full request-profile bundle.

No H100 rerun was required.

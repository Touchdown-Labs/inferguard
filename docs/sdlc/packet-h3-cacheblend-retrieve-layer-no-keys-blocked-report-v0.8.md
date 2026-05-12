# Packet H3 CacheBlend retrieve_layer no-key blocked report v0.8

Date: 2026-05-10
Repo: `/Users/chen/Projects/inferguard`
Lane: H3-only vLLM + LMCache + InferGuard CLI
Status: blocked, score unchanged

## Scope

This pass was H3-only. No H2/SGLang, Mooncake, DLM, A-F, G1, or H1 reruns were performed.

## Root cause

The H3 artifact `20260510T214803Z` showed LMCache `LMCacheEngine.retrieve_layer` entering the no-key layerwise retrieval path from CacheBlend. In local LMCache source, `mem_obj_consumer` and `to_count_down` are assigned only inside `if keys:`, but the function unconditionally synchronizes `next(mem_obj_consumer)` and unpins `to_count_down` after the `else` path.

That no-key path yielded the expected per-layer `None` values, then crashed before InferGuard report generation:

```text
File "/opt/lmcache/lmcache/v1/cache_engine.py", line 1034, in retrieve_layer
  next(mem_obj_consumer)
UnboundLocalError: cannot access local variable 'mem_obj_consumer' where it is not associated with a value
```

## RED/GREEN proof

RED target:

```bash
cd /Users/chen/Projects/inferguard
uv run pytest -q tests/test_lmcache_embedded_advanced_modal_packet_lab.py -q
```

A new test now reproduces the no-key `retrieve_layer` shape and proves the H3 runtime source patch must initialize `mem_obj_consumer` / `to_count_down` before the branch and guard the final sync/unpin block.

GREEN gate after local fix:

```bash
cd /Users/chen/Projects/inferguard
uv run pytest -q tests/test_lmcache_embedded_advanced_modal_packet_lab.py tests/test_lmcache_live_fixtures.py tests/test_observability_coverage.py
# 57 passed, 1 skipped
```

## Single authorized H3 rerun

- Modal app: https://modal.com/apps/ocwc22/main/ap-4tEKdQ3t1GfmFxUlcNuVF2
- Intended packet: `run_packet_h3_cacheblend`
- Remote artifact: `lmcache-embedded-advanced-lab:/packet-h3-cacheblend/20260510T215929Z`
- Local artifact: `/Users/chen/Projects/inferguard/modal-out/pulls/h3-cacheblend-20260510T215929Z/20260510T215929Z`

Progress preserved:

- `lmcache_otel.jsonl` exists and is non-empty.
- `lmcache_blend_metrics.prom` exists and includes `lmcache_blend_lookup_requests_total`, `lmcache_blend_lookup_requested_tokens_total`, `lmcache_blend_lookup_hit_tokens_total`, `lmcache_blend_retrieve_requests_total`, and `lmcache_blend_retrieve_chunks_total`.
- `lmcache_retrieve_layer_no_keys_patch.json` exists and records the H3 runtime source-patch intent.

Blocked result:

- No accepted `packet_h3` fixture imported.
- No `engine_metrics_loaded.prom`, `lmcache_compat_report.json`, or `observability_coverage.json` was produced.
- The first runtime patch guarded the final sync but failed to insert the pre-branch `mem_obj_consumer = None` initializer because its source predicate matched `if mem_obj_consumer is not None` as a substring. The live run therefore still failed with `UnboundLocalError`, now at the guarded line.

```text
File "/opt/lmcache/lmcache/v1/cache_engine.py", line 1034, in retrieve_layer
  if mem_obj_consumer is not None:
UnboundLocalError: cannot access local variable 'mem_obj_consumer' where it is not associated with a value
```

## Post-run local fix

After the single allowed H3 rerun was spent, the H3 runtime source patch was corrected locally to require the exact assignment line `\n        mem_obj_consumer = None\n`, insert the initializer before `request_configs`, and fail fast if the initializer, `to_count_down`, or guarded sync is absent.

This local correction is tested but not live-rerun in this pass because the cost guard allowed only one H3 rerun.

## Result

Do not import a `packet_h3` fixture. Do not run I1. Score remains 96/100.

## Exact next action

Spend the next authorized live run only after reviewing the corrected local H3 source patch:

```bash
cd /Users/chen/Projects/inferguard
modal run scripts/lmcache_embedded_advanced_modal_packet_lab.py::run_packet_h3_cacheblend
```

Accept H3 only if the run completes traffic, generates InferGuard reports, and preserves non-empty `lmcache_otel.jsonl` with `cb.*` plus observed `lmcache_blend_*` metrics.

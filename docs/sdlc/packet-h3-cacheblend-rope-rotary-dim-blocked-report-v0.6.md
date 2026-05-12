# Packet H3 CacheBlend RoPE / Rotary Dim Blocked Report v0.6

Date: 2026-05-10
Status: H3 RoPE `rope_parameters` keyword blocker cleared locally; H3 still blocked before `/health`; score remains 96/100

## Scope

This pass was H3-only. It touched only the H3 CacheBlend runner overlay and its tests. H2/SGLang, Mooncake, and DLM were not touched or rerun.

## RoPE root cause and strategy

Local LMCache CacheBlend calls:

```text
lmcache.v1.compute.positional_encoding.get_fused_rope -> vllm_get_rope(..., rope_parameters=...)
```

The previous live H3 artifact showed the installed vLLM runtime rejecting `rope_parameters` even though the local vLLM checkout currently exposes a newer-compatible `get_rope(..., rope_parameters=...)` signature. The H3-only strategy is therefore runtime-signature adaptation in the existing `sitecustomize.py` overlay, not broad dependency movement.

The overlay now inspects LMCache's imported `positional_encoding.vllm_get_rope` signature and:

- preserves `rope_parameters` when the installed vLLM function supports it;
- maps `rope_parameters["rope_type"]` to older `rope_scaling["type"]` when needed;
- maps `rope_theta` to `base` when the older signature exposes `base`;
- maps or derives `rotary_dim` from `rope_dim` or `head_size * partial_rotary_factor` when the older signature requires it;
- filters unsupported kwargs such as `dual_chunk_attention_config`.

This keeps the fix local to the H3 diagnostic packet and avoids patching vLLM or LMCache source globally.

## RED proof

```bash
cd /Users/chen/Projects/inferguard
uv run pytest -q tests/test_lmcache_embedded_advanced_modal_packet_lab.py -k 'rope_patch'
# before shim: 1 failed, 1 passed, 24 deselected
# failure: TypeError: old_vllm_get_rope() got an unexpected keyword argument 'rope_parameters'
```

## GREEN proof before Modal rerun

```bash
cd /Users/chen/Projects/inferguard
uv run pytest -q tests/test_lmcache_embedded_advanced_modal_packet_lab.py -k 'rope_patch'
# 2 passed, 24 deselected in 0.28s

uv run pytest -q tests/test_lmcache_embedded_advanced_modal_packet_lab.py tests/test_lmcache_live_fixtures.py tests/test_observability_coverage.py
# 51 passed in 0.72s
```

## Single H3 rerun result

- Modal app: https://modal.com/apps/ocwc22/main/ap-F8ehy0FYLZTasK1gvdKJ1p
- Intended packet: `run_packet_h3_cacheblend`
- Remote artifact: `lmcache-embedded-advanced-lab:/packet-h3-cacheblend/20260510T195425Z`
- Local artifact: `/Users/chen/Projects/inferguard/modal-out/pulls/h3-cacheblend-20260510T195425Z/20260510T195425Z`
- Result: blocked before `/health`; no traffic; no accepted fixture imported.

Progress proved by artifact:

- `vllm_cacheblend_model_tracker_patch.json` includes `rope_compat: map LMCache rope_parameters onto installed vLLM get_rope signature when needed`.
- The previous fatal `TypeError: get_rope() got an unexpected keyword argument 'rope_parameters'` is not present.
- The run reaches the shim wrapper and fails after keyword mapping.

New blocker:

```text
TypeError: get_rope() missing 1 required positional argument: 'rotary_dim'
```

Trace path:

```text
LMCache LMCBlender -> infer_model_from_vllm -> LMCQwen3Model ->
LMCModelBase.__init__ -> get_fused_rope -> vllm_get_rope ->
sitecustomize.py::_inferguard_rope_compat_get_rope -> original_get_rope(...)
```

The local shim has now been extended to derive `rotary_dim` for the older signature. This is locally tested but not live-rerun in this pass because the cost guard allowed only one H3 rerun.

## Missing score-moving proof

- no `/health`
- no traffic
- no `engine_metrics_loaded.prom`
- no `lmcache_otel.jsonl`
- no `cb.*` spans
- no compact H3 fixture

## Result

No H3 fixture was imported. I1 release readiness was not run. Score remains 96/100.

## Exact next engineering command

Use the already-green local patch and spend the next allowed live run only on H3 CacheBlend:

```bash
cd /Users/chen/Projects/inferguard
modal run scripts/lmcache_embedded_advanced_modal_packet_lab.py::run_packet_h3_cacheblend
```

Do not rerun A-F, G1, H1, H2/SGLang, Mooncake, or DLM for this blocker.

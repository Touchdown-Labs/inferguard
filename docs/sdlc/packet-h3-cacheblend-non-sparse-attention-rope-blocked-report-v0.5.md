# Packet H3 CacheBlend Non-Sparse Attention / RoPE Blocked Report v0.5

Date: 2026-05-10
Status: H3 FlashInfer dependency blocker cleared; H3 still blocked before `/health`; score remains 96/100

## Scope

This pass was H3-only. It touched the H3 CacheBlend runner patch and its local tests. H2/SGLang, Mooncake, and DLM were not touched or rerun.

## Root cause and strategy

LMCache CacheBlend supports a non-sparse attention path: `infer_attn_backend_from_vllm()` dispatches `FlashAttentionImpl` with `enable_sparse=False` to `LMCFlashAttnBackend`. LMCache docs/examples only opt into FlashInfer for sparse CacheBlend via `LMCACHE_EXTRA_CONFIG={"enable_sparse": true}` and `VLLM_ATTENTION_BACKEND=FLASHINFER`.

The previous H3 failure was caused by `lmcache.v1.compute.attention.utils` eagerly importing `flash_infer_sparse`, which imports the optional `flashinfer` package even though this diagnostic packet does not enable sparse attention.

Chosen strategy: do not install broad `flashinfer`/`vllm[flashinfer]` extras for this packet. Preserve the existing vLLM/transformers/tokenizers pins and patch only the H3 `sitecustomize.py` runtime hook so `attention.utils` remains lazy: non-sparse FlashAttention imports `LMCFlashAttnBackend`; sparse FlashInfer is imported only if `enable_sparse=True`.

## RED proof

```bash
cd /Users/chen/Projects/inferguard
uv run pytest -q tests/test_lmcache_embedded_advanced_modal_packet_lab.py -k 'flashinfer or lazy_attention'
# before fix: 2 failed, 22 deselected
# failures: missing patch["attention_backend"] and no lazy attention_utils patch
```

## GREEN proof before Modal rerun

```bash
cd /Users/chen/Projects/inferguard
uv run pytest -q tests/test_lmcache_embedded_advanced_modal_packet_lab.py -k 'flashinfer or lazy_attention'
# 2 passed, 22 deselected in 0.37s

uv run pytest -q tests/test_lmcache_embedded_advanced_modal_packet_lab.py tests/test_lmcache_live_fixtures.py tests/test_observability_coverage.py
# 49 passed in 0.83s
```

## Single H3 rerun result

- Modal app: https://modal.com/apps/ocwc22/main/ap-BurUdsYrC9LY6ie4sNOxA7
- Intended packet: `run_packet_h3_cacheblend`
- Remote artifact: `lmcache-embedded-advanced-lab:/packet-h3-cacheblend/20260510T191419Z`
- Local artifact: `/Users/chen/Projects/inferguard/modal-out/pulls/h3-cacheblend-20260510T191419Z/20260510T191419Z`
- Result: blocked before `/health`; no traffic; no accepted fixture imported.

Progress proved by artifact:

- `vllm_cacheblend_model_tracker_patch.json` includes `attention_backend: lazy non-sparse FlashAttention path for CacheBlend`.
- `engine.log` reports `Using Flash Attention backend on V1 engine.`
- `engine.log` again proves `Registering vllm model for vllm-instance` followed by `Creating blender for vllm-instance`.
- The previous fatal `ModuleNotFoundError: No module named 'flashinfer'` is not present in this artifact.

New blocker:

```text
TypeError: get_rope() got an unexpected keyword argument 'rope_parameters'
```

Trace path:

```text
LMCache LMCBlender -> infer_model_from_vllm -> LMCQwen3Model ->
LMCModelBase.__init__ -> get_fused_rope -> vllm_get_rope(..., rope_parameters=...)
```

This indicates the local LMCache CacheBlend positional-encoding path is calling a newer/different vLLM `get_rope` signature than the pinned vLLM `0.10.2` runtime exposes.

The vLLM usage telemetry `py-cpuinfo` JSONDecodeError appears in a background thread again, but it is not the fatal engine-start blocker in this run.

## Missing score-moving proof

- no `/health`
- no traffic
- no `engine_metrics_loaded.prom`
- no `lmcache_otel.jsonl`
- no `cb.*` spans
- no compact H3 fixture

## Result

No H3 fixture was imported. I1 release readiness was not run. Score remains 96/100.

## Exact next engineering task

Add a TDD-backed H3-only compatibility strategy for LMCache CacheBlend's `get_fused_rope` / vLLM `get_rope` signature mismatch while preserving the existing vLLM/transformers/tokenizers pins. Do not rerun H3 again without explicit approval because the one allowed rerun for this pass was spent.

Current local gate to keep green:

```bash
cd /Users/chen/Projects/inferguard
uv run pytest -q tests/test_lmcache_embedded_advanced_modal_packet_lab.py tests/test_lmcache_live_fixtures.py tests/test_observability_coverage.py
```

# Packet H3 CacheBlend vLLM Registration Fixed / FlashInfer Blocked Report v0.4

Date: 2026-05-10
Status: original H3 `vllm-instance` model-registration blocker fixed; H3 still blocked before `/health`; score remains 96/100

## Scope

This H3-only retry touched only the H3 CacheBlend runner patch and its local tests. H2/SGLang, Mooncake, and DLM remained paused and were not rerun.

## Root cause fixed

The previous H3 artifact failed because LMCache created the CacheBlend blender during vLLM KV connector initialization, before vLLM had loaded the model:

- previous Modal app: https://modal.com/apps/ocwc22/main/ap-pjSGuideEiSL3gGFgjaXlh
- previous local artifact: `/Users/chen/Projects/inferguard/modal-out/pulls/h3-cacheblend-20260509T225829Z/20260509T225829Z`
- previous blocker: `ValueError: vllm model for vllm-instance not found.`

The local H3 `sitecustomize.py` patch now defers `LMCBlenderBuilder.get_or_create(...)` when `VLLMModelTracker` has not registered `vllm-instance` yet, then registers the loaded vLLM model from `GPUModelRunner.load_model` and creates the real blender.

## RED proof

```bash
cd /Users/chen/Projects/inferguard
uv run pytest -q tests/test_lmcache_embedded_advanced_modal_packet_lab.py -k 'defers_blender_until_vllm_model_load or model_tracker_patch_registers_loaded_vllm_model'
# before fix: 2 failed, 20 deselected
# failure included: ValueError: vllm model for vllm-instance not found.
```

## GREEN proof before Modal rerun

```bash
cd /Users/chen/Projects/inferguard
uv run pytest -q tests/test_lmcache_embedded_advanced_modal_packet_lab.py -k 'defers_blender_until_vllm_model_load or model_tracker_patch_registers_loaded_vllm_model'
# 2 passed, 20 deselected

uv run pytest -q tests/test_lmcache_embedded_advanced_modal_packet_lab.py tests/test_lmcache_live_fixtures.py tests/test_observability_coverage.py
# 47 passed in 0.80s
```

## Single H3 rerun result

- Modal app: https://modal.com/apps/ocwc22/main/ap-BcWgP9Q8YhH6g7tG0IZFs3
- Intended packet: `run_packet_h3_cacheblend`
- Remote artifact: `lmcache-embedded-advanced-lab:/packet-h3-cacheblend/20260510T183211Z`
- Local artifact: `/Users/chen/Projects/inferguard/modal-out/pulls/h3-cacheblend-20260510T183211Z/20260510T183211Z`
- Result: blocked before `/health`; no traffic; no accepted fixture imported.

Progress proved by `engine.log`:

- `Registering vllm model for vllm-instance`
- `Creating blender for vllm-instance`

This clears the previous model-registration timing blocker.

New blocker:

```text
ModuleNotFoundError: No module named 'flashinfer'
```

The import happens after the vLLM model is loaded and registered, while LMCache creates `LMCBlender` and imports the Qwen3 CacheBlend model path:

```text
lmcache.v1.compute.models.qwen3 -> lmcache.v1.compute.models.base ->
lmcache.v1.compute.attention.utils -> lmcache.v1.compute.attention.flash_infer_sparse ->
from flashinfer import VariableBlockSparseAttentionWrapper
```

The vLLM usage telemetry `py-cpuinfo` JSONDecodeError also appears again in a background thread, but it is not the fatal engine-start blocker in this run.

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

Add a TDD-backed H3 runtime dependency strategy for LMCache CacheBlend's FlashInfer import path, then run the same local gate before any future H3 rerun:

```bash
cd /Users/chen/Projects/inferguard
uv run pytest -q tests/test_lmcache_embedded_advanced_modal_packet_lab.py tests/test_lmcache_live_fixtures.py tests/test_observability_coverage.py
```

Next live command after that local gate passes:

```bash
modal run scripts/lmcache_embedded_advanced_modal_packet_lab.py::run_packet_h3_cacheblend
```

# Packet H2/H3 Cost-Gated Blocked Report v0.3

Date: 2026-05-09
Status: H2 paused backend expansion; H3 active blocker; score remains 96/100

## Scope

This report records the single authorized H2 rerun and single authorized H3 rerun after local TDD fixes for the v0.2 blockers. No A-F, G1, or H1 reruns were performed. After the focus decision, H2/SGLang is paused backend expansion; H3 CacheBlend/vLLM model-registration timing is the active vLLM + LMCache finish-line blocker.

## RED proof

Before implementation, the focused runner test failed on the three new contracts:

```bash
cd /Users/chen/Projects/inferguard
uv run pytest -q tests/test_lmcache_embedded_advanced_modal_packet_lab.py -q
# failed: MODAL_SGLANG_PYTHON_SOURCE missing
# failed: H3 patch doc/code still referenced GPUWorker.load_model
# failed: LMCACHE_TRACK_USAGE missing from runtime/runner env
```

## Fixes shipped before reruns

- H2 image build cost: Modal now copies only `/Users/chen/Projects/sglang/python` to `/opt/sglang/python` and ignores `.git`, `.venv`, `__pycache__`, `uv.lock`, and `*.egg-info` instead of copying the whole local SGLang checkout.
- H3 vLLM hook: `sitecustomize.py` now patches version-tolerant `GPUModelRunner.load_model` import locations and no longer imports nonexistent `GPUWorker` from `vllm.v1.worker.gpu_worker`.
- H3 py-cpuinfo guard: H packet runtime and runner env set `LMCACHE_TRACK_USAGE=false`, bypassing LMCache's non-critical usage telemetry path that called `cpuinfo.get_cpu_info()` and failed with `json.decoder.JSONDecodeError` in the previous artifact.

## GREEN proof before Modal reruns

```bash
cd /Users/chen/Projects/inferguard
uv run pytest -q tests/test_lmcache_embedded_advanced_modal_packet_lab.py
# 21 passed in 0.16s

uv run pytest -q tests/test_lmcache_embedded_advanced_modal_packet_lab.py tests/test_lmcache_live_fixtures.py tests/test_observability_coverage.py
# 46 passed in 0.46s
```

## Cost-gated H2 rerun — paused backend expansion

- Modal app: https://modal.com/apps/ocwc22/main/ap-uxwSka8BhbIPgBAnG0IC9n
- Intended packet: `run_packet_h2_sglang_embedded`
- Local artifact: `/Users/chen/Projects/inferguard/modal-out/pulls/h2-20260509T225427Z/20260509T225427Z`
- Progress: image build timeout fixed. The final editable-source image `im-hPcjVQETWY9NR28VhTQmV9` built in 88.46s, and the Modal mount list shows `/Users/chen/Projects/sglang/python` instead of the full SGLang repo.
- Blocker: primary SGLang engine exited before `/health` with code 1.
- Exact blocker: `ModuleNotFoundError: No module named 'sgl_kernel'` from `/opt/sglang/python/sglang/srt/layers/quantization/fp8_kernel.py` while importing SGLang quantization methods during `ServerArgs.get_model_config()`.
- Missing score-moving proof: no `/health`, no traffic, no `engine_metrics_loaded.prom`, no compact H2 fixture. H2 is paused and is not an active blocker for core vLLM/LMCache coverage until a TDD-backed minimal `sgl_kernel` runtime strategy exists.

## Cost-gated H3 rerun — active blocker

- Modal app: https://modal.com/apps/ocwc22/main/ap-pjSGuideEiSL3gGFgjaXlh
- Intended packet: `run_packet_h3_cacheblend`
- Local artifact: `/Users/chen/Projects/inferguard/modal-out/pulls/h3-cacheblend-20260509T225829Z/20260509T225829Z`
- Progress: previous blockers cleared. `engine.log` has no `GPUWorker` ImportError, no `json.decoder.JSONDecodeError`, no `cpuinfo` failure, and no `self.lmcache_engine is not None` assertion failure.
- Blocker: primary vLLM engine exited before `/health` with code 1 because LMCache creates the CacheBlend blender during KV connector initialization before vLLM has loaded and registered the model.
- Exact blocker: `ValueError: vllm model for vllm-instance not found.` from `VLLMModelTracker.get_model(instance_id)` in `/opt/lmcache/lmcache/v1/compute/blend/utils.py`.
- Missing score-moving proof: no `/health`, no traffic, no `engine_metrics_loaded.prom`, no `lmcache_otel.jsonl`, no `cb.*` spans, no compact H3 fixture.

## Result

No accepted H2 or H3 fixture was imported. I1 release readiness was not run. Score remains 96/100. H2/SGLang is paused backend expansion; H3 remains the active blocker for the vLLM + LMCache + InferGuard CLI finish line.

## Exact next engineering task

H3: fix CacheBlend/vLLM model-registration timing. Determine whether CacheBlend can be initialized after vLLM model load in vLLM 0.10.2, or whether the runner must use an LMCache/vLLM runtime contract that registers the model before `LMCBlenderBuilder.get_or_create()`. Add local TDD first; rerun H3 only after local gates pass.

Paused resume blocker: H2 can resume only after a TDD-backed minimal `sgl_kernel` runtime strategy exists for the SGLang launch path without installing blind full SGLang requirements.

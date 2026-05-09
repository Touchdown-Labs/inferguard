# Packet H2/H3 Cost-Gated Blocked Report v0.2

Date: 2026-05-09
Status: superseded by v0.3; score remains 96/100

## Scope

This historical report records the single authorized H2 rerun and single authorized H3 rerun after local gates. No A-F, G1, or H1 reruns were performed. Superseding focus decision: H2/SGLang is paused backend expansion; H3 CacheBlend/vLLM model-registration timing is the active vLLM + LMCache finish-line blocker.

## RED proof

### H2 SGLang embedded

- Modal app: https://modal.com/apps/ocwc22/main/ap-muTJLBHZbwWU2qaNe26qXU
- Intended packet: `run_packet_h2_sglang_embedded`
- Local artifact: none; the run failed during Modal image build before the packet function created `/out/packet-h2-sglang-embedded/<timestamp>`.
- Prior artifact retained for the previous runtime blocker: `/Users/chen/Projects/inferguard/modal-out/pulls/h2-20260509T220959Z/20260509T220959Z`
- Progress: the image build command explicitly installed `IPython` and `orjson` while preserving `vllm==0.10.2`, `transformers==4.57.6`, and `tokenizers==0.22.2`.
- Blocker: Modal image build timed out while saving/building the final editable-source image after `python -m pip install -e /opt/lmcache --no-build-isolation --no-deps`, `python -m pip install -e /opt/sglang/python --no-build-isolation --no-deps`, and `python -m pip install -e /opt/inferguard` completed.
- Exact failure line: `Image build for im-lNwqR4LJ2DATVJGA1EBxuQ failed` / `Terminating task due to error: timeout`.

### H3 CacheBlend

- Modal app: https://modal.com/apps/ocwc22/main/ap-RnrG85pKJIpQHtAi8AOt4G
- Intended packet: `run_packet_h3_cacheblend`
- Local artifact: `/Users/chen/Projects/inferguard/modal-out/pulls/h3-cacheblend-20260509T223947Z/20260509T223947Z`
- Progress: the disposable `sitecustomize.py` patch artifact was created before engine launch and records `engine_name=vllm-instance` in `vllm_cacheblend_model_tracker_patch.json`.
- Blocker 1: `sitecustomize.py` import failed on vLLM 0.10.2 because `vllm.v1.worker.gpu_worker` does not export `GPUWorker` as imported by the hook.
- Blocker 2: engine startup then failed in LMCache initialization before `/health`: `cpuinfo.get_cpu_info()` returned non-JSON output, causing `json.decoder.JSONDecodeError`, `LMCacheManager` degraded mode, `self.lmcache_engine is not None` assertion failure, and vLLM engine exit code 1.
- Missing score-moving proof: no `/health`, no traffic, no `engine_metrics_loaded.prom`, no `lmcache_otel.jsonl`, no `cb.*` spans, no compact H3 fixture.

## GREEN proof

Local gates before reruns:

```bash
cd /Users/chen/Projects/inferguard
uv run pytest -q tests/test_lmcache_embedded_advanced_modal_packet_lab.py tests/test_lmcache_live_fixtures.py tests/test_observability_coverage.py
# 44 passed in 0.51s

uv run pytest -q tests/test_launch_engine_sglang.py
# 4 skipped in 0.13s
```

Targeted TDD added:

- H2 minimal SGLang runtime deps now assert `("orjson", "IPython")` while preserving vLLM/Transformers/Tokenizers pins and avoiding full SGLang requirements.
- H3 patch tests now materialize `sitecustomize.py`, assert the `vllm-instance` mapping, and assert the patch step occurs before engine launch.

## Result

No accepted H2 or H3 fixture was imported. I1 release readiness was not run. Score remains 96/100. Superseded by v0.3: H2/SGLang is paused backend expansion, while H3 remains active.

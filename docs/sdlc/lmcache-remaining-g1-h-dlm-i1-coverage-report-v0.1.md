# LMCache remaining G1/H/DLM/I1 coverage report v0.1

Date: 2026-05-09
Owner: Touchdown Labs / InferGuard
Control SSoT: `/Users/chen/Projects/Touchdown-Labs/docs/sdlc/195-2026-05-07-lmcache-vllm-inferguard-100-coverage-ssot.md`
Implementation repo: `/Users/chen/Projects/inferguard`

## Baseline

- Starting SSoT score: 92 / 100.
- Accepted live fixtures before this pass: Packet A/B/C/D/E/F.
- Guardrail: do not claim paused backend expansion lanes as core vLLM/LMCache blockers. H1 is accepted; H2/SGLang, Mooncake, and DLM are paused; H3 CacheBlend/vLLM model-registration timing is the active finish-line blocker.

## Local gates

Required local gates passed before any H100 attempt:

```bash
cd /Users/chen/Projects/inferguard
uv run pytest tests/test_lmcache_live_fixtures.py -q       # 3 passed before edit; 4 passed after G1 test
uv run pytest tests/test_lmcache_mp_modal_packet_lab.py -q # 28 passed
uv run pytest tests/test_observability_coverage.py -q      # 21 passed
```

Additional H-lane runner-contract gate:

```bash
uv run pytest tests/test_lmcache_embedded_advanced_modal_packet_lab.py -q # 10 passed
```

Final focused verification after the G1 test landed:

```bash
uv run pytest tests/test_lmcache_live_fixtures.py -q
uv run pytest tests/test_lmcache_mp_modal_packet_lab.py -q
uv run pytest tests/test_observability_coverage.py -q
uv run pytest tests/test_lmcache_embedded_advanced_modal_packet_lab.py -q
```

Observed result: 4 passed, 28 passed, 21 passed, 10 passed.

## Matrix

| Lane | State after this pass | Evidence | Score impact |
| --- | --- | --- | --- |
| G1 diagnostic calibration | `live_validated` for accepted Packet A-F diagnostic outputs | Added non-skipping test `test_g1_diagnostic_calibration_is_pinned_by_accepted_live_packet_diagnoses` in `tests/test_lmcache_live_fixtures.py`. It pins accepted live Modal/H100 fixture diagnosis outputs: Packet A `lmcache_mp_empty_cache_salt` inferred, Packet B `lmcache_mp_l1_failures` measured, Packet C `lmcache_mp_l1_eviction_pressure` measured, Packet D `vllm_external_prefix_no_hits` inferred, Packet E `lmcache_mp_empty_cache_salt` inferred, Packet F `vllm_external_prefix_no_hits` inferred. | +4, SSoT 92 -> 96 |
| H1 embedded vLLM | `live_validated` / accepted | Accepted Modal/H100 run `https://modal.com/apps/ocwc22/main/ap-SfIwqyS0PgfNcMtHf1jvM6`; fixture `tests/fixtures/lmcache_live/packet_h1/`; strict compat `detected_mode=embedded`, `failure_reasons=[]`. | 0; advanced rung accounting remains unchanged |
| H2 SGLang embedded | `paused_backend_expansion` | Source binding and image-build optimization are fixed; cost-gated rerun `https://modal.com/apps/ocwc22/main/ap-uxwSka8BhbIPgBAnG0IC9n` stops at `ModuleNotFoundError: No module named 'sgl_kernel'`. This is not an active core vLLM/LMCache blocker. Resume only after a TDD-backed minimal `sgl_kernel` runtime strategy exists. | 0 |
| H3 CacheBlend/P2P/PD | `blocked` / active finish-line blocker | CacheBlend rerun `https://modal.com/apps/ocwc22/main/ap-pjSGuideEiSL3gGFgjaXlh` cleared the prior `GPUWorker` import and `py-cpuinfo` blockers, then failed before `/health` on `ValueError: vllm model for vllm-instance not found.` from `VLLMModelTracker.get_model(instance_id)`. | 0 |
| Mooncake | `paused_backend_expansion` / classification-only | No runnable local Mooncake source/runtime exists; current support is connector-label classification only. Resume only after a runnable Mooncake source/runtime path and packet acceptance contract exist. | 0 |
| DLM | `paused_backend_expansion` / `detection_only` | `llm-d` prefixes are detected, but `LLMD_FIELD_MAP = {}` and CLI output reports `adapter_not_implemented`; not LMCache MP proof. Resume only after a runtime contract and validated Prometheus field map exist. | 0 |
| I1 release readiness | `blocked` / partial | Docs and CLI references exist; release closeout waits on active vLLM + LMCache + InferGuard CLI finish line, starting with H3 CacheBlend/vLLM model-registration timing. | 0 |

## H100 decision log

One H100-gated live attempt was justified because H1 has a defined runner and H1 is a live-only evidence lane. The command was:

```bash
cd /Users/chen/Projects/inferguard
modal run scripts/lmcache_embedded_advanced_modal_packet_lab.py::run_packet_h1_embedded_vllm
```

Modal URL: `https://modal.com/apps/ocwc22/main/ap-DG9BBVushKHYwPFvUIEEa7`.

Outcome: blocked before live packet artifact. The image build pip step backtracked across many `vllm` versions because the H runner image installs unpinned `vllm`, `lmcache`, and `sglang` together. The run was stopped as a systemic packaging blocker. No H1 fixture was imported and no score was awarded for H1.

## Continuation: H-lane image blocker TDD and H1 rerun

The continuation pass targeted the shared embedded/advanced H runner image blocker with TDD before any new H100 runtime claim.

RED evidence:

```bash
cd /Users/chen/Projects/inferguard
uv run pytest tests/test_lmcache_embedded_advanced_modal_packet_lab.py -q
```

Observed RED: `test_embedded_advanced_image_avoids_shared_unpinned_runtime_backtracking` failed because the Modal image pip install set still contained unpinned `vllm`, `lmcache`, and `sglang`. A follow-up RED also pinned the CUDA source-build contract: the runner was still using a slim image instead of a CUDA devel base, and later proved `.env(...)` had to be applied before `.run_commands(...)` so `TORCH_CUDA_ARCH_LIST` and `CUDA_HOME` reached the LMCache source build.

GREEN evidence:

```bash
uv run pytest tests/test_lmcache_embedded_advanced_modal_packet_lab.py -q # 12 passed
uv run pytest tests/test_lmcache_live_fixtures.py -q                    # 4 passed
uv run pytest tests/test_lmcache_mp_modal_packet_lab.py -q              # 28 passed
uv run pytest tests/test_observability_coverage.py -q                   # 21 passed
```

Image-fix attempts before the final runtime blocker:

| Modal URL | State | Blocker |
| --- | --- | --- |
| `https://modal.com/apps/ocwc22/main/ap-MZ95a3k2mf5U3TykjICDhz` | image build advanced beyond pip resolver backtracking | LMCache source build failed with `CUDA_HOME environment variable is not set` |
| `https://modal.com/apps/ocwc22/main/ap-f57Af7Apv7DmdyrLPfABPx` | CUDA devel image reached LMCache source build | CUDA 13 image mismatched torch CUDA 12.8 |
| `https://modal.com/apps/ocwc22/main/ap-CRnpLXQsQqC1qFcVZ2Sxhn` | CUDA 12.8 image used | env ordering meant `TORCH_CUDA_ARCH_LIST` did not reach the build command |
| `https://modal.com/apps/ocwc22/main/ap-nwjSHdGcyYQeSxd2rqIEYL` | image built and H100 container reached runtime | vLLM CLI rejected `--kv-offloading-backend lmcache` |

Final H1 artifact after the fixed image/runtime state:

```text
/Users/chen/Projects/inferguard/modal-out/packet-h1-embedded-vllm/20260509T192422Z
```

The final H1 run produced launch proof, env snapshots, `engine.log`, and `summary.md`, but no accepted fixture. Exact blocker from `engine.log`:

```text
vllm: error: unrecognized arguments: --kv-offloading-backend lmcache
```

H2 and H3 were not run. The cost gate permits one H100 run per H lane per fixed image/runtime state, and H1 showed the next shared blocker is the embedded vLLM command contract rather than the original image dependency resolver.

Exact next code target before any further H100 run: update the H1 vLLM launch command to the current vLLM LMCache connector contract, likely `--kv-transfer-config '{"kv_connector":"LMCacheConnectorV1","kv_role":"kv_both"}'`, with a focused RED/GREEN test replacing the old `--kv-offloading-backend lmcache` proof.

## Paused backend expansion contracts

SGLang/H2, Mooncake, and DLM are paused backend expansion lanes. Do not spend H100 or treat them as active blockers for the core vLLM + LMCache + InferGuard CLI finish line.

### DLM future integration spec

Do not claim DLM support from current code. Future DLM work needs a concrete runtime contract first:

1. Define whether the target is DLM, `llm-d`, or another disaggregated-serving runtime.
2. Identify prefill, decode, and transfer metrics endpoints.
3. Populate `LLMD_FIELD_MAP` or a DLM-specific adapter from real Prometheus output.
4. Add a DLM packet runner that emits launch/config proof, request-profile artifacts, metrics timelines, `lmcache-compat`, `observability-coverage`, and `diagnose-bottleneck` outputs.
5. Import a compact sanitized live fixture only after the CLI chain passes.

## Remaining exact gap

Score after this pass: 96 / 100.

Remaining 4 points:

- Active finish line: vLLM + LMCache + InferGuard CLI coverage, with A-F, G1, and H1 accepted.
- Active blocker: H3 CacheBlend/vLLM model-registration timing (`ValueError: vllm model for vllm-instance not found`).
- Paused backend expansion: H2/SGLang at missing `sgl_kernel`; Mooncake at no runnable local source/runtime; DLM/llm-d at `adapter_not_implemented` with no validated field map.
- I1 release readiness remains blocked until the active vLLM/LMCache finish line and release docs/build/rollback gates pass.

Exact next command after fixing the H3 CacheBlend/vLLM model-registration timing with TDD:

```bash
cd /Users/chen/Projects/inferguard
modal run scripts/lmcache_embedded_advanced_modal_packet_lab.py::run_packet_h3_cacheblend
```

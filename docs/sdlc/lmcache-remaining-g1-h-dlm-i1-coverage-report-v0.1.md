# LMCache remaining G1/H/DLM/I1 coverage report v0.1

Date: 2026-05-09
Owner: Touchdown Labs / InferGuard
Control SSoT: `/Users/chen/Projects/Touchdown-Labs/docs/sdlc/195-2026-05-07-lmcache-vllm-inferguard-100-coverage-ssot.md`
Implementation repo: `/Users/chen/Projects/inferguard`

## Baseline

- Starting SSoT score: 92 / 100.
- Accepted live fixtures before this pass: Packet A/B/C/D/E/F.
- Guardrail: do not claim H1/H2/H3 or DLM support without accepted live fixtures.

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
| H1 embedded vLLM | `blocked` after image TDD fix; no accepted fixture | Runner exists: `scripts/lmcache_embedded_advanced_modal_packet_lab.py::run_packet_h1_embedded_vllm`. The original image resolver blocker is fixed by tests and code: the shared image no longer installs unpinned `vllm`, `lmcache`, and `sglang`; it pins `vllm==0.10.2`, uses a CUDA 12.8 devel image, installs local LMCache from `/opt/lmcache`, and applies CUDA build env before image build commands. Cost-gated H1 rerun `https://modal.com/apps/ocwc22/main/ap-nwjSHdGcyYQeSxd2rqIEYL` built successfully and reached runtime, then failed before health because pinned vLLM rejected the runner command: `vllm: error: unrecognized arguments: --kv-offloading-backend lmcache`. Local artifact: `/Users/chen/Projects/inferguard/modal-out/packet-h1-embedded-vllm/20260509T192422Z`. | 0 |
| H2 SGLang embedded | `runner_scaffold_exists`, not run after H1 runtime command blocker | Runner exists: `run_packet_h2_sglang_embedded`; local contract test passed. Not run because H1 exposed a shared embedded/advanced runtime contract blocker after image build succeeded. | 0 |
| H3 CacheBlend/P2P/PD | `runner_scaffold_exists` / parser-only surfaces, not run after H1 runtime command blocker | Runners exist: `run_packet_h3_cacheblend`, `run_packet_h3_p2p`, `run_packet_h3_pd`; local contract test passed. No accepted CacheBlend/P2P/PD live fixture exists. | 0 |
| DLM | `not_started` for DLM-specific support; `llm-d` detection-only exists | Search evidence: no concrete `DLM` packet runner or CLI chain exists. Code has `LLMD_FIELD_MAP: dict[str, str] = {}` and returns `adapter_not_implemented` for `llm-d`; docs say llm-d support is detection-only until `LLMD_FIELD_MAP` is validated. | 0 |
| I1 release readiness | `blocked` / partial | Docs and CLI references exist, but H1/H2/H3 accepted live fixtures are missing and full release closeout has not run. I1 cannot be marked release-ready while H1 is blocked at the vLLM command contract. | 0 |

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

## DLM future integration spec

Do not claim DLM support from current code. Future DLM work needs a concrete runtime contract first:

1. Define whether the target is DLM, `llm-d`, or another disaggregated-serving runtime.
2. Identify prefill, decode, and transfer metrics endpoints.
3. Populate `LLMD_FIELD_MAP` or a DLM-specific adapter from real Prometheus output.
4. Add a DLM packet runner that emits launch/config proof, request-profile artifacts, metrics timelines, `lmcache-compat`, `observability-coverage`, and `diagnose-bottleneck` outputs.
5. Import a compact sanitized live fixture only after the CLI chain passes.

## Remaining exact gap

Score after this pass: 96 / 100.

Remaining 4 points:

- H grouped lane: H1/H2/H3 live accepted fixtures remain missing. The original image dependency resolver blocker is fixed, but H1 is now blocked by the pinned vLLM command contract rejecting `--kv-offloading-backend lmcache`.
- I1 release readiness remains blocked until H lanes close and release docs/build/rollback gates pass.

Exact next command after fixing the H1 vLLM connector launch contract with TDD:

```bash
cd /Users/chen/Projects/inferguard
modal run scripts/lmcache_embedded_advanced_modal_packet_lab.py::run_packet_h1_embedded_vllm
```

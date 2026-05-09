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
| H1 embedded vLLM | `runner_scaffold_exists`, live attempt blocked before artifact | Runner exists: `scripts/lmcache_embedded_advanced_modal_packet_lab.py::run_packet_h1_embedded_vllm`. Local runner-contract test passed. H100 Modal attempt URL: `https://modal.com/apps/ocwc22/main/ap-DG9BBVushKHYwPFvUIEEa7`. The attempt did not reach packet execution or produce an accepted fixture because image build entered pip resolver backtracking while installing unpinned `vllm`, `lmcache`, and `sglang`. | 0 |
| H2 SGLang embedded | `runner_scaffold_exists`, not run after H1 systemic packaging blocker | Runner exists: `run_packet_h2_sglang_embedded`; local contract test passed. Not run because H1 showed the shared embedded/advanced image can stall before runtime. | 0 |
| H3 CacheBlend/P2P/PD | `runner_scaffold_exists` / parser-only surfaces, not run after H1 systemic packaging blocker | Runners exist: `run_packet_h3_cacheblend`, `run_packet_h3_p2p`, `run_packet_h3_pd`; local contract test passed. No accepted CacheBlend/P2P/PD live fixture exists. | 0 |
| DLM | `not_started` for DLM-specific support; `llm-d` detection-only exists | Search evidence: no concrete `DLM` packet runner or CLI chain exists. Code has `LLMD_FIELD_MAP: dict[str, str] = {}` and returns `adapter_not_implemented` for `llm-d`; docs say llm-d support is detection-only until `LLMD_FIELD_MAP` is validated. | 0 |
| I1 release readiness | `blocked` / partial | Docs and CLI references exist, but H1/H2/H3 accepted live fixtures are missing, the embedded/advanced image is unpinned, and full release closeout has not run. | 0 |

## H100 decision log

One H100-gated live attempt was justified because H1 has a defined runner and H1 is a live-only evidence lane. The command was:

```bash
cd /Users/chen/Projects/inferguard
modal run scripts/lmcache_embedded_advanced_modal_packet_lab.py::run_packet_h1_embedded_vllm
```

Modal URL: `https://modal.com/apps/ocwc22/main/ap-DG9BBVushKHYwPFvUIEEa7`.

Outcome: blocked before live packet artifact. The image build pip step backtracked across many `vllm` versions because the H runner image installs unpinned `vllm`, `lmcache`, and `sglang` together. The run was stopped as a systemic packaging blocker. No H1 fixture was imported and no score was awarded for H1.

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

- H grouped lane: H1/H2/H3 live accepted fixtures remain missing.
- I1 release readiness remains blocked until H lanes close and release docs/build/rollback gates pass.

Exact next command after fixing the embedded/advanced image pinning blocker:

```bash
cd /Users/chen/Projects/inferguard
modal run scripts/lmcache_embedded_advanced_modal_packet_lab.py::run_packet_h1_embedded_vllm
```

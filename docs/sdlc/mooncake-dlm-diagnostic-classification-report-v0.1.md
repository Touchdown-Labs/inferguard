# Mooncake + DLM diagnostic classification report v0.1

Date: 2026-05-09
Scope: WS-Mooncake and WS-DLM from `docs/sdlc/lmcache-sglang-mooncake-all-backends-integration-spec-v0.1.md`.

## Summary

Mooncake and DLM are **paused backend expansion** lanes and are **not live-validated** in InferGuard as of this pass. They are not active blockers for the core vLLM + LMCache + InferGuard CLI finish line.

- Mooncake state: `paused_backend_expansion` for runnable packet validation; `fixture_backed` only for SGLang connector-label parsing.
- DLM / `llm-d` state: `paused_backend_expansion` / `detection_only`; adapter intentionally returns `adapter_not_implemented` because `LLMD_FIELD_MAP = {}`.
- H100 decision: no Modal/H100 run was performed. There is no runnable local Mooncake or DLM contract that satisfies the integration spec's local/TDD acceptance gate.
- Score decision: no Touchdown SSoT score increase.

## Mooncake discovery

Workspace/source discovery found no runnable Mooncake source or runtime checkout under the loaded InferGuard/Touchdown/LMCache/vLLM workspace roots. Local filesystem discovery found only an old Inferscope prompt-export mentioning Mooncake, not a Mooncake source tree or executable runtime.

Existing InferGuard references:

- `tests/fixtures/sglang.txt` and `tests/fixtures/sglang_hicache.txt` include SGLang `sglang:kv_transfer_*{connector="mooncake"}` fixture metrics.
- `src/inferguard/disagg/adapters.py` detects connector labels, including `connector="mooncake"`, on KV-transfer metric families.
- `tests/test_disagg_adapters.py` now pins that Mooncake is currently a connector label in SGLang metrics, not proof that a runnable Mooncake runtime exists.
- `tests/test_cli_disagg.py` now pins that `inferguard disagg status --engine sglang` reports `connector="mooncake"` from local mock SGLang metrics.

Interpretation boundary:

Mooncake is currently represented as a SGLang KV-transfer connector label. That supports diagnostic classification of a metrics scrape, but it does **not** prove Mooncake runtime availability, RDMA/disaggregated serving behavior, LMCache backend behavior, or end-to-end KV movement.

## Mooncake blocked packet contract

A Mooncake packet can resume from `paused_backend_expansion` and be promoted beyond blocked/classification-only only after all prerequisites below exist:

1. A local Mooncake source/runtime checkout, or a source-backed SGLang/vLLM integration contract that names the Mooncake connector module and launch flags.
2. A local command that starts the relevant prefill/decode or transfer endpoint without GPU/H100 spend.
3. Metrics/log evidence identifying Mooncake as the active transfer backend, not just a synthetic `connector="mooncake"` label.
4. A CLI chain that emits:
   - `disagg status` JSON with prefill/decode roles and connector identity;
   - request-profile or equivalent traffic evidence;
   - transfer-byte and transfer-error counters;
   - `diagnose-bottleneck` findings when transfer stalls or errors occur.
5. Only after local gates pass: one cost-gated live packet may run and import a sanitized fixture.

Current blocker: no runnable Mooncake source/runtime contract exists locally.

Exact next command if source appears:

```bash
cd /Users/chen/Projects/inferguard
INFERGUARD_MOONCAKE_LOCAL_SOURCE=/Users/chen/Projects/<mooncake-source> \
uv run pytest tests/test_disagg_adapters.py tests/test_cli_disagg.py -q
```

Then add a Mooncake packet runner only after the source-backed local contract is known.

## DLM status

Existing InferGuard state:

- Engine detection recognizes `llmd_` and `llm_d_` prefixes as `llm-d`.
- `LLMD_FIELD_MAP = {}` in `src/inferguard/disagg/adapters.py`.
- Forced or detected `llm-d` returns `scrape_error="adapter_not_implemented"`.
- `tests/test_disagg_adapters.py` now pins the adapter-pending behavior.
- `tests/test_cli_disagg.py` now pins that `inferguard disagg status --engine llm-d --json` reports `engine="llm-d"` and `adapter_not_implemented` rather than conflating DLM with LMCache MP.

DLM is therefore `detection_only`, not `supported` and not LMCache MP proof.

## DLM promotion contract

DLM / `llm-d` can resume from `paused_backend_expansion` and move beyond `detection_only` only after a concrete runtime contract exists:

1. Decide whether the target is DLM, `llm-d`, or another disaggregated-serving runtime.
2. Identify stable prefill, decode, transfer, TTFT, TPOT, queue, and KV-transfer metric names from real Prometheus output.
3. Populate `LLMD_FIELD_MAP` from that live output.
4. Add a DLM packet or local fixture suite that runs the same CLI chain as other disaggregated-serving diagnostics.
5. Import a compact sanitized live fixture only after the runtime contract passes.

Current blocker: no concrete DLM/`llm-d` runtime contract or validated Prometheus field map exists.

## Verification

Local tests added/updated:

```bash
cd /Users/chen/Projects/inferguard
uv run pytest tests/test_disagg_adapters.py tests/test_cli_disagg.py -q
```

No H100/Modal command was run.

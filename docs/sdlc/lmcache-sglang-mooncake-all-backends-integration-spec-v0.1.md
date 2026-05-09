# LMCache + SGLang + Mooncake all-backends integration spec v0.1

## Objective
Historical backend-expansion plan for LMCache, vLLM, SGLang, and Mooncake. As of the vLLM/LMCache focus decision, the active finish line is vLLM + LMCache + InferGuard CLI coverage. SGLang, Mooncake, and DLM are paused backend expansion lanes and must not block the core finish line.

## Non-negotiables
- Do not rerun accepted A-F/G1/H1 lanes.
- Do not spend H100 until local/static/TDD gates pass and the packet has an explicit acceptance contract.
- Do not open upstream PRs yet.
- Do not edit Touchdown-Labs except the SSoT file when measured evidence changes.
- Do not import live fixtures unless the packet acceptance contract passes.
- If a backend is not locally present, add clear source-binding diagnostics and setup docs instead of silently skipping.

## Current focus decision — 2026-05-09

- Active finish line: vLLM + LMCache + InferGuard CLI coverage.
- Active blocker: H3 CacheBlend/vLLM model-registration timing (`ValueError: vllm model for vllm-instance not found`).
- Paused: H2/SGLang at missing `sgl_kernel`; Mooncake at no runnable local source/runtime; DLM/llm-d at `adapter_not_implemented` with no validated field map.
- Resume paused lanes only after the exact resume blockers in `vllm-lmcache-focus-backend-expansion-paused-spec-v0.1.md` are cleared.

## Workstreams

### WS-SGLang
Status: `paused_backend_expansion`. Earlier goal was to make H2 prove LMCache + SGLang integration or produce a precise blocked artifact; it is now paused so the active vLLM/LMCache finish line can close first.

Steps:
1. Locate SGLang source checkout in /Users/chen/Projects/sglang or /Users/chen/Projects/SGLang.
2. If absent, clone public SGLang source into /Users/chen/Projects/sglang when network/auth allow it.
3. Add/verify `INFERGUARD_H_SGLANG_LOCAL_SOURCE` contract.
4. Add TDD coverage for source binding, install strategy, and clear blocked report when absent.
5. Run local gates.
6. Run H2 exactly once if source binding passes.
7. If accepted, import sanitized packet_h2 fixture, run fixture tests, and update SSoT.

### WS-Mooncake
Status: `paused_backend_expansion`. Earlier goal was to add a Mooncake integration lane that complements LMCache/vLLM/SGLang diagnostics; it is now paused until a runnable Mooncake source/runtime exists.

Steps:
1. Discover existing Mooncake references/repos/workspace roots.
2. Determine the correct integration boundary: LMCache backend, KV transfer path, RDMA/disaggregated serving path, or diagnostic-only lane.
3. Add a packet spec and CLI surface for Mooncake evidence classification.
4. Add local/unit tests first. No H100 unless a runnable local contract exists.
5. If no runnable Mooncake source/runtime exists, save blocked spec and setup contract with exact missing prerequisite.

Status update — 2026-05-09:
- Mooncake is `paused_backend_expansion` for runnable packet validation because no runnable Mooncake source/runtime exists locally.
- Current InferGuard support is diagnostic classification only: SGLang `sglang:kv_transfer_*{connector="mooncake"}` labels are parsed and reported, but this is not runtime proof.
- Report: `docs/sdlc/mooncake-dlm-diagnostic-classification-report-v0.1.md`.
- No H100 run was performed.

### WS-DLM
Status: `paused_backend_expansion` / `detection_only`. Earlier goal was to ensure DLM is represented as a diagnostic/backend classification lane, not conflated with LMCache MP; it is now paused until a runtime contract and validated Prometheus field map exist.

Steps:
1. Search existing InferGuard docs/tests/CLI for DLM.
2. Add or update classification docs/tests so CLI reports DLM coverage/gaps explicitly.
3. No live run unless a runnable DLM backend exists.

Status update — 2026-05-09:
- DLM / `llm-d` is `paused_backend_expansion` / `detection_only`: metric prefixes are recognized, but `LLMD_FIELD_MAP = {}` and CLI output reports `adapter_not_implemented` when forced to `--engine llm-d`.
- DLM is not supported, not live-validated, and not LMCache MP evidence.
- Report: `docs/sdlc/mooncake-dlm-diagnostic-classification-report-v0.1.md`.
- No H100 run was performed.

## Acceptance
- H2 remains paused until missing `sgl_kernel` has a TDD-backed runtime strategy; accept only with live SGLang + LMCache evidence and sanitized fixture tests.
- H3 accepted only with CacheBlend/OTel evidence if SSoT requires `cb.*` traces.
- Mooncake accepted only after a source-backed packet/CLI lane exists with runnable evidence.
- Score can reach 100 only if SSoT acceptance rows support it; otherwise leave exact blockers and next commands.

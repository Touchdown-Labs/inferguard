# InferGuard vLLM + LMCache focus / backend pause spec v0.1

## Decision
Active finish line is vLLM + LMCache + InferGuard CLI coverage. SGLang, Mooncake, and DLM remain important, but they are paused as follow-up backend expansion lanes so they do not distract from closing the original vLLM/LMCache production-readiness gap.

## Active lane
### vLLM + LMCache + InferGuard CLI
- Keep A-F, G1, and H1 accepted evidence as canonical.
- Continue H3 CacheBlend/vLLM model-registration timing blocker.
- Do not rerun A-F/G1/H1.
- Only rerun H3 after local TDD proves the vLLM model tracker registration timing fix.
- Complete I1 release readiness only after the vLLM/LMCache acceptance contract is evidence-backed.

## Paused lanes
### SGLang / H2
Status: paused after source binding and image-build improvements.
Known progress:
- `/Users/chen/Projects/sglang` found.
- Runner binds SGLang source into Modal.
- `orjson` and `IPython` blockers cleared.
- Full-repo image build timeout cleared by copying only `sglang/python`.
Known blocker:
- `ModuleNotFoundError: No module named 'sgl_kernel'`.
Resume condition:
- Add source-backed minimal `sgl_kernel` runtime strategy with TDD, then one H2 run.

### Mooncake
Status: paused / blocked classification only.
Known progress:
- No runnable local Mooncake source/runtime found.
- InferGuard can classify connector-label evidence when metrics mention `connector="mooncake"`.
Known blocker:
- No local Mooncake runtime contract for live validation.
Resume condition:
- A runnable Mooncake source/runtime path exists and a packet acceptance contract is written.

### DLM / llm-d
Status: paused / detection-only.
Known progress:
- CLI/tests pin `adapter_not_implemented` instead of conflating DLM with LMCache MP.
Known blocker:
- No concrete DLM runtime contract or validated Prometheus field map.
Resume condition:
- Runtime contract and field map exist.

## Progress tracker policy
- Current score remains 96/100 until evidence-backed vLLM/LMCache acceptance changes it.
- Non-vLLM backend work should not block the vLLM/LMCache finalization track.
- SSoT must distinguish `paused backend expansion` from `failed core coverage`.

## Next active engineering task
Fix H3 CacheBlend/vLLM model registration timing:
- Root: CacheBlend calls `VLLMModelTracker` / `LMCBlenderBuilder.get_or_create()` before vLLM registers `vllm-instance`.
- Add local TDD around the runner hook/config.
- Rerun H3 once only after local gates pass.

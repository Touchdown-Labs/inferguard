# SGLang + LMCache MP 100 Compatibility Execution v0.2

InferGuard acceptance phase for the full local-fork path.

## Goal
Make InferGuard CLI capture and classify complete SGLang + LMCache MP observability in detail from real or fixture artifacts, without fabricating evidence.

## Inputs
- SGLang `/metrics` or engine metrics file.
- LMCache MP `/metrics` or LMCache metrics file.
- Optional LMCache L0 boundary evidence file.
- Optional SGLang KV-events evidence file.
- Expected engine: `sglang`.
- Expected mode: `mp`.

## Required Report Detail
InferGuard must report:
- engine identity and detected engines
- expected/detected LMCache mode
- SGLang LMCache mode labels and connector evidence when present
- MP family status for:
  - storage_manager
  - lookup_tokens
  - l1_counters
  - l1_memory
  - lifecycle/abort/error when present
- acceptance state:
  - complete/accepted only if all required MP families are present and mode is MP
  - incomplete/mixed if expected families are missing or mode falls back to embedded/mixed

## Test Requirements
- Add or update complete SGLang+LMCache MP fixture/report test.
- Add or preserve incomplete/mixed rejection test.
- Do not inject fabricated launch evidence.
- Run:
  - `uv run ruff check src/inferguard/lmcache_packet.py src/inferguard/cli.py src/inferguard/observability_coverage.py tests/test_lmcache_packet.py tests/test_observability_coverage.py`
  - `uv run pytest tests/test_lmcache_packet.py tests/test_observability_coverage.py -q`
  - `uv run mkdocs build` if docs changed.

## Non-Claims
Synthetic fixtures prove parser/classifier behavior only. Real H100 artifacts are required for measured acceptance.

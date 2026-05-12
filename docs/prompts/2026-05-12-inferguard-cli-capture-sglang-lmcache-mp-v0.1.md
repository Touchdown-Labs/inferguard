# InferGuard CLI capture SGLang + LMCache MP telemetry v0.1

## Objective

Move SGLang + LMCache MP telemetry capture into InferGuard CLI instead of depending on SGLang source changes for product proof.

## Decision

- Do not make SGLang source changes the default strategy.
- Treat SGLang as the serving engine surface and LMCache as the cache/MP observability source.
- InferGuard should capture both surfaces from URLs or saved artifacts and generate one evidence packet:
  - raw engine Prometheus scrape
  - raw LMCache Prometheus scrape
  - safe LMCache HTTP evidence
  - optional logs/traces/OTel/lookup-hash/L0-boundary/KV-events evidence
  - LMCache compatibility report
  - cross-engine observability coverage report

## Evidence Standard

- `measured`: live URL/file artifact was captured and parsed.
- `measured_partial`: artifacts exist but coverage/mode is partial or mixed.
- `fixture_tested`: synthetic fixture proves parser/CLI behavior only.
- `not_proven`: no live artifact.

## Source Ledger

- InferGuard current CLI: `/Users/chen/Projects/inferguard/src/inferguard/cli.py`
- InferGuard packet collector: `/Users/chen/Projects/inferguard/src/inferguard/lmcache_packet.py`
- InferGuard observability coverage builder: `/Users/chen/Projects/inferguard/src/inferguard/observability_coverage.py`
- Current SGLang + LMCache MP H100 artifact shape: `/artifacts/ocwc22_lmcache_mp/20260512T042314Z`

## Implementation Tasks

1. Extend `collect-lmcache` so it can capture SGLang+LMCache MP observability without SGLang patches:
   - `--expected-engine auto|vllm|sglang`
   - `--expect-mode auto|mp|embedded` remains LMCache mode expectation
   - `--sglang-kv-events-evidence-file`
   - `--lmcache-l0-boundary-evidence-file`
   - `--external-cache-configured`
   - `--cpu-offload-configured`
   - `--disaggregated-or-external-cache`
2. Have packet collection write `observability_coverage_report.json` using already captured metrics/evidence.
3. Include that artifact and summary in `packet_manifest.json`.
4. Add focused tests proving the CLI writes the coverage report from SGLang engine metrics + LMCache MP metrics.

## Non-Claims

- Do not claim SGLang upstream changes are required.
- Do not claim pure accepted MP if InferGuard detects mixed mode or missing MP families.
- Do not claim performance improvement from telemetry capture.

## Verification

Run:

```bash
uv run --with pytest --with pytest-asyncio --with aiohttp --with msgpack pytest -q tests/test_lmcache_packet.py tests/test_observability_coverage.py
uv run ruff check src/inferguard/cli.py src/inferguard/lmcache_packet.py tests/test_lmcache_packet.py
```

# InferGuard

[![PyPI](https://img.shields.io/pypi/v/inferguard.svg)](https://pypi.org/project/inferguard/)
[![Python](https://img.shields.io/pypi/pyversions/inferguard.svg)](https://pypi.org/project/inferguard/)
[![License](https://img.shields.io/badge/License-BUSL--1.1-blue.svg)](LICENSE)
[![CodeQL](https://github.com/Touchdown-Labs/inferguard/actions/workflows/codeql.yml/badge.svg)](https://github.com/Touchdown-Labs/inferguard/actions/workflows/codeql.yml)

> Read-only disaggregated-serving diagnostics for vLLM, SGLang, Dynamo, and llm-d.

## What is this?

InferGuard is a source-available CLI and MCP server for validating inference benchmark evidence, profiling OpenAI-compatible endpoints, collecting engine/GPU timelines, and turning completed runs into refusal-gated operator reports. It is built for engineers running production-like vLLM, SGLang, Dynamo, LMCache, and llm-d stacks on GPU fleets where incomplete evidence is worse than no evidence. InferGuard does not promise every model fits every GPU. It tells the operator what fits, what fails, why it fails, and what hardware/config to use next.

InferGuard is distributed under the Business Source License 1.1 (`BUSL-1.1`). The Additional Use Grant allows teams to use InferGuard in their own source repositories, CI/CD, staging, internal tools, and internal production environments to benchmark, monitor, diagnose, validate, or optimize inference workloads they own, operate, or are authorized to evaluate. Offering InferGuard as a paid or hosted observability, benchmarking, diagnostics, optimization, inference operations, managed service, SaaS, or substantially similar competing commercial product requires a separate commercial license from Touchdown Labs. Each covered version converts to Apache-2.0 on the Change Date specified in `LICENSE`, or earlier if required by the BSL 1.1 terms.

## Current release: 0.7.4

`inferguard==0.7.4` is the LMCache PR #3255 downstream-observability release.
It adds InferGuard parser/report support for the new LMCache MP L0 GPU KV block
allocation counters and redacted boundary evidence:

- `lmcache_mp_l0_block_allocation_records_total`
- `lmcache_mp_l0_block_allocated_blocks_total`
- optional `inferguard-l0-block-boundary-event/v1` JSONL evidence proving the
  adapter → server → lifecycle-subscriber path without storing raw tokens or raw
  block IDs

The release is source-backed by a Modal H100 Packet B run using vLLM plus local
LMCache source containing PR #3255 and the updated InferGuard CLI. Scope remains
conservative: no vLLM source changes, no LMCache performance-improvement claim,
and no DCGM/NVML hardware telemetry claim are made by this release. See
[`CHANGELOG.md`](CHANGELOG.md),
[`docs/sdlc/pr3255-packet-b-downstream-h100-measured-report-v0.1.md`](docs/sdlc/pr3255-packet-b-downstream-h100-measured-report-v0.1.md),
and [`release_proofs/v0.7.4/README.md`](release_proofs/v0.7.4/README.md).

## Quick start (60 seconds)

```bash
pip install inferguard==0.7.4

# Generate a local synthetic GPU bundle for smoke testing.
inferguard simulate-gpu --results-root /tmp/inferguard-smoke --hardware b200 --engine vllm

# Validate a completed run. Synthetic smoke tests intentionally do not pass --strict.
inferguard validate-completed --results-root /tmp/inferguard-smoke || true

# Profile per-request latency against an OpenAI-compatible endpoint.
cat >/tmp/inferguard-requests.jsonl <<'JSONL'
{"request_id":"doc-001","messages":[{"role":"user","content":"Reply with one short sentence about InferGuard."}],"max_tokens":24}
JSONL

inferguard request-profile \
  --output-dir /tmp/inferguard-profile \
  --endpoint http://localhost:8000/v1/chat/completions \
  --model deepseek-ai/DeepSeek-V4-Flash \
  --input-jsonl /tmp/inferguard-requests.jsonl \
  --concurrency 1 \
  --stream

# Diagnose a completed job directory once request, launch, metrics, and validation artifacts exist.
inferguard diagnose-bottleneck --job-dir /path/to/results/jobs/<job-id>
```

From a source checkout, replace `inferguard` with `PYTHONPATH=src python3 -m inferguard.cli`.

## Why InferGuard?

NeoCloud and platform engineers need honest evidence for DSv4-class serving stacks on H100, H200, B200, B300, GB200, and GB300. Most benchmark wrappers are happy to emit a report even when the request rows are empty, the healthcheck failed, DCGM was missing, or the model never actually fit in HBM.

InferGuard's bias is the opposite:

- refuse or downgrade when required artifacts are missing;
- separate synthetic smoke tests from live evidence;
- keep network behavior limited to endpoints you pass explicitly;
- preserve request, engine, GPU, launch, failure, cost, and cliff artifacts in structured schemas;
- make every recommendation trace back to `claim_status`, `claim_reason`, and file-level evidence.

## Commands

| Command | What it does |
|---|---|
| `validate-completed` | Publishability gate; classifies a run as `synthetic_only`, `live_complete`, `live_incomplete`, `missing_required_artifacts`, or `not_publishable`. |
| `request-profile` | Per-request truth: TTFT, TPOT, E2E latency, tokens, HTTP status, errors, and per-field claim status. |
| `collect-metrics` | Normalized engine `/metrics` plus DCGM GPU timelines for live evidence. |
| `launch-engine` | Launch or externally validate vLLM, SGLang, LMCache, or Dynamo-SGLang and capture command/healthcheck artifacts. |
| `diagnose-bottleneck` | Classify one completed job as prefill, decode, KV, queue, network, host, launch, or not-enough-evidence. |
| `classify-failures` | Turn logs and artifacts into ranked operator-actionable failure classes. |
| `report-completed` | Produce refusal-gated operator recommendations from completed validation evidence. |
| `find-cliffs` | Detect capacity cliffs across completed sweeps. |
| `compute-cost` | Compute cost per useful task and safe concurrency envelopes. |
| `agentx-ingest` / `ingest-agentx` | Convert AgentX result CSVs into canonical InferGuard artifacts. |
| `simulate-gpu` | Generate synthetic GPU/Slurm artifacts for local bundle smoke tests. |
| `serve-mimic` | Run a tiny fake OpenAI-compatible endpoint for local demos. |
| `preflight` | Run read-only launch compatibility and tokenizer mismatch checks before paid traffic. |
| `analyze` | Analyze existing InferGuard, InferenceX, AgentX, or eval result directories. |
| `bench ...` | Replay traces, run KVCast/KV stress, compare runs, and run upstream-compatible benchmark modes. |
| `disagg status` | Scrape prefill/decode/transfer Prometheus endpoints and emit disaggregated-serving findings. |
| `profile live` / `profile retro` | Observe existing `/metrics` traffic or inspect saved live-profile artifacts. |
| `agent trace` | Capture local `agent-trace/v1` DAG events for supported agent frameworks. |
| `daemon ...` | Local harness sidecar and multi-node leader/follower fan-in. |
| `telemetry ...` | Local-only telemetry consent and payload audit commands; telemetry is disabled by default. |
| `workload analyze` | Pre-flight workload fingerprinting for routing and reporting. |
| `router classify` | Rule-based execution-path routing from workload fingerprints. |
| `emit-bundle` | Emit a deployment bundle from a router verdict. |

See the [CLI reference](https://touchdown-labs.com/inferguard/reference/cli/) for full `--help` output for every command and subcommand.

## Hardware coverage

InferGuard ships with the DSv4 6-SKU capability matrix: H100, H200, B200, B300, GB200, and GB300 × DSv4 Flash/Pro × vLLM/SGLang × long-context chat/coding = 48 cells. Each cell is honestly classified:

- `WORKING_TEMPLATE` (28 cells)
- `INFEASIBLE_DOCUMENTED` (4 cells: H100 × DSv4-Pro single-node)
- `FUTURE_EXTERNAL` (16 cells: GB200/GB300, awaiting rack-level external access)

See [hardware coverage](https://touchdown-labs.com/inferguard/reference/hardware-coverage/) for the full matrix and status definitions.

## Documentation

- [Documentation](https://touchdown-labs.com/inferguard/)
- [Architecture](https://touchdown-labs.com/inferguard/system-design/architecture/)
- [CLI reference](https://touchdown-labs.com/inferguard/reference/cli/)
- [Hardware coverage](https://touchdown-labs.com/inferguard/reference/hardware-coverage/)
- [Schemas](https://touchdown-labs.com/inferguard/reference/schemas/)
- [Examples](examples/)
- [Troubleshooting](https://touchdown-labs.com/inferguard/guides/troubleshooting/)
- [Contributing](CONTRIBUTING.md)
- [Security policy](SECURITY.md)
- [Code of conduct](CODE_OF_CONDUCT.md)
- [Changelog](CHANGELOG.md)

## Claim status discipline

InferGuard never lies about what it measured. Every publishable artifact uses the canonical `claim_status` enum:

| Value | Meaning |
|---|---|
| `synthetic` | No real GPU evidence; dry-run or synthetic mimic only. |
| `inferred` | Indirect evidence; read `claim_reason` or `claim_caveat` before quoting. |
| `measured` | Live evidence with the required artifact set. |
| `not_proven` | Claim could not be verified. |

`live_complete` requires five gates:

1. non-empty request-profile rows;
2. at least one successful request;
3. launch healthcheck with status code `200` or an equivalent success status;
4. non-empty engine metrics timeline with recognized live engine metrics;
5. non-empty GPU metrics timeline with required DCGM signals.

If any gate is missing, InferGuard downgrades the claim instead of filling the gap with guesses.

## Privacy and network behavior

InferGuard has zero telemetry by default. CLI network calls happen only to endpoints passed with flags such as `--endpoint`, `--engine-metrics-url`, `--dcgm-metrics-url`, `--prefill`, or `--decode`. Telemetry commands are local audit/consent tooling; hard overrides such as `INFERGUARD_TELEMETRY=disabled` and `DO_NOT_TRACK=1` are honored.

## Examples

- [Validate a synthetic run](examples/01-validate-synthetic-run.md)
- [Profile a real or mock endpoint](examples/02-profile-real-endpoint.md)

## License

Business Source License 1.1 (`BUSL-1.1`). See [LICENSE](LICENSE).

## Citation

If you use InferGuard in academic work, please cite:

```bibtex
@software{inferguard2026,
  author = {Chen, William},
  title = {InferGuard: Read-only disaggregated-serving diagnostics for vLLM, SGLang, Dynamo, and llm-d},
  year = {2026},
  url = {https://github.com/Touchdown-Labs/inferguard},
  version = {0.7.4}
}
```

See [CITATION.cff](CITATION.cff).

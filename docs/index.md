---
title: InferGuard
description: Evidence-gated inference diagnostics for production serving stacks.
---

# InferGuard

InferGuard is a source-available CLI and MCP server for validating inference benchmark evidence,
profiling OpenAI-compatible endpoints, collecting engine and GPU timelines, and turning completed
runs into refusal-gated operator reports. The current release line is distributed under BUSL-1.1;
see the repository license for the Additional Use Grant and Change License details.

It is built for production-class vLLM, SGLang, Dynamo, LMCache, and llm-d stacks where incomplete
evidence is worse than no evidence.

## Start here

- [Install the CLI](getting-started/install.md)
- [Run the evidence loop](getting-started/quick-start.md)
- [Read how InferGuard works](how-this-works/overview.md)
- [Use the command map](reference/cli.md)

## What InferGuard proves

- Per-request timing: TTFT, TPOT, end-to-end latency, queue behavior, and retry storms.
- Engine and GPU telemetry: vLLM, SGLang, Dynamo, LMCache, llm-d, Prometheus, and DCGM evidence.
- Publishability: each claim is marked `measured`, `inferred`, `synthetic`, or `not_proven`.
- Operator action: bottleneck verdicts, hardware fit, engine configuration, and cost-per-useful-task.

## Current boundaries

InferGuard can validate local evidence, profile endpoints you provide, collect engine/GPU timelines,
run synthetic smoke tests, and emit local reports. It does not train models, provision cloud
infrastructure, upload telemetry by default, operate a hosted dashboard, or make publishable claims
when required live artifacts are missing.

## Current release: 0.7.4

`inferguard==0.7.4` is the LMCache PR #3255 downstream-observability release.
It adds support for LMCache MP L0 allocation counters and redacted L0 boundary
JSONL evidence, with Modal H100 downstream evidence recorded through the
InferGuard CLI. This is an observability/reporting release: it does not claim
vLLM source changes, LMCache performance gains, or DCGM/NVML hardware telemetry.

Release evidence:

- [PyPI package](https://pypi.org/project/inferguard/0.7.4/)
- [GitHub release](https://github.com/Touchdown-Labs/inferguard/releases/tag/v0.7.4)
- [Changelog](https://github.com/Touchdown-Labs/inferguard/blob/main/CHANGELOG.md)
- [PR3255 H100 measured report](sdlc/pr3255-packet-b-downstream-h100-measured-report-v0.1.md)
- [v0.7.4 release proof bundle](https://github.com/Touchdown-Labs/inferguard/tree/main/release_proofs/v0.7.4)

## Package links

- [PyPI](https://pypi.org/project/inferguard/)
- [Repository](https://github.com/Touchdown-Labs/inferguard)
- [Issues](https://github.com/Touchdown-Labs/inferguard/issues)
- [Releases](https://github.com/Touchdown-Labs/inferguard/releases)

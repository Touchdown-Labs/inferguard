---
title: InferGuard
description: Evidence-gated inference diagnostics for production serving stacks.
---

# InferGuard

InferGuard is an open-source CLI and MCP server for validating inference benchmark evidence,
profiling OpenAI-compatible endpoints, collecting engine and GPU timelines, and turning completed
runs into refusal-gated operator reports.

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

## Package links

- [PyPI](https://pypi.org/project/inferguard/)
- [Repository](https://github.com/Touchdown-Labs/inferguard)
- [Issues](https://github.com/Touchdown-Labs/inferguard/issues)
- [Releases](https://github.com/Touchdown-Labs/inferguard/releases)

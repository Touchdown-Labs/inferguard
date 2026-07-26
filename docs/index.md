---
title: InferGuard
description: Evidence-gated inference diagnostics inside Touchdown Labs' company AI architecture.
---

# InferGuard

InferGuard is the evidence and diagnostics product inside [Touchdown Labs](https://touchdown-labs.com/).
Touchdown helps companies build AI around real workflows through private evaluations, learning and execution
loops, managed model and infrastructure decisions, and full-stack optimization. InferGuard supplies one part of
that system: trustworthy evidence about how inference actually behaved.

InferGuard is a source-available CLI and MCP server for validating inference benchmark evidence,
profiling OpenAI-compatible endpoints, collecting engine and GPU timelines, and turning completed
runs into refusal-gated operator reports. The current release line is distributed under BUSL-1.1;
see the repository license for the Additional Use Grant and Change License details.

It is built for production-class vLLM, SGLang, Dynamo, LMCache, and llm-d stacks where incomplete
evidence is worse than no evidence.

!!! info "Where InferGuard fits"
    A complete company AI system starts with the workflow and private definition of success. InferGuard does
    not replace the workflow, eval, agent, context, routing, or operating architecture. It helps prove what
    happened in the inference layer so the company can make better serving, cache, hardware, and cost decisions.

    - Company overview: [Build AI around your work](https://touchdown-labs.com/)
    - Start one company workflow: [Touchdown workflow intake](https://touchdown-labs.com/start/)
    - Coding-agent product: [InferGuard for coding agents](https://touchdown-labs.com/coding-agents/)

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

Those measurements become useful only when connected to the customer outcome. Touchdown's broader system
joins inference evidence to private evals, accepted work, human corrections, workflow cost, and deployment policy.

## Current boundaries

InferGuard can validate local evidence, profile endpoints you provide, collect engine/GPU timelines,
run synthetic smoke tests, and emit local reports. It does not train models, provision cloud
infrastructure, upload telemetry by default, operate a hosted dashboard, or make publishable claims
when required live artifacts are missing.

InferGuard also does not claim to be the complete Touchdown platform or the complete customer learning loop.
It is a focused evidence tool and product component.

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

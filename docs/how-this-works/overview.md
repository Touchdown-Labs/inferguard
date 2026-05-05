---
title: What InferGuard does
description: What InferGuard is, who it's for, and what it refuses to do.
---

InferGuard is an open-source CLI and MCP server for validating inference
benchmark evidence, profiling OpenAI-compatible endpoints, collecting
engine and GPU timelines, and turning completed runs into refusal-gated
operator reports.

It is built for engineers running production-class vLLM, SGLang, Dynamo,
LMCache, and llm-d stacks on GPU fleets, where incomplete evidence is
worse than no evidence.

InferGuard does not promise every model fits every GPU. It tells the
operator what fits, what fails, why it fails, and what hardware or config
to use next.

## Who it's for

- NeoCloud and platform engineers running real serving stacks.
- Inference operators who need defensible numbers for cost-per-task,
  bottleneck attribution, and hardware decisions.
- Researchers and benchmark authors who want reproducible runs over a
  vendor-neutral substrate.

## What makes it different

- **Refusal-gated reports.** No verdict ships without live evidence.
  Every claim is labeled `measured`, `inferred`, `synthetic`, or
  `not_proven`.
- **Per-request timing fused with engine internals.** TTFT, TPOT, and
  end-to-end latency are joined to engine `/metrics` and DCGM on a
  single timeline.
- **Multi-engine.** First-class support for vLLM, SGLang, Dynamo,
  LMCache, and llm-d.
- **Apache 2.0.** Read the code, fork it, ship it.

## What it does not do

- Train models. InferGuard is inference-only.
- Make claims it cannot back up. The publishability gate refuses
  reports built on synthetic, inferred, or unproven inputs unless
  explicitly downgraded.
- Lock you in. The CLI runs anywhere Python runs. The schemas are
  open. The traces are reproducible.

## Next

- [Install the CLI](/inferguard/getting-started/install/)
- [Run the evidence loop](/inferguard/getting-started/quick-start/)
- [Use the command map](/inferguard/reference/cli/)

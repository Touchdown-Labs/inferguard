# ISB-1 DSv4 Agent Trace Pack

This directory contains the first synthetic ISB-1 DSv4 Agent Trace Pack for InferGuard replay testing. The pack is designed to exercise long-context coding-agent and chat-agent behavior against DSv4-style serving stacks without using real customer data or proprietary code.

## Shipped workload classes

The v1 pack ships seven priority workload classes:

1. `coding-long` — long fictional repository and file context with multi-turn debugging prompts.
2. `agent-chat` — multi-turn enterprise assistant sessions with long operational context.
3. `multi-agent-coding` — planner, coder, and reviewer turn structure for coding tasks.
4. `tool-heavy` — file-read, grep, stack-trace, pytest, and JSON tool-output heavy prompts.
5. `session-resume` — paused and resumed agent tasks with shared session prefixes.
6. `prefix-reuse` — many sessions sharing a stable prefix with divergent suffix requests.
7. `kv-pressure` — cold unique long contexts with no `prefix_group` to stress KV pressure.

Four lower-priority classes are reserved for a future pack revision: `repo-level-coding`, `long-context-debugging`, `rag-generation`, and `high-concurrency-dev-assistant`.

## Directory layout

The layout follows `SPEC.md` section 6.4:

```text
traces/isb1-dsv4-agent/
  README.md
  coding-long/*.jsonl
  agent-chat/*.jsonl
  multi-agent-coding/*.jsonl
  tool-heavy/*.jsonl
  session-resume/*.jsonl
  prefix-reuse/*.jsonl
  kv-pressure/*.jsonl
```

Each JSONL line is a single `TraceRecord`-valid object with string-only message content and roles limited to `system`, `user`, `assistant`, and `tool`.

## Replay

From `oss/inferguard`:

```bash
inferguard bench replay \
  --trace-dir traces/isb1-dsv4-agent \
  --concurrency 1,4 \
  --endpoint <url> \
  --model <model>
```

## Synthetic-content disclaimer

All trace content is synthetic and illustrative. Fictional package names, stack traces, tool outputs, tickets, and repository snippets are used intentionally. This pack contains no real customer data and no real proprietary code.

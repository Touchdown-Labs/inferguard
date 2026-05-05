---
title: Run the evidence loop
description: Generate a synthetic bundle, validate it, and profile a real endpoint.
---

This walkthrough takes about a minute and verifies your install on a local
machine. It uses a synthetic GPU bundle so you do not need real hardware
to see the full pipeline.

## 1. Install the CLI

```bash
pip install inferguard
```

See [Install the CLI](/inferguard/getting-started/install/) if you want a source checkout
or the optional extras.

## 2. Generate a synthetic GPU bundle

Useful for smoke-testing the validators without booking a GPU.

```bash
inferguard simulate-gpu \
  --results-root /tmp/inferguard-smoke \
  --hardware b200 \
  --engine vllm
```

This writes a directory tree under `/tmp/inferguard-smoke/` that mimics
what a real run would produce.

## 3. Validate the run

```bash
inferguard validate-completed --results-root /tmp/inferguard-smoke || true
```

Synthetic smoke tests are intentionally non-strict: the validator will
flag the `synthetic` label on every claim. Pass `--strict` only when you
want hard refusals.

## 4. Profile a real endpoint

If you have an OpenAI-compatible endpoint running, profile a single
request against it.

```bash
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
```

You get a per-request timeline with TTFT, TPOT, and end-to-end latency
labeled with their measurement provenance.

## 5. Diagnose a job

Once a job directory contains the request log, the launch metadata,
the engine `/metrics` snapshots, and a validation pass, run the
bottleneck verdict tree.

```bash
inferguard diagnose-bottleneck --job-dir /path/to/results/jobs/<job-id>
```

The verdict explains *why* the workload was slow (compute-bound,
memory-bandwidth-bound, KV-cache-bound, prefix-cache miss, retry-storm,
etc.) and what to try next.

## Next

- [Run the harness](/inferguard/guides/harness/) — for the full benchmark loop
- [Analyze a run](/inferguard/guides/analyze/) — for digging into a finished job
- [Use the command map](/inferguard/reference/cli/) — every command and flag

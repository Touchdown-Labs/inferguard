# InferGuard

InferGuard is a standalone-first monitoring agent for inference endpoints. It
scrapes `/metrics`, detects anomalies, diagnoses likely root causes, recommends
engine-specific fixes, stores incident memory, and can re-check outcomes over
time. The default runtime path uses direct HTTP scraping and Upstash REST
clients; any broader Inferscope reuse remains optional and verified-only.

## Supported v1 scope

### Models

| Family | Notes |
|---|---|
| GPT-OSS-120B / 20B | Standard GQA-style interpretation with engine-aware remediation |
| DeepSeek-R1 + selected distills | Requires more conservative KV interpretation because of MLA |
| Qwen3.5 family | Hybrid DeltaNet / GatedAttention behavior can under-report pressure in standard KV metrics |

### Engines

| Engine | Status |
|---|---|
| vLLM | In scope |
| SGLang | In scope |
| Dynamo / TRT-LLM / ATOM | Out of scope for InferGuard v1 |

### GPUs

| GPU | Status |
|---|---|
| H100 SXM | In scope |
| H200 SXM | In scope |
| B200 | In scope |
| A100 / MI300X / MI355X / consumer GPUs | Out of scope for v1 |

## Install

Core CLI:

```bash
pip install -e .
```

Development and tests:

```bash
pip install -e '.[dev]'
pytest tests
```

Replay-harness operator extras:

```bash
pip install -e '.[demo]'
```

Optional MCP server:

```bash
pip install -e '.[mcp]'
```

## Environment variables

| Variable | Required | Purpose |
|---|---|---|
| `TARGET_ENDPOINT` | yes for scan/watch/serve | Base URL for the monitored vLLM or SGLang endpoint |
| `UPSTASH_REDIS_URL` | optional | Upstash Redis REST URL for state/event storage |
| `UPSTASH_REDIS_TOKEN` | optional | Upstash Redis REST token |
| `UPSTASH_VECTOR_URL` | optional | Upstash Vector REST URL for incident recall |
| `UPSTASH_VECTOR_TOKEN` | optional | Upstash Vector REST token |
| `GMI_BASE_URL` | optional | GMI Cloud diagnosis API base URL, default `https://api.gmi-serving.com/v1` |
| `GMI_API_KEY` | optional | GMI Cloud diagnosis API key |
| `GMI_MODEL` | optional | Diagnosis model name, default `openai/gpt-oss-120b` |
| `KV_ALERT_THRESHOLD` | optional | Base KV saturation threshold, default `0.85` |
| `TTFT_ALERT_MULTIPLIER` | optional | TTFT alert multiplier over baseline, default `2.0` |
| `POLL_INTERVAL_SECONDS` | optional | Watch-loop interval, default `30` |

For low-cost backward compatibility, InferGuard also reads `LLM_BASE_URL`,
`LLM_API_KEY`, and `LLM_MODEL` when the corresponding `GMI_*` variable is
unset. That compatibility path exists only to ease migration of earlier local
shells or Blaxel secrets.

See `.env.example` for a full template.

## CLI usage

```bash
inferguard scan http://localhost:8000
inferguard scan http://localhost:8000 --model deepseek-ai/DeepSeek-R1-0528
inferguard watch http://localhost:30000 --model Qwen/Qwen3.5-72B --interval 30
inferguard recall "KV cache pressure on GPT-OSS"
inferguard serve http://localhost:8000
```

## Architecture

```text
scrape -> detect -> diagnose -> recommend -> remember -> evaluate -> repeat
```

## Demo UI

InferGuard includes a lightweight web dashboard for demo and presentation use.
It consumes structured agent reports and streams them to a single-page UI via
Server-Sent Events.

### Quick start (Bronze / mock mode)

```bash
pip install -e '.[demo]'
python demo/run_demo.py
# Open http://127.0.0.1:8080
```

This starts the mock endpoint and the UI in one command. Press Ctrl-C to stop.

### Live mode

```bash
python demo/run_demo.py --endpoint http://vllm-host:8000 --model deepseek-ai/DeepSeek-R1-0528
```

### Standalone UI server

```bash
python demo/ui.py --endpoint http://localhost:18000 --model openai/gpt-oss-120b --interval 10
```

### Proof levels

The UI prominently labels the current proof level:

| Level | Meaning |
|---|---|
| **MOCK** | Running against the local mock endpoint. Proves the control loop, not live engine behavior. |
| **LIVE** | Connected to a real inference endpoint. |
| **UNKNOWN** | Could not determine — the /health probe failed or returned no mock marker. |

### Operational impact

The impact panel shows relative operational deltas (KV headroom recovered,
TTFT improvement, queue reduction, detection latency) observed during the
current session. These are **not** dollar-cost savings — they are operational
measurements clearly labeled with the session's proof level.

## Deploy (simplest Upstash + Blaxel path)

This is the simplest practical operator path if you want Upstash-backed memory
and a Blaxel-hosted InferGuard surface without changing the standalone-first
package architecture.

### 1. Provision Upstash

Create both of these in Upstash:

- **Redis** for short-term state and event logging
- **Vector** for incident recall (create the index with an embedding model so
  text upserts auto-embed)

Collect:

- `UPSTASH_REDIS_URL`
- `UPSTASH_REDIS_TOKEN`
- `UPSTASH_VECTOR_URL`
- `UPSTASH_VECTOR_TOKEN`

### 2. Verify locally first

Set the env vars plus a real monitored endpoint:

```bash
export TARGET_ENDPOINT="http://your-vllm-or-sglang:8000"
export UPSTASH_REDIS_URL="https://your-redis.upstash.io"
export UPSTASH_REDIS_TOKEN="AX..."
export UPSTASH_VECTOR_URL="https://your-vector.upstash.io"
export UPSTASH_VECTOR_TOKEN="AX..."
export GMI_BASE_URL="https://api.gmi-serving.com/v1"
export GMI_API_KEY="gmi-..."
export GMI_MODEL="openai/gpt-oss-120b"
```

Then run a one-shot scan:

```bash
inferguard scan "$TARGET_ENDPOINT"
```

### 3. Deploy to Blaxel

The repo now includes a minimal Blaxel entrypoint in `serve.py` and a corrected
`blaxel.toml`.

Typical flow:

```bash
pip install -e '.[mcp,blaxel]'
bl login
bl secrets set target_endpoint "http://your-vllm-or-sglang:8000"
bl secrets set upstash_redis_url "https://your-redis.upstash.io"
bl secrets set upstash_redis_token "AX..."
bl secrets set upstash_vector_url "https://your-vector.upstash.io"
bl secrets set upstash_vector_token "AX..."
bl secrets set gmi_api_key "gmi-..."
bl secrets set gmi_base_url "https://api.gmi-serving.com/v1"
bl secrets set gmi_model "openai/gpt-oss-120b"
bl deploy
```

### 4. What Blaxel is doing here

Blaxel is acting as a **host / preview / deploy layer** for the InferGuard MCP
surface. It is **not** provisioning GPUs or replacing the monitored endpoint.
You still point InferGuard at an existing vLLM or SGLang endpoint via
`TARGET_ENDPOINT`.

## Demo / replay surface

The `demo/` directory vendors the InferenceX replay harness plus a curated
bundle set that stays inside the documented support boundary:

- core `supported` bundles
- the committed `core/vllm/code_8k1k.json` file, which remains `reviewed_preview`
- `131k1k` `reviewed_preview` GPT-OSS chat/code bundles plus Qwen3.5 code-only bundles
- bounded `500k` `reviewed_preview` code-only bundles
- no DeepSeek-R1 `131k1k`
- no Qwen `1M` in the default demo tree

The vendored replay helper supports the truthful smoke path from the execution
runbook: use `--skip-tokenizer-load` when you want replay selection without
requiring the heavier tokenizer stack.

## Notes on optional surfaces

- MCP is optional and installed separately with `.[mcp]`.
- The replay helper is copied from InferenceX and kept standalone-first; it
  does not imply that InferGuard depends on Inferscope runtime imports.
- Live endpoint validation, replay validation, and mock rehearsal remain
  separate proof levels.

License: Apache-2.0.

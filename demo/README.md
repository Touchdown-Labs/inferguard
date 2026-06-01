# InferGuard Demo — Replay Surface

InferGuard vendors the InferenceX replay harness as a file-based demo helper.
This keeps the load-generation surface aligned with the downstream consumer repo
without making InferGuard depend on Inferscope runtime modules.

For local verification, this directory also includes `mock_endpoint.py`, a tiny
mock OpenAI-compatible endpoint with `/metrics` and `/v1/models`. It is for
local smoke tests only.

## Included files

- `replay_harness.py` — copied from `repos/inferencex/utils/bench_serving/benchmark_export_replay.py`
- `backend_request_func.py` — copied companion helper from `repos/inferencex/utils/bench_serving/backend_request_func.py`

## Included dataset boundary

Only these bundle classes are mirrored into `demo/datasets/`:

- `supported` core bundles
- the committed `core/vllm/code_8k1k.json` file, which remains `reviewed_preview` upstream
- `reviewed_preview` GPT-OSS / Qwen3.5 `131k1k` bundles
- `reviewed_preview` bounded `500k` code-only bundles

Explicitly excluded from the default demo tree:

- DeepSeek-R1 `131k1k`
- Qwen `1M`
- offload-core preview bundles

## Demo UI

The `demo/` directory includes a lightweight web dashboard for presenting
InferGuard's monitoring loop. It serves a single-page HTML dashboard with
live metrics sparklines, anomaly/diagnosis/remediation panels, an operational
impact summary, and an incident log.

When diagnosis is enabled, the UI inherits the main package's GMI Cloud-first
env contract: `GMI_API_KEY`, `GMI_BASE_URL`, and `GMI_MODEL`, with `LLM_*`
accepted only as documented compatibility aliases.

### Files

| File | Purpose |
|---|---|
| `ui.py` | aiohttp web server — serves HTML and SSE agent stream |
| `static/index.html` | Single-page dashboard (inline CSS/JS, no external deps) |
| `impact.py` | Operational impact computation over agent report sequences |
| `run_demo.py` | Orchestrator — starts mock endpoint + UI in one command |

### Run the full demo (Bronze / mock mode)

```bash
python demo/run_demo.py
# Open http://127.0.0.1:8080
```

Options:
- `--scenario healthy|pressure_ramp|incident|recovery` — mock scenario (default: healthy)
- `--engine vllm|sglang` — mock engine type
- `--model <name>` — model name hint
- `--mock-port 18000` — mock endpoint port
- `--ui-port 8080` — UI server port
- `--interval 10` — agent poll interval in seconds

### Run UI standalone

```bash
python demo/ui.py --endpoint http://localhost:18000 --model openai/gpt-oss-120b --interval 10
```

### Live mode (Gold)

```bash
python demo/run_demo.py --endpoint http://vllm-host:8000 --model deepseek-ai/DeepSeek-R1-0528
```

Skips mock startup and connects the UI directly to the real endpoint.

### Proof-level labels

The UI prominently displays **MOCK**, **LIVE**, or **UNKNOWN** proof level:
- **Mock** mode proves the InferGuard control loop, not live engine behavior.
- **Live** mode connects to a real inference endpoint.
- The proof level is detected via the `/health` endpoint's `mock` marker.

## Quick start

Install demo extras:

```bash
pip install -e '.[demo]'
```

Show replay harness help:

```bash
python demo/replay_harness.py --help
```

Start the local mock endpoint:

```bash
python demo/mock_endpoint.py --port 18000
```

Truthful smoke check using the runbook’s fallback tokenizer mode:

```bash
python demo/replay_harness.py \
  --export-file demo/datasets/core/vllm/chat_8k1k.json \
  --model openai/gpt-oss-120b \
  --base-url http://localhost:9999 \
  --runtime-stack-id standalone:vllm \
  --hardware-profile-id nvidia:h100_sxm_80gb \
  --canonical-model-id gpt_oss_120b \
  --max-sessions 1 \
  --skip-tokenizer-load \
  --disable-tqdm
```

This should reach selection / request setup and then fail with a connection
error if no compatible server is running.

## Dataset inventory

| Bundle | Engine | Status |
|---|---|---|
| `core/sglang/chat_8k1k.json` | SGLang | `supported` |
| `core/sglang/code_8k1k.json` | SGLang | `supported` |
| `core/vllm/chat_8k1k.json` | vLLM | `supported` |
| `core/vllm/code_8k1k.json` | vLLM | `reviewed_preview` upstream, mirrored because the committed core file exists |
| `extension_131k/sglang/chat_131k1k.json` | SGLang | `reviewed_preview` |
| `extension_131k/sglang/code_131k1k.json` | SGLang | `reviewed_preview` |
| `extension_131k/sglang/code_131k1k_qwen3.5.json` | SGLang | `reviewed_preview` |
| `extension_131k/vllm/chat_131k1k.json` | vLLM | `reviewed_preview` |
| `extension_131k/vllm/code_131k1k.json` | vLLM | `reviewed_preview` |
| `extension_131k/vllm/code_131k1k_qwen3.5.json` | vLLM | `reviewed_preview` |
| `preview/long_context_500k/inferencex_trace_replay__coding_gptoss_xlc2_500k_preview_v1__sglang.json` | SGLang | `reviewed_preview` |
| `preview/long_context_500k/inferencex_trace_replay__coding_gptoss_xlc2_500k_preview_v1__vllm.json` | vLLM | `reviewed_preview` |
| `preview/long_context_500k/inferencex_trace_replay__coding_qwen3.5_xlc2_500k_preview_v1__sglang.json` | SGLang | `reviewed_preview` |
| `preview/long_context_500k/inferencex_trace_replay__coding_qwen3.5_xlc2_500k_preview_v1__vllm.json` | vLLM | `reviewed_preview` |

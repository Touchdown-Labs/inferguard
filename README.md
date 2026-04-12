# InferGuard

Autonomous KV cache inference optimization agent for vLLM and SGLang endpoints.

InferGuard **detects** anomalies, **diagnoses** root causes via a Blaxel-hosted AI brain, **recommends** per-session surgical fixes grounded in academic primitives (Attention Matching, RLM decomposition, MAD thresholding), **validates** proposed remediations in Daytona sandboxes, and **learns** from resolved outcomes via Upstash Vector memory.

## Architecture (v6)

```
L1  Production engine (vLLM / SGLang)           read-only /metrics scrape
L2  InferGuard core (src/inferguard/)            detect, remember, call brain
L3  Blaxel agent brain (blaxel_agent/)           RLM decomposer + Daytona orchestration
L4  Daytona sandbox                              canary replay + AM compaction validation
L5  Upstash memory (Redis + Vector)              rolling state + shape-keyed learning loop
```

- L2 never imports `rlm` or `daytona-sdk` (those live in L3 only)
- L3 never imports from `inferguard.*` (layers communicate via dict payloads)
- Every advisory carries `advisory_only=True` in v1

## Reactive SAFE actions

| Action | Trigger |
|---|---|
| `recommend_compaction` | KV pressure + prefix thrashing (AM compaction, arXiv:2602.16284) |
| `throttle_concurrency` | KV > threshold + preemption delta (CONCUR AIMD) |
| `flush_session_radix` | RLM prefix cache thrashing |
| `drain_and_recycle` | Swap activity or VRAM drift |
| `quarantine_shape` | Deterministic crash on specific request shape |
| `shrink_speculation_window` | Spec-decode acceptance collapse |

## Proactive advisories

The Blaxel brain runs a proactive investigation every N cycles using RLM-style W1-W4 decomposition (trend / pattern / leading indicators / compaction opportunity) and surfaces advisories before thresholds cross.

## Install

```bash
pip install -e .           # core CLI
pip install -e '.[dev]'    # development + tests
pip install -e '.[demo]'   # demo UI + replay harness
pip install -e '.[mcp]'    # MCP server
```

## Environment variables

| Variable | Required | Purpose |
|---|---|---|
| `TARGET_ENDPOINT` | yes | Monitored vLLM/SGLang endpoint URL |
| `GMI_API_KEY` | optional | GMI Cloud diagnosis API key |
| `GMI_BASE_URL` | optional | GMI Cloud API base (default `https://api.gmi-serving.com/v1`) |
| `GMI_MODEL` | optional | Diagnosis model (default `openai/gpt-oss-120b`) |
| `UPSTASH_REDIS_URL` | optional | Redis REST URL for state/events |
| `UPSTASH_REDIS_TOKEN` | optional | Redis REST token |
| `UPSTASH_VECTOR_URL` | optional | Vector REST URL for incident recall |
| `UPSTASH_VECTOR_TOKEN` | optional | Vector REST token |
| `INFERGUARD_BRAIN_MODE` | optional | `local` or `remote` (default `local`) |
| `INFERGUARD_PROACTIVE_CYCLE_EVERY` | optional | Proactive cycle cadence (default `5`, `0` to disable) |
| `BL_API_KEY` | optional | Blaxel API key (remote brain mode) |
| `DAYTONA_API_KEY` | optional | Daytona API key (canary validation) |
| `KV_ALERT_THRESHOLD` | optional | Base KV threshold (default `0.85`) |
| `TTFT_ALERT_MULTIPLIER` | optional | TTFT alert multiplier (default `2.0`) |
| `POLL_INTERVAL_SECONDS` | optional | Watch-loop interval (default `30`) |

See `.env.example` for a full template.

## CLI

```bash
inferguard scan http://localhost:8000
inferguard scan http://localhost:8000 --model deepseek-ai/DeepSeek-R1-0528
inferguard watch http://localhost:30000 --interval 30
inferguard recall "KV cache pressure on GPT-OSS"
inferguard serve http://localhost:8000
```

## Demo

```bash
# Mock mode with proactive brain
INFERGUARD_BRAIN_MODE=local \
GMI_API_KEY=your-key GMI_MODEL=deepseek-ai/DeepSeek-V3.2 \
python demo/run_demo.py --scenario incident --model deepseek-ai/DeepSeek-R1-0528
# Open http://127.0.0.1:8080
```

Dashboard: Status, Sparkline, Anomalies, Diagnosis, Recommended Fix, Autonomous Actions (ADVISORY pills), Proactive Advisories (confidence bars + horizon chips), Impact, Incident Log.

## Deploy to Blaxel

```bash
bl login touchdown-labs
bl secrets set gmi_api_key "your-key"
bl secrets set target_endpoint "http://your-vllm:8000"
bl deploy
```

## Project layout

```
src/inferguard/          L2 core
  agent.py               reactive loop + proactive dispatch
  brain_client.py        L2-to-L3 bridge (local/remote)
  config.py              env-backed configuration
  diagnosis.py           GMI Cloud structured diagnosis
  memory.py              Upstash Redis + Vector facade
  metrics.py             Prometheus scrape + anomaly detection
  safe_actions.py        SAFE action factories + decision rules
  remediation.py         engine-specific fix generation

blaxel_agent/            L3 Blaxel brain
  brain.py               InferGuardBrain + W1-W4 decomposition
  rlm_decomposer.py      RLM wrapper with direct-GMI fallback
  daytona_client.py       Daytona canary orchestration
  app.py                 FastAPI for bl deploy
  canary_scripts/        Daytona workspace scripts

demo/                    demo UI + mock + replay
serve.py                 Blaxel deployment entrypoint
```

## Research basis

- **AM:** Zweiger et al., MIT, arXiv:2602.16284
- **RLM:** Zhang et al., MIT, arXiv:2512.24601
- **Latent Briefing:** Geist, Ramp Labs, 2026
- **CONCUR:** Chen et al., arXiv:2601.22705
- **Sarathi-Serve:** Agrawal et al., OSDI 2024
- **KevlarFlow:** Qian et al., arXiv:2601.22438

## v1 scope

Models: GPT-OSS-120B/20B, DeepSeek-R1, Qwen3.5. Engines: vLLM, SGLang. GPUs: H100/H200/B200.

License: Apache-2.0.

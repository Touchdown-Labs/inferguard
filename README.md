# InferGuard

KV/cache-aware serving health monitor and advisory agent for vLLM and SGLang endpoints.

InferGuard **detects** KV cache, latency, queue, preemption, and swap anomalies from Prometheus metrics, **diagnoses** likely root causes via GMI Cloud or a deterministic fallback, **recommends** incident-scoped advisory actions, and **stores** incident memory for future recall. In v1, InferGuard is still **advisory-first**: it does not ship direct production-engine mutation, and optional actuation is limited to allowlisted webhook dispatch.

> For the current-state coverage map of what InferGuard actually detects, approximates, and does not cover today, see [`docs/inferguard/15-2026-04-13-coverage-guide.md`](../../docs/inferguard/15-2026-04-13-coverage-guide.md).
>
> For a skeptical-operator view of where InferGuard is useful now and what must exist before deeper production adoption, see [`docs/inferguard/16-2026-04-13-vllm-operator-current-fit-and-adoption-path.md`](../../docs/inferguard/16-2026-04-13-vllm-operator-current-fit-and-adoption-path.md).
>
> For the builder-facing implementation plan with milestones, workstreams, and exit criteria, see [`docs/inferguard/17-2026-04-13-production-build-plan.md`](../../docs/inferguard/17-2026-04-13-production-build-plan.md).

When configured with an ISB-1 replay export, InferGuard can also run optional replay-backed validation using the vendored replay harness in `demo/replay_harness.py` and attach the result to anomaly reports.

InferGuard can also run a tightly gated, operator-controlled actuation path for allowlisted actions through an external webhook. This is off by default and is intended for controlled remediation, not broad autonomous mutation.

## Architecture (v6)

```
L1  Production engine (vLLM / SGLang)           read-only /metrics scrape
L2  InferGuard core (src/inferguard/)            detect, remember, call brain
L3  RLM agent brain (rlm_agent/)                 RLM decomposer + advisory scaffolding
L4  Daytona sandbox                              stub canary path (no end-to-end execution proof in v1)
L5  Upstash memory (Redis + Vector)              rolling state + incident recall
```

- L2 never imports `rlm` or `daytona-sdk` (those live in L3 only)
- L3 never imports from `inferguard.*` (layers communicate via dict payloads)
- Every advisory carries `advisory_only=True` in v1

## Reactive SAFE actions

| Action | Trigger | Status |
|---|---|---|
| `recommend_compaction` | KV pressure + prefix thrashing (AM compaction, arXiv:2602.16284) | Emitted |
| `throttle_concurrency` | KV > threshold + preemption delta | Emitted |
| `flush_session_radix` | RLM prefix cache thrashing | Emitted |
| `drain_and_recycle` | Swap activity | Emitted |
| `quarantine_shape` | Deterministic crash on specific request shape | Factory only — no trigger path in v1 |
| `shrink_speculation_window` | Spec-decode acceptance collapse | Factory only — no trigger path in v1 |

## Proactive advisories

The RLM brain runs a periodic proactive investigation using RLM-style W1-W4 decomposition (trend / pattern / leading indicators / compaction opportunity) and can emit heuristic proactive advisories. Only local brain mode is implemented today. `INFERGUARD_BRAIN_MODE=remote` is reserved but not implemented. Local mode requires `GMI_API_KEY`.

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
| `INFERGUARD_BRAIN_MODE` | optional | `local` today; `remote` is reserved but not implemented (default `local`) |
| `INFERGUARD_BRAIN_AGENT_NAME` | optional | Reserved brain agent name for future remote mode (default `inferguard-brain`) |
| `INFERGUARD_PROACTIVE_CYCLE_EVERY` | optional | Proactive cycle cadence (default `5`, `0` to disable) |
| `BL_API_KEY` | optional | Future-only Blaxel credential; not used by the current local runtime path |
| `DAYTONA_API_KEY` | optional | Optional Daytona key for the stub canary path |
| `KV_ALERT_THRESHOLD` | optional | Base KV threshold (default `0.85`) |
| `TTFT_ALERT_MULTIPLIER` | optional | TTFT alert multiplier (default `2.0`) |
| `POLL_INTERVAL_SECONDS` | optional | Watch-loop interval (default `30`) |
| `INFERGUARD_REPLAY_EXPORT_FILE` | optional | Path to an ISB-1 replay export JSON for replay-backed validation |
| `INFERGUARD_REPLAY_MAX_CONCURRENCY` | optional | Max replay concurrency (default `4`) |
| `INFERGUARD_REPLAY_MAX_SESSIONS` | optional | Limit replay sessions for faster validation (`0` = all) |
| `INFERGUARD_REPLAY_RUNTIME_STACK_ID` | optional | Filter replay cells to a runtime stack such as `standalone:vllm` |
| `INFERGUARD_REPLAY_SKIP_TOKENIZER` | optional | Use approximate token counting during replay validation (default `true`) |
| `INFERGUARD_ACTUATION_MODE` | optional | `off`, `dry_run`, or `live` (default `off`) |
| `INFERGUARD_ACTUATION_ENDPOINT` | optional | Webhook URL for allowlisted live actuation |
| `INFERGUARD_ACTUATION_ALLOWLIST` | optional | Comma-separated action types eligible for execution |
| `INFERGUARD_ACTUATION_VERIFY_DELAY` | optional | Delay before post-action verification scrape (default `60`) |

See `.env.example` for a full template.

## Actuation boundary

Actuation dispatches to an external operator-controlled webhook. InferGuard does not ship a built-in vLLM or SGLang admin adapter.

## CLI

```bash
inferguard scan http://localhost:8000
inferguard scan http://localhost:8000 --model deepseek-ai/DeepSeek-R1-0528
inferguard watch http://localhost:30000 --interval 30
inferguard validate http://localhost:8000 demo/datasets/core/vllm/chat_8k1k.json --model openai/gpt-oss-120b --runtime-stack-id standalone:vllm
INFERGUARD_ACTUATION_MODE=dry_run INFERGUARD_ACTUATION_ALLOWLIST=throttle_concurrency inferguard scan http://localhost:8000
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

rlm_agent/               L3 RLM brain
  brain.py               InferGuardBrain + W1-W4 decomposition
  rlm_decomposer.py      RLM wrapper with direct-GMI fallback
  daytona_client.py      Daytona canary orchestration
  app.py                 FastAPI agent service entrypoint
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

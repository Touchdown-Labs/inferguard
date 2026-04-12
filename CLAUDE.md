# InferGuard — Agent Instructions

## What this is

Autonomous KV cache inference optimization agent (v6). Three-layer architecture:
- **L2** (`src/inferguard/`) — core monitoring, detection, memory. No `rlm` or `daytona-sdk` imports.
- **L3** (`blaxel_agent/`) — Blaxel-hosted AI brain with RLM decomposer + Daytona canary client. No `inferguard.*` imports.
- **L4** — Daytona sandbox for canary replay (external, called from L3).

## Layer isolation (hard rule)

- `src/inferguard/*.py` must NEVER import `rlm`, `daytona`, or `daytona_sdk`. Those are L3 deps only.
- `blaxel_agent/*.py` must NEVER import from `inferguard.*`. L3 uses dict payloads, not shared types.
- Every `ProactiveAdvisory` and `SafeAction` must have `advisory_only=True`. No code path creates a non-advisory record in v1.

## Key files

| File | Role |
|---|---|
| `src/inferguard/agent.py` | Reactive watch loop + proactive cycle dispatch via BrainClient |
| `src/inferguard/brain_client.py` | L2-to-L3 bridge. `local` mode imports brain.py in-process; `remote` uses BlAgent |
| `src/inferguard/safe_actions.py` | SAFE action factories (recommend_compaction, throttle, drain, flush, quarantine, shrink_spec) + `decide_safe_actions` rule cascade |
| `src/inferguard/metrics.py` | Prometheus scrape, `detect_anomalies`, `detect_rlm_anomalies`, `get_effective_kv_threshold` |
| `src/inferguard/memory.py` | Upstash Redis + Vector memory facade |
| `src/inferguard/diagnosis.py` | GMI Cloud `/chat/completions` for structured diagnosis |
| `src/inferguard/config.py` | Env-backed config including brain_mode, proactive_cycle_every |
| `blaxel_agent/brain.py` | InferGuardBrain — W1-W4 decomposition prompt, GMI call, advisory emission |
| `blaxel_agent/rlm_decomposer.py` | `rlm` package wrapper with direct-GMI fallback |
| `blaxel_agent/daytona_client.py` | Daytona canary client with graceful degradation |
| `blaxel_agent/app.py` | FastAPI for `bl deploy` |
| `demo/run_demo.py` | Single-command demo launcher |
| `demo/mock_endpoint.py` | Deterministic vLLM mock scenarios (healthy, pressure_ramp, incident, recovery, self_repair) |
| `demo/static/index.html` | Dashboard with Autonomous Actions + Proactive Advisories panels |

## PRD authority

| Version | File | Governs |
|---|---|---|
| v4 | `docs/inferguard/08-2026-04-11-prd-v4-final.md` | v1 scope (models, engines, GPUs) |
| v5 | `docs/inferguard/11-2026-04-11-prd-v5-production-failure-modes.md` | 10-mode failure taxonomy |
| v5.1 | `docs/inferguard/12-2026-04-11-prd-v5.1-compaction-addendum.md` | AM compaction advisory |
| v6 | `docs/inferguard/14-2026-04-11-prd-v6-blaxel-daytona-rlm-split.md` | Three-layer architecture |

## Running the demo

```bash
INFERGUARD_BRAIN_MODE=local \
GMI_API_KEY=your-key GMI_MODEL=deepseek-ai/DeepSeek-V3.2 \
python demo/run_demo.py --scenario incident --model deepseek-ai/DeepSeek-R1-0528
```

## Testing

```bash
pytest tests/ -v
```

## Commit convention

Follow RTK: `NN-YYYY-MM-DD-slug.md` for docs. Focused commits per milestone. SDLC + changelog entries for material work.

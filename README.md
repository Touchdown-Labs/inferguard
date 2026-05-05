# InferGuard

[![License: Apache-2.0](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](LICENSE)
[![CI](https://img.shields.io/github/actions/workflow/status/touchdown-labs/inferguard/ci.yml?branch=main)](https://github.com/touchdown-labs/inferguard/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/inferguard.svg)](https://pypi.org/project/inferguard/)
[![Python Versions](https://img.shields.io/pypi/pyversions/inferguard.svg)](https://pypi.org/project/inferguard/)

**InferenceX tells you how fast the hardware is; InferGuard tells you why your serving stack is breaking and where to look.**

InferGuard is an OSS-safe CLI + MCP server for read-only inference diagnostics, lightweight OpenAI-compatible endpoint benchmarking, and evidence-gated profile → diagnose → recommend → cliff → cost workflows.

> **How InferGuard fits the Touchdown Labs AI Spend Recovery wedge.** InferGuard is the OSS substrate behind the Touchdown Labs *AI Spend Recovery* services line — the audit/diagnose/optimize playbook that turns "our AI bill is too high" into a ranked, dollar-quantified savings backlog with shipped fixes. InferGuard provides the trace ingestion, KV stress probes, runtime correlation, and finding-code surface that the audit relies on. The customer-facing wedge framing lives in `docs/strategy/98-2026-05-03-touchdown-labs-AI-SPEND-RECOVERY-CANONICAL-WEDGE-...md` (CEO/CFO category) and the engineering audit blueprint lives in `docs/sdlc/134-2026-05-03-inference-utilization-truth-matrix-audit-blueprint-...md` (hardware × model × workload × KV truth matrix). The 50-cause ranked GPU underutilization taxonomy used by `inferguard analyze` lives in `docs/strategy/99-2026-05-03-touchdown-labs-GPU-UNDERUTILIZATION-50-CAUSE-TAXONOMY-...md`.

## What it is / is not

InferGuard OSS includes:

- `inferguard disagg status` for read-only prefill/decode metrics checks.
- `inferguard bench replay` for replaying trace JSONL against `/v1/chat/completions` endpoints.
- `inferguard bench kv-stress` for synthetic long-context pressure probes.
- `inferguard analyze` for native bench outputs plus supported existing benchmark artifacts.
- `inferguard validate-completed` for completed-run publishability validation and claim-keyed downgrades.
- `inferguard request-profile` for per-request TTFT, TPOT, E2E latency, token, and failure evidence.
- `inferguard collect-metrics` for normalized vLLM/SGLang/LMCache/DCGM metric timelines.
- `inferguard launch-engine` for vLLM/SGLang/LMCache launch capture, healthcheck, and external-launch validation.
- `inferguard diagnose-bottleneck` for the eight-verdict prefill/decode/KV/queue/network/host/launch/no-evidence diagnosis layer.
- `inferguard classify-failures` for 12-class failure triage from job logs and artifacts.
- `inferguard report-completed` for refusal-gated operator recommendations from completed evidence.
- `inferguard find-cliffs` for capacity-envelope and cliff detection across completed sweeps.
- `inferguard compute-cost` for cost-per-useful-task and safe concurrency envelopes.
- `inferguard agentx-ingest` for AgentX result CSV to canonical InferGuard artifact conversion; `inferguard ingest-agentx` remains an alias.

InferGuard OSS is **not**:

- a dashboard, leaderboard, SaaS agent, or hosted control plane;
- a Kubernetes/cloud provisioner;
- an authenticated GMI/OpenAI account manager;
- a source of true KV eviction/fragmentation claims unless your engine metrics separately prove them;
- a source of operator recommendations when required live evidence is missing. The Phase B/C reports mark claims `not_proven`, downgrade synthetic evidence, or refuse to recommend rather than filling gaps with guesses.

The benchmark and profile clients make network calls only to endpoints you pass with runtime flags such as `--endpoint`, `--engine-metrics-url`, or `--dcgm-metrics-url`.

## Privacy

- Zero telemetry by default in every channel: OSS CLI, harness wrapper, daemon, and tests all start disabled.
- No phone-home from the CLI; network calls happen only to endpoints you pass explicitly via flags such as `--endpoint`, `--prefill`, `--decode`, or `--metrics-url`.
- `INFERGUARD_TELEMETRY=disabled` and `DO_NOT_TRACK=1` are honored as hard overrides that consent tokens cannot bypass.
- Consent tokens are stored separately at `~/.config/inferguard/secrets/consent.token` with mode `0o600`; pending payloads live under `~/.config/inferguard/uploads-pending/`.
- Full source-of-truth posture: [`docs/telemetry/v0/POSTURE.md`](docs/telemetry/v0/POSTURE.md).
- Verifiable locally with `inferguard telemetry status` and `inferguard telemetry verify-payload <PATH>`.

## v0.5 New: Harness layer

Production-grade in v0.5:

| Status | Capability | What shipped |
|---|---|---|
| ✅ Production | NeoCloud environment detection | Modal, Crusoe Slinky/CMK, CoreWeave CKS/SUNK, Lambda 1-Click signals, Fireworks target metadata, RadixArk/SGLang, and GMI mode detection. |
| ✅ Production | Multi-node daemon fan-in | `inferguard daemon start --leader` and `--follower <leader-url>` merge rank-labeled follower snapshots into a leader Prometheus endpoint. |
| ✅ Production | DCGM × vLLM correlation | `inferguard.harness.dcgm_correlate` and `scripts/run_dcgm_correlated.sh` emit `dcgm-correlated/v1` JSONL keyed by DCGM GPU UUID/index labels. |
| ✅ Production | LangGraph agent tracing | `LangGraphCallback` records model-call, tool-call, and branch nodes into redacted `agent-trace/v1` JSONL. |
| ✅ Production | Privacy gates | Broader outbound-call test guards, value-level redaction, hard opt-outs, secure consent-token storage, and local payload audit. |

Command summary:

- `inferguard agent trace ...` — wrap a subprocess and write redacted `agent-trace/v1` JSONL; use `LangGraphCallback` for production LangGraph DAG capture.
- `inferguard daemon start|stop|status` — run the local sidecar, or use `--leader` / `--follower` for multi-node fan-in.
- `inferguard telemetry status|enable|disable|log|verify-payload` — audit zero-by-default telemetry consent and inspect the local-only v0.5 payload spool.

Framework-hook status:

| Framework | v0.5 status |
|---|---|
| LangGraph | ✅ Production callback hook. |
| raw OpenAI-compatible traffic | ✅ HTTP/proxy capture path. |
| CrewAI | ⚠️ Stub; raises `NotImplementedError` in v0.5. |
| AutoGen | ⚠️ Stub; raises `NotImplementedError` in v0.5. |
| Claude Code | ⚠️ Stub; raises `NotImplementedError` in v0.5. |
| Cursor SDK | ⚠️ Stub; raises `NotImplementedError` in v0.5. |

## Install

After the public release is published to PyPI:

```bash
pip install inferguard
```

If the package has not appeared on PyPI yet, install from TestPyPI or from a checkout:

```bash
python3 -m pip install --index-url https://test.pypi.org/simple/ --extra-index-url https://pypi.org/simple/ inferguard
# or from a checkout
pip install -e '.[dev]'
```

Check the CLI:

```bash
inferguard --help
inferguard bench replay --help
inferguard bench kv-stress --help
inferguard analyze --help
```

## Launch vLLM or SGLang on bare metal

Template scripts are included as placeholders you can copy and edit for a GMI bare-metal host or any equivalent machine:

```bash
cp scripts/launch_vllm_gmi.sh /tmp/launch_vllm_gmi.sh
MODEL_NAME=/models/deepseek-v4 TP_SIZE=8 PORT=8000 /tmp/launch_vllm_gmi.sh

cp scripts/launch_sglang_gmi.sh /tmp/launch_sglang_gmi.sh
MODEL_NAME=/models/deepseek-v4 TP_SIZE=8 PORT=8000 /tmp/launch_sglang_gmi.sh
```

Both scripts launch an OpenAI-compatible server. They do not provision machines, install drivers, authenticate, or manage cloud APIs. `MODEL_NAME` is intentionally required; use a local/private GMI model path or a verified model repo.

## DSv4 agent trace pack and smoke test

InferGuard v0.3.0 includes the ISB-1 DSv4 Agent Trace Pack at `traces/isb1-dsv4-agent/`. It is synthetic, contains no real customer data, and is intended for long-context coding-agent, multi-agent, prefix-reuse, tool-heavy, session-resume, and KV-pressure replay.

The trace format is OpenAI-compatible `messages` shape (role/content) consumed by `inferguard bench replay`. AgentX's compact KV-hash replay schema is a separate artifact shape.

For a quick endpoint validation before a full GMI run:

```bash
MODEL_NAME=/models/deepseek-v4 \
ENDPOINT_URL=http://127.0.0.1:8000/v1/chat/completions \
scripts/run_dsv4_smoke.sh
```

The smoke script checks endpoint readiness, captures a best-effort `disagg status`, replays the DSv4 trace pack at concurrency `1,4`, and writes an analyzer report. For the full GMI execution plan, see `../../docs/runbooks/03-2026-04-29-gmi-dsv4-bare-metal-bench.md` from the Touchdown-Labs repo root.

## Replay traces

Trace files are JSONL. Each line must include:

```json
{
  "trace_id": "trace-001",
  "session_id": "session-a",
  "turn_index": 0,
  "workload_class": "coding-long",
  "messages": [{"role": "user", "content": "Explain this codebase."}],
  "expected_input_tokens": 8192,
  "expected_output_tokens": 512,
  "prefix_group": "repo-a",
  "tool_heavy": false,
  "metadata": {"source": "example"}
}
```

Run replay:

```bash
inferguard bench replay \
  --endpoint http://127.0.0.1:8000/v1/chat/completions \
  --model /models/deepseek-v4 \
  --trace-dir ./traces/isb1-dsv4-agent \
  --concurrency 1,4,8,16,32 \
  --redact-prompts \
  --output-dir ./runs/replay-001
```

The client uses HTTP streaming and measures TTFT from request start to the first non-empty generated content token. First SSE timing is recorded separately. If the endpoint omits OpenAI usage token counts, InferGuard records approximate counts with `input_tokens_source: estimated` and/or `output_tokens_source: estimated`.

For DSv4 streaming, set `tool_choice=none` in traces and do not request tool calls during benchmark runs to mitigate vLLM Issue #40800 (DSv4 + auto + streaming can intermittently leak DSML fragments).

For safety, endpoints with URL userinfo, query strings, or fragments are rejected so secrets are not copied into artifacts. `--output-dir` must be empty unless you pass `--force`; `--force` allows writing into a non-empty output directory and known artifact files may be overwritten. Use `--redact-prompts` before sharing artifacts outside the operator team.

## KVCast / KV stress

`kvcast` is the preferred command for synthetic cache stress. `kv-stress` remains as a compatibility alias with the same mode options. Supported modes are:

- `cold-pressure`: unique long contexts; infer raw cache/memory pressure.
- `prefix-reuse`: shared repo/session prefix; measure warm-cache behavior when engine metrics are available.
- `mixed-agent`: mixed coding-agent traffic shape with shared prefixes, cold sessions, resumes, and tool-heavy turns.

Example:

```bash
inferguard bench kvcast \
  --mode cold-pressure \
  --endpoint http://127.0.0.1:8000/v1/chat/completions \
  --model /models/deepseek-v4 \
  --context-lengths 8192,32768,65536,131072 \
  --concurrency 1,4,8,16 \
  --requests-per-level 16 \
  --duration-seconds 600 \
  --warmup-seconds 120 \
  --output-tokens 512 \
  --redact-prompts \
  --output-dir ./runs/kvcast-cold-pressure-001
```

KV pressure is labeled `inferred_without_engine_metrics`. Use `--duration-seconds` plus `--warmup-seconds` for partner-preview runs; otherwise throughput should be treated as finite-batch smoke-test output. Use engine Prometheus metrics or logs if you need true eviction, fragmentation, offload, or prefix-cache conclusions.

## Analyze results

Analyze native InferGuard bench output or supported existing artifacts:

```bash
inferguard analyze ./runs/replay-001 --output-dir ./runs/replay-001/inferguard_report
inferguard analyze ./runs/kvcast-cold-pressure-001 --format both --fail-on never
```

The analyzer writes `report.json` and/or `report.md` and keeps `inferguard analyze <results_dir>` usable for previously supported result layouts.

## Native bench artifacts

Each bench run writes these files under `--output-dir`:

| File | Purpose |
|---|---|
| `run.json` | Run identity, timing, InferGuard version, artifact paths. |
| `config.json` | Endpoint, model, command, concurrency, and workload config. |
| `requests.jsonl` | Normalized request specs used in the run. |
| `metrics.jsonl` | One row per request per concurrency level, including latency, TTFT, success, token counts, and token source labels. |
| `summary.json` | Aggregate counts, failed rate, runtime, latency/TTFT percentiles, throughput, token totals, concurrency summaries, workload breakdown. |
| `report.md` | Human-readable summary. |

`requests.jsonl` stores replay prompt text unless `--redact-prompts` is used. Treat native bench output directories as sensitive if your traces contain proprietary prompts, code, hostnames, or customer data.

## GMI bare-metal workflow

For the v0.3.0 DSv4 campaign, use the full runbook at `../../docs/runbooks/03-2026-04-29-gmi-dsv4-bare-metal-bench.md` from the Touchdown-Labs repo root.

1. Reserve or access a bare-metal GMI host with GPUs and drivers already installed.
2. Install the serving engine and model weights according to your internal runbook.
3. Copy one of the template launch scripts from `scripts/` and fill in model, TP size, memory, and context parameters.
4. Verify the server exposes `/v1/chat/completions`.
5. Run `inferguard bench replay` for trace-derived traffic or `inferguard bench kv-stress` for synthetic long-context pressure.
6. Archive the output directory and run `inferguard analyze` to produce publishable JSON/Markdown evidence.

## Disaggregated status and MCP usage

```bash
inferguard disagg status --prefill http://localhost:18000 --decode http://localhost:18001 --json
inferguard-mcp --transport stdio
```

Exposed MCP tools:

1. `disagg_status(prefill_url, decode_url, transfer_url?)`
2. `path_trace(sample_size=10)`
3. `recent_events(minutes=10)`

## Supported engines

| Engine | Status | Coverage notes |
|---|---|---|
| vLLM | Supported | `disagg_status` + OpenAI-compatible bench when the server exposes `/v1/chat/completions`. |
| SGLang | Supported | `disagg_status` + OpenAI-compatible bench when the server exposes `/v1/chat/completions`. |
| NVIDIA Dynamo | Detected — adapter pending | `disagg_status`; bench support depends on the exposed OpenAI-compatible endpoint. |
| llm-d | Detected — adapter pending | `disagg_status`; bench support depends on the exposed OpenAI-compatible endpoint. |

See:
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)
- [docs/ANALYZE.md](docs/ANALYZE.md)
- [docs/SUPPORTED_INPUTS.md](docs/SUPPORTED_INPUTS.md)
- [docs/SUPPORTED_ENGINES.md](docs/SUPPORTED_ENGINES.md)
- [docs/SCHEMAS.md](docs/SCHEMAS.md)

## Limitations

- Token estimation is approximate without endpoint `usage` fields.
- Synthetic KV stress approximates context length with code-like text; it is not model-tokenizer exact.
- Native bench does not collect engine metrics; KV pressure is inferred unless you co-publish metrics/logs.
- No auth/login/dashboard/SaaS/Kubernetes/cloud APIs are included in OSS.

## Community

- [Contributing](CONTRIBUTING.md)
- [Code of Conduct](CODE_OF_CONDUCT.md)
- [Security](SECURITY.md)

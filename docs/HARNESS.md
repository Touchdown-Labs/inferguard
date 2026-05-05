---
title: "InferGuard Harness Layer"
status: "production-v0.5-contract"
date: "2026-04-30"
purpose: "Operator-facing production guide for the v0.5 harness layer, including NeoCloud detection, multi-node fan-in, LangGraph tracing, DCGM correlation, and privacy gates."
supersedes-policy: "Updates the v0.5 draft harness overview; does not supersede oss/inferguard/docs/SPEC.md."
---

# InferGuard Harness Layer

## 1. Source of truth

This document describes the v0.5 InferGuard harness for OSS readers and production operators.
It is an operator guide, not the architecture authority.
The canonical design is `docs/designs/2026-04-30-inferguard-harness-architecture.md`.
The production-readiness investigation is `docs/investigations/2026-04-30-v0.5-harness-production-readiness.md`.
The public-source research note is `docs/research/38-2026-04-30-industry-harness-research.md`.
The existing OSS CLI contract remains `oss/inferguard/docs/SPEC.md`.
The zero-telemetry posture is published in `oss/inferguard/docs/telemetry/v0/POSTURE.md`.
The opt-in telemetry schema is published in `oss/inferguard/docs/telemetry/v1/SPEC.md`.
The agent trace schema is published in `oss/inferguard/docs/schemas/agent-trace-v1.md`.
The DCGM correlation schema is published in `oss/inferguard/docs/schemas/dcgm-correlated-v1.md`.

## 2. What the harness is

The harness is the v0.5 layer around the existing InferGuard OSS CLI.
It does not replace `bench`, `analyze`, `disagg status`, or MCP.
It adds production-ready environment detection, LangGraph tracing, multi-node daemon fan-in, DCGM × vLLM correlation, and auditable telemetry tooling.
It is built for operators running real inference systems, not synthetic demos.
The target operator runs vLLM, SGLang, Dynamo-vLLM, or a compatible OpenAI-style endpoint.
The target workload includes DeepSeek V4 style long-context requests and coding-agent traces.
The target hardware includes H100, H200, B200, and GB200 topologies.
The harness can run fully offline.
The harness keeps the OSS trust posture intact.
The harness creates local artifacts that can later feed hosted analysis only after explicit consent.

## 3. Three-layer architecture

InferGuard remains split into three layers.
The split is the product boundary.
Each higher layer asks the operator to grant more trust.
Each lower layer remains useful without the higher layer.

| Layer | Name | Trust requirement | Network behavior | Account requirement |
|---|---|---:|---|---|
| 1 | OSS CLI | None beyond running local code | User-supplied endpoints only | None |
| 2 | Harness | Local package install and optional sidecar | Same as CLI unless telemetry is explicitly enabled | None unless uploading |
| 3 | Hosted | Account, token, terms, and retention policy | `api.touchdown.ai` or enterprise endpoint | Required |

The Layer 1 CLI is the wedge.
It runs `inferguard bench`, `inferguard analyze`, `inferguard disagg status`, and the read-only MCP server.
It writes local artifacts.
It does not phone home.
It does not require a Touchdown account.
It does not require the harness.

The Layer 2 harness is the integration layer.
It understands where the workload is running.
It can wrap a LangGraph callback or an agent subprocess.
It can watch an endpoint continuously.
It can fan in multi-node follower snapshots to a leader.
It can align per-GPU DCGM samples with vLLM aggregate metrics.
It can render a telemetry payload before any upload exists.
It is Apache-2.0 OSS.
It keeps state locally.
It remains optional.

The Layer 3 hosted service is InferGuard Ops.
It receives explicitly consented telemetry.
It performs peer aggregation.
It runs diagnose-and-recommend agents.
It powers dashboards and longer-term InferKV workload analysis.
It is not required for local CLI or harness use.

## 4. What is production-ready in v0.5

v0.5 keeps the existing v0.4 CLI surface valid and adds the production-grade harness surfaces below.
These are no longer labeled experimental in operator docs:

| Capability | Status | Implementation |
|---|---|---|
| NeoCloud environment detection | Production-ready v0.5 | `inferguard.harness.env.EnvironmentAdapter` detects Modal, Crusoe, CoreWeave, Lambda, Fireworks metadata, RadixArk/SGLang, and GMI. |
| Multi-node daemon fan-in | Production-ready v0.5 | `inferguard.harness.cluster_daemon.ClusterDaemon` supports leader/follower mode, rank labels, heartbeats, stale follower marking, and buffered replay. |
| DCGM × vLLM correlation | Production-ready v0.5 | `inferguard.harness.dcgm_correlate.DcgmCorrelator` emits `dcgm-correlated/v1` JSONL. |
| LangGraph callback hook | Production-ready v0.5 | `LangGraphCallback` records model, tool, and branch nodes into `agent-trace/v1`. |
| Privacy gates and secure local storage | Production-ready v0.5 | Broad outbound test guards, value-level redaction, hard opt-outs, and consent token storage under `~/.config/inferguard/secrets/`. |

v0.5 still does not add default telemetry.
v0.5 still does not upload to the network by default.
v0.5 still does not ship a hosted ingest server.
v0.5 still uses `mechanism: "stub"` and `library: "stub"` for DP metadata; real PipelineDP integration remains a later hosted release.
CrewAI, AutoGen, Claude Code, and Cursor SDK framework hooks remain explicit stubs in v0.5 and raise `NotImplementedError` when requested.

## 5. Installation

Install the normal OSS CLI when you only need local diagnostics.

```bash
python -m pip install inferguard
```

Install the harness extra when you want agent tracing or daemon mode.

```bash
python -m pip install 'inferguard[harness]'
```

Operators who vendor the package may pin the release.

```bash
python -m pip install 'inferguard[harness]==0.7.1'
```

The harness must not start background services at install time.
The harness must not open sockets at import time.
The harness must not make outbound calls at import time.
The harness starts only when a user invokes a harness command.
The daemon starts only when a user invokes a daemon command or installs a service explicitly.

## 6. Directory layout

The v0.5 harness code lives under `oss/inferguard/src/inferguard/harness/`.
The v0.5 schema validators live under `oss/inferguard/src/inferguard/schemas/`.
The harness docs live under `oss/inferguard/docs/`.
Agent-trace schema docs live under `oss/inferguard/docs/schemas/`.
Telemetry posture docs live under `oss/inferguard/docs/telemetry/`.
Local runtime artifacts should be created under user-controlled output directories.
Daemon state should live under a user config or cache directory.
Telemetry consent secrets live under `~/.config/inferguard/secrets/`.
Telemetry pending payloads live under `~/.config/inferguard/uploads-pending/`.

## 7. Command summary

| Command | Layer | Default network behavior | Purpose |
|---|---|---|---|
| `inferguard agent trace <subprocess args...>` | Harness | Local proxy to user target only when configured | Capture agent DAG shape, model calls, tool calls, timing, and counts |
| `inferguard daemon start` | Harness | Local metrics and user endpoints only | Start a sidecar watcher for endpoint metrics and recent artifacts |
| `inferguard daemon start --leader` | Harness | Binds the configured host/port for follower fan-in | Start a cluster fan-in leader and merged Prometheus endpoint |
| `inferguard daemon start --follower <leader-url>` | Harness | Posts privacy-gated local snapshots to the leader URL | Start a follower rank that buffers while the leader is unavailable |
| `inferguard daemon stop` | Harness | None | Stop the local sidecar |
| `inferguard daemon status` | Harness | None | Show sidecar state, socket path, watched endpoints, and buffer health |
| `inferguard telemetry status` | OSS/Harness | None | Prove current telemetry state and hard overrides |
| `inferguard telemetry enable` | Harness | v0.5 local pending write; hosted upload deferred | Start explicit consent flow |
| `inferguard telemetry disable` | Harness | None | Disable telemetry and clear local upload work |
| `inferguard telemetry log` | Harness | None | Show local telemetry attempt log |
| `inferguard telemetry verify-payload` | OSS/Harness | None | Render exact candidate payload for audit |

## 8. NeoCloud environment adapter

The environment adapter normalizes how InferGuard runs commands and labels artifacts.
It detects local PTY execution.
It detects Docker execution.
It detects Slurm execution from scheduler environment variables.
It detects Kubernetes execution from service environment variables and downward-API labels.
It detects bare-metal multi-node patterns from NCCL and host topology hints.
It detects provider-specific production environments for Modal, Crusoe, CoreWeave, Lambda, Fireworks metadata, RadixArk/SGLang, and GMI.
It can represent a GB200 disaggregated prefill/decode pair as one logical target.
It emits a rig context that later code can use for labels and paths.
It lets the same CLI command run in local development, CI, and production scheduler contexts.

Detection precedence is:

```text
Modal → Crusoe → CoreWeave → Lambda → GMI → RadixArk/SGLang → Generic K8s → Slurm → Docker → Local
```

### 8.1 Provider capability matrix

| Provider | Env detection | Multi-node | DCGM correlation | Agent trace LangGraph |
|---|---|---|---|---|
| Modal | `MODAL_TASK_ID`, sandbox, region, cloud, and `modal.experimental.get_cluster_info()` rank/cluster metadata. | Supported via Modal clustered rank metadata plus `daemon` leader/follower fan-in over Modal private networking. | Supported when the operator exposes vLLM and DCGM Prometheus endpoints in the Modal container. | Supported through `LangGraphCallback`; non-LangGraph framework hooks remain stubs. |
| Crusoe | Slinky/CMK node-type labels and hostnames such as `b200-180gb-sxm-ib.8x` and `h200-141gb-sxm-ib.8x`; does not rely on undocumented `CRUSOE_INSTANCE_ID`. | Supported for Slinky-managed Slurm pods by running one follower per rank and one leader per job. | Supported with DCGM exporter on each GPU node and vLLM metrics URL passed to the correlator. | Supported through `LangGraphCallback`; non-LangGraph framework hooks remain stubs. |
| CoreWeave | CKS/SUNK labels: `ds.coreweave.com/nvlink.domain`, `node.coreweave.cloud/rack`, `ib.coreweave.cloud/fabric`, and `ib.coreweave.cloud/superpod`. | Supported for SUNK/Slurm jobs with topology-aware scheduling and rank fan-in. | Supported on GB200/Hopper nodes with DCGM exporter default port 9400 and vLLM metrics. | Supported through `LangGraphCallback`; non-LangGraph framework hooks remain stubs. |
| Lambda | 1-Click cluster signals, Lambda env hints, managed K8s/Slurm, and InfiniBand fallback. | Supported for Slurm/K8s jobs once an operator starts leader/follower daemons in the allocation. | Supported when endpoint and DCGM Prometheus surfaces are reachable. | Supported through `LangGraphCallback`; non-LangGraph framework hooks remain stubs. |
| Fireworks | Target-provider metadata for Fireworks dedicated endpoints; hosted runtime env is the operator's own. | Supported when the operator has a multi-node deployment behind a dedicated endpoint and runs local fan-in daemons. | Supported only for self-managed fleets where the operator has DCGM/vLLM metrics; hosted-only endpoints expose no DCGM. | Supported through `LangGraphCallback` for local client-side agents pointed at Fireworks endpoints. |
| RadixArk | `SGLANG_*`, RadixArk deployment IDs, commercial SGLang signals, and `--enable-metrics` detection. | Supported for SGLang deployments with one follower per rank/container and a leader service. | Supported when SGLang/vLLM-compatible metrics and DCGM exporter are available; SGLang requires metrics enabled. | Supported through `LangGraphCallback`; non-LangGraph framework hooks remain stubs. |
| GMI | Scratch-path, GPU model, bare-metal/CaaS/K8s mode, and existing GMI campaign conventions. | Supported for bare-metal, CaaS, K8s, and Slurm jobs through leader/follower fan-in. | Supported by `scripts/run_dcgm_correlated.sh` and the Python correlator. | Supported through `LangGraphCallback`; non-LangGraph framework hooks remain stubs. |

The NeoCloud facts above are grounded in the investigation's public web probe and the industry research note.
Examples: Modal clustered functions expose `modal.experimental.get_cluster_info()` rather than Slurm env, Crusoe Managed Slurm runs on CMK via Slinky, CoreWeave CKS/SUNK exposes the rack/NVLink/InfiniBand labels listed above, and SGLang metrics require `--enable-metrics`.

### 8.2 Environment examples

Example local run:

```bash
inferguard bench replay --endpoint http://localhost:8000/v1/chat/completions --input requests.jsonl
```

Example Slurm-oriented pattern:

```bash
inferguard daemon start --env slurm --metrics-url http://127.0.0.1:8000/metrics
```

Example disaggregated endpoint pattern:

```bash
inferguard bench replay \
  --prefill-url http://prefill:8000/v1/chat/completions \
  --decode-url http://decode:8000/v1/chat/completions \
  --input requests.jsonl
```

## 9. Agent tracing

Agent tracing answers one operator question: what did the agent actually do with my inference endpoint?
The output is `agent-trace/v1` JSONL.
The normative schema is `oss/inferguard/docs/schemas/agent-trace-v1.md`.

The production-ready v0.5 framework hook is LangGraph.
Use it from Python when the agent process can install a callback:

```python
from inferguard.harness import AgentTracer, LangGraphCallback

tracer = AgentTracer(output_dir="runs/agent-trace-001", framework="langgraph")
graph.invoke({"input": "debug this repository"}, config={"callbacks": [LangGraphCallback(tracer)]})
tracer.finish()
```

`LangGraphCallback` captures:

- `on_chat_model_start` and `on_chat_model_end` as `kind="model_call"` nodes;
- `on_tool_start` and `on_tool_end` as `kind="tool_call"` nodes;
- `on_chain_start` and `on_chain_end` as `kind="branch"` nodes.

HTTP-only capture remains the fallback when hooks are unavailable.
CrewAI, AutoGen, Claude Code, and Cursor SDK labels are accepted as documented framework names but their v0.5 hooks raise `NotImplementedError` by design.
Do not document those four hooks as production-ready until their adapters ship.

Expected local outputs include an agent trace JSONL file.
Expected local outputs may include a summary file.
Expected local outputs may include a DOT graph for visualization.
The default trace redacts prompt text.
The default trace redacts model output text.
The default trace redacts tool argument values.
A local-only `--save-prompts` debugging mode may exist.
That debugging mode must never be uploaded by telemetry.

## 10. Daemon mode and multi-node fan-in

Daemon mode is an explicit sidecar.
It does not run after install.
It does not run unless the operator starts it.
It can poll a metrics endpoint.
It can keep a local ring buffer of recent traces and metrics.
It can expose Prometheus-compatible local metrics.
It can support scheduled local benchmarks.
It can support retroactive analysis by retaining recent local context.
It should bind local control surfaces to localhost or a Unix socket for single-node mode.
It can bind a configured cluster leader address for multi-node fan-in.
It should report watched endpoints clearly.

Start a single-node daemon:

```bash
inferguard daemon start --metrics-url http://127.0.0.1:8000/metrics
```

Check daemon status:

```bash
inferguard daemon status
```

Stop the daemon:

```bash
inferguard daemon stop
```

Daemon mode is for operators who want continuous context.
It is not required for one-shot `bench` or `analyze` runs.
It is not required for agent tracing.
It is not required for telemetry verification.

### 10.1 Multi-node deployment guide

Use leader/follower mode when a benchmark spans multiple Slurm ranks, Kubernetes pods, Modal clustered containers, or GB200 disaggregated workers.
Exactly one process should run as the leader.
Every other rank should run as a follower.
Followers POST aggregate snapshots to the leader.
The leader exposes merged Prometheus `/metrics` keyed by rank labels.

Create a shared cluster token on the job filesystem:

```bash
install -d -m 700 "$HOME/.config/inferguard"
python - <<'PY' > "$HOME/.config/inferguard/cluster.token"
import secrets
print(secrets.token_urlsafe(32))
PY
chmod 600 "$HOME/.config/inferguard/cluster.token"
```

Start the leader on rank 0:

```bash
inferguard daemon start \
  --leader \
  --host 0.0.0.0 \
  --port 9466 \
  --cluster-token "$HOME/.config/inferguard/cluster.token" \
  --watch-dir "$RESULTS_ROOT/traces/rank-${RANK:-0}"
```

Start a follower on every nonzero rank:

```bash
inferguard daemon start \
  --follower "http://${INFERGUARD_LEADER_HOST:-leader}:9466" \
  --host 0.0.0.0 \
  --port "${INFERGUARD_FOLLOWER_PORT:-9467}" \
  --cluster-token "$HOME/.config/inferguard/cluster.token" \
  --watch-dir "$RESULTS_ROOT/traces/rank-${RANK:-1}"
```

The follower payload includes `slurm_procid`, `slurm_nodeid`, `cluster_node_name`, `cluster_id`, and `rank` when those labels are present.
The leader marks a follower stale after 30 seconds without a heartbeat.
Followers retain a five-minute buffer when the leader is temporarily unavailable and replay buffered snapshots after reconnect.
Cluster fan-in is privacy-gated on both leader and follower.

Validate the merged leader endpoint:

```bash
curl -fsS "http://${INFERGUARD_LEADER_HOST:-127.0.0.1}:9466/metrics" | grep -E 'inferguard_.*rank|inferguard_cluster_followers'
```

Provider-specific runbooks under `docs/runbooks/05-*`, `06-*`, and `07-*` show CoreWeave SUNK, Modal clustered, and Crusoe Slinky/CMK deployment patterns.

## 11. DCGM × vLLM correlation

The v0.5 correlator emits `dcgm-correlated/v1` JSONL from a vLLM metrics endpoint and a DCGM exporter endpoint.
It samples both endpoints on an aligned five-second window by default.
It keys DCGM rows by `gpu_uuid` using the exporter `UUID` label.
It preserves the `gpu` index label as `gpu_index`.
It broadcasts vLLM aggregate fields onto every GPU row in the same window and labels them as aggregate context, not per-GPU vLLM measurements.
It emits a null row instead of crashing when a scrape is empty or malformed.

Run the existing script when benchmarking a local vLLM endpoint:

```bash
cd oss/inferguard
MODEL_NAME="deepseek-ai/DeepSeek-V4-Pro" \
ENDPOINT_URL="http://127.0.0.1:8000/v1/chat/completions" \
VLLM_METRICS_URL="http://127.0.0.1:8000/metrics" \
DCGM_METRICS_URL="http://127.0.0.1:9400/metrics" \
TRACE_DIR="traces/isb1-dsv4-agent" \
OUTPUT_DIR="runs/dcgm-correlated-001" \
scripts/run_dcgm_correlated.sh
```

Use the Python helper directly when the benchmark is launched by another scheduler:

```bash
python -m inferguard.harness.dcgm_correlate \
  --vllm-metrics-url "${VLLM_METRICS_URL:-http://127.0.0.1:8000/metrics}" \
  --dcgm-metrics-url "${DCGM_METRICS_URL:-http://127.0.0.1:9400/metrics}" \
  --output-dir "$RESULTS_ROOT/dcgm-correlated" \
  --duration-seconds "${CORRELATION_DURATION_SECONDS:-600}" \
  --interval-seconds "${INTERVAL_SECONDS:-5}"
```

The default DCGM exporter port is 9400.
The standard fields are `DCGM_FI_DEV_*` names.
The industry research note documents the DCGM exporter and vLLM/SGLang metrics that this correlator consumes.

## 12. Telemetry in v0.5

Telemetry is default-off.
Telemetry remains default-off in every channel.
`DO_NOT_TRACK=1` is a hard override.
`INFERGUARD_TELEMETRY=disabled` is a hard override.
A fresh install must report no telemetry.
A fresh install must make no outbound telemetry calls.
The posture file is `oss/inferguard/docs/telemetry/v0/POSTURE.md`.
The v1 opt-in schema file is `oss/inferguard/docs/telemetry/v1/SPEC.md`.

Status check:

```bash
inferguard telemetry status
```

Expected fresh-install posture:

```text
No telemetry. No network calls outside endpoints you pass via flags. Verified: see oss/inferguard/docs/telemetry/v0/POSTURE.md.
```

Enable flow:

```bash
inferguard telemetry enable --consent-token "$INFERGUARD_CONSENT_TOKEN"
```

The enable flow must show the schema first.
The enable flow must require explicit user action.
The enable flow must record consent state locally.
The consent token is stored at `~/.config/inferguard/secrets/consent.token` with file mode `0o600`.
Pending local payloads are stored separately under `~/.config/inferguard/uploads-pending/`.
The enable flow must honor hard opt-out environment variables.
In v0.5, enabled telemetry produces local pending payloads only.
In v0.5, real hosted upload is not shipped.

Disable flow:

```bash
inferguard telemetry disable
```

The disable flow must stop future payload generation.
The disable flow must clear pending payloads.
The disable flow must make status return disabled.
The disable flow must not require network access.

## 13. Payload audit

Operators must be able to inspect telemetry before trusting it.
`inferguard telemetry verify-payload` renders candidate bytes.
It must include the schema version.
It must include consent state.
It must include redaction flags.
It must include the DP parameters that would be used.
It must not include prompt text.
It must not include output token text.
It must not include tool argument values.
It must not include file paths.
It must not include environment variables.
It must not include API keys.
It must not include IP addresses.
It must not include usernames.
It must not include raw KV block IDs.
It must not include raw block hashes.

Example:

```bash
inferguard telemetry verify-payload runs/agent-trace-001
```

## 14. Operator workflow

Start with the existing CLI.
Run a benchmark against a target endpoint.
Analyze the local artifacts.
Use agent tracing when the workload is an agent, not a static replay.
Use daemon mode when the endpoint should be observed over time.
Use leader/follower fan-in when the job has more than one rank.
Use DCGM correlation when GPU power, thermal, utilization, or XID context is needed.
Use telemetry status to prove default-off behavior.
Use verify-payload before enabling telemetry.
Enable telemetry only after reviewing the payload contract.
Disable telemetry whenever the local policy changes.
Use hosted service only when peer aggregation or Ops agents are desired.

## 15. Trust invariants

The CLI must remain useful without the harness.
The harness must remain useful without hosted upload.
The hosted layer must not be required for local artifact analysis.
No background service may start at install time.
No telemetry may be sent without explicit enablement.
No prompt text may be included in default traces.
No output text may be included in default traces.
No tool arguments may be included in default traces.
No code path may bypass `DO_NOT_TRACK=1`.
No code path may bypass `INFERGUARD_TELEMETRY=disabled`.
No real upload path ships in v0.5.

## 16. Relationship to OpenTelemetry

InferGuard should interoperate with existing observability stacks.
The OpenTelemetry GenAI mapping is documented in `docs/research/38-2026-04-30-industry-harness-research.md` §D.1.
`input_tokens` maps to `gen_ai.client.token.usage` with token type `input`.
`output_tokens` maps to `gen_ai.client.token.usage` with token type `output`.
`ttft_seconds` maps to `gen_ai.server.time_to_first_token`.
`latency_seconds` maps to `gen_ai.client.operation.duration`.
The conventions are experimental as of the cited research note.
InferGuard should label exported spans clearly when OpenTelemetry export is enabled.
OpenTelemetry export must be separately configured by the operator.
OpenTelemetry export is not the same thing as Touchdown telemetry.

## 17. What v0.5 does not do

v0.5 does not implement hosted dashboards.
v0.5 does not implement cross-customer aggregation.
v0.5 does not implement real PipelineDP noise.
v0.5 does not ingest raw KV block IDs.
v0.5 does not ingest raw block hashes.
v0.5 does not implement autonomous remediation.
v0.5 does not implement CrewAI, AutoGen, Claude Code, or Cursor SDK hooks beyond explicit stubs.
v0.5 does not require ACP or Atropos RL.
v0.5 does not provision cloud infrastructure.

## 18. Troubleshooting

If `telemetry status` reports disabled, that is the expected fresh-install state.
If `DO_NOT_TRACK=1` is set, telemetry must stay disabled.
If `INFERGUARD_TELEMETRY=disabled` is set, telemetry must stay disabled.
If agent tracing records no model calls, confirm the target process uses the LangGraph callback or an OpenAI-compatible endpoint proxy.
If a non-LangGraph framework hook raises `NotImplementedError`, that is expected in v0.5.
If a multi-node follower does not appear on the leader, confirm the shared `cluster.token`, leader URL, rank network route, and privacy opt-in.
If DCGM correlation emits null rows, confirm the DCGM exporter is reachable on port 9400 and exposes `UUID` or `gpu` labels.
If verify-payload contains sensitive strings, treat that as a release blocker.
If network verification finds unexpected calls, treat that as a release blocker.

## 19. Review checklist

Read the canonical design at `docs/designs/2026-04-30-inferguard-harness-architecture.md`.
Read the production-readiness investigation at `docs/investigations/2026-04-30-v0.5-harness-production-readiness.md`.
Read the industry research note at `docs/research/38-2026-04-30-industry-harness-research.md`.
Read the current CLI spec at `oss/inferguard/docs/SPEC.md`.
Read the agent schema at `oss/inferguard/docs/schemas/agent-trace-v1.md`.
Read the DCGM correlation schema at `oss/inferguard/docs/schemas/dcgm-correlated-v1.md`.
Read the v0 posture at `oss/inferguard/docs/telemetry/v0/POSTURE.md`.
Read the v1 telemetry spec at `oss/inferguard/docs/telemetry/v1/SPEC.md`.
Confirm every cross-reference is repo-relative.
Confirm local-only behavior works without a hosted account.
Confirm default-off telemetry is visible in `telemetry status`.
Confirm sensitive defaults are redacted in agent traces and telemetry payloads.
Confirm multi-node fan-in is documented in the provider runbook used by the operator.

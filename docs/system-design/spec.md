---
title: Spec
description: The full InferGuard specification.
---

**Status:** canonical v1.0.12 architecture specification
**Date:** 2026-05-03
**Owner:** Touchdown Labs
**Canonical path:** `oss/inferguard/docs/SPEC.md`
**Repo scope:** `oss/inferguard/` OSS package plus referenced Touchdown planning docs
**Supersedes:** architectural authority of `oss/inferguard/docs/ARCHITECTURE.md` and scattered InferGuard Bench + Analyze SDLC / research / runbook notes.
**Does not delete:** SDLC, changelog, research, and runbook docs remain the audit trail.

This document is the single source of truth for **InferGuard Bench + Analyze** in the OSS package. It consolidates the current implementation, schemas, engine surfaces, workload pack, artifact contracts, run topology, and claim boundaries.

Every claim in this spec is grounded in the actual code in `oss/inferguard/src/inferguard/**`. Where the code emits less than a sibling doc claims, this spec records the **emitted-today** behavior and marks the rest as planned.

---

## 0. Document control

### 0.1 What this spec supersedes

This spec supersedes the architectural authority of:

- `oss/inferguard/docs/ARCHITECTURE.md` — currently disagg-only and not bench/replay/kvcast/analyze-aware. After this spec lands, that file becomes a one-line pointer to this spec.
- `docs/sdlc/67-2026-04-29-inferguard-bench-product-scope.md` — still the primary product-scope audit record, but no longer the canonical architecture spec.
- Related SDLC / changelog / research fragments listed in §12.

Existing docs may remain as quickstarts, detailed schema appendices, or audit trail. **Future architectural changes must update this spec first.**

### 0.2 Update history

### v1.0.12 (2026-05-03)

- Added Phase 1 LMCache/TensorMesh internal coverage only: a dedicated LMCache Prometheus adapter module (`src/inferguard/disagg/adapters/lmcache.py`) and normalized schema (`src/inferguard/disagg/metrics_schema.py`).
- Normalized live LMCache metric aliases for hit/miss counts, hit rate, evictions, save/retrieve counts, tier residency bytes, offload/NIXL bytes, retrieve/NIXL latency, CacheBlend/CacheGen/MP mode, connector type, and cache-salt exposure; unknown LMCache metric names are preserved in `raw_metrics_extra`.
- Added six deterministic LMCache workload JSONL generators under `src/inferguard/bench/workloads/lmcache_*.py`: `multi_round_chat`, `long_doc_qa`, `mtrag_reorder`, `agent_skills`, `multi_tenant_salt`, and `mp_moe_redundant_prefill`.
- Operator brief now always renders "LMCache comparison" and "Measured vs inferred" sections. LMCache/TensorMesh findings without live engine metrics remain labeled `inferred_without_engine_metrics`; cross-tenant isolation remains `not_proven` unless cache-salt engine evidence is present.

### v1.0.11 (2026-05-03)

- Added CI/CD + deployment safety cluster scenarios from the OWN backlog: S-79 canary quality regression, S-80 blue/green p99 regression, S-82 tokenizer mismatch rollout, and S-83 prompt-template/tool-parser regression.
- New finding codes: `canary_quality_regression`, `blue_green_p99_regression`, `tokenizer_mismatch_silent_drift`, and `prompt_template_tool_parser_regression`.
- `bench replay` adds `--canary-eval-set <path-or-dataset>` and `--tool-call-schema <path>` and emits `canary_quality` / `tool_call_schema_eval` summary blocks when configured.
- `bench compare` adds `--blue-green`, treating run A as blue/baseline and run B as green/candidate, with statistically-gated p99 TTFT/TPOT regression findings.
- `inferguard preflight` adds `--detect-tokenizer-mismatch` plus tokenizer probe evidence fields. Operator brief adds Quality regression, Blue/green comparison, Output structure, and tokenizer/config drift rendering.

### v1.0.10 (2026-05-03)

- Added S-26 retry-storm characterization via `bench kvcast --mode retry-storm` with `--burst-multiplier`, `--burst-window-seconds`, and `--baseline-rps`.
- New finding code: `retry_storm_engine_overload` with `{burst_peak_qps, queue_depth_max, recovery_seconds, preemption_count}` evidence.
- Deepened S-01 `cold_start_ramp_extended` evidence to include `model_load_seconds`, `cudagraph_capture_seconds`, and `first_60s_p99_ttft_seconds`; operator brief adds "Cold-start decomposition".
- Deepened S-03 `engine_crash_recovery_slow` evidence with `in_flight_request_loss_count`, `customer_error_signature`, and `successful_retry_count_post_recovery`; operator brief adds "Crash recovery".
- Operator brief adds "Retry storm" section summarizing burst survival, queue depth, recovery, and preemptions.

### v1.0.9 (2026-05-03)

- Added S-14 idle GPU amortization cost-economics depth.
- New finding code: `cost_idle_underutilization_high`.
- `bench replay` adds `--idle-active-mix-mode`, `--active-window-seconds`, and `--idle-window-seconds` to alternate active traffic and idle windows for utilization economics characterization.
- Analyzer cost output now includes `cost_economics` with `cost_per_token_by_utilization[]`, `customer_idle_amortization[]`, and `idle_amortization_penalty` relative to a 90% target utilization.
- Operator brief adds a "Cost economics" section with utilization-bucket $/token and per-customer idle-amortization rows.

### v1.0.8 (2026-05-03)

- Added Item A failure-mode characterization scenarios: S-09 partial GPU degradation and S-11 giant-prefill OOM blast-radius characterization.
- New finding codes: `gpu_partial_degradation` and `oom_giant_prefill_blast_radius`.
- `dcgm-correlated/v1` consumers now detect per-GPU SM-activity, temperature, XID, and ECC divergence against the cluster median. `gpu_partial_degradation` evidence includes `{gpu_index, gpu_uuid, divergence_metric, divergence_value}` plus optional window context.
- `bench replay` adds `--inject-giant-prefill-tokens N`, gated by `--allow-chaos`, and emits `oom_giant_prefill` summary/timeline fields with `{killed_batch_count, killed_in_flight_count, engine_recovery_seconds, engine}`.
- Operator brief adds a Hardware health section and includes both new findings in JSON and Markdown output.

### v1.0.7 (2026-05-02)

- Added platform-engineer scenario coverage from `docs/inferguard/24`: S-21 per-customer KV footprint accounting, S-13 per-customer × workload cost decomposition, S-07 cache-lineage scaffolding, S-05 `bench kvcast --mode multi-tenant-storm`, S-01 `bench cold-start`, and S-03 gated crash-recovery scaffolding.
- New finding codes: `kv_footprint_imbalance`, `prefix_eviction_cross_customer`, `cold_start_ramp_extended`, `engine_crash_recovery_slow`, and `multi_tenant_noisy_neighbor`.
- New flags: `bench replay --track-cache-lineage`; `bench kvcast --customers`, `--sla-tiers`, `--track-cache-lineage`, `--inject-crash-after-seconds`, `--allow-chaos`; and new `bench cold-start --capture-seconds`.
- Operator brief now renders top-5 "KV by customer" and "Cost by customer × workload" tables. Full engine block-ID lineage and SGLang #23743 chaos reproduction remain 🟡 PENDING upstream instrumentation/version-gated expansion.

### v1.0.5 (2026-05-02)

- Added `inferguard profile live` as a top-level live endpoint profiler that observes existing `/metrics` traffic, streams profile findings, and emits `inferguard-profile-sample/v1` / `inferguard-profile-summary/v1` artifacts.

### v1.0.5 (2026-05-01)

- Extended KVCast with `eviction-probe` and `fragmentation-probe`, 512K/1M default context bands, and Poisson arrival scheduling for `bench kvcast`.

### v1.0.5 (2026-05-01)

- Added `inferguard bench compare` and `inferguard-compare/v1` artifacts for cross-engine ISB-1 parity reports.

### v1.0.4 (2026-05-01)

- Reconcile §5 adapter coverage with actual code state; add prefix-cache fields per R2.

### v1.0.3 (2026-05-01)

- Added `inferguard analyze --operator-brief/--no-operator-brief` and `inferguard-operator-brief/v1` artifacts for GMI operator handoff.

### v1.0.2 (2026-04-30)

- Added Tier 1 SemiAnalysis-shape parity: topology capture in native bench `config.json`, analyzer v1.1 throughput/interactivity/QPS/full percentile/workload-shape metrics, and `inferguard-agentx-export/v1` per-cell `agg_*.json` export.
- Added `inferguard analyze --emit-agentx-shape <PATH>` for AgentX/InferenceX-compatible JSON output.

Material changes require:

1. Update this file and bump the version line.
2. Add a new SDLC entry under `docs/sdlc/NN-YYYY-MM-DD-…md`.
3. Add a changelog entry under `docs/changelog/NN-YYYY-MM-DD-…md`.
4. Preserve schema compatibility per §4.16.

### 0.3 How to read this spec

- **§§1–2** are orientation: what InferGuard is, what it is not, how it fits.
- **§§3–4** are the API surfaces (CLI / MCP / schemas) — paste-quality.
- **§5** is the engine specification — the section the rest of the world wants.
- **§6** is the workload pack.
- **§§7–9** describe how to run benchmarks and consume the outputs.
- **§10** is claim hygiene — read before publishing partner-facing material.
- **§11** is the roadmap — what is deliberately not in OSS today.
- **§12** is the audit trail.
- **§§14–16** are v0.5 production harness additions: multi-node fan-in, NeoCloud detection, and DCGM correlation.

---

## 1. Overview

InferGuard OSS is a read-only inference diagnostics and benchmark-analysis package for production-like LLM serving workloads.

It has six OSS surfaces:

1. **Live overlay:** `inferguard disagg status`
2. **Live profiler:** `inferguard profile live` observes existing endpoint traffic via `/metrics`
3. **Preflight checks:** `inferguard preflight` catches known launch compatibility traps before paid benchmark traffic
4. **Native benchmark runner:** `inferguard bench replay`, `inferguard bench kvcast`, `inferguard bench kv-stress`
5. **Cross-engine comparator:** `inferguard bench compare <run_a_dir> <run_b_dir>`
6. **Post-run analyzer:** `inferguard analyze <results_dir>`
7. **MCP server:** `inferguard-mcp` exposing `disagg_status`, `path_trace`, `recent_events`

### 1.1 Product statement

InferGuard Bench + Analyze answers:

> Is this inference benchmark result valid, where did the serving stack degrade, and what evidence explains the bottleneck?

It complements SemiAnalysis **InferenceX** and **AgentX**. It does not replace them.

### 1.2 What InferGuard OSS is not

InferGuard OSS is not:

- an inference engine;
- a leaderboard;
- a dashboard or SaaS control plane;
- a cloud / Kubernetes provisioner;
- an authenticated GMI / OpenAI account manager;
- an auto-remediator;
- a private memory / recall agent;
- a replay validator with actuation;
- a source of true KV eviction / fragmentation claims without engine metrics;
- a replacement for InferenceX benchmark authority;
- a replacement for AgentX trace replay infrastructure.

### 1.3 Ecosystem split

```text
InferenceX     = benchmark authority / scoreboard
AgentX         = trace replay and agentic benchmark infrastructure
ISB-1          = workload traces and stress scenarios
InferGuard CLI = run + live diagnostics + analyze + report layer
GMI Cloud      = hardware execution substrate / co-publish partner
SemiAnalysis   = methodology authority and benchmark credibility
Touchdown Labs = diagnostics, workload interpretation, and report layer
```

This split is the scope boundary. InferGuard complements; it does not compete.

---

## 2. Architecture

### 2.1 Component map

```text
OpenAI-compatible endpoint
        │
        ├── inferguard bench replay / kvcast / kv-stress
        │       ├── requests.jsonl
        │       ├── metrics.jsonl
        │       ├── summary.json
        │       └── report.md
        │
        ├── inferguard disagg status
        │       ├── /metrics scrape
        │       ├── engine adapter
        │       └── detector findings
        │
        └── external harness artifacts
                ├── InferenceX agg_*.json
                ├── AgentX detailed_results.csv
                ├── AgentX metrics_server_metrics.csv
                └── eval results*.json

All artifacts
        │
        └── inferguard analyze <results_dir>
                ├── report.json
                ├── report.md
                ├── operator_brief.json  (when --operator-brief, or default-on with --gpus)
                └── operator_brief.md    (when --operator-brief, or default-on with --gpus)
```

### 2.2 OSS modules

| Module | Purpose |
|---|---|
| `inferguard.cli` | Typer CLI for `disagg`, `bench`, and `analyze`. |
| `inferguard.mcp_server` | MCP server exposing read-only tools. |
| `inferguard.disagg.*` | Live Prometheus scrape, engine detection, detector rules, public disagg schema types. |
| `inferguard.profile.*` | Live endpoint profiler loop, profile-local findings, and `profile.jsonl` / summary artifacts. |
| `inferguard.bench.*` | Native replay / KVCast runner, OpenAI streaming client, synthetic workloads, artifact writer. |
| `inferguard.schemas.trace` | Trace JSONL validation and workload-class enum. |
| `inferguard.analyze.*` | Read-only post-run artifact parser, compare reporter, and report generator. |
| `inferguard.metrics_core` | Dependency-free Prometheus text parser. |
| `inferguard.utils.jsonl` | JSONL artifact writer. |

### 2.3 Data flow

1. Operator launches a vLLM / SGLang / Dynamo-vLLM serving stack.
2. Optional live overlay runs `inferguard disagg status`.
3. Optional live profile runs `inferguard profile live --endpoint <url>` against an already-loaded endpoint; it does not send chat/completion traffic.
4. Benchmark executes via InferenceX, AgentX, or native `inferguard bench`.
5. Artifacts are stored under a results directory.
6. `inferguard bench compare <run_a_dir> <run_b_dir>` can compare two native/upstream bench run directories and emit `inferguard-compare/v1` artifacts.
7. `inferguard analyze <results_dir>` discovers supported artifacts.
8. Analyzer emits `inferguard-analyze/v1.1` `report.json` and a human `report.md`.

### 2.4 OSS layer rule

The OSS package must not import private / pro-tier modules.

Forbidden import names:

```text
agent
brain_client
diagnosis
memory
executor
replay_validation
safe_actions
remediation
blaxel_agent
```

**Intended coverage:**

- `src/inferguard/disagg/**`
- `src/inferguard/profile/**`
- `src/inferguard/bench/**`
- `src/inferguard/schemas/**`
- `src/inferguard/utils/**`
- `src/inferguard/analyze/**`
- `src/inferguard/cli.py`
- `src/inferguard/mcp_server.py`

**Current workflow coverage (2026-04-29):** `.github/workflows/layer-lint.yml` checks all intended OSS boundary paths listed above.

### 2.5 Claim hygiene levels

| Level | Meaning |
|---|---|
| `dev` | Local smoke result, not publishable. |
| `internal` | Useful for Touchdown debugging, not partner-facing. |
| `partner-preview` | Shareable with GMI / SemiAnalysis with caveats. |
| `publishable` | Complete artifact bundle, valid run, claim boundaries documented. |
| `semianalysis-compatible` | Uses InferenceX / AgentX methodology and preserves upstream authority. |

---

## 3. CLI and MCP specification

### 3.1 `inferguard disagg status`

```bash
inferguard disagg status \
  --prefill <url> \
  --decode <url> \
  [--transfer <url>] \
  [--engine auto|vllm|sglang|dynamo|llm-d] \
  [--json] \
  [--timeout seconds]
```

Behavior:

- Scrape `/metrics` from prefill / decode / optional transfer endpoints.
- Normalize engine metrics into `disagg-status/v1`.
- Run detector rules (§4.1).
- Print table or JSON.

Exit codes:

| Code | Meaning |
|---:|---|
| 0 | No warning / critical findings. |
| 1 | Warning finding present. |
| 2 | Critical finding present. |

### 3.1a `inferguard profile live`

```bash
inferguard profile live \
  --endpoint <endpoint-or-metrics-url> \
  [--duration 60] \
  [--interval 2] \
  [--engine auto|vllm|sglang|dynamo|lmcache|llm-d] \
  [--output-dir inferguard_profile_live] \
  [--format table|json] \
  [--timeout seconds]
```

Behavior:

- Observes an existing endpoint by scraping `{endpoint}/metrics`; if the operator passes a URL ending in `/metrics`, the CLI normalizes it to the endpoint base URL.
- Does **not** send OpenAI/chat/completion traffic.
- Computes sample-to-sample deltas for cumulative counters such as `preemptions_total`, prefix-cache hits/queries, KV-transfer counters, and KV-offload counters.
- Streams profile findings as soon as rules trip: high/critical KV usage, rising preemptions, queue backlog, low prefix-hit-rate delta, offload churn, and metrics unavailable.
- Writes `profile.jsonl` (`inferguard-profile-sample/v1`), `profile_summary.json` (`inferguard-profile-summary/v1`), and `profile.md`.

Exit codes:

| Code | Meaning |
|---:|---|
| 0 | Profile artifacts written; no warning / critical findings. |
| 1 | Warning finding present. |
| 2 | Critical finding present. |
| 3 | Invalid profile options, scrape-loop setup failure, or artifact writing failure. |

### 3.1b `inferguard preflight`

```bash
inferguard preflight \
  [--model deepseek-ai/DeepSeek-V4-Pro] \
  [--engine vllm|sglang|dynamo|lmcache|llm-d|auto] \
  [--kv-offloading-backend native] \
  [--disable-hybrid-kv-cache-manager / --no-disable-hybrid-kv-cache-manager] \
  [--config config.json] \
  [--detect-tokenizer-mismatch --endpoint <openai-chat-completions-url>] \
  [--sample-text "Hello world..."] \
  [--client-tokenizer <label> --server-tokenizer <label>] \
  [--json]
```

Behavior:

- Runs local, read-only compatibility checks before benchmark traffic.
- Currently surfaces the HMA/native-offload guard for hybrid-attention model families such as DeepSeek V4 on vLLM.
- Accepts a native bench `config.json` and reads `model`, `framework`, `kv_offloading_backend`, `offloading`, and `disable_hybrid_kv_cache_manager` fields when present.
- Emits `inferguard-preflight/v1` JSON when `--json` is supplied.
- When `--detect-tokenizer-mismatch` is supplied, compares a client-side token count for known text with server `usage.prompt_tokens` (or config-provided probe counts) and emits `tokenizer_mismatch_silent_drift` when divergence exceeds 1%.

Exit codes follow finding severity: 0 for no findings, 1 for warnings, 2 for critical findings, and 3 for unreadable config input.

### 3.2 `inferguard bench replay`

```bash
inferguard bench replay \
  --endpoint <openai-chat-completions-url> \
  --model <model> \
  --trace-dir <trace-jsonl-dir> \
  [--concurrency 1,4,8,16,32] \
  [--output-dir inferguard_bench_replay] \
  [--output-tokens 512] \
  [--timeout 300] \
  [--duration-seconds seconds] \
  [--warmup-seconds seconds] \
  [--force] \
  [--redact-prompts] \
  [--idle-active-mix-mode --active-window-seconds N --idle-window-seconds M] \
  [--inject-giant-prefill-tokens N --allow-chaos] \
  [--canary-eval-set <path-or-hf-dataset>] \
  [--tool-call-schema <path>] \
  [--json]
```

Behavior:

- Replay validated trace JSONL records against `/v1/chat/completions`.
- Use HTTP streaming.
- Measure TTFT from request start to first non-empty streamed `delta.content` (first SSE timing recorded separately).
- Write the six native artifacts listed in §8.1.
- When `--idle-active-mix-mode` is supplied, alternate active request windows and idle windows. The runner records `idle_active_mix` metadata so the analyzer can compute idle amortization and cost-per-token by utilization bucket.
- When `--inject-giant-prefill-tokens N --allow-chaos` is supplied, inject one oversized prefill request mid replay, emit `oom_giant_prefill` summary metadata, and append before/during/after batch-state records to `metrics_timeline.jsonl`.
- When `--canary-eval-set` points to a local eval artifact, emit canary quality summary evidence with baseline/canary accuracy, sample count, and a two-proportion significance estimate.
- When `--tool-call-schema` is supplied, validate captured tool-call JSON response structure against the expected schema and emit compliance-rate evidence.

### 3.3 `inferguard bench kvcast`

```bash
inferguard bench kvcast \
  --endpoint <openai-chat-completions-url> \
  --model <model> \
  [--context-lengths 8192,32768,65536,131072,524288,1048576] \
  [--concurrency 1,4,8,16] \
  [--mode cold-pressure|prefix-reuse|mixed-agent|eviction-probe|fragmentation-probe|multi-tenant-storm|retry-storm] \
  [--burst-multiplier 50 --burst-window-seconds 30 --baseline-rps 4] \
  [--output-tokens 512] \
  [--requests-per-level 4] \
  [--duration-seconds seconds] \
  [--warmup-seconds seconds] \
  [--arrival-mode steady|poisson] \
  [--arrival-rate-rps float] \
  [--redact-prompts] \
  [--force] \
  [--json]
```

Modes:

| Mode | Meaning |
|---|---|
| `cold-pressure` | Unique long contexts; no shared prefix group. |
| `prefix-reuse` | Shared synthetic prefix; warm-cache / prefix-reuse probe. |
| `mixed-agent` | Mix of shared prefixes, cold sessions, resumes, and tool-heavy turns. |
| `eviction-probe` | Warm an anchor prefix, issue larger pressure traffic, then retest the anchor prefix as a cold-resume penalty probe. |
| `fragmentation-probe` | Interleave short, mid/resume, and long requests to expose allocator / KV-memory fragmentation symptoms. |
| `multi-tenant-storm` | Mixed tenant classes with independent customer IDs and SLA tiers. |
| `retry-storm` | Function/tool retry burst: baseline request rate multiplied for a fixed burst window, then recovery observed. |

KV pressure from this command is always labeled:

```text
inferred_without_engine_metrics
```

### 3.4 `inferguard bench kv-stress`

Compatibility alias for KVCast mode generation. Uses the same mode machinery as `kvcast`. Command identity remains `inferguard bench kv-stress`. The default context bands match `kvcast`, including 512K and 1M synthetic targets.

### 3.5 `inferguard bench agentx-replay`

```bash
inferguard bench agentx-replay \
  --endpoint <openai-api-base-url> \
  --model <model-label> \
  --trace-source <hf-dataset-or-local-path> \
  [--concurrency 32] \
  [--duration-seconds 1800] \
  [--output-dir inferguard_bench_agentx_replay] \
  [--tester-path <kv-cache-tester-checkout-or-script>] \
  [--allow-network-clone] \
  [--json]
```

Behavior:

- Wraps Cam Quilici's external `kv-cache-tester` AgentX trace replay tester (`trace_replay_tester.py`).
- If `--tester-path` is omitted, uses `~/.cache/inferguard/agentx-tester/`; it clones `https://github.com/callanjfox/kv-cache-tester.git` branch `agentx-minimized` only when `--allow-network-clone` is passed.
- Runs the tester with `--start-users` and `--max-users` both set to `--concurrency`, `--test-duration`, recycled traces, original inter-turn timing, and server metrics output enabled.
- Warns when `--duration-seconds < 900`, because AgentX steady-state runs should be at least 15 minutes.
- Converts AgentX `detailed_results.csv` rows into InferGuard `requests.jsonl`, `metrics.jsonl`, `summary.json`, `run.json`, and `report.md` artifacts while retaining the raw CSVs.

### 3.6 `inferguard bench upstream`

```bash
inferguard bench upstream vllm|sglang \
  --profile <profile> \
  --model <model> \
  [--endpoint http://localhost:8000] \
  [--num-prompts 100] \
  [--request-rate <float>] \
  [--dataset-path <path>] \
  [--enable-radix-cache / --disable-radix-cache] \
  [--output-dir inferguard_bench_upstream] \
  [--timeout seconds] \
  [--force] \
  [--json]
```

Supported profiles:

| Engine | Profiles |
|---|---|
| `vllm` | `random`, `sharegpt`, `prefix-repetition`, `sonnet` |
| `sglang` | `random` |

Behavior:

- Shells out to `vllm bench serve` or `python3 -m sglang.bench_serving`.
- Captures upstream stdout/stderr and the JSON payload when emitted.
- Writes `inferguard-bench-upstream/v1` `run.json` plus InferGuard-compatible
  `config.json`, `requests.jsonl`, `metrics.jsonl`, and `summary.json` so
  `inferguard analyze <results_dir>` can ingest the run directory.

### 3.7 `inferguard bench compare`

```bash
inferguard bench compare <run_a_dir> <run_b_dir> \
  [--output-dir inferguard_bench_compare] \
  [--label-a vllm] \
  [--label-b sglang] \
  [--min-identity-overlap 0.50] \
  [--strict-identity] \
  [--cost-per-gpu-hour <float>] \
  [--gpus <int>] \
  [--blue-green] \
  [--force] \
  [--json]
```

Behavior:

- Reads two bench run directories containing `summary.json` plus optional `config.json`, `requests.jsonl`, and `metrics.jsonl`.
- Emits `compare.json` with `schema_version: "inferguard-compare/v1"` and a human `compare.md` report.
- Validates cross-run trace identity using deduplicated `(trace_id, turn_index)` keys from `requests.jsonl`, falling back to `metrics.jsonl` when request specs are unavailable.
- Treats identity overlap as valid only when `overlap / min(run_a_count, run_b_count) > --min-identity-overlap`; default is >50%.
- Emits a warning finding for low overlap by default, or exits with code 3 before writing if `--strict-identity` is set.
- Compares each workload class with p99 TTFT, p99 TPOT, p99 latency, optional cost-per-task, and cliff-concurrency deltas. Delta fields are `run_b - run_a`.
- With `--blue-green`, treats run A as blue/baseline and run B as green/candidate; emits `blue_green_p99_regression` when candidate p99 TTFT or TPOT is >1.5× baseline and the raw metric distributions pass a p<0.05 significance gate.

### 3.8 Native bench exit codes

| Code | Meaning |
|---:|---|
| 0 | Benchmark artifacts written and either at least one request succeeded or no requests were attempted. |
| 2 | Requests were attempted and all requests failed. |
| 3 | `BenchError` or artifact writing failure. |

Typer validation errors use Typer's standard bad-parameter behavior.

### 3.9 `inferguard analyze`

```bash
inferguard analyze <results_dir> \
  [--output-dir <path>] \
  [--format json|md|both] \
  [--fail-on never|warning|critical] \
  [--strict / --best-effort] \
  [--timeline-glob "**/inferguard_timeline.jsonl"] \
  [--cost-per-gpu-hour <float>] \
  [--gpus <int>] \
  [--cost-currency <label>] \
  [--plots] \
  [--operator-brief / --no-operator-brief] \
  [--emit-agentx-shape <path>] \
  [--json]
```

`--operator-brief` emits `operator_brief.json` and `operator_brief.md`. If the flag is omitted, the CLI enables it automatically when `--gpus` is provided.

Exit codes:

| Code | Meaning |
|---:|---|
| 0 | Report written; no finding at or above threshold. |
| 1 | Warning threshold tripped. |
| 2 | Critical threshold tripped. |
| 3 | No supported artifacts, unreadable input, or report writing failure. |

### 3.10 MCP tools

Console script:

```bash
inferguard-mcp --transport stdio
```

Tools:

| Tool | Purpose |
|---|---|
| `disagg_status(prefill_url, decode_url, transfer_url?, engine="auto")` | Return `disagg-status/v1`. |
| `path_trace(sample_size=10)` | OSS scaffold; aggregate-only. No fabricated per-session tracing (§4.2). |
| `recent_events(minutes=10)` | Return recent in-process detector events (§4.3). |

Transport behavior beyond `--transport stdio` depends on FastMCP and is documented in `README.md`, not pinned at the code-arg level.

---

## 4. Schemas and version policy

InferGuard emits versioned contracts. Breaking changes require a sibling `v2`; do not mutate existing `v1` meanings. Where the on-disk `schema_version` field exists, it is named explicitly. Where the contract is a logical row shape with no on-disk schema field, this spec marks it **logical contract name only**.

### 4.1 `disagg-status/v1` (live)

Emitted by `inferguard disagg status` and the `disagg_status` MCP tool. Source of truth: `inferguard.disagg.types.DisaggStatus`.

Required:

```text
schema_version
prefill
decode
findings
```

Optional:

```text
transfer
```

Primary types: `EndpointId`, `DisaggSnapshot`, `DisaggFinding`, `DisaggStatus`.

Detector finding codes (closed enum):

```text
connector_mismatch
prefill_decode_imbalance
kv_transfer_errors_present
kv_transfer_stall
endpoint_unreachable
engine_unidentified
```

Severity enum: `info`, `warning`, `critical`.

### 4.2 `path-trace/v1` (implemented shape)

OSS path tracing is scaffolded only. Per-session prefill / decode attribution is **not fabricated**.

Implemented response shape:

```json
{
  "schema_version": "path-trace/v1",
  "samples": [],
  "engine_support": "aggregate_only",
  "note": "Per-session path tracing is not available in the OSS tier. Use disagg_status for aggregate signals.",
  "requested_sample_size": 10
}
```

Per-session tracing requires engine labels or external tracing not included in OSS v1.


### 4.3 `recent-events/v1` (implemented shape)

Emitted by the `recent_events` MCP tool.

Implemented response shape:

```json
{
  "schema_version": "recent-events/v1",
  "window_minutes": 10,
  "events": [
    {
      "at": 1760000000.0,
      "endpoints": ["http://prefill", "http://decode"],
      "code": "connector_mismatch",
      "severity": "warning",
      "message": "..."
    }
  ]
}
```

Current event records use `at` (epoch float) and `endpoints` (list). They do **not** include `t`, singular `endpoint`, or `evidence` keys.

### 4.4 `inferguard-timeline/v1` (planned wrapper)

JSONL wrapper format the analyzer can consume from a live overlay capture loop. Each line is either this wrapper or a raw `disagg-status/v1` object.

Required wrapper fields:

```text
schema_version = "inferguard-timeline/v1"
observed_at
sequence
capabilities
disagg_status
```

Capabilities are OSS-safe constants:

```json
{
  "diagnosis": "on",
  "actuation": "off",
  "replay": "off",
  "recall": "off"
}
```

Status: planned. Analyzer already unwraps the embedded `disagg_status` when present and falls back to treating each line as a raw `disagg-status/v1` record.

### 4.5 `isb1-trace/v1` (logical contract — input to `bench replay`)

Trace JSONL input contract. The current `TraceRecord` validator does **not** require an on-record `schema_version`; the contract name is logical.

Required fields:

```text
trace_id
session_id
turn_index
workload_class
messages
```

Optional fields:

```text
expected_input_tokens
expected_output_tokens
prefix_group
tool_heavy
metadata
```

Message constraints (enforced at validation time):

- `messages` must be a non-empty list.
- `messages[*].role` must be one of `system`, `user`, `assistant`, `tool`.
- `messages[*].content` must be a string.
- Multimodal or structured tool-call content is **not** accepted in OSS v1.

`workload_class` must be a member of the closed enum in §6.2.

### 4.6 `inferguard-bench-spec/v1` (logical contract — `requests.jsonl` rows)

Logical row contract. Source of truth: `inferguard.bench.types.RequestSpec`.

Fields:

```text
request_id
trace_id
session_id
turn_index
workload_class
messages
expected_input_tokens
expected_output_tokens
prefix_group
tool_heavy
metadata
```

> **Implementation note:** Rows do **not** carry an on-disk `schema_version` field today. Treat `inferguard-bench-spec/v1` as a logical contract name. When `--redact-prompts` is used, message `content` is replaced with `<redacted>` and metadata gains `prompts_redacted: true`.

### 4.7 `inferguard-bench-metric/v1` (logical contract — `metrics.jsonl` rows)

Logical row contract. Source of truth: `inferguard.bench.types.RequestMetric`.

Fields:

```text
request_id
trace_id
session_id
turn_index
workload_class
concurrency
success
start_time
end_time
latency_seconds
ttft_seconds
input_tokens
output_tokens
input_tokens_source
output_tokens_source
tokens_per_second
error
status_code
first_sse_seconds
first_content_token_seconds
done_seen
valid_content_seen
prefix_group
tool_heavy
kv_pressure_label
metadata
```

> **Implementation note:** Rows do **not** carry an on-disk `schema_version` field today. Treat `inferguard-bench-metric/v1` as a logical contract name.

### 4.8 `inferguard-bench-summary/v1` (on-disk — `summary.json`)

Emits `schema_version: "inferguard-bench-summary/v1"`.

Fields include:

```text
run_id
command
model
endpoint
benchmark_mode
kvcast_mode
requests_per_level
duration_seconds
warmup_seconds
redact_prompts
raw_request_counts
request_counts
runtime_seconds
latency_seconds
ttft_seconds
average_tokens_per_second
throughput_req_per_second
output_tokens_per_second_wall
tokens
concurrency
workloads
customer_breakdown
cache_lineage
cold_start
chaos_recovery
oom_giant_prefill
idle_active_mix
canary_quality
tool_call_schema_eval
limitations
```

Warmup rows are excluded from summary metrics when `--warmup-seconds` is used.

`oom_giant_prefill` is present only for `bench replay --inject-giant-prefill-tokens N --allow-chaos`. It includes `inject_giant_prefill_tokens`, `killed_batch_count`, `killed_in_flight_count`, `engine_recovery_seconds`, `engine`, `blast_radius`, and before/during/after batch-state blocks when observed.

`idle_active_mix` is present only for `bench replay --idle-active-mix-mode`. It includes `mode`, `active_window_seconds`, `idle_window_seconds`, `observed_utilization`, `idle_fraction`, and `runtime_seconds`.

`canary_quality` is present only for `bench replay --canary-eval-set` when an eval set is registered or scored. It includes `baseline_accuracy`, `canary_accuracy`, `accuracy_delta`, `eval_sample_count`, and `p_value`.

`tool_call_schema_eval` is present only for `bench replay --tool-call-schema`. It includes `baseline_compliance_rate`, `candidate_compliance_rate`, `schema_id`, `divergent_field_paths`, and sample count/status fields.

### 4.9 `inferguard-bench/v1` — `run.json`

Emits `schema_version: "inferguard-bench/v1"`.

Required identity fields:

```text
run_id
command
started_at
completed_at
runtime_seconds
inferguard_version
artifacts
```

### 4.9a `inferguard-bench-agentx/v1` — `run.json`

Emits `schema_version: "inferguard-bench-agentx/v1"` for `inferguard bench agentx-replay` runs. The bridge also writes `summary.json` with `schema_version: "inferguard-bench-summary/v1"` so `inferguard analyze` can ingest the directory through the existing native-bench summary parser.

AgentX bridge artifacts include:

```text
run.json
config.json
requests.jsonl
metrics.jsonl
summary.json
report.md
trace_replay/detailed_results.csv
metrics_server_metrics.csv (when the external tester emits server metrics)
```

AgentX CSV columns ingested from `detailed_results.csv`:

```text
trace_id
request_idx
success
request_start_time
request_complete_time
ttft
ttlt
itl
input_tokens
output_tokens_actual
output_tokens_expected
cache_hit_blocks
cache_miss_blocks
```

Conversion rules:

- `input_tokens` and `output_tokens_actual` are treated as server-authoritative token counts.
- `ttft` maps to `ttft_seconds`; `ttlt` maps to end-to-end `latency_seconds`; `itl` is preserved in row metadata.
- `cache_hit_blocks` and `cache_miss_blocks` are preserved as AgentX theoretical cache-block metadata.
- The bridge runs recycled traces with original inter-turn timing and warns for durations below 900 seconds.
- Network cloning of the external tester is disabled unless `--allow-network-clone` is explicitly passed.

### 4.10 `inferguard-bench-upstream/v1` — upstream `run.json`

Emits `schema_version: "inferguard-bench-upstream/v1"` for `inferguard bench upstream`.
It is a sibling of `inferguard-bench/v1`, with additional upstream identity fields:

```text
run_id
command = upstream
engine
profile
started_at
completed_at
runtime_seconds
inferguard_version
subprocess.args
subprocess.returncode
artifacts
```

The same run directory also includes `summary.json` with
`schema_version: "inferguard-bench-summary/v1"`, `metrics.jsonl`, and
`requests.jsonl` when request-level upstream records are available. This keeps
upstream baselines analyzable without changing `inferguard analyze` discovery.

### 4.11 `inferguard-bench-config/v1` — `config.json`

Emits `schema_version: "inferguard-bench-config/v1"`. Existing bench configuration fields are preserved; v1.0.2 adds a sibling `topology` block copied from GMI launch environment variables.

Records:

```text
run_id
command
endpoint
model
concurrency_levels
output_dir
output_tokens
trace_dir
context_lengths
timeout_seconds
force
redact_prompts
kvcast_mode
requests_per_level
duration_seconds
warmup_seconds
arrival_mode
arrival_rate_rps
topology
```

`topology` keys are lower-case environment variable names captured from launch scripts when present:

```text
tp
ep_size
dp_attention
offloading
spec_decoding
hw
runner_type
model_prefix
framework
precision
image
is_multinode
prefill_num_workers
prefill_tp
prefill_ep
prefill_dp_attn
decode_num_workers
decode_tp
decode_ep
decode_dp_attn
```

### 4.12 `inferguard-analyze/v1.1` — `report.json`

Top-level analyzer output contract.

Required top-level fields:

```text
schema_version = "inferguard-analyze/v1.1"
generated_at
input_root
analyzer
run_summary
cells
findings
artifact_manifest
```

Cell `source_format` enum:

```text
inferencex-static
inferencex-srt-slurm
agentx-trace-replay
inferguard-bench-native
eval
mixed
unknown
```

**Finding codes — emitted today:**

```text
missing_required_artifact
invalid_run_no_successful_requests
partial_run
metrics_unavailable
kv_footprint_imbalance
prefix_eviction_cross_customer
cold_start_ramp_extended
engine_crash_recovery_slow
multi_tenant_noisy_neighbor
gpu_partial_degradation
oom_giant_prefill_blast_radius
cost_idle_underutilization_high
retry_storm_engine_overload
canary_quality_regression
blue_green_p99_regression
tokenizer_mismatch_silent_drift
prompt_template_tool_parser_regression
```

Additional platform-scenario evidence contracts:

| Finding code | Evidence fields |
|---|---|
| `gpu_partial_degradation` | `gpu_index`, `gpu_uuid`, `divergence_metric`, `divergence_value`, plus optional `timestamp`, `consecutive_snapshots`, `cluster_median`, and `observed_value`. |
| `oom_giant_prefill_blast_radius` | `killed_batch_count`, `killed_in_flight_count`, `engine_recovery_seconds`, `engine`, plus optional `inject_giant_prefill_tokens`, `blast_radius`, and batch-state blocks. |
| `cost_idle_underutilization_high` | `customer_id`, `observed_utilization`, `idle_fraction`, `idle_amortization_penalty`, `cost_per_token`, and `recommendation`. |
| `retry_storm_engine_overload` | `burst_peak_qps`, `queue_depth_max`, `recovery_seconds`, and `preemption_count`. |
| `cold_start_ramp_extended` | `model_load_seconds`, `cudagraph_capture_seconds`, `first_60s_p99_ttft_seconds`, `steady_state_p99_ttft_seconds`, and optional `first_successful_request_seconds`. |
| `engine_crash_recovery_slow` | `recovery_time_seconds`, `in_flight_request_loss_count`, `customer_error_signature`, and `successful_retry_count_post_recovery`. |
| `canary_quality_regression` | `baseline_accuracy`, `canary_accuracy`, `accuracy_delta`, `eval_sample_count`, and `p_value`. |
| `blue_green_p99_regression` | `stack_a_id`, `stack_b_id`, `metric`, `baseline_p99`, `candidate_p99`, `regression_factor`, and `p_value`. |
| `tokenizer_mismatch_silent_drift` | `client_tokenizer`, `server_tokenizer`, `divergence_pct`, and `sample_text_length`. |
| `prompt_template_tool_parser_regression` | `baseline_compliance_rate`, `candidate_compliance_rate`, `schema_id`, and `divergent_field_paths`. |

**Finding codes — planned / reserved (documented but not yet emitted by code):**

```text
ttft_cliff
tpot_degradation
throughput_plateau
kv_pressure
kv_offload_thrash
prefix_cache_regression
prefill_decode_imbalance
kv_transfer_stall
kv_transfer_errors_present
endpoint_unreachable
engine_unidentified
eval_regression
```

The live disagg detector codes (`prefill_decode_imbalance`, `kv_transfer_*`, `endpoint_unreachable`, `engine_unidentified`) appear in `report.json` only when an `inferguard_timeline.jsonl` file is present and is unwrapped by the analyzer.

v1.1 cell metrics add SemiAnalysis-compatible fields: `input_tput_tps`, `output_tput_tps`, `total_tput_tps`, `input_tput_per_gpu`, `output_tput_per_gpu`, `tput_per_gpu`; `mean|median|p90|p99|p99.9|std` ladders for `ttft`, `e2el`, `itl`, `tpot`, `qps`, `input_tokens`, and `output_tokens_actual`; and `mean|median|p90|p99|p99.9|std_intvty` where interactivity fields are derived from TPOT fields. `p95_*` remains as a legacy compatibility field where available.

Each cell also carries the copied `topology` block when native `config.json` provides it. `num_gpus` is derived from `--gpus`, or for multinode runs from `prefill_num_workers * prefill_tp + decode_num_workers * decode_tp`.

### 4.13 `inferguard-agentx-export/v1` — per-cell `agg_*.json`

Emitted only when `inferguard analyze --emit-agentx-shape <PATH>` is provided. One file is written per report cell as `<PATH>/agg_<cell_id>.json` with `_schema_version: "inferguard-agentx-export/v1"`.

Top-level fields match the AgentX / InferenceX aggregate shape used by upstream jq consumers:

```text
hw, conc, image, model, infmax_model_prefix, framework, precision, spec_decoding,
disagg, scenario_type, is_multinode, tp, ep, dp_attention, offloading,
num_requests_total, num_requests_successful,
mean_qps, median_qps, p90_qps, p99_qps, p99.9_qps, std_qps,
mean_ttft, median_ttft, p90_ttft, p99_ttft, p99.9_ttft, std_ttft,
mean_e2el, median_e2el, p90_e2el, p99_e2el, p99.9_e2el, std_e2el,
mean_itl, median_itl, p90_itl, p99_itl, p99.9_itl, std_itl,
mean_tpot, median_tpot, p90_tpot, p99_tpot, p99.9_tpot, std_tpot,
mean_intvty, median_intvty, p90_intvty, p99_intvty, p99.9_intvty, std_intvty,
mean_input_tokens, median_input_tokens, p90_input_tokens, p99_input_tokens, p99.9_input_tokens, std_input_tokens,
mean_output_tokens_actual, median_output_tokens_actual, p90_output_tokens_actual, p99_output_tokens_actual, p99.9_output_tokens_actual, std_output_tokens_actual,
input_tput_tps, output_tput_tps, total_tput_tps, duration_seconds,
tput_per_gpu, output_tput_per_gpu, input_tput_per_gpu
```

Multinode disaggregated exports also include `prefill_num_workers`, `prefill_tp`, `prefill_ep`, `prefill_dp_attention`, `num_prefill_gpu`, `decode_num_workers`, `decode_tp`, `decode_ep`, `decode_dp_attention`, and `num_decode_gpu`.

### 4.14 `inferguard-compare/v1` — `compare.json`

Emitted by `inferguard bench compare <run_a_dir> <run_b_dir>` alongside `compare.md`.

Required top-level fields:

```text
schema_version = "inferguard-compare/v1"
generated_at
inferguard_version
run_a
run_b
options
trace_identity
workload_classes
findings
notes
```

Run identity blocks include:

```text
path
label
engine
run_id
command
model
endpoint
request_count
success_count
```

`trace_identity` fields:

```text
run_a_count
run_b_count
overlap_count
overlap_ratio
min_required_overlap_ratio
status
sample_overlap_keys
```

`status` is `ok` only when `overlap_ratio > min_required_overlap_ratio`. Otherwise it is `low_overlap`, and the report includes a `trace_identity_overlap_low` finding.

Each `workload_classes[]` row includes:

```text
workload_class
best_engine
run_a
run_b
delta
```

The per-run workload block includes request counts, p99 TTFT, p99 TPOT, p99 latency, optional cost-per-task, and cliff concurrency. `delta` fields are run B minus run A. p99 TPOT is derived from per-request rows as `(latency_seconds - ttft_seconds) / output_tokens` when an explicit TPOT field is absent. Cliff concurrency is the first concurrency level where p99 TTFT is at least 2× the baseline level or failed-request rate reaches 10%.

### 4.14a `inferguard-profile-sample/v1` — `profile.jsonl`

Emitted by `inferguard profile live`. Each JSONL row represents one live `/metrics` scrape. Rows are additive to the disagg snapshot contract: the `snapshot` field is the normalized `DisaggSnapshot.as_dict()` payload for the observed endpoint.

Required top-level fields:

```text
schema_version = "inferguard-profile-sample/v1"
profile_id
sequence
observed_at
mode
snapshot
deltas
findings
```

Field semantics:

- `profile_id`: stable identifier for one profile run, e.g. `profile_20260502_120000`.
- `sequence`: zero-based sample number.
- `observed_at`: UTC ISO-8601 timestamp for the row.
- `mode`: `single-endpoint` for PR-T1.
- `snapshot`: normalized endpoint snapshot, including `endpoint.engine`, `kv_cache_usage`, `requests_running`, `requests_waiting`, `preemptions_total`, prefix-cache counters, transfer counters, offload counters, and `scrape_error` when present.
- `deltas`: sample-to-sample deltas for cumulative counters present in both the prior and current sample, including keys like `preemptions_total_delta`, `prefix_cache_hits_delta`, `prefix_cache_queries_delta`, and `kv_offload_bytes_gpu_to_cpu_delta`.
- `findings`: profile-local findings emitted on this sample.

Profile-local finding codes for PR-T1:

| Code | Trigger | Severity |
|---|---|---|
| `profile_kv_cache_high` | `kv_cache_usage >= 0.90`. | warning |
| `profile_kv_cache_critical` | `kv_cache_usage >= 0.95`. | critical |
| `profile_preemptions_rising` | `preemptions_total` delta > 0. | warning |
| `profile_queue_backlog` | `requests_waiting > requests_running` for 2+ samples. | warning |
| `profile_prefix_hit_rate_low` | query delta >= 50 and hit/query delta < 0.50. | info or warning |
| `profile_offload_churn` | offload counters rise while KV usage stays high. | warning |
| `profile_metrics_unavailable` | live metrics scrape failed. | critical |

### 4.14b `inferguard-profile-summary/v1` — `profile_summary.json`

Emitted by `inferguard profile live` after the sampling window completes.

Required top-level fields:

```text
schema_version = "inferguard-profile-summary/v1"
profile_id
duration_seconds
sample_count
engine
highest_kv_cache_usage
max_requests_waiting
preemptions_total_delta
prefix_cache_hit_rate_observed
recommendation
findings
```

The summary aggregates high-water marks, first/last cumulative deltas, observed prefix-cache hit rate when counters are exposed, de-duplicated findings, and a one-sentence operator recommendation. It is a live profiler artifact, not a benchmark result and not a post-run analyzer report.

### 4.15 `inferguard-operator-brief/v1` — `operator_brief.json`

Emitted by `inferguard analyze --operator-brief`, and by default when `--gpus` is provided.

Required top-level fields:

```text
schema_version = "inferguard-operator-brief/v1"
generated_at
source_report
input_root
summary
best_stable_config
cliff_detection
recommended_engine_config
repro_commands
raw_artifact_paths
```

Runbook 08 adds two optional cost-focused blocks to the same v1 schema:

```text
summary.cost
cost_comparison[]
cost_economics
hardware_health[]
tokenizer_drift[]
quality_regression[]
blue_green_comparison[]
output_structure[]
```

`summary.cost` mirrors `run_summary.cost` and includes the GPU-hour price and GPU count when all cells share one value. Each `cost_comparison[]` row groups a cell by workload, engine, and cache mode and includes `gpu_hour_cost`, `gpus`, `completed_sessions`, `completed_requests`, `compute_cost`, `cost_per_completed_session`, and `cost_per_completed_request`. These are additive fields; old readers may ignore them.

`cost_economics` groups S-14 utilization economics and includes:

```text
cost_per_token_by_utilization[]
customer_idle_amortization[]
observed_utilization
idle_amortization_penalty
```

Utilization buckets are `0-25%`, `25-50%`, `50-75%`, and `75-100%`. The idle-amortization penalty is computed against a 90% target-utilization denominator.

`hardware_health[]` contains one row per `gpu_partial_degradation` finding with
`gpu_index`, `gpu_uuid`, `divergence_metric`, `divergence_value`, `severity`,
`cell_id`, and raw evidence.

`tokenizer_drift[]` contains one row per `tokenizer_mismatch_silent_drift` preflight finding and is rendered adjacent to hardware/config drift evidence.

`quality_regression[]`, `blue_green_comparison[]`, and `output_structure[]` summarize CI/CD rollout quality, p99 blue/green regressions, and prompt-template/tool-parser contract drift for orchestrators to consume as rollback evidence.

The brief is derived from `inferguard-analyze/v1.1` cells and existing run artifacts only. It does not launch benchmarks or collect new measurements.

Cliff fields:

- `best_stable_config`: per workload class, lowest cost-per-task stable cell where success rate is at least 95% and p99 TTFT is below 2x the conc=1 baseline.
- `cliff_detection.ttft_p99`: first concurrency where p99 TTFT is above 2x the conc=1 baseline, or a not-observed message.
- `cliff_detection.failure`: first concurrency where success rate drops below 95%, or a not-observed message.
- `cliff_detection.oom`: first `metrics_timeline.jsonl` sample where `gpu_cache_usage` / `kv_cache_usage` is above 0.95 or `preemptions_total` begins/increases.
- `recommended_engine_config`: one-line recommendation derived from the best stable cell.
- `repro_commands`: reconstructed native `inferguard bench ...` commands when `config.json` artifacts are present.
- `raw_artifact_paths`: absolute paths to `report.json`, discovered raw artifacts, `metrics_timeline.jsonl`, and generated plots when present.

### 4.16 Versioning policy

Rules:

1. Never change the meaning of an existing `v1` field.
2. Additive optional fields are allowed only if old readers can ignore them.
3. Breaking changes require sibling schemas (e.g., `disagg-status/v2`).
4. Reports may include both `v1` and `v2` artifacts during migration.
5. Do not silently reuse a `v1` schema name for a different artifact shape.

Examples:

- Adding optional `engine_build_info` to `DisaggSnapshot` may remain `disagg-status/v1`.
- Renaming `kv_cache_usage` or changing units requires `disagg-status/v2`.
- Adding `schema_version` row fields to `requests.jsonl` / `metrics.jsonl` is purely additive and may keep the logical contract names in §4.6 / §4.7.

---

## 5. Engine specification

The engine metric map is grounded in:

```text
src/inferguard/disagg/adapters.py
src/inferguard/disagg/engines.py
tests/fixtures/vllm.txt
tests/fixtures/sglang.txt
```

`oss/inferguard/docs/SUPPORTED_ENGINES.md` is a one-page summary; **this section is canonical**.

### 5.1 Engine detection

Auto-detection prefixes (first match wins):

| Engine | Detection prefixes |
|---|---|
| vLLM | `vllm:` |
| SGLang | `sglang:` |
| Dynamo / Dynamo-vLLM | `dynamo_`, `nv_llm_` |
| llm-d | `llmd_`, `llm_d_` |
| unknown | no recognized prefix |

Explicit `--engine` overrides auto-detection. If detection fails the adapter records `scrape_error: "no_metrics_recognized"` (or `"empty_body"`), and `detect.py` may emit `engine_unidentified`.

### 5.2 Shared connector detection

Connector labels are scanned only on KV-transfer metric families:

- vLLM: samples whose metric name starts with `vllm:kv_transfer`
- SGLang: samples whose metric name starts with `sglang:kv_transfer`

Candidate label keys are checked in this exact order:

1. `kv_transfer_backend`
2. `connector`
3. `transfer_impl`
4. `backend`

The first non-empty value wins and is lowercased. If no label is found, the connector is the empty string `""`.

### 5.3 vLLM

**Support level:** implemented in OSS v0.2.0.

Exact normalized map parsed by code:

| Normalized field | Prometheus metric |
|---|---|
| `kv_cache_usage` | `vllm:gpu_cache_usage_perc` |
| `requests_running` | `vllm:num_requests_running` |
| `requests_waiting` | `vllm:num_requests_waiting` |
| `requests_swapped` | `vllm:num_requests_swapped` |
| `preemptions_total` | `vllm:num_preemptions_total` |
| `kv_transfer_sent_bytes_total` | `vllm:kv_transfer_sent_bytes_total` |
| `kv_transfer_recv_bytes_total` | `vllm:kv_transfer_recv_bytes_total` |
| `kv_transfer_errors_total` | `vllm:kv_transfer_errors_total` |
| `prefix_cache_hits` | `vllm:prefix_cache_hits_total` |
| `prefix_cache_queries` | `vllm:prefix_cache_queries_total` |
| `cpu_prefix_cache_hits` | `vllm:cpu_prefix_cache_hits_total` |
| `cpu_prefix_cache_queries` | `vllm:cpu_prefix_cache_queries_total` |
| `kv_offload_bytes_gpu_to_cpu` | `vllm:kv_offload_bytes_gpu_to_cpu` |
| `kv_offload_bytes_cpu_to_gpu` | `vllm:kv_offload_bytes_cpu_to_gpu` |
| `kv_offload_time_gpu_to_cpu` | `vllm:kv_offload_time_gpu_to_cpu` |
| `kv_offload_time_cpu_to_gpu` | `vllm:kv_offload_time_cpu_to_gpu` |
| `cpu_kv_cache_usage_pct` | `vllm:cpu_kv_cache_usage_pct` |
| `ttft_avg_seconds` | `vllm:time_to_first_token_seconds_sum / vllm:time_to_first_token_seconds_count` |
| `tpot_avg_seconds` | `vllm:time_per_output_token_seconds_sum / vllm:time_per_output_token_seconds_count` |

Exact vLLM fixture sample names currently covered:

```text
vllm:gpu_cache_usage_perc
vllm:num_requests_running
vllm:num_requests_waiting
vllm:num_requests_swapped
vllm:num_preemptions_total
vllm:kv_transfer_sent_bytes_total{connector="nixl"}
vllm:kv_transfer_recv_bytes_total{connector="nixl"}
vllm:kv_transfer_errors_total{connector="nixl"}
vllm:prefix_cache_hits_total
vllm:prefix_cache_queries_total
vllm:cpu_prefix_cache_hits_total
vllm:cpu_prefix_cache_queries_total
vllm:kv_offload_bytes_gpu_to_cpu
vllm:kv_offload_bytes_cpu_to_gpu
vllm:kv_offload_time_gpu_to_cpu
vllm:kv_offload_time_cpu_to_gpu
vllm:cpu_kv_cache_usage_pct
vllm:time_to_first_token_seconds_sum
vllm:time_to_first_token_seconds_count
vllm:time_per_output_token_seconds_sum
vllm:time_per_output_token_seconds_count
```

Known gaps:

- vLLM prefix-cache and KV-offload metrics are normalized when Prometheus exposes the names above; first GMI live endpoint pass should verify the v0.12 offload byte/time names.
- Native bench scrapes engine metrics when `--metrics-url` is provided and promotes overlapped request `kv_pressure_label` values to `measured`.
- `path_trace` remains `aggregate_only` unless deployment exports request / session labels and the OSS scaffold is extended.

### 5.4 SGLang

**Support level:** implemented in OSS v0.2.0.

Exact normalized map parsed by code:

| Normalized field | Prometheus metric |
|---|---|
| `kv_cache_usage` | `sglang:token_usage` |
| `requests_running` | `sglang:num_running_reqs` |
| `requests_waiting` | `sglang:num_queue_reqs` |
| `preemptions_total` | `sglang:num_preemptions_total` |
| `kv_transfer_sent_bytes_total` | `sglang:kv_transfer_sent_bytes_total` |
| `kv_transfer_recv_bytes_total` | `sglang:kv_transfer_recv_bytes_total` |
| `kv_transfer_errors_total` | `sglang:kv_transfer_errors_total` |
| `ttft_avg_seconds` | `sglang:time_to_first_token_seconds_sum / sglang:time_to_first_token_seconds_count` |
| `tpot_avg_seconds` | `sglang:time_per_output_token_seconds_sum / sglang:time_per_output_token_seconds_count` |

Exact SGLang fixture sample names currently covered:

```text
sglang:token_usage
sglang:num_running_reqs
sglang:num_queue_reqs
sglang:num_preemptions_total
sglang:kv_transfer_sent_bytes_total{connector="mooncake"}
sglang:kv_transfer_recv_bytes_total{connector="mooncake"}
sglang:kv_transfer_errors_total{connector="mooncake"}
sglang:time_to_first_token_seconds_sum
sglang:time_to_first_token_seconds_count
sglang:time_per_output_token_seconds_sum
sglang:time_per_output_token_seconds_count
```

Known gaps:

- SGLang long-context / offload observability is weaker than vLLM in current runnable paths.
- Direct CPU KV / offload confirmation may require logs or additional metrics.
- The `requests_swapped` field is not collected (no equivalent SGLang metric in scope today).

### 5.5 NVIDIA Dynamo / Dynamo-vLLM

**Support level:** provisional KVBM metric normalization implemented; live endpoint validation still pending.

Detection prefixes:

```text
dynamo_
nv_llm_
```

Current adapter state in `src/inferguard/disagg/adapters.py` (`DYNAMO_FIELD_MAP` and `_DYNAMO_RESIDENCY_PREFIX`):

| Normalized field | Prometheus metric |
|---|---|
| `dynamo_block_l1_count` | `dynamo:kvbm_blocks{tier="l1_gpu"}` |
| `dynamo_block_l2_count` | `dynamo:kvbm_blocks{tier="l2_cpu"}` |
| `dynamo_block_l3_count` | `dynamo:kvbm_blocks{tier="l3_storage"}` |
| `dynamo_kvbm_evictions` | `dynamo:kvbm_evictions_total` |
| `dynamo_kvbm_promotions` | `dynamo:kvbm_promotions_total` |
| `dynamo_block_residency_seconds` | `dynamo:kvbm_block_residency_seconds_sum / dynamo:kvbm_block_residency_seconds_count` |

Behavior:

- If forced or detected as `dynamo`, the adapter parses the KVBM fields above when present.
- If no recognized Dynamo metric is present, the adapter returns `scrape_error = "no_metrics_recognized"`.
- GB200 Dynamo-vLLM benchmarking is still a target run topology through InferenceX srt-slurm recipes (§7).
- `inferguard analyze` can still parse Dynamo-vLLM benchmark artifacts via the InferenceX `agg_*.json` path.

Validation caveat:

- These metric names are inferred from Dynamo KVBM tier semantics and covered by `tests/fixtures/dynamo_kvbm.txt`; first live-endpoint pass on GMI should confirm or correct them before partner-facing "validated Dynamo live metrics" claims.

Canonical partner-facing wording:

> InferGuard can analyze Dynamo-vLLM benchmark artifacts today and has provisional Dynamo KVBM metric normalization in OSS; live Dynamo metric claims remain validation-pending until confirmed against GMI / upstream Prometheus output.

### 5.6 llm-d

**Support level:** engine **detection only**; live metric normalization is **not** implemented.

Detection prefixes:

```text
llmd_
llm_d_
```

Current adapter state:

```python
LLMD_FIELD_MAP = {}
```

Behavior:

- If forced or detected as `llm-d`, the adapter returns a snapshot with `scrape_error = "adapter_not_implemented"`.

### 5.7 LMCache / TensorMesh / other KV offload layers

**Support level:** partial, mode-specific LMCache observability implemented;
live golden fixtures and detector coverage still pending.

InferGuard treats LMCache as two architecture families:

- **New priority architecture: standalone MP.** LMCache runs as
  `lmcache server`; vLLM attaches with `LMCacheMPConnector`; required cache
  telemetry comes from the LMCache MP server (`lmcache_mp_*`, MP HTTP API,
  EventBus metrics/logs, optional `.lct` trace recording, optional OTel spans).
  Current vLLM source does not export LMCache MP connector-specific Prometheus
  metrics because `LMCacheMPConnector.build_prom_metrics()` returns `None`.
- **Old/backcompat architecture: embedded/in-process.** vLLM uses
  `LMCacheConnectorV1` or `LMCacheConnectorV1Dynamic`; SGLang current mainline
  uses `--enable-lmcache` with `LMCacheLayerwiseConnector` through SGLang's
  radix-cache path. Legacy vLLM `LMCacheConnector` without `V1` is stale unless
  the operator documents a pinned old stack.

SGLang MP is not a supported claim yet. It remains a candidate lane until a
current-mainline connector contract and live fixture prove SGLang traffic
reaches a standalone LMCache MP server.

`EngineName` includes `lmcache` alongside `vllm`, `sglang`, `dynamo`, `llm-d`, and `unknown`.

Current adapter state:

- `src/inferguard/disagg/adapters.py` remains the public compatibility import surface.
- `src/inferguard/disagg/adapters/lmcache.py` contains the focused LMCache parser shim.
- `src/inferguard/disagg/metrics_schema.py` defines `LmcacheMetrics`, alias matching, and `raw_metrics_extra` preservation.
- `src/inferguard/lmcache_http.py` parses LMCache HTTP evidence.
- `src/inferguard/lmcache_trace.py` parses LMCache `.lct` trace evidence.
- `src/inferguard/lmcache_otel.py` parses LMCache OTel JSONL span evidence.
- `src/inferguard/lmcache_packet.py` writes packet artifacts and
  `lmcache_compat_report.json` through `inferguard collect-lmcache`.

Normalized LMCache fields exposed when live metrics are present:

```text
lmcache_enabled
lmcache_hit_count
lmcache_miss_count
lmcache_hit_rate
lmcache_eviction_count
lmcache_save_count
lmcache_retrieve_count
lmcache_tier_hbm_bytes
lmcache_tier_cpu_bytes
lmcache_tier_disk_bytes
lmcache_tier_remote_bytes
lmcache_offload_bytes_total
lmcache_retrieve_latency_ms_p50
lmcache_retrieve_latency_ms_p95
lmcache_retrieve_latency_ms_p99
lmcache_nixl_transfer_bytes
lmcache_nixl_transfer_latency_ms
lmcache_cacheblend_enabled
lmcache_cachegen_enabled
lmcache_mp_mode_enabled
lmcache_connector_type
lmcache_cache_salt_enabled
raw_metrics_extra
```

Validation caveat:

- These LMCache metric names are alias-matched across plausible upstream variants and covered by synthetic Prometheus fixtures under `tests/fixtures/lmcache_metrics/`; live endpoint validation is still required before partner-facing compatibility claims.
- MP Prometheus, HTTP, `.lct`, and OTel inputs are accepted as evidence, but
  full support requires live fixtures and detector rules.
- Do not claim LMCache compatibility for DSv4 hybrid-attention deployments until upstream LMCache support is validated.
- Do not claim real LMCache compatibility, true eviction proof, fragmentation proof, CacheBlend proof, cache-salt isolation proof, or TensorMesh production-stack support unless live LMCache/vLLM/SGLang metrics prove them. Inferred-only findings must remain labeled `inferred_without_engine_metrics`.

---

## 6. ISB-1 DSv4 Agent Workload Pack

### 6.1 Decision: sibling extension, not replacement

The new InferGuard Bench workload pack is a **sibling extension** of the April-10 ISB-1 InferenceX harness. It does **not** supersede:

```text
docs/isb1/harness/isb1-master.yaml
docs/isb1/01-2026-04-10-core-contributor-readiness.md
docs/isb1/02-2026-04-10-provider-handoff-qwen-long-context.md
docs/isb1/03-2026-04-10-isb1-readme.md
docs/isb1/04-2026-04-10-isb1-support-matrix.md
```

Relationship:

| Surface | Role |
|---|---|
| April-10 ISB-1 harness | InferenceX replay cell catalog and support matrix. |
| InferGuard ISB-1 DSv4 Agent Workload Pack | Operator workload traces for native InferGuard replay and analyzer-compatible long-context / agent runs. |
| AgentX | Trace replay substrate when upstream AgentX cells exist. |
| InferenceX | Benchmark authority and scoreboard-compatible execution. |

### 6.2 Workload class enum

Closed enum from `inferguard.schemas.trace.ALLOWED_WORKLOAD_CLASSES` (verified 2026-04-29):

```text
coding-long
agent-chat
multi-agent-coding
tool-heavy
session-resume
prefix-reuse
repo-level-coding
long-context-debugging
rag-generation
high-concurrency-dev-assistant
kv-pressure
```

Adding a new class requires updating both `schemas/trace.py` and this spec.

### 6.3 Trace JSONL record (`isb1-trace/v1`)

Example:

```json
{
  "trace_id": "trace-001",
  "session_id": "repo-debug-session-001",
  "turn_index": 0,
  "workload_class": "coding-long",
  "messages": [
    {"role": "system", "content": "You are a coding assistant."},
    {"role": "user", "content": "Analyze this repository context..."}
  ],
  "expected_input_tokens": 8192,
  "expected_output_tokens": 512,
  "prefix_group": "repo-a",
  "tool_heavy": false,
  "metadata": {
    "source": "isb1-dsv4-agent"
  }
}
```

Validation rules: §4.5.

### 6.4 Directory layout

Recommended pack layout:

```text
traces/
  isb1-dsv4-agent/
    coding-long/*.jsonl
    agent-chat/*.jsonl
    multi-agent-coding/*.jsonl
    tool-heavy/*.jsonl
    session-resume/*.jsonl
    prefix-reuse/*.jsonl
    repo-level-coding/*.jsonl
    long-context-debugging/*.jsonl
    rag-generation/*.jsonl
    high-concurrency-dev-assistant/*.jsonl
    kv-pressure/*.jsonl
```

Native runner input:

```bash
inferguard bench replay --trace-dir traces/isb1-dsv4-agent
```


### 6.5 Prefix-group conventions

`prefix_group` means the trace intentionally shares reusable context with other records.

Recommended values:

```text
repo-<id>
session-<id>
kvcast-shared-<context_length>
kvcast-mixed-repo-<context_length>
kvcast-resume-<context_length>
kvcast-tools-<context_length>
```

Rules:

- Use `null` for cold unique-context pressure.
- Use a stable value for repeated repository / session prefixes.
- Do not encode secrets, customer names, or hostnames in `prefix_group`.

### 6.5.1 LMCache-specific JSONL workload generators

Phase 1 adds standalone deterministic generators under `src/inferguard/bench/workloads/lmcache_*.py`. They emit JSONL records with:

```text
trace_id, session_id, tenant_id, turn_index, context_length_target,
expected_prefix_overlap_ratio, expected_non_prefix_reuse_ratio,
cache_mode, cache_salt, workload_family, prompt/prompt_redacted/prompt_sha256,
metadata.seed and metadata.claim_boundary
```

Generator families:

| Family | Purpose |
|---|---|
| `multi_round_chat` | Shared system prompt plus growing chat history. |
| `long_doc_qa` | Stable 40-document corpus for tier-latency observation. |
| `mtrag_reorder` | Same retrieved documents reordered to break prefix-only caching. |
| `agent_skills` | Reusable skill/tool docs after dynamic user content. |
| `multi_tenant_salt` | Same prefix bytes across tenant IDs with explicit salt labels; this is not a security proof without engine cache-salt evidence. |
| `mp_moe_redundant_prefill` | Duplicate long contexts across MP/MoE-style ranks for MP-mode observation. |

### 6.6 Synthetic KVCast generation

Generated by:

```text
inferguard.bench.workloads.generate_kv_stress_specs
```

Modes:

| Mode | Workload classes emitted |
|---|---|
| `cold-pressure` | `kv-pressure` |
| `prefix-reuse` | `prefix-reuse` |
| `mixed-agent` | `prefix-reuse`, `kv-pressure`, `session-resume`, `tool-heavy` |
| `eviction-probe` | `prefix-reuse`, `kv-pressure`, `session-resume` |
| `fragmentation-probe` | `agent-chat`, `kv-pressure`, `session-resume` |
| `multi-tenant-storm` | `agent-chat`, `kv-pressure`, `session-resume` |
| `retry-storm` | `tool-heavy`, `agent-chat` |

Synthetic context uses deterministic code-like text and approximate token sizing. It is **not** tokenizer-exact. The 512K and 1M bands intentionally avoid tokenizer dependencies and materialize approximately 4 characters per target token, so tests can validate request shape without loading a model tokenizer; live engines remain the source of truth for exact prompt token counts.

### 6.7 Redaction policy

`requests.jsonl` may contain proprietary prompts unless redacted.

Use:

```bash
--redact-prompts
```

Effect:

- Replaces message `content` with `<redacted>`.
- Preserves metadata and workload shape.
- Adds `prompts_redacted: true` to metadata.

Public artifact bundles should use `--redact-prompts` unless traces are intentionally public.

---

## 7. Run topology and hardware matrix

Operational commands live in `docs/runbooks/02-2026-04-29-gmi-dsv4-inferencex-runbook.md`. **This spec pins the topology; the runbook pins paste-executable commands.**

### 7.1 Hardware scope

| Hardware | Role |
|---|---|
| H100 | Optional Hopper baseline when an upstream DSv4 cell exists. |
| H200 | Hopper lead baseline. |
| B200 | Blackwell baseline. |
| B300 | Blackwell flagship single-node. |
| GB200 NVL72 | Headline multi-node disaggregated run. |
| GB300 | Optional follow-up only. |

### 7.2 Engine × hardware × topology matrix

| Hardware | vLLM | SGLang | Dynamo-vLLM | Primary workload surface |
|---|---|---|---|---|
| H100 | Optional if upstream DSv4 cell exists | Optional / preview if upstream row exists | Not primary | Hopper comparison, ISB-1 replay if available |
| H200 | Single-node DSv4 FP8 baseline | Optional standalone rows | Not primary | Fixed-sequence + agent workload baseline |
| B200 | Single-node DSv4 FP4 baseline | Standalone preview / long-context rows where supported | Not primary | Blackwell baseline, KVCast, replay |
| B300 | Single-node DSv4 FP4 flagship | Standalone where upstream rows exist | Not primary | Blackwell flagship comparison |
| GB200 | Not primary as standalone | Not primary as standalone | Multi-node disagg / prefill-decode headline | DSv4 Dynamo-vLLM srt-slurm recipes |

### 7.3 Deployment modes

| Mode | Meaning |
|---|---|
| single GPU | One GPU; not primary for DSv4 frontier cells. |
| single-node multi-GPU | TP / EP / DP-attention on one host. |
| multi-node | Multiple hosts via Slurm or equivalent. |
| disagg-KV | KV transfer layer involved. |
| prefill-decode split | Separate prefill / decode workers / endpoints. |

### 7.4 GB200 recipe ladder

Use the runbook as command authority. Conceptual order:

1. Smoke recipe.
2. Low-latency recipe.
3. Low / middle curve.
4. Mid / high curve.
5. Max-throughput recipe.
6. Headline disaggregated recipe.
7. MegaMOE / max-throughput follow-up if present upstream.

Do **not** mix recipe families from different InferenceX / AgentX branches in one publishable chart unless the report labels repo refs clearly.

### 7.5 Launch templates

InferGuard OSS includes GMI bare-metal launch templates:

```text
oss/inferguard/scripts/launch_vllm_gmi.sh
oss/inferguard/scripts/launch_sglang_gmi.sh
```

Both require:

```bash
MODEL_NAME=<local/private model path or verified HF repo>
```

They do **not** provision machines, install drivers, authenticate, or manage cloud APIs.

---

## 8. Artifact bundle

### 8.1 Native InferGuard bench output

Each native run writes:

```text
run.json
config.json
requests.jsonl
metrics.jsonl
summary.json
report.md
```

| File | Purpose |
|---|---|
| `run.json` | Run identity, timestamps, version, artifact paths. (`inferguard-bench/v1`) |
| `config.json` | Reproducibility config for endpoint / model / workload / concurrency. (`inferguard-bench/v1`) |
| `requests.jsonl` | Request specs used in the run. (Logical: `inferguard-bench-spec/v1`.) |
| `metrics.jsonl` | Per-request latency, TTFT, success, token, streaming, and metadata rows. (Logical: `inferguard-bench-metric/v1`.) |
| `summary.json` | Aggregate counts, latency / TTFT percentiles, throughput, workload and concurrency summaries. (`inferguard-bench-summary/v1`) |
| `report.md` | Human-readable native bench summary. |

### 8.2 Analyzer-required native companions

For `source_format: inferguard-bench-native`, the analyzer expects:

```text
summary.json
metrics.jsonl
requests.jsonl
run.json
config.json
```

Missing required companions produce a `missing_required_artifact` finding.

### 8.3 External artifacts actually parsed in v0.2.0

Current parser discovery covers:

- `agg_*.json`
- `detailed_results.csv`
- `metrics_server_metrics.csv`
- `results*.json`
- `sample*.jsonl`
- `meta_env.json`
- `inferguard_timeline.jsonl`

Do **not** claim current manifest registration for arbitrary `server.log`, `*.log`, `*.tar.gz`, or campaign-level `manifest.json`. Those are described in `oss/inferguard/docs/SUPPORTED_INPUTS.md` as planned, but the current `analyze_results()` does not discover or register them. Tracked under follow-up §11 / D-7.

### 8.4 Campaign bundle layout

Recommended for cross-rig publishable bundles (operational, not enforced by code):

```text
results/<RUN_ID>/
  manifests/
    repo_refs.txt
    hardware_inventory.txt
    run_matrix.csv
  rigs/
    h200/
    b200/
    b300/
    gb200/
  inferguard_report/
    report.json
    report.md
  co_publish_manifest.md
```

The native runner writes only one run directory's six artifacts; campaign assembly is a runbook-level activity.

---

## 9. Analyzer

### 9.1 Source-format detection

Analyzer walks `<results_dir>` recursively and detects:

| Pattern | Source format |
|---|---|
| `agg_*.json` with `is_multinode` or `disagg` | `inferencex-srt-slurm` |
| `agg_*.json` otherwise | `inferencex-static` |
| `detailed_results.csv` | `agentx-trace-replay` |
| `summary.json` with `schema_version == "inferguard-bench-summary/v1"` | `inferguard-bench-native` |
| `results*.json`, `sample*.jsonl`, `meta_env.json` | `eval` |
| Multiple formats in one cell | `mixed` |

### 9.2 InferenceX fields currently normalized from `agg_*.json`

Identity:

```text
hw                  -> hardware
model               -> model
infmax_model_prefix  -> infmax_model_prefix
framework            -> framework
precision            -> precision
image                -> image
disagg               -> disagg
is_multinode         -> is_multinode
isl                 -> isl
osl                 -> osl
conc                -> concurrency
recipe_name         -> recipe_name
```

Topology:

```text
tp
ep
dp_attention
prefill_tp
prefill_ep
prefill_dp_attention
prefill_num_workers
decode_tp
decode_ep
decode_dp_attention
decode_num_workers
num_prefill_gpu
num_decode_gpu
```

Metrics:

```text
tput_per_gpu
output_tput_per_gpu
input_tput_per_gpu
total_tput_tps
output_tput_tps
input_tput_tps
mean_ttft
p50_ttft
p90_ttft
p95_ttft
p99_ttft
mean_tpot
p50_tpot
p90_tpot
p95_tpot
p99_tpot
mean_itl
p99_itl
intvty
```

### 9.3 AgentX fields currently consumed

From `detailed_results.csv`:

```text
success
request_start_time
request_complete_time
ttft
ttlt
itl
input_tokens
output_tokens_expected
output_tokens_actual
cache_hit_blocks
cache_miss_blocks
```

From `metrics_server_metrics.csv`:

```text
prefix_cache_hits
prefix_cache_queries
cpu_prefix_cache_hits
cpu_prefix_cache_queries
kv_offload_bytes_gpu_to_cpu
kv_offload_bytes_cpu_to_gpu
kv_offload_time_gpu_to_cpu
kv_offload_time_cpu_to_gpu
cpu_kv_cache_usage_pct
prompt_tokens_total
generation_tokens_total
request_success_total
```

### 9.4 Completion and validity

Analyzer computes:

```text
num_requests_total
num_requests_successful
success_rate
status
```

Status rules:

| Status | Meaning |
|---|---|
| `complete` | Success rate is 1.0. |
| `partial` | Some success but below complete. |
| `failed` | Zero successful requests. |
| `unknown` | No completion data. |

Findings emitted from validity rules:

- `invalid_run_no_successful_requests` — zero-success runs.
- `partial_run` — success rate below 95%.
- `metrics_unavailable` — optional but important metrics absent.
- `missing_required_artifact` — required companion artifacts absent.

### 9.5 Output

Default output:

```text
<results_dir>/inferguard_report/report.json
<results_dir>/inferguard_report/report.md
```

With `--operator-brief`, or implicitly when `--gpus` is provided, analyzer also writes:

```text
<results_dir>/inferguard_report/operator_brief.json
<results_dir>/inferguard_report/operator_brief.md
```

`report.json` is the canonical machine-readable output (`inferguard-analyze/v1.1`). `report.md` is for operators and partners; it must remain evidence-based and must not recommend automatic actuation. The operator brief is a derived handoff artifact for best-stable config, cliffs, recommended config, repro command, and raw artifact paths.

---

## 10. Claim hygiene and non-claims

### 10.1 Valid claims

InferGuard OSS may claim:

- read-only disaggregated-serving diagnostics;
- OpenAI-compatible endpoint replay benchmarking;
- synthetic KVCast pressure probes;
- artifact completeness analysis;
- success / failure / partial-run detection;
- TTFT / latency / throughput summaries;
- live overlay findings when `inferguard_timeline.jsonl` exists;
- inferred KV pressure when engine metrics are absent;
- true cache / offload observations only when source artifacts expose them.

### 10.2 Invalid claims

InferGuard OSS must **not** claim:

- automatic optimization;
- automatic remediation;
- private memory / recall;
- LLM diagnosis in OSS;
- cloud provisioning;
- benchmark authority over InferenceX;
- AgentX replacement;
- true KV eviction / fragmentation without engine metrics;
- validated LMCache / TensorMesh compatibility without live endpoint evidence;
- validated Dynamo live metric support before the provisional KVBM field map is confirmed against live Prometheus output;
- llm-d live metric support before `LLMD_FIELD_MAP` is implemented.

### 10.3 Partner wording

Safe wording:

> GMI ran current SemiAnalysis InferenceX / AgentX DSv4 benchmark cells; Touchdown Labs added a read-only InferGuard diagnostic overlay and post-run artifact analysis.

Unsafe wording:

> InferGuard optimized the run.
>
> InferGuard fixed the deployment.
>
> InferGuard proves KV offload correctness.

### 10.4 Crediting

- **GMI Cloud:** crediting is required for any benchmark execution on GMI hardware. Cite the rig (H100 / H200 / B200 / B300 / GB200) and node count.
- **SemiAnalysis (Cam Quilici):** crediting is required for any use of InferenceX or AgentX configs, recipes, or methodology. Reference upstream commit refs in published artifacts.

---

## 11. Roadmap

### 11.1 Day-2 OSS hardening (non-spec follow-ups)

The follow-up tasks below are filed against this spec. Shipped rows are struck through; open rows remain deferred follow-ups.

| ID | Task |
|---|---|
| ~~D-1~~ | ~~Extend `.github/workflows/layer-lint.yml` to cover `bench/`, `schemas/`, `utils/`, `analyze/`.~~ Shipped in v1.0.1. |
| ~~D-2~~ | ~~Reconcile `path-trace/v1` between code (`samples`, string `engine_support`) and `oss/inferguard/docs/SCHEMAS.md` (`rows`, object `engine_support`).~~ Shipped in v1.0.1. |
| ~~D-3~~ | ~~Reconcile `recent-events/v1` event records (`at`/`endpoints` in code vs `t`/`endpoint`/`evidence` in `SCHEMAS.md`).~~ Shipped in v1.0.1. |
| D-4 | Decide whether `requests.jsonl` / `metrics.jsonl` rows should emit row-level `schema_version`. If yes, add it; if no, leave as logical contract names. |
| D-5 | Populate `DYNAMO_FIELD_MAP` from validated live Dynamo Prometheus output. |
| D-6 | Populate `LLMD_FIELD_MAP` from validated live llm-d Prometheus output. |
| D-7 | Extend `analyze_results()` to discover / register arbitrary logs, tarballs, and campaign-level `manifest.json` if claimed in support docs. |
| ~~D-8~~ | ~~Extend InferenceX `agg_*.json` parser to preserve `infmax_model_prefix`, `image`, `disagg`, p50/p90/p95 latency fields.~~ Shipped in v1.0.1. |
| ~~D-9~~ | ~~Extend AgentX parser to preserve `input_tokens`, `output_tokens_expected`, `prompt_tokens_total`, `generation_tokens_total`, `request_success_total`.~~ Shipped in v1.0.1. |
| ~~D-10~~ | ~~Distinguish "emitted today" from "reserved" finding codes in `oss/inferguard/docs/SCHEMAS.md` (this spec already does so in §4.11).~~ Shipped in v1.0.1. |
| ~~D-11~~ | ~~Soften `oss/inferguard/README.md` engine table for Dynamo / llm-d from "Supported" to "Detected — adapter pending" until D-5 / D-6 land.~~ Shipped in v1.0.1. |
| ~~D-12~~ | ~~Add recursive trace-pack loading to `load_trace_dir` (or a sibling helper) so the `traces/isb1-dsv4-agent/<class>/*.jsonl` layout in §6.4 works without manual flattening.~~ Shipped in v1.0.1. |

### 11.2 Other planned OSS work

- vLLM / SGLang prefix-cache metric normalization in `disagg_status`.
- Stronger `report.md` validity gates and operator recommendation text (non-actuating).
- Cost model in `summary.json` and `report.md`.
- `inferguard bench compare` command.
- InferenceX / AgentX export bundle.
- Eval and quality scoring when eval artifacts are present.

### 11.3 Pro-tier surfaces deliberately not in OSS

The PRD v7 "inference optimizing agent" direction includes private / pro-tier concepts that are **not** in OSS v1:

```text
LLM diagnosis
memory / recall
safe actions
remediation
replay validation
Daytona sandbox validation
Blaxel agent integration
customer-specific advisory playbooks
hosted dashboards
longitudinal SaaS reports
```

OSS remains read-only and artifact-based.

---

## 12. References and audit trail

### 12.1 Canonical OSS files

| Path | Role |
|---|---|
| `oss/inferguard/README.md` | User quickstart. |
| `oss/inferguard/docs/SPEC.md` | **Canonical architecture spec (this file).** |
| `oss/inferguard/docs/ANALYZE.md` | Analyzer command detail (sub-spec). |
| `oss/inferguard/docs/SCHEMAS.md` | Schema appendix (subordinate to §4 of this spec). |
| `oss/inferguard/docs/SUPPORTED_INPUTS.md` | Analyzer input appendix (subordinate to §§8–9 of this spec). |
| `oss/inferguard/docs/SUPPORTED_ENGINES.md` | Engine summary (subordinate to §5 of this spec). |
| `oss/inferguard/docs/ARCHITECTURE.md` | Pointer to this spec (legacy disagg-only diagram). |

### 12.2 Implementation ground truth

| Path | Role |
|---|---|
| `src/inferguard/cli.py` | CLI command surface (§3). |
| `src/inferguard/mcp_server.py` | MCP tools (§3.7). |
| `src/inferguard/disagg/adapters.py` | Engine metric maps (§5.3 / §5.4). |
| `src/inferguard/disagg/detect.py` | Detector rules (§4.1). |
| `src/inferguard/disagg/engines.py` | Engine detection (§5.1). |
| `src/inferguard/disagg/types.py` | `disagg-status/v1` types. |
| `src/inferguard/disagg/events.py` | `recent-events/v1` event records (§4.3). |
| `src/inferguard/profile/live.py` | Live profiler scrape loop and trend detectors (§3.1a / §4.14a). |
| `src/inferguard/profile/types.py` | `inferguard-profile-sample/v1` and `inferguard-profile-summary/v1` types. |
| `src/inferguard/profile/render.py` | Profile streaming row and markdown rendering. |
| `src/inferguard/bench/client.py` | Streaming OpenAI client and TTFT semantics. |
| `src/inferguard/bench/runner.py` | Bench runner and artifact writer (§8). |
| `src/inferguard/bench/workloads.py` | KVCast workload generation (§6.6). |
| `src/inferguard/bench/types.py` | `RequestSpec` / `RequestMetric` (§§4.6 / 4.7). |
| `src/inferguard/schemas/trace.py` | Trace validation and workload enum (§6.2). |
| `src/inferguard/analyze/core.py` | Analyzer (§9). |
| `src/inferguard/metrics_core.py` | Prometheus parser. |
| `tests/test_profile_live.py` | Mocked vLLM `/metrics` coverage for `profile live`. |

### 12.3 Touchdown SDLC audit trail

| ID | Title |
|---|---|
| SDLC 59 | InferGuard v0.2.0 OSS release. |
| SDLC 61 | InferenceX / AgentX refresh plan. |
| SDLC 63 | GMI DSv4 InferGuard benchmark plan. |
| SDLC 64 | InferGuard OSS analyze command. |
| SDLC 65 | DSv4 agent workload scope refinement. |
| SDLC 66 | InferGuard Bench CLI. |
| SDLC 67 | InferGuard Bench + Analyze product scope. |
| SDLC 68 | InferGuard Bench Day 1 hardening. |
| SDLC 69 | InferGuard SPEC v1.0 consolidation. |
| SDLC 70 | InferGuard SPEC v1.0.1 D-task batch. |
| SDLC 78 | InferGuard v0.5 harness implementation. |
| SDLC 79 | InferGuard v0.5 production-quality push. |

### 12.4 Touchdown changelog audit trail

| ID | Title |
|---|---|
| Changelog 51 | InferGuard OSS disagg release docs. |
| Changelog 52 | InferenceX / AgentX refresh plan. |
| Changelog 53 | InferenceX 14-day commit review. |
| Changelog 54 | GMI DSv4 InferGuard benchmark plan. |
| Changelog 55 | InferGuard OSS analyze command. |
| Changelog 56 | DSv4 agent workload scope. |
| Changelog 57 | InferGuard Bench CLI. |
| Changelog 58 | InferGuard Bench product scope. |
| Changelog 59 | InferGuard Bench Day 1 hardening. |
| Changelog 60 | InferGuard SPEC v1.0 consolidation. |
| Changelog 61 | InferGuard SPEC v1.0.1 D-task batch. |
| Changelog 69 | InferGuard v0.5 harness implementation. |
| Changelog 70 | InferGuard v0.5 production-quality push. |

### 12.5 Research and runbook references

| Path | Role |
|---|---|
| `docs/research/28-2026-04-29-inferencex-14-day-commit-review.md` | Upstream InferenceX context. |
| `docs/research/29-2026-04-29-gmi-dsv4-inferguard-run-analysis.md` | Run-analysis framing. |
| `docs/runbooks/02-2026-04-29-gmi-dsv4-inferencex-runbook.md` | Operational GMI execution runbook (paste-executable commands). |
| `docs/runbooks/05-2026-04-30-coreweave-gb200-disagg.md` | CoreWeave CKS/SUNK GB200 disagg runbook. |
| `docs/runbooks/06-2026-04-30-modal-multi-node-bench.md` | Modal clustered multi-node harness runbook. |
| `docs/runbooks/07-2026-04-30-crusoe-slinky-cmk-bench.md` | Crusoe Slinky/CMK Slurm-on-K8s harness runbook. |
| `docs/investigations/2026-04-29-inferguard-centralized-architecture-spec.md` | Investigation that produced this consolidation. |

### 12.6 ISB-1 references

| Path | Role |
|---|---|
| `docs/isb1/01-2026-04-10-core-contributor-readiness.md` | April-10 ISB-1 readiness. |
| `docs/isb1/02-2026-04-10-provider-handoff-qwen-long-context.md` | Provider handoff. |
| `docs/isb1/03-2026-04-10-isb1-readme.md` | ISB-1 replay artifact readme. |
| `docs/isb1/04-2026-04-10-isb1-support-matrix.md` | Support matrix. |
| `docs/isb1/harness/isb1-master.yaml` | InferenceX-style cell catalog. |
| `docs/isb1/configs/qwen3_coder_next.yaml` | Qwen3-Coder-Next reference config. |

### 12.7 External integration references

| Path | Role |
|---|---|
| `InferenceX-agentx-1201/utils/process_result.py` | InferenceX static `agg_*.json` writer. |
| `InferenceX-agentx-1201/utils/process_agentic_result.py` | AgentX `agg_*.json` writer. |
| `InferenceX-agentx-1201/utils/collect_results.py` | Aggregated result collector. |
| `Inferscope/docs/gmi-bench/00_README.md` | Campaign positioning context. |

## 13. Harness layer (v0.5)

InferGuard v0.5 adds the **harness layer** around the existing OSS read-only
Bench + Analyze package. The harness does not replace `bench`, `analyze`,
`disagg status`, or MCP. It adds environment detection, agent-run tracing,
local sidecar aggregation, and explicit telemetry-consent tooling.

### 13.1 Canonical harness docs

The normative harness references are subordinate to this SPEC but carry the
field-level contracts for v0.5:

| Path | Role |
|---|---|
| `docs/HARNESS.md` | Harness overview, layer map, privacy boundaries, and operator workflows. |
| `docs/schemas/agent-trace-v1.md` | Normative `agent-trace/v1` JSONL stream schema. |
| `docs/telemetry/v0/POSTURE.md` | Current zero-telemetry posture and verification recipe. |
| `docs/telemetry/v1/SPEC.md` | Future opt-in telemetry schema, consent state machine, DP policy, and `verify-payload` semantics. |

### 13.2 New CLI command groups

The v0.5 CLI adds three top-level command groups:

```text
inferguard agent trace ...
inferguard daemon start|stop|status
inferguard telemetry status|enable|disable|log|verify-payload
```

`inferguard agent trace ...` wraps a user-supplied subprocess and writes a
local `agent-trace/v1` JSONL file. Supported framework labels are
`langgraph`, `crewai`, `autogen`, `claude_code`, `cursor_sdk`, and
`raw_openai`. The default trace redacts prompts, outputs, and tool arguments;
`--save-prompts` writes a local debug-only prompt file that is never uploaded.

`inferguard daemon start|stop|status` exposes the local sidecar surface. In
v0.5 the daemon binds Prometheus-compatible metrics only on loopback and can
load local agent-trace files from a watch directory. It does not create a
cloud control plane, provision infrastructure, or mutate serving engines.

`inferguard telemetry status|enable|disable|log|verify-payload` exposes the
consent and audit surface. `status` prints the v0 posture reference and the
current consent state. `enable --consent-token <TOK>` stores an explicit
consent token. `disable` removes the token and clears local state. `log` lists
local pending payloads. `verify-payload <PATH>` renders the exact local
`inferguard-telemetry/v1` candidate payload without contacting the network.

### 13.3 Runtime modules

The implementation ground truth for v0.5 is:

| Path | Role |
|---|---|
| `src/inferguard/harness/env.py` | Detect local, Slurm, Docker, Kubernetes, multi-node, Modal, Crusoe, CoreWeave, Lambda, Fireworks metadata, RadixArk/SGLang, GMI, and disaggregated endpoint context. |
| `src/inferguard/harness/agent_trace.py` | `AgentTracer`, local proxy helpers, subprocess wrapper, JSONL writer, and production `LangGraphCallback`. |
| `src/inferguard/harness/daemon.py` | Sliding-window aggregate core and loopback Prometheus metrics endpoint. |
| `src/inferguard/harness/cluster_daemon.py` | Leader/follower multi-node fan-in, rank labels, heartbeats, stale follower handling, and buffered replay. |
| `src/inferguard/harness/dcgm_correlate.py` | vLLM aggregate metrics × per-GPU DCGM correlation into `dcgm-correlated/v1` JSONL. |
| `src/inferguard/harness/telemetry.py` | Consent state machine, hard overrides, value-level sanitization, secure token storage, DP stub, pending-payload writer. |
| `src/inferguard/harness/permissions.py` | Permission decisions for protected filesystem/network/command operations. |
| `src/inferguard/schemas/agent_trace.py` | Dataclass validator for `agent-trace/v1` plus graph-integrity checks. |
| `src/inferguard/schemas/telemetry.py` | Dataclass validator for `inferguard-telemetry/v1`. |

### 13.4 Privacy and claim boundary

v0.5 remains OSS-safe and local-first. There is still no default telemetry and
no phone-home. The only network calls made by existing benchmark commands are
to endpoints explicitly supplied by the operator. Harness telemetry in v0.5 is
limited to writing validated pending payload JSON files under the local config
directory after explicit consent; real upload and real DP libraries are out of
scope until a later release.

`DO_NOT_TRACK=1` and `INFERGUARD_TELEMETRY=disabled` are hard overrides. They
force telemetry status to disabled even if a consent token exists. Consent tokens
are stored under `~/.config/inferguard/secrets/consent.token` with mode `0o600`;
pending payloads are stored separately under `~/.config/inferguard/uploads-pending/`.
The sanitizer drops blocked keys and redacts sensitive string values such as
emails, file paths, IP addresses, prompt-like long strings, base64-looking blobs,
and long hex tokens.

### 13.5 Compatibility

The harness layer is additive. Existing `disagg-status/v1`, native bench
artifacts, analyzer reports, and MCP tools remain valid. Future material
changes to harness schemas must update this section, the schema docs above,
and the SDLC / changelog audit trail required by §0.2.

---

## 14. Multi-node fan-in (v0.5 production)

InferGuard v0.5 adds production multi-node harness fan-in for Slurm, Kubernetes,
Modal clustered containers, and equivalent rank-based deployments. The purpose is
not to provision the cluster; the purpose is to merge rank-local harness evidence
into one leader endpoint and one audit trail.

### 14.1 CLI contract

```bash
inferguard daemon start --leader --host 0.0.0.0 --port 9466
inferguard daemon start --follower http://leader:9466 --host 0.0.0.0 --port 9467
```

`--leader` and `--follower` are mutually exclusive. A leader requires Prometheus
metrics enabled so followers have a merge target. A follower keeps its own local
daemon metrics endpoint and posts privacy-gated snapshots to the configured
leader URL.

### 14.2 Protocol contract

| Field / behavior | Contract |
|---|---|
| Snapshot schema | `inferguard-cluster-snapshot/v1`. |
| POST path | `/cluster/v1/snapshots`. |
| Follower listing | `/cluster/v1/followers`. |
| Metrics endpoint | Leader exposes merged Prometheus text at `/metrics`. |
| Rank labels | `slurm_procid`, `slurm_nodeid`, `cluster_node_name`, `cluster_id`, `rank`. |
| Heartbeat | Default 5 seconds. |
| Stale threshold | Default 30 seconds without heartbeat. |
| Offline buffer | Default five-minute follower ring buffer with replay on reconnect. |
| Auth | Shared bearer token loaded from a local `cluster.token`. |
| Privacy | Leader and follower must both opt in for fan-in. |

### 14.3 Implementation ground truth

| Path | Role |
|---|---|
| `src/inferguard/harness/cluster_daemon.py` | Leader/follower protocol, rank labels, stale handling, buffer/replay, token auth. |
| `src/inferguard/cli.py` | `daemon start --leader` and `--follower` flags. |
| `tests/test_cluster_daemon.py` | Rank labels, privacy gate, bearer auth, HTTP fan-in, buffering, stale followers, merged metrics. |

### 14.4 Claim boundary

This feature is production-ready for fan-in of harness snapshots and metrics.
It is not a cloud provisioner.
It does not modify Slurm, Kubernetes, Modal, SUNK, or Slinky scheduling.
It does not replace Prometheus, Grafana, or provider-native observability.
It can be deployed alongside those systems and scraped by them.

## 15. NeoCloud environment detection (v0.5 production)

InferGuard v0.5 extends `RigContext` and `EnvironmentAdapter` with provider-specific
detection. This closes the investigation gap where the harness recognized only
generic Slurm/Docker/Kubernetes and GMI string hints.

### 15.1 Detection precedence

```text
Modal → Crusoe → CoreWeave → Lambda → GMI → RadixArk/SGLang → Generic K8s → Slurm → Docker → Local
```

### 15.2 Provider-specific fields

| Provider | Detection inputs | Selected context fields |
|---|---|---|
| Modal | `MODAL_TASK_ID`, `MODAL_SANDBOX_ID`, Modal cloud/region/image/env vars, optional `modal.experimental.get_cluster_info()`. | `provider`, `modal_task_id`, `modal_sandbox_id`, `modal_cloud_provider`, `modal_region`, `modal_cluster_id`, `rank`, `world_size`. |
| Crusoe | Slinky/CMK node-type strings such as `b200-180gb-sxm-ib.8x`, K8s labels, hostnames. | `provider`, `crusoe_node_type`, `crusoe_managed_via`. |
| CoreWeave | CKS labels `ds.coreweave.com/nvlink.domain`, `node.coreweave.cloud/rack`, `ib.coreweave.cloud/fabric`, `ib.coreweave.cloud/superpod`. | `provider`, `coreweave_nvlink_domain`, `coreweave_rack_id`, `coreweave_ib_fabric`, `coreweave_superpod`, `coreweave_orchestrator`. |
| Lambda | 1-Click cluster hints, Lambda env vars, K8s/InfiniBand fallback. | `provider`, `lambda_one_click`, `lambda_cluster_id`. |
| Fireworks | Operator-supplied Fireworks dedicated endpoint metadata. | `target_provider`, `fireworks_endpoint`. |
| RadixArk / SGLang | `SGLANG_*`, RadixArk env vars, commercial SGLang markers, `--enable-metrics` text. | `provider`, `engine_provider`, `radixark_deployment_id`, `sglang_metrics_enabled`. |
| GMI | Scratch paths, GPU model, container/K8s/bare-metal heuristics. | `provider`, `is_gmi`, `gmi_mode`, `gmi_gpu_model`. |

The verified NeoCloud facts that drive these detectors are recorded in the
production-readiness investigation and the industry research note. Modal uses
`MODAL_TASK_ID`, Crusoe Managed Slurm runs on CMK via Slinky, CoreWeave CKS/SUNK
uses rack/NVLink/InfiniBand labels, SGLang requires metrics enablement, and GB200
NCCL should be left to auto-detection rather than forced generic NCCL env vars.

### 15.3 Implementation ground truth

| Path | Role |
|---|---|
| `src/inferguard/harness/env.py` | Provider cascade and `RigContext` fields. |
| `tests/fixtures/neocloud_envs.py` | Realistic provider fixture dictionaries. |
| `tests/test_harness_env.py` | Provider detection, precedence, false-positive, and mode coverage. |

### 15.4 Claim boundary

Environment detection labels the run and chooses safe local behavior.
It does not authenticate to provider APIs.
It does not provision GPUs.
It does not guarantee that a provider exposes DCGM, vLLM, SGLang, or hosted endpoint metrics.

## 16. DCGM correlation (v0.5 production)

InferGuard v0.5 adds a production DCGM correlation stream for hardware context.
The output schema is `dcgm-correlated/v1` and is documented in
`docs/schemas/dcgm-correlated-v1.md`.

### 16.1 Inputs

| Input | Default | Notes |
|---|---|---|
| vLLM metrics URL | `http://localhost:8000/metrics` | vLLM metrics use the `vllm:` prefix; Prometheus may expose underscore-normalized names. |
| DCGM metrics URL | `http://localhost:9400/metrics` | DCGM exporter default port is 9400 and standard fields use `DCGM_FI_DEV_*`. |
| Duration | 600 seconds | Configurable with `--duration-seconds`. |
| Interval | 5 seconds | Aligned scrape window. |
| Output | `dcgm-correlated-v1.jsonl` | One row per GPU per aligned window, or one null row for empty DCGM scrapes. |

### 16.2 Join semantics

DCGM samples are per GPU and use the `UUID` label as `gpu_uuid`; the `gpu` label
is preserved as `gpu_index`. vLLM samples are aggregate per engine in v0.5, so
InferGuard joins them by time window and broadcasts the vLLM aggregate fields to
each DCGM GPU row. Consumers must not treat the broadcast vLLM fields as per-GPU
engine measurements.

Empty or malformed scrapes do not crash the run. Empty DCGM scrapes emit a null
row; empty vLLM scrapes keep DCGM rows and set vLLM fields to null.

### 16.2a Partial GPU degradation detector (v1.0.8)

Consumers of `dcgm-correlated/v1` can emit `gpu_partial_degradation` when one
GPU diverges materially from the cluster median:

- `dcgm_gpu_util` (SM-activity proxy) below 70% of cluster median for at least
  two consecutive aligned snapshots;
- `dcgm_gpu_temp` more than 15°C above cluster median for at least two
  consecutive aligned snapshots; or
- any non-zero XID/ECC counter (`dcgm_xid_errors`,
  `dcgm_ecc_sbe_volatile_total`, `dcgm_ecc_dbe_volatile_total`,
  `dcgm_ecc_sbe_aggregate_total`, or `dcgm_ecc_dbe_aggregate_total`).

The finding evidence must include:

```text
gpu_index
gpu_uuid
divergence_metric
divergence_value
```

and may include timestamp/window context.

### 16.3 Implementation ground truth

| Path | Role |
|---|---|
| `src/inferguard/harness/dcgm_correlate.py` | Prometheus parsing, DCGM normalization, vLLM broadcast fields, aligned JSONL writer. |
| `scripts/run_dcgm_correlated.sh` | Existing operator script that starts the correlator next to a bench run. |
| `docs/schemas/dcgm-correlated-v1.md` | Normative row schema. |
| `tests/test_dcgm_correlate.py` | UUID/index parsing, empty-scrape handling, vLLM parsing, JSONL writer coverage. |

### 16.4 Claim boundary

DCGM correlation proves hardware telemetry alignment with workload windows.
It does not prove KV-cache correctness by itself.
It does not certify vLLM per-GPU scheduling behavior when vLLM emits only aggregate metrics.
It is local-first and does not require telemetry upload.

---

**End of spec.** Next material change updates this file, the version line, and adds an SDLC + changelog entry per §0.2.

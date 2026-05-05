# Supported Analyzer Inputs

This document specifies the planned input artifacts for `inferguard analyze <results_dir>` when analyzing DeepSeek-V4 GMI benchmark outputs from SemiAnalysis InferenceX and AgentX.

The analyzer is best-effort by default: it discovers supported files recursively, records missing-artifact findings, and emits a partial report when enough data exists. Strict mode may treat missing required artifacts as fatal.

## Directory discovery

The analyzer walks `<results_dir>` recursively and groups artifacts into cells using this precedence:

1. Explicit metadata inside `agg_*.json`.
2. Recipe or script directory name.
3. Parent directory basename.
4. File path fallback.

Common layout:

```text
results/gmi-dsv4-YYYYMMDD/
  rigs/
    h200/single_node/<cell>/
    b200/single_node/<cell>/
    b300/single_node/<cell>/
    gb200/multi_node/<recipe>/
  inferguard_report/
```

## Artifact matrix

| Artifact | Producer | Required? | Purpose |
|---|---|---:|---|
| `agg_*.json` | InferenceX `utils/process_result.py` or `utils/process_agentic_result.py` | Yes for InferenceX fixed-sequence cells | Primary normalized benchmark summary. |
| `detailed_results.csv` | AgentX trace replay | Yes for AgentX cells | Per-request success, timing, token, and cache-hit data. |
| `metrics_server_metrics.csv` | AgentX metrics collector | Recommended for AgentX cells | Prefix-cache, KV offload, and server aggregate metrics. |
| `results*.json` | Benchmark/eval runner | Optional | Raw benchmark or eval outputs. |
| `sample*.jsonl` | Eval runner | Optional | Sample-level eval outputs. |
| `meta_env.json` | Runner or workflow | Optional | Environment and commit metadata. |
| `inferguard_timeline.jsonl` | `inferguard disagg status --json` live overlay loop | Optional enrichment | Live disagg findings and endpoint snapshots. |
| `summary.csv` | InferenceX workflow or collector | Optional | Sweep-level summary table. |
| `benchmark_command.txt` | Run harness | Optional | Reproducibility metadata. |
| `server.log`, `*.log`, `*.tar.gz` | Runner / srt-slurm | Optional | Evidence links in the artifact manifest; not parsed as metrics in v1. |
| `manifest.json` | Campaign wrapper | Optional | Expected cells, upload targets, and whether live timeline was expected. |
| `summary.json` | InferGuard Bench native runner | Yes for native InferGuard runs | Aggregate counts, latency, TTFT, throughput, tokens, concurrency, workload breakdown, KVCast mode, and redaction status. |
| `requests.jsonl` | InferGuard Bench native runner | Yes for native InferGuard runs | Request specs used in the run. Prompt content may be redacted when `--redact-prompts` is used. |
| `metrics.jsonl` | InferGuard Bench native runner | Yes for native InferGuard runs | Per-request client metrics including latency, TTFT, first SSE timing, token source labels, success/error, and KVCast metadata. |
| `run.json` / `config.json` | InferGuard Bench native runner | Yes for native InferGuard runs | Reproducibility metadata for the benchmark invocation and artifact bundle. |

## InferGuard native bench output

Native InferGuard runs are recognized by `summary.json` with `schema_version: inferguard-bench-summary/v1`. The analyzer reports these cells as `source_format: inferguard-bench-native`.

Expected companion files:

```text
run.json
config.json
requests.jsonl
metrics.jsonl
summary.json
report.md
```

Native output records KVCast/replay metadata but does not claim official InferenceX methodology. `concurrency` is `null` at the cell identity level when a native run contains multiple concurrency levels; the full list is preserved under `topology.concurrency_levels`.

## InferenceX `agg_*.json`

Static and srt-slurm cells should include these fields when available.

### Identity fields

| Field | Meaning |
|---|---|
| `hw` | Hardware label, for example `h200`, `b200`, `b300`, `gb200`. |
| `model` | Model name or path. |
| `infmax_model_prefix` | InferenceX model prefix, when emitted. |
| `framework` | Serving stack, for example `vllm` or `dynamo-vllm`. |
| `precision` | Weight/KV precision label, for example `fp4` or `fp8`. |
| `image` | Container image. |
| `disagg` | Whether the run used disaggregated serving. |
| `is_multinode` | Whether the run was multi-node. |

### Shape fields

| Field | Meaning |
|---|---|
| `isl` | Input sequence length. |
| `osl` | Output sequence length. |
| `conc` | Concurrency. |

### Topology fields

Single-node fields:

- `tp`
- `ep`
- `dp_attention`

Multi-node/disagg fields:

- `prefill_tp`
- `prefill_ep`
- `prefill_dp_attention`
- `prefill_num_workers`
- `decode_tp`
- `decode_ep`
- `decode_dp_attention`
- `decode_num_workers`
- `num_prefill_gpu`
- `num_decode_gpu`

### Throughput fields

- `tput_per_gpu`
- `output_tput_per_gpu`
- `input_tput_per_gpu`
- total throughput fields if present
- output throughput fields if present
- input throughput fields if present

### Latency fields

The analyzer should preserve emitted latency keys and normalize common ones:

- `mean_ttft`
- `p50_ttft`
- `p90_ttft`
- `p95_ttft`
- `p99_ttft`
- `mean_tpot`
- `p50_tpot`
- `p90_tpot`
- `p95_tpot`
- `p99_tpot`
- `mean_itl`
- `p99_itl`
- `intvty`

## AgentX `detailed_results.csv`

Expected columns:

| Column | Meaning |
|---|---|
| `success` | Request success flag. |
| `request_start_time` | Request start timestamp. |
| `request_complete_time` | Request completion timestamp. |
| `ttft` | Time to first token. |
| `ttlt` | Time to last token. |
| `itl` | Inter-token latency. |
| `input_tokens` | Prompt token count. |
| `output_tokens_expected` | Expected generated tokens. |
| `output_tokens_actual` | Actual generated tokens. |
| `cache_hit_blocks` | Prefix/KV cache-hit block count. |
| `cache_miss_blocks` | Prefix/KV cache-miss block count. |

Derived metrics:

- request count
- success rate
- QPS
- mean/p99 TTFT
- mean/p99 TTLT
- mean/p99 ITL
- output tokens per second
- theoretical cache hit rate

## AgentX `metrics_server_metrics.csv`

Expected fields when available:

| Field | Meaning |
|---|---|
| `prefix_cache_hits` | Server prefix-cache hit count. |
| `prefix_cache_queries` | Server prefix-cache query count. |
| `cpu_prefix_cache_hits` | CPU prefix-cache hit count. |
| `cpu_prefix_cache_queries` | CPU prefix-cache query count. |
| `kv_offload_bytes_gpu_to_cpu` | Bytes offloaded from GPU to CPU. |
| `kv_offload_bytes_cpu_to_gpu` | Bytes restored from CPU to GPU. |
| `kv_offload_time_gpu_to_cpu` | Time spent on GPU→CPU offload. |
| `kv_offload_time_cpu_to_gpu` | Time spent on CPU→GPU restore. |
| `cpu_kv_cache_usage_pct` | CPU KV cache utilization percentage. |
| `prompt_tokens_total` | Prompt token total. |
| `generation_tokens_total` | Generated token total. |
| `request_success_total` | Successful request total. |

Derived metrics:

- server GPU cache hit rate
- server CPU cache hit rate
- KV offload bytes by direction
- KV offload time by direction
- cache/offload pressure findings

## Eval artifacts

The v1 analyzer treats eval files as tolerant JSON/JSONL inputs because the exact schema can vary by runner.

Supported filenames:

```text
results*.json
sample*.jsonl
meta_env.json
```

Behavior:

- Preserve top-level numeric and string metrics when possible.
- Link sample files in `artifact_manifest`.
- Emit `eval_regression` only when comparable baseline fields are present.
- Emit `metrics_unavailable` only when eval analysis was expected but no eval artifact exists.

## srt-slurm multi-node result directories

The analyzer should recurse through recipe output trees and associate files with the nearest cell/recipe directory.

Expected patterns:

```text
**/agg_*.json
**/*results*.json
**/inferguard_timeline.jsonl
**/server*.log
**/benchmark*.log
**/multinode_server_logs.tar.gz
```

Cell identity should prefer fields from `agg_*.json`; path inference is fallback only.

## `inferguard_timeline.jsonl`

Timeline input is optional enrichment. Missing timeline should not make a run invalid unless `manifest.json` declares it expected.

Supported line shapes:

1. `inferguard-timeline/v1` wrapper records.
2. Raw `disagg-status/v1` records from one-shot captures.

Wrapper record shape:

```json
{
  "schema_version": "inferguard-timeline/v1",
  "observed_at": "2026-04-29T22:01:30Z",
  "sequence": 0,
  "status": "healthy",
  "proof_level": "live",
  "capabilities": {
    "diagnosis": "on",
    "actuation": "off",
    "replay": "off",
    "recall": "off"
  },
  "disagg_status": {
    "schema_version": "disagg-status/v1",
    "prefill": {},
    "decode": {},
    "transfer": null,
    "findings": []
  }
}
```

Timeline-derived metrics:

- sample count
- first observed timestamp
- last observed timestamp
- finding counts by code
- first finding timestamp
- first critical finding timestamp
- first live disagg finding before a post-run TTFT cliff, when computable

## Unsupported inputs in v1

The planned v1 analyzer does not parse these as structured metrics:

- arbitrary server logs
- binary profiler dumps
- private/pro-tier InferGuard memory or replay outputs
- cloud provider billing exports
- benchmark harnesses unrelated to InferenceX or AgentX

Unsupported files may still appear in `artifact_manifest` for traceability.

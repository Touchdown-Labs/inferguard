---
title: Analyze a run
description: Diagnose bottlenecks and assemble a report from a completed run.
---

Planned CLI for post-run analysis of DeepSeek-V4 GMI benchmark outputs produced by SemiAnalysis InferenceX and AgentX.

```bash
inferguard analyze <results_dir> \
  --output-dir <results_dir>/inferguard_report \
  --format both \
  --fail-on critical \
  --best-effort
```

`inferguard analyze` is a read-only report generator. It does not launch benchmarks, change serving configuration, call private/pro-tier modules, use LLMs, or perform actuation. The command complements the live overlay command:

```bash
inferguard disagg status --prefill <url> --decode <url> --json
```

The live command can produce `inferguard_timeline.jsonl` during a run; the analyzer consumes that timeline after the run alongside InferenceX and AgentX result artifacts.

## Command shape

```text
inferguard analyze <results_dir> [OPTIONS]
```

| Argument / flag | Default | Meaning |
|---|---:|---|
| `<results_dir>` | required | Root directory containing one or more benchmark cells or recipe result directories. |
| `--output-dir PATH` | `<results_dir>/inferguard_report` | Destination for generated reports. |
| `--format json\|md\|both` | `both` | Select `report.json`, `report.md`, or both. |
| `--fail-on never\|warning\|critical` | `critical` | Exit non-zero after report generation when a finding at or above this severity exists. |
| `--strict / --best-effort` | `--best-effort` | Strict mode fails on missing required artifacts; best-effort mode records findings and continues. |
| `--timeline-glob TEXT` | `**/inferguard_timeline.jsonl` | Discovery pattern for live overlay timeline files. |
| `--json` | `false` | Also print the generated JSON report to stdout. |

## Exit codes

| Code | Meaning |
|---:|---|
| `0` | Report written; no finding at or above `--fail-on`. |
| `1` | Report written; warning threshold tripped. |
| `2` | Report written; critical threshold tripped. |
| `3` | No supported benchmark artifacts found, input parsing failed before a report could be produced, or report writing failed. |

## Output files

By default the analyzer writes:

```text
<results_dir>/inferguard_report/
  report.json
  report.md
```

Per-cell reports may also live beside raw result artifacts when a caller runs the analyzer on a cell directory directly.

## `report.json`

`report.json` uses schema version `inferguard-analyze/v1`. See [Schemas](../reference/schemas.md) for the normative field contract.

Top-level sections:

| Field | Meaning |
|---|---|
| `schema_version` | Always `inferguard-analyze/v1`. |
| `generated_at` | UTC timestamp for report generation. |
| `input_root` | Analyzer input directory. |
| `analyzer` | InferGuard version and OSS capability declaration. |
| `run_summary` | Cell counts, completion status, and missing-artifact summary. |
| `cells` | Normalized per-cell records. |
| `cross_run` | Cross-cell comparisons and detected curves. |
| `findings` | Flattened finding list across the run. |
| `artifact_manifest` | Files discovered and files written. |

## `report.md`

`report.md` is the human-readable companion report. Planned sections:

1. Executive summary
2. Benchmark matrix
3. Artifact completeness
4. Per-cell results
5. Live InferGuard timeline
6. Bottleneck analysis
7. Evidence-based next measurements
8. Co-publish artifact manifest

The report may describe observed cliffs, plateaus, missing artifacts, or follow-up measurements. It must not recommend automatic configuration changes or use Pro-tier advisory/actuation language.

## Supported benchmark modes

The analyzer is planned to support these DeepSeek-V4 GMI result shapes:

| Mode | Primary artifacts |
|---|---|
| InferenceX single-node fixed sequence | `agg_*.json`, benchmark `results*.json`, optional `inferguard_timeline.jsonl` |
| InferenceX multi-node srt-slurm disagg | `agg_*.json`, recipe result subdirectories, logs, optional `inferguard_timeline.jsonl` |
| AgentX trace replay | `detailed_results.csv`, `metrics_server_metrics.csv`, optional `agg_*.json` |
| Eval outputs | `results*.json`, `sample*.jsonl`, `meta_env.json` |

Detailed input requirements are in [Supported inputs](../reference/supported-inputs.md).

## Finding codes

Analyzer-native codes:

| Code | Severity | Meaning |
|---|---|---|
| `missing_required_artifact` | warning or critical | A required input for the detected result type is absent. |
| `invalid_run_no_successful_requests` | critical | The run completed with zero successful requests. |
| `partial_run` | warning | Success rate is below the planned validity threshold. |
| `metrics_unavailable` | warning | Metrics needed for a requested analysis section are missing. |
| `ttft_cliff` | warning or critical | p99 TTFT jumps materially while throughput gain is small. |
| `tpot_degradation` | warning | p99 TPOT worsens materially versus a comparable point. |
| `throughput_plateau` | info or warning | Higher concurrency produces little throughput gain while latency worsens. |
| `kv_pressure` | warning | Cache usage or offload signals indicate sustained KV pressure. |
| `kv_offload_thrash` | warning | GPU→CPU and CPU→GPU offload both rise with latency degradation. |
| `prefix_cache_regression` | warning | Observed cache hit rate drops versus comparable points or theoretical rate. |
| `eval_regression` | warning | Eval metrics regress versus the selected baseline. |

Live-overlay codes reused when read from `inferguard_timeline.jsonl`:

- `prefill_decode_imbalance`
- `kv_transfer_stall`
- `kv_transfer_errors_present`
- `endpoint_unreachable`
- `engine_unidentified`

## Metric normalization

The analyzer normalizes metrics into these groups when present:

| Group | Fields |
|---|---|
| Identity | `hardware`, `model`, `framework`, `precision`, `source_format`, `recipe_name` |
| Shape | `isl`, `osl`, `concurrency`, `scenario_type`, `is_multinode` |
| Topology | `tp`, `ep`, `dp_attention`, `prefill_*`, `decode_*`, `num_prefill_gpu`, `num_decode_gpu` |
| Completion | `num_requests_total`, `num_requests_successful`, `success_rate`, `status` |
| Throughput | `total_tput_tps`, `input_tput_tps`, `output_tput_tps`, `tput_per_gpu`, `input_tput_per_gpu`, `output_tput_per_gpu` |
| Latency | `mean_ttft`, `p99_ttft`, `mean_tpot`, `p99_tpot`, `mean_itl`, `p99_itl`, `intvty` |
| Cache/offload | `theoretical_cache_hit_rate`, `server_gpu_cache_hit_rate`, `server_cpu_cache_hit_rate`, `kv_offload_bytes_gpu_to_cpu`, `kv_offload_bytes_cpu_to_gpu` |
| Timeline | sample count, first finding time, finding counts by code, lead time to detected TTFT cliff |

Missing optional metrics are represented as `null` in JSON and called out only when they block a requested analysis section.

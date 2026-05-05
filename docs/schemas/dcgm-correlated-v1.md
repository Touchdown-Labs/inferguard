---
title: "dcgm-correlated/v1 JSONL Schema"
status: "draft-v0.5-normative"
date: "2026-04-30"
purpose: "Normative schema for time-aligned vLLM aggregate and per-GPU DCGM samples."
producer: "inferguard.harness.dcgm_correlate.DcgmCorrelator"
---

# `dcgm-correlated/v1` JSONL Schema

## 1. Status

This document is normative for `dcgm-correlated/v1` files emitted by InferGuard v0.5.
The producer is the DCGM correlation helper in `inferguard.harness.dcgm_correlate`.
The intended operator entry point is `scripts/run_dcgm_correlated.sh`.
The schema is line-oriented JSONL.
Each line MUST be one complete JSON object.
Each line MUST validate independently.
Blank lines SHOULD NOT be emitted.
Consumers MAY ignore blank lines when reading historical files.
The file SHOULD be written using UTF-8.
The file SHOULD be append-safe during a running benchmark.
The file MAY be tailed by monitoring tools while the producer is still running.
The producer MUST NOT require hosted telemetry.
The producer MUST NOT upload this file automatically.
The producer MUST work with loopback Prometheus endpoints by default.

## 2. Normative language

The key words MUST, MUST NOT, SHOULD, SHOULD NOT, and MAY are normative.
A producer is a process that writes this schema.
A consumer is a process that reads this schema.
A scrape is one HTTP GET against a Prometheus exposition endpoint.
A window is a fixed-width timestamp bucket.
A DCGM sample is a metric family row emitted by NVIDIA DCGM exporter.
A vLLM sample is a metric family row emitted by vLLM's Prometheus endpoint.
A row is a joined JSON object emitted by the producer.
A null row is a row where no DCGM GPU identity was observed for the window.
A broadcast field is a vLLM aggregate value copied onto every GPU row in a window.

## 3. File naming and placement

The default output directory is supplied by `--output-dir`.
The default filename MUST be `dcgm-correlated-v1.jsonl`.
The parent directory SHOULD be named `dcgm-correlated` in scripted runs.
A complete scripted path is commonly `results/.../dcgm-correlated/dcgm-correlated-v1.jsonl`.
The producer MAY overwrite an existing file at the start of a new run.
The producer MUST NOT append rows from separate benchmark runs unless the operator explicitly arranges that.
Consumers SHOULD treat one file as one correlation run.
Consumers SHOULD NOT infer benchmark identity from the path alone.

## 4. Time alignment

The producer samples vLLM and DCGM endpoints at a configured interval.
The default interval MUST be five seconds.
The field `timestamp_window_seconds` MUST contain the configured interval in seconds.
The timestamp used for joining MUST be rounded down to the nearest interval boundary.
For example, an observed Unix timestamp of `1730000004.999` in a five-second window maps to `1730000000`.
For example, an observed Unix timestamp of `1730000005.000` in a five-second window maps to `1730000005`.
The emitted `timestamp` MUST be the UTC ISO 8601 representation of the aligned boundary.
The emitted `timestamp` MUST end with `Z`.
The emitted `timestamp` MUST NOT include local timezone offsets.
Subsecond precision SHOULD be omitted from the emitted timestamp.
A producer MAY scrape the two endpoints sequentially.
If both scrapes land in the same aligned window, the producer MUST join them.
The producer SHOULD keep the wall-clock gap between the two endpoint scrapes small.
Consumers MUST use `timestamp` and `timestamp_window_seconds` as the time key.

## 5. Join model

DCGM exporter emits per-GPU rows.
DCGM rows MUST be keyed by `(timestamp, gpu_uuid)`.
DCGM labels SHOULD include `UUID`.
DCGM labels SHOULD include `gpu` as the integer GPU index.
When the `UUID` label is present, it MUST populate `gpu_uuid`.
When the `gpu` label is present, it MUST populate `gpu_index`.
When `UUID` is absent but `gpu` is present, the producer MAY use a stable fallback string derived from the index.
When both `UUID` and `gpu` are absent, the producer SHOULD drop that DCGM sample.
vLLM metrics in v0.5 are aggregate per engine.
vLLM metrics generally do not include a GPU UUID label.
The producer MUST join vLLM metrics on time only.
The producer MUST broadcast vLLM aggregate values onto every DCGM GPU row in the same window.
The producer SHOULD log the warning: `vLLM metrics are aggregate per-engine; correlation joins on time only`.
Future vLLM releases MAY add per-GPU labels.
Consumers MUST NOT assume that broadcast vLLM values are per-GPU measurements.
Consumers SHOULD display broadcast vLLM fields as workload context for each GPU.

## 6. Empty scrape behavior

The producer MUST NOT crash on an empty DCGM scrape.
The producer MUST log a warning for an empty DCGM scrape.
The producer MUST emit one null row for an empty DCGM scrape.
A null row MUST contain `gpu_uuid: null`.
A null row MUST contain `gpu_index: null`.
A null row MUST contain every DCGM field with value `null`.
A null row MAY still contain vLLM broadcast fields if the vLLM scrape succeeded.
The producer MUST NOT crash on an empty vLLM scrape.
The producer MUST log a warning for an empty vLLM scrape.
Rows produced with an empty vLLM scrape MUST set every vLLM field to `null`.
Rows produced with an empty vLLM scrape MAY still contain DCGM fields.
HTTP failures SHOULD be treated like empty scrapes.
Malformed Prometheus text SHOULD be treated like an empty scrape.
Partial Prometheus text SHOULD emit the valid parsed samples and ignore invalid samples.
Consumers MUST tolerate `null` for any metric field.

## 7. Row object

Each row MUST be a JSON object.
Each row MUST include `schema_version`.
Each row MUST include `timestamp`.
Each row MUST include `timestamp_window_seconds`.
Each row MUST include `gpu_uuid`.
Each row MUST include `gpu_index`.
Each row MUST include all DCGM fields listed in this document.
Each row MUST include all vLLM fields listed in this document.
Rows MUST NOT include prompt text.
Rows MUST NOT include model output text.
Rows MUST NOT include request payloads.
Rows MUST NOT include customer identifiers.
Rows MAY include additive non-sensitive fields in a later schema revision.
Consumers operating in strict v1 mode SHOULD reject unknown fields.
Consumers operating in permissive mode MAY ignore unknown fields.

## 8. Top-level fields

| Field | Type | Required | Units | Description |
|---|---|---:|---|---|
| `schema_version` | string | yes | none | MUST equal `dcgm-correlated/v1`. |
| `timestamp` | string | yes | UTC ISO 8601 | Aligned scrape window start. |
| `timestamp_window_seconds` | integer | yes | seconds | Window width used for alignment. |
| `gpu_uuid` | string or null | yes | none | DCGM GPU UUID label. |
| `gpu_index` | integer or null | yes | none | DCGM `gpu` label parsed as an integer. |

`schema_version` MUST be exactly `dcgm-correlated/v1`.
`timestamp_window_seconds` SHOULD be `5` for default runs.
`timestamp_window_seconds` MUST be positive.
`gpu_uuid` SHOULD be stable for the lifetime of the process.
`gpu_index` SHOULD match DCGM exporter ordering.
Consumers SHOULD NOT use `gpu_index` as a cross-node identity.
Consumers SHOULD prefer `gpu_uuid` when grouping per-device rows.

## 9. DCGM metric fields

| Field | Source metric | Type | Units | Notes |
|---|---|---|---|---|
| `dcgm_sm_clock` | `DCGM_FI_DEV_SM_CLOCK` | number or null | MHz | SM clock. |
| `dcgm_mem_clock` | `DCGM_FI_DEV_MEM_CLOCK` | number or null | MHz | Memory clock. |
| `dcgm_gpu_temp` | `DCGM_FI_DEV_GPU_TEMP` | number or null | Celsius | GPU temperature. |
| `dcgm_mem_temp` | `DCGM_FI_DEV_MEMORY_TEMP` or `DCGM_FI_DEV_MEM_TEMP` | number or null | Celsius | Memory temperature. |
| `dcgm_power_usage` | `DCGM_FI_DEV_POWER_USAGE` | number or null | watts | Instantaneous power draw. |
| `dcgm_total_energy_consumption` | `DCGM_FI_DEV_TOTAL_ENERGY_CONSUMPTION` | number or null | millijoules | Cumulative energy. |
| `dcgm_gpu_util` | `DCGM_FI_DEV_GPU_UTIL` | number or null | percent | GPU utilization. |
| `dcgm_mem_copy_util` | `DCGM_FI_DEV_MEM_COPY_UTIL` | number or null | percent | Memory copy utilization. |
| `dcgm_fb_free` | `DCGM_FI_DEV_FB_FREE` | number or null | MiB | Free framebuffer memory. |
| `dcgm_fb_used` | `DCGM_FI_DEV_FB_USED` | number or null | MiB | Used framebuffer memory. |
| `dcgm_xid_errors` | `DCGM_FI_DEV_XID_ERRORS` | number or null | count | XID error count. |
| `dcgm_nvlink_bandwidth_total` | `DCGM_FI_DEV_NVLINK_BANDWIDTH_TOTAL` | number or null | exporter-defined | Sum across links for a GPU. |

DCGM fields MUST be numeric when present.
DCGM fields MUST be `null` when not observed in a scrape.
The producer SHOULD sum multiple NVLink bandwidth rows for the same GPU.
The producer SHOULD keep the latest value for duplicate non-NVLink DCGM fields in the same scrape.
Consumers SHOULD treat counter-like fields according to their DCGM meaning.
Consumers SHOULD not assume all DCGM exporter deployments enable every field.

## 10. vLLM broadcast fields

| Field | Source metric | Type | Units | Notes |
|---|---|---|---|---|
| `vllm_num_requests_running` | `vllm:num_requests_running` | number or null | requests | Aggregate running requests. |
| `vllm_num_requests_waiting` | `vllm:num_requests_waiting` | number or null | requests | Aggregate waiting requests. |
| `vllm_kv_cache_usage_perc` | `vllm:kv_cache_usage_perc` | number or null | fraction or percent | Mirrors vLLM exposition. |
| `vllm_num_preemptions_total` | `vllm:num_preemptions_total` | number or null | count | Aggregate preemptions. |
| `vllm_e2e_request_latency_seconds_p99` | `vllm:e2e_request_latency_seconds` | number or null | seconds | P99 quantile or histogram estimate. |

vLLM fields MUST be numeric when present.
vLLM fields MUST be `null` when not observed in a scrape.
The producer MUST accept both colon and underscore metric spellings.
The producer SHOULD sum request-count fields across model labels.
The producer SHOULD take the maximum KV-cache usage across model labels.
The producer SHOULD take the maximum p99 latency across model labels.
The producer MAY estimate p99 from histogram buckets when a direct quantile series is absent.
Consumers MUST label these fields as broadcast aggregate values.

## 11. Example row

```json
{"schema_version":"dcgm-correlated/v1","timestamp":"2024-10-27T03:33:20Z","timestamp_window_seconds":5,"gpu_uuid":"GPU-aaaa","gpu_index":0,"dcgm_sm_clock":1410.0,"dcgm_mem_clock":1593.0,"dcgm_gpu_temp":61.0,"dcgm_mem_temp":68.0,"dcgm_power_usage":455.5,"dcgm_total_energy_consumption":9000.0,"dcgm_gpu_util":83.0,"dcgm_mem_copy_util":44.0,"dcgm_fb_free":1024.0,"dcgm_fb_used":79360.0,"dcgm_xid_errors":0.0,"dcgm_nvlink_bandwidth_total":20.0,"vllm_num_requests_running":3.0,"vllm_num_requests_waiting":7.0,"vllm_kv_cache_usage_perc":0.82,"vllm_num_preemptions_total":2.0,"vllm_e2e_request_latency_seconds_p99":4.2}
```

The example is compact for JSONL readability.
Pretty-printed JSON SHOULD NOT be used in the actual JSONL file.
Consumers SHOULD parse the object rather than relying on field order.

## 12. Validation checklist

A valid file has at least one row for a completed non-zero-duration run.
Every row has the exact schema version.
Every timestamp is aligned to the declared window.
Every GPU row has a GPU UUID or is an explicit null row.
Every null row has all DCGM fields set to `null`.
Every metric value is a JSON number or `null`.
No metric value is NaN.
No metric value is Infinity.
No row contains prompt content.
No row contains tool argument content.
No row contains raw HTTP response bodies.
No row contains environment dumps.
No row relies on outbound network access beyond the configured metrics endpoints.

## 13. Compatibility notes

This schema is intentionally separate from `agent-trace/v1`.
This schema is intentionally separate from benchmark request-level metrics.
The correlation file is a hardware/workload context stream.
A benchmark analyzer MAY join this file with replay output by timestamp.
A benchmark analyzer SHOULD use the same windowing rules when joining.
A daemon MAY expose aggregates derived from this file.
Telemetry upload remains governed by the telemetry posture and consent gates.
Future revisions may add per-rank labels.
Future revisions may add per-node labels.
Future revisions may add per-engine labels.
Future revisions may add vLLM per-GPU labels if upstream exposes them.
Future revisions MUST bump `schema_version` for breaking changes.

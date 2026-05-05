---
title: Schemas
description: JSON schemas for InferGuard inputs and outputs.
---

InferGuard emits versioned contracts.

- `disagg-status/v1`
- `path-trace/v1`
- event record shape for `recent_events`
- planned `inferguard-timeline/v1` for live overlay JSONL records
- planned `inferguard-analyze/v1` for `inferguard analyze <results_dir>` reports
- `inferguard-cost/v1` for optional analyzer cost accounting blocks

Breaking schema changes must ship as a sibling `v2` contract (for example `disagg-status/v2`) rather than mutating `v1` fields.

## `disagg-status/v1` (JSON Schema)

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "disagg-status/v1",
  "type": "object",
  "required": ["schema_version", "prefill", "decode", "findings"],
  "properties": {
    "schema_version": { "const": "disagg-status/v1" },
    "prefill": { "$ref": "#/$defs/snapshot" },
    "decode": { "$ref": "#/$defs/snapshot" },
    "transfer": {
      "anyOf": [
        { "$ref": "#/$defs/snapshot" },
        { "type": "null" }
      ]
    },
    "findings": {
      "type": "array",
      "items": { "$ref": "#/$defs/finding" }
    }
  },
  "$defs": {
    "endpoint": {
      "type": "object",
      "required": ["url", "role", "engine"],
      "properties": {
        "url": { "type": "string" },
        "role": { "enum": ["prefill", "decode", "transfer"] },
        "engine": { "enum": ["vllm", "sglang", "dynamo", "llm-d", "unknown"] },
        "engine_version": { "type": "string" },
        "connector": { "type": "string" }
      },
      "additionalProperties": true
    },
    "snapshot": {
      "type": "object",
      "required": ["endpoint", "scraped_at"],
      "properties": {
        "endpoint": { "$ref": "#/$defs/endpoint" },
        "scraped_at": { "type": "number" },
        "kv_cache_usage": { "type": ["number", "null"] },
        "requests_running": { "type": ["integer", "null"] },
        "requests_waiting": { "type": ["integer", "null"] },
        "requests_swapped": { "type": ["integer", "null"] },
        "preemptions_total": { "type": ["integer", "null"] },
        "ttft_avg_seconds": { "type": ["number", "null"] },
        "tpot_avg_seconds": { "type": ["number", "null"] },
        "kv_transfer_sent_bytes_total": { "type": ["integer", "null"] },
        "kv_transfer_recv_bytes_total": { "type": ["integer", "null"] },
        "kv_transfer_errors_total": { "type": ["integer", "null"] },
        "prefill_queue_depth": { "type": ["integer", "null"] },
        "decode_queue_depth": { "type": ["integer", "null"] },
        "scrape_error": { "type": "string" },
        "raw_labels": { "type": "object", "additionalProperties": { "type": "string" } }
      },
      "additionalProperties": true
    },
    "finding": {
      "type": "object",
      "required": ["code", "severity", "message", "evidence"],
      "properties": {
        "code": {
          "enum": [
            "connector_mismatch",
            "prefill_decode_imbalance",
            "kv_transfer_errors_present",
            "kv_transfer_stall",
            "endpoint_unreachable",
            "engine_unidentified"
          ]
        },
        "severity": { "enum": ["info", "warning", "critical"] },
        "message": { "type": "string" },
        "evidence": { "type": "object", "additionalProperties": true }
      },
      "additionalProperties": true
    }
  }
}
```

## `path-trace/v1` (JSON Schema)

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "path-trace/v1",
  "type": "object",
  "required": ["schema_version", "samples", "engine_support", "note", "requested_sample_size"],
  "properties": {
    "schema_version": { "const": "path-trace/v1" },
    "samples": {
      "type": "array",
      "maxItems": 0
    },
    "engine_support": { "const": "aggregate_only" },
    "note": {
      "const": "Per-session path tracing is not available in the OSS tier. Use `disagg_status` for aggregate signals."
    },
    "requested_sample_size": { "type": "integer", "minimum": 0 }
  },
  "additionalProperties": true
}
```

## Planned `inferguard-timeline/v1` wrapper

`inferguard_timeline.jsonl` is the planned live-overlay artifact consumed by `inferguard analyze`. Each line should be either this wrapper shape or a raw `disagg-status/v1` object.

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "inferguard-timeline/v1",
  "type": "object",
  "required": ["schema_version", "observed_at", "sequence", "capabilities", "disagg_status"],
  "properties": {
    "schema_version": { "const": "inferguard-timeline/v1" },
    "observed_at": { "type": "string", "format": "date-time" },
    "sequence": { "type": "integer", "minimum": 0 },
    "status": { "enum": ["healthy", "degraded", "critical", "unknown"] },
    "proof_level": { "enum": ["live", "post_run", "unknown"] },
    "capabilities": {
      "type": "object",
      "required": ["diagnosis", "actuation", "replay", "recall"],
      "properties": {
        "diagnosis": { "enum": ["on", "off"] },
        "actuation": { "const": "off" },
        "replay": { "const": "off" },
        "recall": { "const": "off" }
      },
      "additionalProperties": false
    },
    "disagg_status": {
      "type": "object",
      "description": "Embedded disagg-status/v1 object.",
      "required": ["schema_version", "prefill", "decode", "findings"],
      "properties": {
        "schema_version": { "const": "disagg-status/v1" }
      },
      "additionalProperties": true
    }
  },
  "additionalProperties": true
}
```

## Planned `inferguard-analyze/v1`

`report.json` from `inferguard analyze <results_dir>` uses this top-level contract. Fields may be `null` when the source artifact does not expose that metric.

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "inferguard-analyze/v1",
  "type": "object",
  "required": [
    "schema_version",
    "generated_at",
    "input_root",
    "analyzer",
    "run_summary",
    "cells",
    "findings",
    "artifact_manifest"
  ],
  "properties": {
    "schema_version": { "const": "inferguard-analyze/v1" },
    "generated_at": { "type": "string", "format": "date-time" },
    "input_root": { "type": "string" },
    "analyzer": {
      "type": "object",
      "required": ["inferguard_version", "capabilities"],
      "properties": {
        "inferguard_version": { "type": "string" },
        "capabilities": {
          "type": "object",
          "required": ["diagnosis", "actuation", "replay", "recall"],
          "properties": {
            "diagnosis": { "enum": ["on", "off"] },
            "actuation": { "const": "off" },
            "replay": { "const": "off" },
            "recall": { "const": "off" }
          },
          "additionalProperties": false
        }
      },
      "additionalProperties": true
    },
    "run_summary": {
      "type": "object",
      "required": ["status", "total_cells", "successful_cells", "failed_cells", "missing_artifacts"],
      "properties": {
        "status": { "enum": ["complete", "partial", "failed", "unknown"] },
        "total_cells": { "type": "integer", "minimum": 0 },
        "successful_cells": { "type": "integer", "minimum": 0 },
        "failed_cells": { "type": "integer", "minimum": 0 },
        "missing_artifacts": { "type": "array", "items": { "type": "string" } },
        "cost": { "$ref": "#/$defs/cost_block" }
      },
      "additionalProperties": true
    },
    "cells": {
      "type": "array",
      "items": { "$ref": "#/$defs/analyze_cell" }
    },
    "cross_run": { "type": "object", "additionalProperties": true },
    "findings": {
      "type": "array",
      "items": { "$ref": "#/$defs/analyze_finding" }
    },
    "artifact_manifest": {
      "type": "array",
      "items": { "$ref": "#/$defs/artifact" }
    }
  },
  "$defs": {
    "analyze_cell": {
      "type": "object",
      "required": ["cell_id", "source_format", "artifacts", "completion", "metrics", "findings"],
      "properties": {
        "cell_id": { "type": "string" },
        "source_format": {
          "enum": [
            "inferencex-static",
            "inferencex-srt-slurm",
            "agentx-trace-replay",
            "inferguard-bench-native",
            "eval",
            "mixed",
            "unknown"
          ]
        },
        "hardware": { "type": ["string", "null"] },
        "model": { "type": ["string", "null"] },
        "framework": { "type": ["string", "null"] },
        "precision": { "type": ["string", "null"] },
        "scenario_type": { "type": ["string", "null"] },
        "is_multinode": { "type": ["boolean", "null"] },
        "recipe_name": { "type": ["string", "null"] },
        "isl": { "type": ["integer", "null"] },
        "osl": { "type": ["integer", "null"] },
        "concurrency": { "type": ["integer", "null"] },
        "topology": { "type": "object", "additionalProperties": true },
        "artifacts": { "type": "object", "additionalProperties": { "type": ["string", "array", "null"] } },
        "completion": { "type": "object", "additionalProperties": true },
        "metrics": { "type": "object", "additionalProperties": { "type": ["number", "integer", "string", "boolean", "null"] } },
        "timeline": { "type": "object", "additionalProperties": true },
        "cost": { "$ref": "#/$defs/cost_block" },
        "findings": { "type": "array", "items": { "$ref": "#/$defs/analyze_finding" } }
      },
      "additionalProperties": true
    },
    "cost_block": {
      "type": "object",
      "required": ["schema_version", "currency", "gpu_hours", "gpu_hour_cost", "compute_cost"],
      "properties": {
        "schema_version": { "const": "inferguard-cost/v1" },
        "currency": { "type": "string" },
        "duration_seconds": { "type": ["number", "null"] },
        "gpus": { "type": ["integer", "null"] },
        "gpu_hours": { "type": ["number", "null"] },
        "gpu_hour_cost": { "type": ["number", "null"] },
        "compute_cost": { "type": ["number", "null"] },
        "completed_sessions": { "type": ["integer", "null"] },
        "completed_requests": { "type": ["integer", "null"] },
        "completion_basis": { "enum": ["session-based", "request-based"] },
        "cost_per_completed_session": { "type": ["number", "null"] },
        "cost_per_completed_request": { "type": ["number", "null"] },
        "cost_per_million_input_tokens": { "type": ["number", "null"] },
        "cost_per_million_output_tokens": { "type": ["number", "null"] }
      },
      "additionalProperties": true
    },
    "analyze_finding": {
      "type": "object",
      "required": ["code", "severity", "message", "evidence"],
      "properties": {
        "code": {
          "description": "Emitted today: missing_required_artifact, invalid_run_no_successful_requests, partial_run, metrics_unavailable. Reserved / planned: ttft_cliff, tpot_degradation, throughput_plateau, kv_pressure, kv_offload_thrash, prefix_cache_regression, prefill_decode_imbalance, kv_transfer_stall, kv_transfer_errors_present, endpoint_unreachable, engine_unidentified, eval_regression.",
          "enum": [
            "missing_required_artifact",
            "invalid_run_no_successful_requests",
            "partial_run",
            "metrics_unavailable",
            "ttft_cliff",
            "tpot_degradation",
            "throughput_plateau",
            "kv_pressure",
            "kv_offload_thrash",
            "prefix_cache_regression",
            "prefill_decode_imbalance",
            "kv_transfer_stall",
            "kv_transfer_errors_present",
            "endpoint_unreachable",
            "engine_unidentified",
            "eval_regression"
          ]
        },
        "severity": { "enum": ["info", "warning", "critical"] },
        "message": { "type": "string" },
        "cell_id": { "type": ["string", "null"] },
        "evidence": { "type": "object", "additionalProperties": true }
      },
      "additionalProperties": true
    },
    "artifact": {
      "type": "object",
      "required": ["path", "kind"],
      "properties": {
        "path": { "type": "string" },
        "kind": { "type": "string" },
        "cell_id": { "type": ["string", "null"] },
        "required": { "type": "boolean" },
        "present": { "type": "boolean" }
      },
      "additionalProperties": true
    }
  },
  "additionalProperties": true
}
```

## `inferguard-cost/v1`

`inferguard-cost/v1` appears as an optional `cost` block on each `analyze_cell` and on `run_summary` when `inferguard analyze` is run with cost inputs. If cost flags are not provided, the analyzer omits the block.

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "inferguard-cost/v1",
  "type": "object",
  "required": ["schema_version", "currency", "gpu_hours", "gpu_hour_cost", "compute_cost"],
  "properties": {
    "schema_version": { "const": "inferguard-cost/v1" },
    "currency": { "type": "string" },
    "duration_seconds": { "type": ["number", "null"] },
    "gpus": { "type": ["integer", "null"] },
    "gpu_hours": { "type": ["number", "null"] },
    "gpu_hour_cost": { "type": ["number", "null"] },
    "compute_cost": { "type": ["number", "null"] },
    "completed_sessions": { "type": ["integer", "null"] },
    "completed_requests": { "type": ["integer", "null"] },
    "completion_basis": { "enum": ["session-based", "request-based"] },
    "cost_per_completed_session": { "type": ["number", "null"] },
    "cost_per_completed_request": { "type": ["number", "null"] },
    "cost_per_million_input_tokens": { "type": ["number", "null"] },
    "cost_per_million_output_tokens": { "type": ["number", "null"] }
  },
  "additionalProperties": true
}
```

Analyzer finding-code support levels mirror `SPEC.md` §4.11.

**Emitted today:**

```text
missing_required_artifact
invalid_run_no_successful_requests
partial_run
metrics_unavailable
```

**Reserved / planned:**

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

Planned analyzer finding codes are documented in [Analyze a run](../guides/analyze.md).

## Event record shape (`recent_events`)

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "disagg-event-record/v1",
  "type": "object",
  "required": ["at", "endpoints", "code", "severity", "message"],
  "properties": {
    "at": { "type": "number", "description": "Unix epoch seconds" },
    "endpoints": { "type": "array", "items": { "type": "string" } },
    "code": {
      "enum": [
        "connector_mismatch",
        "prefill_decode_imbalance",
        "kv_transfer_errors_present",
        "kv_transfer_stall",
        "endpoint_unreachable",
        "engine_unidentified"
      ]
    },
    "severity": { "enum": ["info", "warning", "critical"] },
    "message": { "type": "string" }
  },
  "additionalProperties": true
}
```

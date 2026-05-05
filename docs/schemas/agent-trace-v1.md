---
title: "agent-trace/v1 JSONL Schema"
status: "draft-v0.5-normative"
date: "2026-04-30"
purpose: "Normative schema specification for InferGuard harness agent trace JSONL files."
supersedes-policy: "New schema document; does not supersede oss/inferguard/docs/SCHEMAS.md or oss/inferguard/docs/SPEC.md."
---

# `agent-trace/v1` JSONL Schema

## 1. Status and source documents

This document is normative for `agent-trace/v1` files emitted by the v0.5 harness.
The locked event shapes come from `prompt-exports/2026-04-30-v0.5-harness-build-plan.md`.
The architecture context is `docs/designs/2026-04-30-inferguard-harness-architecture.md`.
The OpenTelemetry mapping is `docs/research/38-2026-04-30-industry-harness-research.md` §D.1.
The operator overview is `oss/inferguard/docs/HARNESS.md`.
The telemetry posture is `oss/inferguard/docs/telemetry/v0/POSTURE.md`.
The upload payload contract is `oss/inferguard/docs/telemetry/v1/SPEC.md`.

## 2. Normative language

The key words MUST, MUST NOT, SHOULD, SHOULD NOT, and MAY are normative.
A producer is the harness component that writes JSONL events.
A consumer is any validator, analyzer, daemon, or hosted ingest path that reads JSONL events.
A file is a UTF-8 text file with one JSON object per line.
Blank lines SHOULD NOT be emitted.
Consumers MAY ignore blank lines.
Each line MUST parse as one complete JSON object.
Each object MUST have `schema_version: "agent-trace/v1"`.
Events MUST be append-only during a run.
Producers SHOULD flush after each line for crash-safe debugging.

## 3. Privacy default

Default traces contain shape, count, and timing information only.
Default traces MUST NOT contain prompt text.
Default traces MUST NOT contain model output text.
Default traces MUST NOT contain tool argument values.
Default traces MUST NOT contain tool result payload content.
Default traces MUST NOT contain full working directory paths.
Default traces MUST NOT contain environment variables.
A local debugging flag MAY persist prompts for local use.
Any local prompt-saving flag MUST default to false.
Any local prompt-saving output MUST be marked in metadata.
Telemetry MUST NOT upload local prompt-saving output.

## 4. Locked schema examples

The following event shapes are locked for v0.5.
They are copied verbatim from the build plan and define the compatibility target.

```json
// node event — a model call, tool call, or branch decision
{
  "schema_version": "agent-trace/v1",
  "event_type": "node",
  "trace_id": "ulid-or-uuid-of-whole-run",
  "node_id": "ulid-or-uuid-of-this-node",
  "parent_node_ids": ["..."],
  "timestamp_start": 1730000000.123,
  "timestamp_end": 1730000001.456,
  "kind": "model_call" | "tool_call" | "branch" | "retry" | "user_input" | "system",
  "framework": "langgraph" | "crewai" | "autogen" | "claude_code" | "cursor_sdk" | "raw_openai" | "unknown",
  "model_call": {                          // present iff kind == "model_call"
    "endpoint": "http://localhost:8000/v1/chat/completions",
    "model": "deepseek-ai/DeepSeek-V4-Pro",
    "input_tokens": 8192,
    "output_tokens": 1024,
    "input_tokens_source": "api" | "estimated",
    "output_tokens_source": "api" | "estimated",
    "ttft_seconds": 0.420,
    "tpot_seconds": 0.012,
    "latency_seconds": 12.345,
    "tool_choice": "auto" | "required" | "none" | null,
    "stream": true,
    "stop_reason": "tool_use" | "end_turn" | "length" | "error" | null,
    "request_id": "...",
    "kv_pressure_label": "measured" | "inferred_without_engine_metrics"
  },
  "tool_call": {                           // present iff kind == "tool_call"
    "name": "filesystem.read_file",
    "wall_time_seconds": 0.083,
    "stall_seconds": 0.003,
    "result_size_bytes": 4096,
    "result_kind": "text" | "json" | "image" | "binary",
    "is_external": true,
    "is_io_bound": true
  },
  "branch": {                              // present iff kind == "branch"
    "branch_kind": "speculative" | "retry" | "fan_out",
    "siblings": ["..."]
  }
}

// summary event — emitted once at end of run
{
  "schema_version": "agent-trace/v1",
  "event_type": "summary",
  "trace_id": "...",
  "started_at": "2026-04-30T12:00:00Z",
  "completed_at": "2026-04-30T12:05:23Z",
  "total_seconds": 323.0,
  "node_counts": {"model_call": 12, "tool_call": 47, "branch": 3, "retry": 1},
  "total_tokens": {"input": 524288, "output": 4096},
  "tool_stall_total_seconds": 145.0,
  "tool_stall_pct": 0.45,
  "exit_status": "success" | "error" | "interrupted",
  "error_message": null,
  "framework_version": {"langgraph": "0.4.x"},
  "rig_label": "h200" | "b200" | "gb200" | "h100" | "auto" | null,
  "engine": "vllm" | "sglang" | "dynamo-vllm" | null,
  "redaction": {
    "prompts_redacted": true,
    "tool_args_redacted": true
  }
}
```

## 5. Event ordering

A trace file MAY interleave node kinds.
A trace file SHOULD order events by completion time.
`timestamp_start` MAY be earlier than the previous line's start time when branches run concurrently.
`timestamp_end` SHOULD be greater than or equal to `timestamp_start`.
A summary event MUST be the last non-blank event in a completed file.
A crashed run MAY omit the summary event.
Consumers MUST tolerate files without a summary event.
Consumers SHOULD surface missing summary as `interrupted` unless another error is known.

## 6. Top-level node fields

| Field | Type | Required | Units | Notes | Example |
|---|---|---:|---|---|---|
| `schema_version` | string | yes | none | MUST equal `agent-trace/v1`. | `agent-trace/v1` |
| `event_type` | string enum | yes | none | MUST be `node` for node events. | `node` |
| `trace_id` | string | yes | none | Stable ID for the whole agent run. | `01J...` |
| `node_id` | string | yes | none | Stable ID for this node event. | `01J...` |
| `parent_node_ids` | array[string] | yes | none | Empty for roots; multiple parents allowed for joins. | `["01J..."]` |
| `timestamp_start` | number | yes | Unix seconds | Fractional seconds are allowed. | `1730000000.123` |
| `timestamp_end` | number | yes | Unix seconds | Fractional seconds are allowed. | `1730000001.456` |
| `kind` | string enum | yes | none | Determines which detail object is present. | `model_call` |
| `framework` | string enum | yes | none | Best-known harness or framework. | `langgraph` |
| `model_call` | object | conditional | none | Present iff `kind == "model_call"`. | `{...}` |
| `tool_call` | object | conditional | none | Present iff `kind == "tool_call"`. | `{...}` |
| `branch` | object | conditional | none | Present iff `kind == "branch"`. | `{...}` |

`trace_id` SHOULD be a ULID or UUID.
`node_id` SHOULD be a ULID or UUID.
`parent_node_ids` MUST reference node IDs in the same trace when known.
`parent_node_ids` MAY reference nodes that appear later when concurrent hooks flush out of order.
`framework` MUST be `unknown` when the producer cannot classify the runtime.
`kind` MUST be one of the locked enum values.
Consumers MUST reject unknown `schema_version` values unless explicitly operating in permissive mode.
Consumers SHOULD ignore unknown additive fields for forward compatibility.

## 7. `kind` enum

| Value | Meaning | Detail object |
|---|---|---|
| `model_call` | A request to an LLM or compatible inference endpoint. | `model_call` |
| `tool_call` | A tool invocation made by the agent framework or wrapper. | `tool_call` |
| `branch` | A graph branch, fan-out, or speculative fork. | `branch` |
| `retry` | A retry node for a failed or repeated operation. | none in v0.5 |
| `user_input` | A user-input wait or boundary observed by the wrapper. | none in v0.5 |
| `system` | A harness/system event needed to preserve DAG shape. | none in v0.5 |

A `retry` node MAY use `parent_node_ids` to point to the failed attempt.
A `user_input` node MUST NOT include raw user content by default.
A `system` node MUST NOT include environment dumps.

## 8. `framework` enum

| Value | Meaning |
|---|---|
| `langgraph` | LangGraph application or hook path. |
| `crewai` | CrewAI application or hook path. |
| `autogen` | AutoGen application or hook path. |
| `claude_code` | Claude Code style agent subprocess. |
| `cursor_sdk` | Cursor Agent SDK style subprocess or hook. |
| `raw_openai` | No framework hook; raw OpenAI-compatible HTTP capture. |
| `unknown` | Producer could not classify the harness. |

Framework values are classification labels.
They are not authorization labels.
They MUST NOT imply that prompt content was captured.

## 9. `model_call` object fields

| Field | Type | Required | Units | OTel relationship | Example |
|---|---|---:|---|---|---|
| `endpoint` | string | yes | none | `server.address` + `server.port` when exported. | `http://localhost:8000/v1/chat/completions` |
| `model` | string | yes | none | `gen_ai.request.model`. | `deepseek-ai/DeepSeek-V4-Pro` |
| `input_tokens` | integer | yes | tokens | `gen_ai.client.token.usage` with `gen_ai.token.type=input`. | `8192` |
| `output_tokens` | integer | yes | tokens | `gen_ai.client.token.usage` with `gen_ai.token.type=output`. | `1024` |
| `input_tokens_source` | enum | yes | none | Source quality for token usage. | `api` |
| `output_tokens_source` | enum | yes | none | Source quality for token usage. | `estimated` |
| `ttft_seconds` | number | optional | seconds | `gen_ai.server.time_to_first_token`. | `0.420` |
| `tpot_seconds` | number | optional | seconds/token | Related to `gen_ai.server.time_per_output_token`. | `0.012` |
| `latency_seconds` | number | yes | seconds | `gen_ai.client.operation.duration`. | `12.345` |
| `tool_choice` | enum or null | optional | none | No direct required OTel field. | `auto` |
| `stream` | boolean | yes | none | Indicates streaming response mode. | `true` |
| `stop_reason` | enum or null | optional | none | Maps to response metadata when exported. | `tool_use` |
| `request_id` | string | optional | none | Provider request correlation ID. | `req_...` |
| `kv_pressure_label` | enum | optional | none | InferGuard-specific signal quality label. | `measured` |

`endpoint` SHOULD be normalized before telemetry upload.
`endpoint` in a local trace MAY include localhost and user-supplied endpoint values.
Telemetry payloads MUST NOT include full internal endpoint URLs.
`input_tokens` MUST be greater than or equal to zero.
`output_tokens` MUST be greater than or equal to zero.
`latency_seconds` MUST be greater than or equal to zero.
`ttft_seconds` MUST be omitted or null when not observed.
`tpot_seconds` MUST be omitted or null when not observed.
`input_tokens_source` MUST be `api` when returned by the inference API.
`input_tokens_source` MUST be `estimated` when counted locally.
`output_tokens_source` follows the same rule.
`request_id` MUST NOT be used as a consent or user identity token.

## 10. `tool_call` object fields

| Field | Type | Required | Units | Notes | Example |
|---|---|---:|---|---|---|
| `name` | string | yes | none | Tool name or normalized tool identifier. | `filesystem.read_file` |
| `wall_time_seconds` | number | yes | seconds | Total observed tool duration. | `0.083` |
| `stall_seconds` | number | optional | seconds | Time waiting on I/O or external resource. | `0.003` |
| `result_size_bytes` | integer | optional | bytes | Size of result payload, not content. | `4096` |
| `result_kind` | enum | optional | none | Shape label for result. | `text` |
| `is_external` | boolean | yes | none | True when the tool touches an external system. | `true` |
| `is_io_bound` | boolean | yes | none | True when dominated by I/O waits. | `true` |

`name` MUST NOT include raw arguments.
`wall_time_seconds` MUST be greater than or equal to zero.
`stall_seconds` MUST be greater than or equal to zero when present.
`stall_seconds` SHOULD be less than or equal to `wall_time_seconds`.
`result_size_bytes` MUST be greater than or equal to zero when present.
`result_kind` MUST be one of `text`, `json`, `image`, or `binary` when present.
`is_external` SHOULD be true for network, filesystem, database, browser, and shell tools.
`is_io_bound` SHOULD be true when the tool blocks on external I/O.
Tool arguments are never part of this object by default.
Tool results are never part of this object by default.

## 11. `branch` object fields

| Field | Type | Required | Units | Notes | Example |
|---|---|---:|---|---|---|
| `branch_kind` | enum | yes | none | Branch classification. | `fan_out` |
| `siblings` | array[string] | yes | none | Node IDs in the same branch family. | `["01J...", "01J..."]` |

`branch_kind` MUST be `speculative`, `retry`, or `fan_out`.
`siblings` SHOULD contain node IDs.
`siblings` MAY be empty only when the producer cannot observe sibling IDs.
Branch events SHOULD preserve DAG shape even when no model call occurs.

## 12. Summary event fields

| Field | Type | Required | Units | Notes | Example |
|---|---|---:|---|---|---|
| `schema_version` | string | yes | none | MUST equal `agent-trace/v1`. | `agent-trace/v1` |
| `event_type` | string enum | yes | none | MUST be `summary`. | `summary` |
| `trace_id` | string | yes | none | Matches node events. | `01J...` |
| `started_at` | string | yes | RFC 3339 | Run start timestamp. | `2026-04-30T12:00:00Z` |
| `completed_at` | string | yes | RFC 3339 | Run completion timestamp. | `2026-04-30T12:05:23Z` |
| `total_seconds` | number | yes | seconds | Wall-clock duration. | `323.0` |
| `node_counts` | object | yes | count | Counts by node kind. | `{"model_call": 12}` |
| `total_tokens` | object | yes | tokens | Input and output totals. | `{"input": 524288}` |
| `tool_stall_total_seconds` | number | optional | seconds | Aggregate tool stall time. | `145.0` |
| `tool_stall_pct` | number | optional | ratio | Stall time divided by total time. | `0.45` |
| `exit_status` | enum | yes | none | Run outcome. | `success` |
| `error_message` | string or null | optional | none | Redacted high-level error. | `null` |
| `framework_version` | object | optional | none | Framework version map. | `{"langgraph":"0.4.x"}` |
| `rig_label` | enum or null | optional | none | Hardware label. | `h200` |
| `engine` | enum or null | optional | none | Inference engine. | `vllm` |
| `redaction` | object | yes | none | Redaction truth flags. | `{"prompts_redacted": true}` |

`started_at` and `completed_at` MUST be UTC or include an offset.
`total_seconds` SHOULD equal `completed_at - started_at` within clock precision.
`node_counts` SHOULD include every kind observed in the file.
`total_tokens.input` SHOULD equal the sum of `input_tokens` from model calls.
`total_tokens.output` SHOULD equal the sum of `output_tokens` from model calls.
`tool_stall_pct` SHOULD be in the inclusive range `[0.0, 1.0]`.
`exit_status` MUST be `success`, `error`, or `interrupted`.
`error_message` MUST NOT include prompt text, output text, file paths, API keys, or tool arguments.
`redaction.prompts_redacted` MUST be true for default traces.
`redaction.tool_args_redacted` MUST be true for default traces.

## 13. OpenTelemetry GenAI mapping

The cited research file says OpenTelemetry GenAI conventions were experimental as of March 2026.
InferGuard uses the names to maximize cross-vendor compatibility.
`input_tokens` maps to `gen_ai.client.token.usage` with `gen_ai.token.type=input`.
`output_tokens` maps to `gen_ai.client.token.usage` with `gen_ai.token.type=output`.
`latency_seconds` maps to `gen_ai.client.operation.duration`.
`ttft_seconds` maps to `gen_ai.server.time_to_first_token`.
`tpot_seconds` relates to `gen_ai.server.time_per_output_token`.
`model` maps to `gen_ai.request.model`.
`endpoint` maps to `server.address` and `server.port` in local OTel export.
Errors should map to `error.type` when represented as spans or metrics.
Operators enabling OTel export may need `OTEL_SEMCONV_STABILITY_OPT_IN=gen_ai_latest_experimental`.
OpenTelemetry export is operator-configured.
OpenTelemetry export is not Touchdown telemetry.

## 14. Minimal valid model-call line

```json
{"schema_version":"agent-trace/v1","event_type":"node","trace_id":"01HVTRACE","node_id":"01HVMODEL","parent_node_ids":[],"timestamp_start":1730000000.123,"timestamp_end":1730000001.456,"kind":"model_call","framework":"raw_openai","model_call":{"endpoint":"http://localhost:8000/v1/chat/completions","model":"deepseek-ai/DeepSeek-V4-Pro","input_tokens":8192,"output_tokens":1024,"input_tokens_source":"api","output_tokens_source":"api","ttft_seconds":0.420,"tpot_seconds":0.012,"latency_seconds":12.345,"tool_choice":"auto","stream":true,"stop_reason":"end_turn","request_id":"req_123","kv_pressure_label":"measured"}}
```

## 15. Minimal valid summary line

```json
{"schema_version":"agent-trace/v1","event_type":"summary","trace_id":"01HVTRACE","started_at":"2026-04-30T12:00:00Z","completed_at":"2026-04-30T12:05:23Z","total_seconds":323.0,"node_counts":{"model_call":1},"total_tokens":{"input":8192,"output":1024},"tool_stall_total_seconds":0.0,"tool_stall_pct":0.0,"exit_status":"success","error_message":null,"framework_version":{"raw_openai":"unknown"},"rig_label":"auto","engine":"vllm","redaction":{"prompts_redacted":true,"tool_args_redacted":true}}
```

## 16. Validation rules

Validators MUST verify `schema_version` first.
Validators MUST verify `event_type` next.
Validators MUST enforce conditional detail objects for `model_call`, `tool_call`, and `branch`.
Validators MUST reject negative durations.
Validators MUST reject negative token counts.
Validators MUST reject negative byte counts.
Validators MUST reject invalid enum values.
Validators MUST reject summary events with no `trace_id`.
Validators SHOULD warn if `timestamp_end < timestamp_start`.
Validators SHOULD warn if summary totals disagree with node totals.
Validators SHOULD warn if redaction flags are false.
Validators SHOULD warn if `endpoint` appears to contain credentials.
Validators SHOULD warn if any string value resembles an API key.
Validators SHOULD warn if any unexpected field appears to contain prompt or output text.

## 17. Forward compatibility

New optional fields MAY be added to node events.
New optional fields MAY be added to summary events.
New enum values require a schema revision unless consumers are explicitly prepared for unknown values.
Renaming a field requires `agent-trace/v2`.
Changing units requires `agent-trace/v2`.
Changing privacy defaults requires `agent-trace/v2` and a posture update.
Consumers SHOULD preserve unknown fields when rewriting local traces.
Telemetry payload builders MUST apply the stricter telemetry blocklist before upload.

## 18. File naming

The recommended file name is `agent-trace.jsonl`.
A run directory MAY include related files such as `summary.json` or `agent-trace.dot`.
The JSONL file is the normative trace.
The DOT file is a visualization artifact only.
The summary event in JSONL is the normative run summary for this schema.

## 19. Non-goals

This schema is not a prompt logging format.
This schema is not an output transcript format.
This schema is not a full OpenTelemetry trace export.
This schema is not a permission system.
This schema is not the hosted upload payload.
This schema is the local harness trace contract.

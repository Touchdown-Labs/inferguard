"""Validators for the locked ``agent-trace/v1`` JSONL schema."""

from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

AGENT_TRACE_SCHEMA_VERSION = "agent-trace/v1"

NODE_KINDS = {"model_call", "tool_call", "branch", "retry", "user_input", "system"}
FRAMEWORKS = {
    "langgraph",
    "crewai",
    "autogen",
    "claude_code",
    "cursor_sdk",
    "raw_openai",
    "unknown",
}
TOKEN_SOURCES = {"api", "estimated"}
TOOL_CHOICES = {"auto", "required", "none", None}
STOP_REASONS = {"tool_use", "end_turn", "length", "error", None}
KV_PRESSURE_LABELS = {"measured", "inferred_without_engine_metrics"}
RESULT_KINDS = {"text", "json", "image", "binary"}
BRANCH_KINDS = {"speculative", "retry", "fan_out"}
EXIT_STATUSES = {"success", "error", "interrupted"}
RIG_LABELS = {"h200", "b200", "gb200", "h100", "auto", None}
ENGINES = {"vllm", "sglang", "dynamo-vllm", None}

NODE_EVENT_KEYS = {
    "schema_version",
    "event_type",
    "trace_id",
    "node_id",
    "parent_node_ids",
    "timestamp_start",
    "timestamp_end",
    "kind",
    "framework",
    "model_call",
    "tool_call",
    "branch",
}
MODEL_CALL_KEYS = {
    "endpoint",
    "model",
    "input_tokens",
    "output_tokens",
    "input_tokens_source",
    "output_tokens_source",
    "ttft_seconds",
    "tpot_seconds",
    "latency_seconds",
    "tool_choice",
    "stream",
    "stop_reason",
    "request_id",
    "kv_pressure_label",
}
TOOL_CALL_KEYS = {
    "name",
    "wall_time_seconds",
    "stall_seconds",
    "result_size_bytes",
    "result_kind",
    "is_external",
    "is_io_bound",
}
BRANCH_KEYS = {"branch_kind", "siblings"}
SUMMARY_KEYS = {
    "schema_version",
    "event_type",
    "trace_id",
    "started_at",
    "completed_at",
    "total_seconds",
    "node_counts",
    "total_tokens",
    "tool_stall_total_seconds",
    "tool_stall_pct",
    "exit_status",
    "error_message",
    "framework_version",
    "rig_label",
    "engine",
    "redaction",
}
REDACTION_KEYS = {"prompts_redacted", "tool_args_redacted"}
TOTAL_TOKEN_KEYS = {"input", "output"}


class AgentTraceValidationError(ValueError):
    """Raised when an ``agent-trace/v1`` event is malformed."""


@dataclass(frozen=True)
class ValidationError:
    """Non-throwing trace-integrity validation error."""

    message: str
    event_index: int | None = None
    field: str | None = None

    def __str__(self) -> str:
        location = "trace" if self.event_index is None else f"event[{self.event_index}]"
        if self.field:
            location = f"{location}.{self.field}"
        return f"{location}: {self.message}"


@dataclass(frozen=True)
class ModelCall:
    endpoint: str
    model: str
    input_tokens: int
    output_tokens: int
    input_tokens_source: Literal["api", "estimated"]
    output_tokens_source: Literal["api", "estimated"]
    ttft_seconds: float
    tpot_seconds: float
    latency_seconds: float
    tool_choice: Literal["auto", "required", "none"] | None
    stream: bool
    stop_reason: Literal["tool_use", "end_turn", "length", "error"] | None
    request_id: str
    kv_pressure_label: Literal["measured", "inferred_without_engine_metrics"]

    @classmethod
    def from_dict(cls, data: dict[str, Any], *, source: str = "model_call") -> ModelCall:
        _require_object(data, source)
        _assert_keys(data, MODEL_CALL_KEYS, source)
        _require_fields(data, MODEL_CALL_KEYS, source)
        input_source = _enum(data["input_tokens_source"], TOKEN_SOURCES, "input_tokens_source", source)
        output_source = _enum(data["output_tokens_source"], TOKEN_SOURCES, "output_tokens_source", source)
        return cls(
            endpoint=_str(data["endpoint"], "endpoint", source),
            model=_str(data["model"], "model", source),
            input_tokens=_non_negative_int(data["input_tokens"], "input_tokens", source),
            output_tokens=_non_negative_int(data["output_tokens"], "output_tokens", source),
            input_tokens_source=input_source,
            output_tokens_source=output_source,
            ttft_seconds=_non_negative_number(data["ttft_seconds"], "ttft_seconds", source),
            tpot_seconds=_non_negative_number(data["tpot_seconds"], "tpot_seconds", source),
            latency_seconds=_non_negative_number(data["latency_seconds"], "latency_seconds", source),
            tool_choice=_enum(data["tool_choice"], TOOL_CHOICES, "tool_choice", source),
            stream=_bool(data["stream"], "stream", source),
            stop_reason=_enum(data["stop_reason"], STOP_REASONS, "stop_reason", source),
            request_id=_str(data["request_id"], "request_id", source),
            kv_pressure_label=_enum(
                data["kv_pressure_label"], KV_PRESSURE_LABELS, "kv_pressure_label", source
            ),
        )

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ToolCall:
    name: str
    wall_time_seconds: float
    stall_seconds: float
    result_size_bytes: int
    result_kind: Literal["text", "json", "image", "binary"]
    is_external: bool
    is_io_bound: bool

    @classmethod
    def from_dict(cls, data: dict[str, Any], *, source: str = "tool_call") -> ToolCall:
        _require_object(data, source)
        _assert_keys(data, TOOL_CALL_KEYS, source)
        _require_fields(data, TOOL_CALL_KEYS, source)
        return cls(
            name=_str(data["name"], "name", source),
            wall_time_seconds=_non_negative_number(
                data["wall_time_seconds"], "wall_time_seconds", source
            ),
            stall_seconds=_non_negative_number(data["stall_seconds"], "stall_seconds", source),
            result_size_bytes=_non_negative_int(data["result_size_bytes"], "result_size_bytes", source),
            result_kind=_enum(data["result_kind"], RESULT_KINDS, "result_kind", source),
            is_external=_bool(data["is_external"], "is_external", source),
            is_io_bound=_bool(data["is_io_bound"], "is_io_bound", source),
        )

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class Branch:
    branch_kind: Literal["speculative", "retry", "fan_out"]
    siblings: list[str]

    @classmethod
    def from_dict(cls, data: dict[str, Any], *, source: str = "branch") -> Branch:
        _require_object(data, source)
        _assert_keys(data, BRANCH_KEYS, source)
        _require_fields(data, BRANCH_KEYS, source)
        return cls(
            branch_kind=_enum(data["branch_kind"], BRANCH_KINDS, "branch_kind", source),
            siblings=_str_list(data["siblings"], "siblings", source),
        )

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class NodeEvent:
    schema_version: Literal["agent-trace/v1"]
    event_type: Literal["node"]
    trace_id: str
    node_id: str
    parent_node_ids: list[str]
    timestamp_start: float
    timestamp_end: float
    kind: Literal["model_call", "tool_call", "branch", "retry", "user_input", "system"]
    framework: Literal[
        "langgraph", "crewai", "autogen", "claude_code", "cursor_sdk", "raw_openai", "unknown"
    ]
    model_call: ModelCall | None = None
    tool_call: ToolCall | None = None
    branch: Branch | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any], *, source: str = "event") -> NodeEvent:
        _require_object(data, source)
        _assert_keys(data, NODE_EVENT_KEYS, source)
        required = {
            "schema_version",
            "event_type",
            "trace_id",
            "node_id",
            "parent_node_ids",
            "timestamp_start",
            "timestamp_end",
            "kind",
            "framework",
        }
        _require_fields(data, required, source)
        _schema(data, source)
        if data["event_type"] != "node":
            raise AgentTraceValidationError(f"{source}: event_type must be 'node'")
        kind = _enum(data["kind"], NODE_KINDS, "kind", source)
        start = _non_negative_number(data["timestamp_start"], "timestamp_start", source)
        end = _non_negative_number(data["timestamp_end"], "timestamp_end", source)
        if end < start:
            raise AgentTraceValidationError(f"{source}: timestamp_end must be >= timestamp_start")

        model_call = _conditional_child(
            data, key="model_call", expected_kind="model_call", actual_kind=kind, cls=ModelCall, source=source
        )
        tool_call = _conditional_child(
            data, key="tool_call", expected_kind="tool_call", actual_kind=kind, cls=ToolCall, source=source
        )
        branch = _conditional_child(
            data, key="branch", expected_kind="branch", actual_kind=kind, cls=Branch, source=source
        )
        return cls(
            schema_version=AGENT_TRACE_SCHEMA_VERSION,
            event_type="node",
            trace_id=_str(data["trace_id"], "trace_id", source),
            node_id=_str(data["node_id"], "node_id", source),
            parent_node_ids=_str_list(data["parent_node_ids"], "parent_node_ids", source),
            timestamp_start=start,
            timestamp_end=end,
            kind=kind,
            framework=_enum(data["framework"], FRAMEWORKS, "framework", source),
            model_call=model_call,
            tool_call=tool_call,
            branch=branch,
        )

    def as_dict(self) -> dict[str, Any]:
        data = asdict(self)
        if self.model_call is None:
            data.pop("model_call")
        if self.tool_call is None:
            data.pop("tool_call")
        if self.branch is None:
            data.pop("branch")
        return data


@dataclass(frozen=True)
class SummaryEvent:
    schema_version: Literal["agent-trace/v1"]
    event_type: Literal["summary"]
    trace_id: str
    started_at: str
    completed_at: str
    total_seconds: float
    node_counts: dict[str, int]
    total_tokens: dict[str, int]
    tool_stall_total_seconds: float
    tool_stall_pct: float
    exit_status: Literal["success", "error", "interrupted"]
    error_message: str | None
    framework_version: dict[str, str]
    rig_label: Literal["h200", "b200", "gb200", "h100", "auto"] | None
    engine: Literal["vllm", "sglang", "dynamo-vllm"] | None
    redaction: dict[str, bool]

    @classmethod
    def from_dict(cls, data: dict[str, Any], *, source: str = "event") -> SummaryEvent:
        _require_object(data, source)
        _assert_keys(data, SUMMARY_KEYS, source)
        _require_fields(data, SUMMARY_KEYS, source)
        _schema(data, source)
        if data["event_type"] != "summary":
            raise AgentTraceValidationError(f"{source}: event_type must be 'summary'")
        total_tokens = _int_map(data["total_tokens"], "total_tokens", source)
        if set(total_tokens) != TOTAL_TOKEN_KEYS:
            raise AgentTraceValidationError(f"{source}: total_tokens must contain input and output")
        redaction = _bool_map(data["redaction"], "redaction", source)
        if set(redaction) != REDACTION_KEYS:
            raise AgentTraceValidationError(
                f"{source}: redaction must contain prompts_redacted and tool_args_redacted"
            )
        error_message = data["error_message"]
        if error_message is not None:
            error_message = _str(error_message, "error_message", source)
        tool_stall_pct = _non_negative_number(data["tool_stall_pct"], "tool_stall_pct", source)
        if tool_stall_pct > 1:
            raise AgentTraceValidationError(f"{source}: tool_stall_pct must be <= 1")
        return cls(
            schema_version=AGENT_TRACE_SCHEMA_VERSION,
            event_type="summary",
            trace_id=_str(data["trace_id"], "trace_id", source),
            started_at=_str(data["started_at"], "started_at", source),
            completed_at=_str(data["completed_at"], "completed_at", source),
            total_seconds=_non_negative_number(data["total_seconds"], "total_seconds", source),
            node_counts=_int_map(data["node_counts"], "node_counts", source),
            total_tokens=total_tokens,
            tool_stall_total_seconds=_non_negative_number(
                data["tool_stall_total_seconds"], "tool_stall_total_seconds", source
            ),
            tool_stall_pct=tool_stall_pct,
            exit_status=_enum(data["exit_status"], EXIT_STATUSES, "exit_status", source),
            error_message=error_message,
            framework_version=_str_map(data["framework_version"], "framework_version", source),
            rig_label=_enum(data["rig_label"], RIG_LABELS, "rig_label", source),
            engine=_enum(data["engine"], ENGINES, "engine", source),
            redaction=redaction,
        )

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


AgentTraceEvent = NodeEvent | SummaryEvent


def validate_agent_trace_event(data: dict[str, Any], *, source: str = "event") -> AgentTraceEvent:
    """Validate and normalize one locked ``agent-trace/v1`` JSON object."""

    _require_object(data, source)
    _schema(data, source)
    event_type = data.get("event_type")
    if event_type == "node":
        return NodeEvent.from_dict(data, source=source)
    if event_type == "summary":
        return SummaryEvent.from_dict(data, source=source)
    raise AgentTraceValidationError(f"{source}: event_type must be node or summary")


def iter_agent_trace_jsonl(path: Path | str) -> Iterable[AgentTraceEvent]:
    """Yield validated events from a JSONL trace file."""

    trace_path = Path(path)
    for line_number, line in enumerate(trace_path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            raw = json.loads(line)
        except json.JSONDecodeError as exc:
            raise AgentTraceValidationError(f"{trace_path}:{line_number}: invalid JSON") from exc
        yield validate_agent_trace_event(raw, source=f"{trace_path}:{line_number}")


def dump_agent_trace_event(event: AgentTraceEvent | dict[str, Any]) -> dict[str, Any]:
    """Return a schema-shaped dictionary after validation."""

    if isinstance(event, dict):
        return validate_agent_trace_event(event).as_dict()
    return event.as_dict()


def validate_trace_integrity(events: list[dict[str, Any]]) -> list[ValidationError]:
    """Return graph-level integrity errors for an ``agent-trace/v1`` event list.

    Event-level schema validation remains handled by ``validate_agent_trace_event``;
    this function adds JSONL-wide checks such as unique node IDs, valid parent
    references, one trace ID, summary/node count consistency, and summary ordering.
    """

    if not isinstance(events, list):
        return [ValidationError("events must be a list")]

    errors: list[ValidationError] = []
    validated: list[tuple[int, AgentTraceEvent]] = []
    for index, data in enumerate(events):
        try:
            validated.append((index, validate_agent_trace_event(data, source=f"event[{index}]")))
        except AgentTraceValidationError as exc:
            errors.append(ValidationError(str(exc), event_index=index))

    if not validated:
        errors.append(ValidationError("trace must contain at least one event"))
        return errors

    trace_ids = {event.trace_id for _, event in validated}
    if len(trace_ids) != 1:
        errors.append(ValidationError("trace must contain exactly one trace_id", field="trace_id"))

    node_entries = [(index, event) for index, event in validated if isinstance(event, NodeEvent)]
    summary_entries = [(index, event) for index, event in validated if isinstance(event, SummaryEvent)]

    node_ids: dict[str, int] = {}
    for index, node in node_entries:
        if node.node_id in node_ids:
            errors.append(
                ValidationError(
                    f"duplicate node_id {node.node_id!r}; first seen at event[{node_ids[node.node_id]}]",
                    event_index=index,
                    field="node_id",
                )
            )
        else:
            node_ids[node.node_id] = index
        if node.timestamp_start > node.timestamp_end:
            errors.append(
                ValidationError(
                    "timestamp_start must be <= timestamp_end",
                    event_index=index,
                    field="timestamp_start",
                )
            )

    real_node_ids = set(node_ids)
    for index, node in node_entries:
        for parent_id in node.parent_node_ids:
            if parent_id not in real_node_ids:
                errors.append(
                    ValidationError(
                        f"parent_node_id {parent_id!r} does not reference a node in this trace",
                        event_index=index,
                        field="parent_node_ids",
                    )
                )

    if not summary_entries:
        errors.append(ValidationError("trace must contain exactly one summary event", field="event_type"))
        return errors
    if len(summary_entries) > 1:
        errors.append(ValidationError("trace must contain exactly one summary event", field="event_type"))

    summary_index, summary = summary_entries[-1]
    if summary_index != len(events) - 1:
        errors.append(
            ValidationError("summary event must appear last", event_index=summary_index, field="event_type")
        )
    if not any(index < summary_index for index, _ in node_entries):
        errors.append(
            ValidationError(
                "summary event must have at least one preceding node",
                event_index=summary_index,
                field="event_type",
            )
        )

    expected_model_calls = sum(1 for _, node in node_entries if node.kind == "model_call")
    actual_model_calls = summary.node_counts.get("model_call", 0)
    if actual_model_calls != expected_model_calls:
        errors.append(
            ValidationError(
                f"node_counts.model_call={actual_model_calls} does not match {expected_model_calls} node event(s)",
                event_index=summary_index,
                field="node_counts.model_call",
            )
        )

    max_node_end = max((node.timestamp_end for _, node in node_entries), default=None)
    completed_at = _timestamp_seconds(summary.completed_at)
    if completed_at is None:
        errors.append(
            ValidationError(
                "completed_at must be an ISO-8601 timestamp or numeric epoch seconds",
                event_index=summary_index,
                field="completed_at",
            )
        )
    elif max_node_end is not None and completed_at < max_node_end:
        errors.append(
            ValidationError(
                "summary.completed_at must be >= max node timestamp_end",
                event_index=summary_index,
                field="completed_at",
            )
        )

    return errors


def _conditional_child(
    data: dict[str, Any],
    *,
    key: str,
    expected_kind: str,
    actual_kind: str,
    cls: type[ModelCall] | type[ToolCall] | type[Branch],
    source: str,
) -> ModelCall | ToolCall | Branch | None:
    present = key in data and data[key] is not None
    if actual_kind == expected_kind and not present:
        raise AgentTraceValidationError(f"{source}: {key} is required when kind == {expected_kind}")
    if actual_kind != expected_kind and present:
        raise AgentTraceValidationError(f"{source}: {key} is present iff kind == {expected_kind}")
    return cls.from_dict(data[key], source=f"{source}.{key}") if present else None


def _schema(data: dict[str, Any], source: str) -> None:
    if data.get("schema_version") != AGENT_TRACE_SCHEMA_VERSION:
        raise AgentTraceValidationError(f"{source}: schema_version must be {AGENT_TRACE_SCHEMA_VERSION!r}")


def _require_object(value: Any, source: str) -> None:
    if not isinstance(value, dict):
        raise AgentTraceValidationError(f"{source}: must be a JSON object")


def _assert_keys(data: dict[str, Any], allowed: set[str], source: str) -> None:
    unknown = sorted(set(data) - allowed)
    if unknown:
        raise AgentTraceValidationError(f"{source}: unknown field(s): {', '.join(unknown)}")


def _require_fields(data: dict[str, Any], required: set[str], source: str) -> None:
    missing = sorted(required - set(data))
    if missing:
        raise AgentTraceValidationError(f"{source}: missing required field(s): {', '.join(missing)}")


def _str(value: Any, key: str, source: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise AgentTraceValidationError(f"{source}: {key} must be a non-empty string")
    return value


def _str_list(value: Any, key: str, source: str) -> list[str]:
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise AgentTraceValidationError(f"{source}: {key} must be a list of strings")
    return list(value)


def _str_map(value: Any, key: str, source: str) -> dict[str, str]:
    if not isinstance(value, dict):
        raise AgentTraceValidationError(f"{source}: {key} must be an object")
    if any(not isinstance(k, str) or not isinstance(v, str) for k, v in value.items()):
        raise AgentTraceValidationError(f"{source}: {key} must map strings to strings")
    return dict(value)


def _int_map(value: Any, key: str, source: str) -> dict[str, int]:
    if not isinstance(value, dict):
        raise AgentTraceValidationError(f"{source}: {key} must be an object")
    result: dict[str, int] = {}
    for item_key, item_value in value.items():
        if not isinstance(item_key, str):
            raise AgentTraceValidationError(f"{source}: {key} keys must be strings")
        result[item_key] = _non_negative_int(item_value, f"{key}.{item_key}", source)
    return result


def _bool_map(value: Any, key: str, source: str) -> dict[str, bool]:
    if not isinstance(value, dict):
        raise AgentTraceValidationError(f"{source}: {key} must be an object")
    result: dict[str, bool] = {}
    for item_key, item_value in value.items():
        if not isinstance(item_key, str):
            raise AgentTraceValidationError(f"{source}: {key} keys must be strings")
        result[item_key] = _bool(item_value, f"{key}.{item_key}", source)
    return result


def _bool(value: Any, key: str, source: str) -> bool:
    if not isinstance(value, bool):
        raise AgentTraceValidationError(f"{source}: {key} must be boolean")
    return value


def _non_negative_int(value: Any, key: str, source: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise AgentTraceValidationError(f"{source}: {key} must be a non-negative integer")
    return value


def _non_negative_number(value: Any, key: str, source: str) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float) or value < 0:
        raise AgentTraceValidationError(f"{source}: {key} must be a non-negative number")
    return float(value)


def _enum(value: Any, allowed: set[Any], key: str, source: str) -> Any:
    if value not in allowed:
        rendered = ", ".join("null" if item is None else repr(item) for item in sorted(allowed, key=str))
        raise AgentTraceValidationError(f"{source}: {key} must be one of {rendered}")
    return value


def _timestamp_seconds(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        return float(value)
    if not isinstance(value, str):
        return None
    try:
        return float(value)
    except ValueError:
        pass
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None

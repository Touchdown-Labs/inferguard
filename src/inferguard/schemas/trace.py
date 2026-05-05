"""Trace JSONL schema for ``inferguard bench replay``."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

ALLOWED_WORKLOAD_CLASSES = {
    "coding-long",
    "agent-chat",
    "multi-agent-coding",
    "tool-heavy",
    "session-resume",
    "prefix-reuse",
    "repo-level-coding",
    "long-context-debugging",
    "rag-generation",
    "high-concurrency-dev-assistant",
    "kv-pressure",
}


class TraceValidationError(ValueError):
    """Raised when a trace JSONL record does not match the v1 schema."""


@dataclass(frozen=True)
class TraceRecord:
    trace_id: str
    session_id: str
    turn_index: int
    workload_class: str
    messages: list[dict[str, Any]]
    expected_input_tokens: int | None = None
    expected_output_tokens: int | None = None
    prefix_group: str | None = None
    tool_heavy: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any], *, source: str = "record") -> TraceRecord:
        if not isinstance(data, dict):
            raise TraceValidationError(f"{source}: record must be a JSON object")
        required = ["trace_id", "session_id", "turn_index", "workload_class", "messages"]
        missing = [key for key in required if key not in data]
        if missing:
            raise TraceValidationError(f"{source}: missing required field(s): {', '.join(missing)}")

        trace_id = _str_field(data, "trace_id", source)
        session_id = _str_field(data, "session_id", source)
        workload_class = _str_field(data, "workload_class", source)
        if workload_class not in ALLOWED_WORKLOAD_CLASSES:
            allowed = ", ".join(sorted(ALLOWED_WORKLOAD_CLASSES))
            raise TraceValidationError(
                f"{source}: workload_class must be one of {allowed} (got {workload_class!r})"
            )

        turn_index = data["turn_index"]
        if not isinstance(turn_index, int) or turn_index < 0:
            raise TraceValidationError(f"{source}: turn_index must be a non-negative integer")

        messages = data["messages"]
        if not isinstance(messages, list) or not messages:
            raise TraceValidationError(f"{source}: messages must be a non-empty list")
        for idx, message in enumerate(messages):
            if not isinstance(message, dict):
                raise TraceValidationError(f"{source}: messages[{idx}] must be an object")
            role = message.get("role")
            content = message.get("content")
            if role not in {"system", "user", "assistant", "tool"}:
                raise TraceValidationError(f"{source}: messages[{idx}].role is invalid")
            if not isinstance(content, str):
                raise TraceValidationError(f"{source}: messages[{idx}].content must be a string")

        expected_input_tokens = _optional_non_negative_int(data, "expected_input_tokens", source)
        expected_output_tokens = _optional_non_negative_int(data, "expected_output_tokens", source)
        prefix_group = data.get("prefix_group")
        if prefix_group is not None and not isinstance(prefix_group, str):
            raise TraceValidationError(f"{source}: prefix_group must be a string or null")
        tool_heavy = data.get("tool_heavy", False)
        if not isinstance(tool_heavy, bool):
            raise TraceValidationError(f"{source}: tool_heavy must be boolean")
        metadata = data.get("metadata", {})
        if not isinstance(metadata, dict):
            raise TraceValidationError(f"{source}: metadata must be an object")

        return cls(
            trace_id=trace_id,
            session_id=session_id,
            turn_index=turn_index,
            workload_class=workload_class,
            messages=messages,
            expected_input_tokens=expected_input_tokens,
            expected_output_tokens=expected_output_tokens,
            prefix_group=prefix_group,
            tool_heavy=tool_heavy,
            metadata=metadata,
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "trace_id": self.trace_id,
            "session_id": self.session_id,
            "turn_index": self.turn_index,
            "workload_class": self.workload_class,
            "messages": self.messages,
            "expected_input_tokens": self.expected_input_tokens,
            "expected_output_tokens": self.expected_output_tokens,
            "prefix_group": self.prefix_group,
            "tool_heavy": self.tool_heavy,
            "metadata": self.metadata,
        }


def _str_field(data: dict[str, Any], key: str, source: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise TraceValidationError(f"{source}: {key} must be a non-empty string")
    return value


def _optional_non_negative_int(data: dict[str, Any], key: str, source: str) -> int | None:
    value = data.get(key)
    if value is None:
        return None
    if not isinstance(value, int) or value < 0:
        raise TraceValidationError(f"{source}: {key} must be a non-negative integer or null")
    return value

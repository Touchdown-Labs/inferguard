"""Input readers for workload fingerprinting."""

from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from inferguard.bench.tokenizer import estimate_text_tokens


@dataclass(frozen=True)
class WorkloadSample:
    source: str
    session_id: str
    trace_id: str | None
    timestamp: float | None
    input_tokens: int
    output_tokens: int
    prefix_key: str
    tool_call_count: int
    retry_count: int
    rag_chunk_count: int
    workload_class: str


def read_openai_jsonl_dir(log_dir: Path) -> list[WorkloadSample]:
    samples: list[WorkloadSample] = []
    for path in sorted(log_dir.rglob("*.jsonl")):
        samples.extend(_read_jsonl(path))
    return samples


def _read_jsonl(path: Path) -> Iterable[WorkloadSample]:
    for index, line in enumerate(path.read_text(encoding="utf-8").splitlines()):
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(record, dict):
            yield _sample_from_record(record, path, index)


def _sample_from_record(record: dict[str, Any], path: Path, index: int) -> WorkloadSample:
    messages = _messages(record)
    prompt_text = "\n".join(_message_text(message) for message in messages)
    usage = record.get("usage") if isinstance(record.get("usage"), dict) else {}
    input_tokens = _int_or_none(record.get("expected_input_tokens")) or _int_or_none(
        usage.get("prompt_tokens")
    )
    output_tokens = (
        _int_or_none(record.get("expected_output_tokens"))
        or _int_or_none(record.get("output_tokens"))
        or _int_or_none(usage.get("completion_tokens"))
    )
    if input_tokens is None:
        input_tokens = estimate_text_tokens(prompt_text)
    if output_tokens is None:
        output_tokens = estimate_text_tokens(_output_text(record))
    session_id = str(
        record.get("session_id")
        or record.get("conversation_id")
        or record.get("user_id")
        or f"{path.stem}-{index}"
    )
    trace_id = record.get("trace_id") or record.get("id") or record.get("request_id")
    prefix_key = str(record.get("prefix_group") or _prefix_key(messages))
    return WorkloadSample(
        source=str(path),
        session_id=session_id,
        trace_id=str(trace_id) if trace_id is not None else None,
        timestamp=_float_or_none(
            record.get("timestamp") or record.get("created_at") or record.get("request_start_time")
        ),
        input_tokens=max(0, int(input_tokens)),
        output_tokens=max(0, int(output_tokens)),
        prefix_key=prefix_key,
        tool_call_count=_tool_call_count(record, messages),
        retry_count=max(0, _int_or_none(record.get("retry_count")) or 0),
        rag_chunk_count=_rag_chunk_count(record, messages),
        workload_class=str(
            record.get("workload_class") or record.get("scenario_type") or "unknown"
        ),
    )


def _messages(record: dict[str, Any]) -> list[dict[str, Any]]:
    raw = record.get("messages")
    if isinstance(raw, list):
        return [item for item in raw if isinstance(item, dict)]
    request = record.get("request") if isinstance(record.get("request"), dict) else {}
    raw = request.get("messages")
    if isinstance(raw, list):
        return [item for item in raw if isinstance(item, dict)]
    prompt = record.get("prompt") or record.get("input")
    if prompt is not None:
        return [{"role": "user", "content": str(prompt)}]
    return []


def _message_text(message: dict[str, Any]) -> str:
    content = message.get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, dict):
                text = item.get("text") or item.get("content")
                if text is not None:
                    parts.append(str(text))
            elif item is not None:
                parts.append(str(item))
        return "\n".join(parts)
    return "" if content is None else str(content)


def _output_text(record: dict[str, Any]) -> str:
    for key in ("output", "completion", "response"):
        value = record.get(key)
        if isinstance(value, str):
            return value
        if isinstance(value, dict):
            choices = value.get("choices")
            if isinstance(choices, list) and choices:
                choice = choices[0] if isinstance(choices[0], dict) else {}
                message = choice.get("message") if isinstance(choice.get("message"), dict) else {}
                return _message_text(message)
    return ""


def _prefix_key(messages: list[dict[str, Any]]) -> str:
    if not messages:
        return ""
    first = messages[0]
    if first.get("role") == "system":
        return _message_text(first)[:2048]
    return _message_text(first)[:512]


def _tool_call_count(record: dict[str, Any], messages: list[dict[str, Any]]) -> int:
    count = 0
    for message in messages:
        tool_calls = message.get("tool_calls")
        if isinstance(tool_calls, list):
            count += len(tool_calls)
    for key in ("tool_calls", "tools_invoked"):
        value = record.get(key)
        if isinstance(value, list):
            count += len(value)
        elif isinstance(value, int):
            count += value
    return count


def _rag_chunk_count(record: dict[str, Any], messages: list[dict[str, Any]]) -> int:
    value = record.get("rag_chunks") or record.get("retrieved_chunks")
    if isinstance(value, list):
        return len(value)
    if isinstance(value, int):
        return value
    return sum(_message_text(message).lower().count("document ") for message in messages)


def _int_or_none(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _float_or_none(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None

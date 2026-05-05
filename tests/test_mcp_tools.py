"""Tests for the three MCP tool functions, invoked directly as async fns."""

import asyncio

from inferguard.disagg.events import default_buffer
from inferguard.mcp_server import (
    tool_disagg_status,
    tool_path_trace,
    tool_recent_events,
)


def test_path_trace_returns_scaffold() -> None:
    result = asyncio.run(tool_path_trace(sample_size=5))
    assert result["schema_version"] == "path-trace/v1"
    assert result["engine_support"] == "aggregate_only"
    assert result["samples"] == []
    assert result["requested_sample_size"] == 5


def test_recent_events_returns_window() -> None:
    # Clear buffer first so test is deterministic in repeated runs.
    buf = default_buffer()
    # Drain without a public API — acceptable for internal test.
    with buf._lock:  # noqa: SLF001
        buf._deque.clear()  # noqa: SLF001

    result = asyncio.run(tool_recent_events(minutes=1))
    assert result["schema_version"] == "recent-events/v1"
    assert result["window_minutes"] == 1
    assert result["events"] == []


def test_disagg_status_unreachable_paths() -> None:
    # Point at a known-closed local port. Should return a structured status
    # without raising.
    result = asyncio.run(
        tool_disagg_status(
            prefill_url="http://127.0.0.1:1",
            decode_url="http://127.0.0.1:2",
        )
    )
    assert result["schema_version"] == "disagg-status/v1"
    codes = [f["code"] for f in result["findings"]]
    assert "endpoint_unreachable" in codes


def test_disagg_status_appends_to_recent_events_buffer() -> None:
    # Same unreachable flow; confirm the ring buffer records it.
    buf = default_buffer()
    with buf._lock:  # noqa: SLF001
        buf._deque.clear()  # noqa: SLF001
    asyncio.run(
        tool_disagg_status(
            prefill_url="http://127.0.0.1:1",
            decode_url="http://127.0.0.1:2",
        )
    )
    events = asyncio.run(tool_recent_events(minutes=60))
    codes = [e["code"] for e in events["events"]]
    assert "endpoint_unreachable" in codes

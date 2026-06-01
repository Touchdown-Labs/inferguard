"""Unit tests for the localized RLM engine."""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, patch

from rlm_agent.rlm_engine.environment import LocalRepl
from rlm_agent.rlm_engine.agent import LocalRlm
from rlm_agent.rlm_engine import tools


def test_calculate_kv_slope_regression() -> None:
    # Testing rising trend
    snapshots = [
        {"timestamp": 10.0, "kv_cache_usage": 0.40},
        {"timestamp": 12.0, "kv_cache_usage": 0.50},
        {"timestamp": 14.0, "kv_cache_usage": 0.60},
    ]
    slope = tools.calculate_kv_slope(snapshots)
    # y changes by 0.20 over 4 seconds, so 0.05 per second
    assert slope == 0.05


def test_calculate_kv_slope_empty_or_single() -> None:
    assert tools.calculate_kv_slope([]) == 0.0
    assert tools.calculate_kv_slope([{"timestamp": 10.0, "kv_cache_usage": 0.40}]) == 0.0


def test_match_prior_incident() -> None:
    match_kv = tools.match_prior_incident("kv_saturation")
    assert match_kv["id"] == "inc-042"
    assert match_kv["remediation_parameters"]["threshold_t"] == 1.0

    match_unknown = tools.match_prior_incident("non-existent")
    assert match_unknown["id"] == "inc-generic"


def test_slice_redis_logs() -> None:
    events = [
        {"event": "preempt_start"},
        {"event": "swapped_start"},
        {"event": "alert_fired"}
    ]
    assert tools.slice_redis_logs(events, 0, 2) == events[0:2]
    assert tools.slice_redis_logs(events, 1) == events[1:]


def test_local_repl_run_code() -> None:
    repl = LocalRepl()
    
    # Test simple print statement
    result = repl.run_code("print('Hello from RLM Sandbox')")
    assert "Hello from RLM Sandbox" in result

    # Test variable persistence
    repl.run_code("x = 10")
    result_var = repl.run_code("print(x * 5)")
    assert "50" in result_var


def test_local_repl_injected_globals() -> None:
    context = {
        "window_snapshots": [{"timestamp": 10.0, "kv_cache_usage": 0.40}],
        "event_log_tail": [{"event": "preempt_start"}]
    }
    repl = LocalRepl(context)
    
    result = repl.run_code("print(len(snapshots))")
    assert "1" in result

    result_tool = repl.run_code("print(match_prior_incident('kv_saturation')['id'])")
    assert "inc-042" in result_tool


@pytest.mark.anyio
async def test_local_rlm_simulated_fallback() -> None:
    context = {
        "current_snapshot": {"kv_cache_usage": 0.94}
    }
    # Using 'fake-api-key' forces simulated mode
    agent = LocalRlm(
        model="openai/gpt-oss-120b",
        api_base="https://fake",
        api_key="fake-api-key",
        context_dict=context
    )
    result = await agent.run("Run KV Cache check")
    
    assert "capacity_cliff_predicted" in result
    assert "W1 Trend" in result
    assert "W2 Match" in result

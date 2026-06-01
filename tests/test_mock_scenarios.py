"""Tests for deterministic mock endpoint demo scenarios."""

from __future__ import annotations

import json

import pytest
from aiohttp.test_utils import make_mocked_request

from demo.mock_endpoint import (
    ScenarioState,
    build_sglang_metrics,
    build_vllm_metrics,
    create_app,
    handle_health,
)
from inferguard.metrics import MetricSnapshot


def _snapshot(engine: str, scenario: str, elapsed_seconds: float) -> MetricSnapshot:
    state = ScenarioState(scenario=scenario, start_time=100.0)
    now = 100.0 + elapsed_seconds
    metrics_text = build_sglang_metrics(state, now=now) if engine == "sglang" else build_vllm_metrics(state, now=now)
    return MetricSnapshot.from_prometheus_text(metrics_text)


@pytest.mark.parametrize("engine", ["vllm", "sglang"])
def test_healthy_scenario_is_stable(engine: str) -> None:
    early = _snapshot(engine, "healthy", 0.0)
    late = _snapshot(engine, "healthy", 600.0)

    assert early.kv_cache_usage == pytest.approx(late.kv_cache_usage)
    assert early.requests_waiting == late.requests_waiting == 0
    assert early.preemptions_total == late.preemptions_total == 0


@pytest.mark.parametrize("engine", ["vllm", "sglang"])
def test_pressure_ramp_progressively_degrades(engine: str) -> None:
    early = _snapshot(engine, "pressure_ramp", 0.0)
    mid = _snapshot(engine, "pressure_ramp", 150.0)
    late = _snapshot(engine, "pressure_ramp", 300.0)

    assert early.kv_cache_usage < mid.kv_cache_usage < late.kv_cache_usage
    assert early.requests_waiting <= mid.requests_waiting <= late.requests_waiting
    assert early.preemptions_total <= mid.preemptions_total <= late.preemptions_total
    assert late.kv_cache_usage > 0.90
    assert late.requests_waiting >= 10
    assert late.preemptions_total > 0


@pytest.mark.parametrize("engine", ["vllm", "sglang"])
def test_incident_transitions_to_and_holds_critical_state(engine: str) -> None:
    healthy = _snapshot(engine, "incident", 30.0)
    incident = _snapshot(engine, "incident", 90.0)
    held = _snapshot(engine, "incident", 240.0)

    assert healthy.kv_cache_usage < 0.50
    assert incident.kv_cache_usage >= 0.92
    assert incident.requests_waiting >= 15
    assert incident.preemptions_total >= 8
    assert held.kv_cache_usage == pytest.approx(incident.kv_cache_usage)
    assert held.requests_waiting == incident.requests_waiting


@pytest.mark.parametrize("engine", ["vllm", "sglang"])
def test_recovery_moves_back_toward_healthy(engine: str) -> None:
    start = _snapshot(engine, "recovery", 0.0)
    mid = _snapshot(engine, "recovery", 120.0)
    late = _snapshot(engine, "recovery", 240.0)

    assert start.kv_cache_usage > mid.kv_cache_usage > late.kv_cache_usage
    assert start.requests_waiting > mid.requests_waiting >= late.requests_waiting
    assert start.prefix_cache_hit_rate < mid.prefix_cache_hit_rate < late.prefix_cache_hit_rate
    assert late.kv_cache_usage < 0.50
    assert late.requests_waiting == 0


@pytest.mark.asyncio
async def test_health_reports_mock_engine_and_scenario() -> None:
    app = create_app(engine="sglang", model_id="openai/gpt-oss-120b", scenario="incident")
    response = await handle_health(make_mocked_request("GET", "/health", app=app))
    payload = json.loads(response.body.decode("utf-8"))

    assert payload == {
        "status": "ok",
        "mock": True,
        "engine": "sglang",
        "scenario": "incident",
    }

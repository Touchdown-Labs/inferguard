"""Tests for the action executor."""

from __future__ import annotations

from unittest.mock import AsyncMock, Mock, patch

import pytest

from inferguard.config import InferGuardConfig
from inferguard.executor import ActionExecutor
from inferguard.safe_actions import SafeAction


def _config(**overrides: object) -> InferGuardConfig:
    defaults = dict(
        target_endpoint="http://fake:8000",
        actuation_mode="off",
        actuation_endpoint="",
        actuation_allowlist=(),
        actuation_verify_delay_seconds=0,
    )
    defaults.update(overrides)
    return InferGuardConfig(**defaults)


def _action(action_type: str = "throttle_concurrency") -> SafeAction:
    return SafeAction(
        id="a1",
        timestamp=0.0,
        action_type=action_type,
        reason="reason",
        parameters={"max_num_seqs_before": 16, "max_num_seqs_after": 8},
        incident_id="inc-1",
    )


def test_is_eligible() -> None:
    executor = ActionExecutor(_config(actuation_mode="dry_run", actuation_allowlist=("throttle_concurrency",)))
    assert executor.is_eligible(_action()) is True
    assert executor.is_eligible(_action("drain_and_recycle")) is False


@pytest.mark.asyncio
async def test_execute_dry_run() -> None:
    executor = ActionExecutor(_config(actuation_mode="dry_run", actuation_allowlist=("throttle_concurrency",)))
    action = await executor.execute(_action())
    assert action.attempted is True
    assert action.applied is False
    assert action.execution_error == "dry_run"


@pytest.mark.asyncio
async def test_execute_live_success() -> None:
    executor = ActionExecutor(
        _config(
            actuation_mode="live",
            actuation_endpoint="http://fake/actuate",
            actuation_allowlist=("throttle_concurrency",),
        )
    )
    with patch("inferguard.executor.httpx.AsyncClient") as mock_client:
        instance = mock_client.return_value.__aenter__.return_value
        response = Mock()
        response.json.return_value = {"accepted": True}
        response.raise_for_status = Mock()
        instance.post = AsyncMock(return_value=response)
        action = await executor.execute(_action())
    assert action.applied is True
    assert action.execution_error == ""


@pytest.mark.asyncio
async def test_verify_improved() -> None:
    executor = ActionExecutor(_config(actuation_mode="dry_run", actuation_allowlist=("throttle_concurrency",)))
    baseline = type("S", (), {"kv_cache_usage": 0.95, "requests_running": 20})()
    current = type("S", (), {"kv_cache_usage": 0.80, "requests_running": 10, "error": None})()
    action = await executor.verify(_action(), AsyncMock(return_value=current), baseline_snapshot=baseline)
    assert action.verified is True
    assert action.verification_result == "improved"

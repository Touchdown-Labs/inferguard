"""Tests for the standalone agent loop."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from inferguard.agent import InferGuardAgent
from inferguard.config import DEFAULT_DIAGNOSIS_MODEL, DEFAULT_GMI_BASE_URL, InferGuardConfig
from inferguard.metrics import MetricSnapshot


def _make_config(**overrides: object) -> InferGuardConfig:
    defaults = dict(
        target_endpoint="http://fake:8000",
        redis_url="",
        redis_token="",
        vector_url="",
        vector_token="",
        llm_base_url=DEFAULT_GMI_BASE_URL,
        llm_api_key="",
        llm_model=DEFAULT_DIAGNOSIS_MODEL,
        kv_alert_threshold=0.85,
        ttft_alert_multiplier=2.0,
        poll_interval_seconds=1,
        replay_export_file="",
        replay_max_concurrency=4,
        replay_max_sessions=0,
        replay_runtime_stack_id="",
        replay_skip_tokenizer=True,
        actuation_mode="off",
        actuation_endpoint="",
        actuation_allowlist=(),
        actuation_verify_delay_seconds=0,
    )
    defaults.update(overrides)
    return InferGuardConfig(**defaults)


class _DummyResponse:
    def __init__(self, status_code: int = 200, payload: Any = None):
        self.status_code = status_code
        self._payload = payload if payload is not None else {}

    def json(self) -> Any:
        return self._payload


class _DummyAsyncClient:
    def __init__(self, response: _DummyResponse | None = None, error: Exception | None = None):
        self._response = response
        self._error = error

    async def __aenter__(self) -> "_DummyAsyncClient":
        return self

    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
        return None

    async def get(self, _: str) -> _DummyResponse:
        if self._error is not None:
            raise self._error
        assert self._response is not None
        return self._response


@pytest.mark.asyncio
async def test_healthy_endpoint() -> None:
    agent = InferGuardAgent(_make_config(), model_name="openai/gpt-oss-120b")
    snapshot = MetricSnapshot(
        timestamp=0,
        engine="vllm",
        kv_cache_usage=0.50,
        prefix_cache_hit_rate=0.80,
        requests_running=3,
        preemptions_total=0,
    )

    with patch("inferguard.agent.MetricSnapshot.scrape_endpoint", new=AsyncMock(return_value=snapshot)):
        report = await agent.run_once()
        await agent.shutdown()

    assert report["status"] == "healthy"
    assert report["metrics"]["kv_cache_usage"] == 0.50
    assert report["proof_level"] == "unknown"


@pytest.mark.asyncio
async def test_kv_anomaly_no_llm() -> None:
    agent = InferGuardAgent(_make_config(), model_name="openai/gpt-oss-120b")
    snapshot = MetricSnapshot(
        timestamp=0,
        engine="vllm",
        kv_cache_usage=0.93,
        prefix_cache_hit_rate=0.10,
        requests_running=50,
        requests_waiting=15,
        preemptions_total=5,
    )

    with patch("inferguard.agent.MetricSnapshot.scrape_endpoint", new=AsyncMock(return_value=snapshot)):
        report = await agent.run_once()
        await agent.shutdown()

    assert report["status"] == "anomaly_detected"
    assert report["diagnosis"]["failure_mode"] == "kv_saturation"
    assert report["remediation"]["config_diff"]["--kv-cache-dtype"] == "fp8_e4m3"
    assert report["proof_level"] == "unknown"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("client", "expected"),
    [
        (_DummyAsyncClient(response=_DummyResponse(payload={"mock": True})), "mock"),
        (_DummyAsyncClient(response=_DummyResponse(payload={"mock": False})), "live"),
        (_DummyAsyncClient(response=_DummyResponse(status_code=404, payload={})), "unknown"),
        (_DummyAsyncClient(error=RuntimeError("boom")), "unknown"),
    ],
)
async def test_detect_proof_level(client: _DummyAsyncClient, expected: str) -> None:
    agent = InferGuardAgent(_make_config(), model_name="openai/gpt-oss-120b")

    with patch("inferguard.agent.httpx.AsyncClient", return_value=client):
        proof_level = await agent._detect_proof_level()

    assert proof_level == expected


def test_config_from_env_reads_gmi_env_first(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TARGET_ENDPOINT", "http://fake:8000")
    monkeypatch.setenv("GMI_API_KEY", "gmi-primary")
    monkeypatch.setenv("GMI_BASE_URL", "https://api.gmi-serving.com/v1")
    monkeypatch.setenv("GMI_MODEL", "openai/gpt-oss-120b")

    config = InferGuardConfig.from_env()

    assert config.llm_api_key == "gmi-primary"
    assert config.llm_base_url == "https://api.gmi-serving.com/v1"
    assert config.llm_model == "openai/gpt-oss-120b"
    assert config.has_llm is True


def test_config_from_env_reads_llm_compatibility_aliases(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TARGET_ENDPOINT", "http://fake:8000")
    monkeypatch.delenv("GMI_API_KEY", raising=False)
    monkeypatch.delenv("GMI_BASE_URL", raising=False)
    monkeypatch.delenv("GMI_MODEL", raising=False)
    monkeypatch.setenv("LLM_API_KEY", "legacy-key")
    monkeypatch.setenv("LLM_BASE_URL", "https://compat.example/v1")
    monkeypatch.setenv("LLM_MODEL", "legacy-model")

    config = InferGuardConfig.from_env()

    assert config.llm_api_key == "legacy-key"
    assert config.llm_base_url == "https://compat.example/v1"
    assert config.llm_model == "legacy-model"


def test_config_from_env_uses_gmi_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TARGET_ENDPOINT", "http://fake:8000")
    monkeypatch.delenv("GMI_API_KEY", raising=False)
    monkeypatch.delenv("GMI_BASE_URL", raising=False)
    monkeypatch.delenv("GMI_MODEL", raising=False)
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.delenv("LLM_BASE_URL", raising=False)
    monkeypatch.delenv("LLM_MODEL", raising=False)

    config = InferGuardConfig.from_env()

    assert config.llm_api_key == ""
    assert config.llm_base_url == DEFAULT_GMI_BASE_URL
    assert config.llm_model == DEFAULT_DIAGNOSIS_MODEL
    assert config.has_llm is False


def test_config_from_env_prefers_gmi_over_llm_aliases(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TARGET_ENDPOINT", "http://fake:8000")
    monkeypatch.setenv("GMI_API_KEY", "gmi-wins")
    monkeypatch.setenv("GMI_BASE_URL", "https://api.gmi-serving.com/v1")
    monkeypatch.setenv("GMI_MODEL", "openai/gpt-oss-120b")
    monkeypatch.setenv("LLM_API_KEY", "legacy-loses")
    monkeypatch.setenv("LLM_BASE_URL", "https://legacy.example/v1")
    monkeypatch.setenv("LLM_MODEL", "legacy-model")

    config = InferGuardConfig.from_env()

    assert config.llm_api_key == "gmi-wins"
    assert config.llm_base_url == "https://api.gmi-serving.com/v1"
    assert config.llm_model == "openai/gpt-oss-120b"


def test_config_from_env_reads_replay_fields(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TARGET_ENDPOINT", "http://fake:8000")
    monkeypatch.setenv("INFERGUARD_REPLAY_EXPORT_FILE", "/tmp/replay.json")
    monkeypatch.setenv("INFERGUARD_REPLAY_MAX_CONCURRENCY", "7")
    monkeypatch.setenv("INFERGUARD_REPLAY_MAX_SESSIONS", "3")
    monkeypatch.setenv("INFERGUARD_REPLAY_RUNTIME_STACK_ID", "standalone:vllm")
    monkeypatch.setenv("INFERGUARD_REPLAY_SKIP_TOKENIZER", "false")

    config = InferGuardConfig.from_env()

    assert config.replay_export_file == "/tmp/replay.json"
    assert config.replay_max_concurrency == 7
    assert config.replay_max_sessions == 3
    assert config.replay_runtime_stack_id == "standalone:vllm"
    assert config.replay_skip_tokenizer is False
    assert config.has_replay is True


def test_has_replay_property() -> None:
    assert _make_config().has_replay is False
    assert _make_config(replay_export_file="/tmp/replay.json").has_replay is True


def test_has_actuation_property() -> None:
    assert _make_config().has_actuation is False
    assert _make_config(actuation_mode="dry_run", actuation_allowlist=("throttle_concurrency",)).has_actuation is True


@pytest.mark.asyncio
@pytest.mark.parametrize("proof_level", ["mock", "live", "unknown"])
async def test_run_once_surfaces_and_caches_proof_level(proof_level: str) -> None:
    agent = InferGuardAgent(_make_config(), model_name="openai/gpt-oss-120b")
    snapshot = MetricSnapshot(
        timestamp=0,
        engine="vllm",
        kv_cache_usage=0.50,
        prefix_cache_hit_rate=0.80,
        requests_running=3,
        preemptions_total=0,
    )
    detect_mock = AsyncMock(return_value=proof_level)

    with (
        patch("inferguard.agent.MetricSnapshot.scrape_endpoint", new=AsyncMock(return_value=snapshot)),
        patch.object(agent, "_detect_proof_level", detect_mock),
    ):
        first_report = await agent.run_once()
        second_report = await agent.run_once()

    await agent.shutdown()

    assert first_report["proof_level"] == proof_level
    assert second_report["proof_level"] == proof_level
    assert detect_mock.await_count == 1


@pytest.mark.asyncio
async def test_agent_includes_replay_validation_when_configured() -> None:
    agent = InferGuardAgent(
        _make_config(replay_export_file="/tmp/replay.json"),
        model_name="openai/gpt-oss-120b",
    )
    snapshot = MetricSnapshot(
        timestamp=0,
        engine="vllm",
        kv_cache_usage=0.93,
        prefix_cache_hit_rate=0.10,
        requests_running=50,
        requests_waiting=15,
        preemptions_total=5,
    )

    with (
        patch("inferguard.agent.MetricSnapshot.scrape_endpoint", new=AsyncMock(return_value=snapshot)),
        patch.object(agent, "_replay_validate", AsyncMock(return_value={"verdict": "improved", "improvements": ["throughput_improved"], "regressions": [], "cache_usage_delta": -0.1})),
    ):
        report = await agent.run_once()
        await agent.shutdown()

    assert report["status"] == "anomaly_detected"
    assert report["replay_validation"]["verdict"] == "improved"


@pytest.mark.asyncio
async def test_agent_dry_run_attempts_safe_action() -> None:
    agent = InferGuardAgent(
        _make_config(
            actuation_mode="dry_run",
            actuation_allowlist=("throttle_concurrency",),
            actuation_verify_delay_seconds=0,
        ),
        model_name="openai/gpt-oss-120b",
    )
    snapshot = MetricSnapshot(
        timestamp=0,
        engine="vllm",
        kv_cache_usage=0.93,
        prefix_cache_hit_rate=0.10,
        requests_running=50,
        requests_waiting=15,
        preemptions_total=5,
    )

    with patch("inferguard.agent.MetricSnapshot.scrape_endpoint", new=AsyncMock(return_value=snapshot)):
        report = await agent.run_once()
        await agent.shutdown()

    throttle = next(action for action in report["safe_actions"] if action["action_type"] == "throttle_concurrency")
    assert throttle["attempted"] is True
    assert throttle["applied"] is False
    assert throttle["execution_error"] == "dry_run"

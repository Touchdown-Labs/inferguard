"""Aiohttp mock SGLang server for launch-engine healthcheck tests."""

from __future__ import annotations

from tests.fixtures.mock_vllm_server import MockServerHandle, start_mock_servers


def start_mock_sglang_server(port: int = 0, *, no_metrics: bool = False) -> MockServerHandle:
    return start_mock_servers(
        "h100",
        port=port,
        model_id="mock-sglang",
        metrics_status_code=404 if no_metrics else 200,
    )


__all__ = ["start_mock_sglang_server"]

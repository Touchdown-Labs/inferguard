"""Tests for the ``inferguard profile live`` MVP."""

from __future__ import annotations

import asyncio
import json
import socket
import threading
import time
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

import pytest
from aiohttp import web
from typer.testing import CliRunner

from inferguard.cli import app


def _pick_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@dataclass(frozen=True)
class MetricFrame:
    kv: float = 0.20
    running: int = 1
    waiting: int = 0
    preemptions: int = 0
    prefix_hits: int = 0
    prefix_queries: int = 0
    offload_bytes: int = 0
    offload_time: float = 0.0


class _MetricsServer(threading.Thread):
    def __init__(self, frames: Sequence[MetricFrame]) -> None:
        super().__init__(daemon=True)
        self.frames = list(frames)
        self.port = _pick_port()
        self.chat_calls = 0
        self.metrics_calls = 0
        self._ready = threading.Event()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._runner: web.AppRunner | None = None

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    def run(self) -> None:
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        app_instance = web.Application()
        app_instance.router.add_get("/metrics", self._metrics)
        app_instance.router.add_post("/v1/chat/completions", self._chat)
        self._runner = web.AppRunner(app_instance)
        self._loop.run_until_complete(self._runner.setup())
        site = web.TCPSite(self._runner, "127.0.0.1", self.port)
        self._loop.run_until_complete(site.start())
        self._ready.set()
        self._loop.run_forever()

    def stop(self) -> None:
        assert self._loop is not None
        assert self._runner is not None

        async def _cleanup() -> None:
            await self._runner.cleanup()

        future = asyncio.run_coroutine_threadsafe(_cleanup(), self._loop)
        future.result(timeout=5)
        self._loop.call_soon_threadsafe(self._loop.stop)

    def wait_ready(self, timeout: float = 5.0) -> None:
        if not self._ready.wait(timeout=timeout):
            raise RuntimeError("metrics server did not become ready")
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                with socket.create_connection(("127.0.0.1", self.port), timeout=0.2):
                    return
            except OSError:
                time.sleep(0.02)
        raise RuntimeError("metrics server socket not accepting")

    async def _metrics(self, _request: web.Request) -> web.Response:
        index = min(self.metrics_calls, len(self.frames) - 1)
        self.metrics_calls += 1
        frame = self.frames[index]
        return web.Response(text=_metrics_text(frame), content_type="text/plain")

    async def _chat(self, _request: web.Request) -> web.Response:
        self.chat_calls += 1
        return web.json_response({"error": "profile should not generate traffic"}, status=500)


@pytest.fixture
def profile_server(request: pytest.FixtureRequest):
    server = _MetricsServer(request.param)
    server.start()
    server.wait_ready()
    try:
        yield server
    finally:
        server.stop()


def test_profile_help_lists_live_command() -> None:
    result = CliRunner().invoke(app, ["profile", "--help"])
    assert result.exit_code == 0
    assert "live" in result.stdout


@pytest.mark.parametrize(
    "profile_server",
    [
        [
            MetricFrame(
                kv=0.91, running=1, waiting=3, preemptions=0, prefix_hits=0, prefix_queries=100
            ),
            MetricFrame(
                kv=0.96,
                running=1,
                waiting=4,
                preemptions=2,
                prefix_hits=10,
                prefix_queries=220,
                offload_bytes=4096,
                offload_time=0.25,
            ),
        ]
    ],
    indirect=True,
)
def test_profile_live_streams_findings_and_writes_artifacts(profile_server, tmp_path: Path) -> None:
    output_dir = tmp_path / "profile"
    result = CliRunner().invoke(
        app,
        [
            "profile",
            "live",
            "--endpoint",
            f"{profile_server.base_url}/metrics",
            "--duration",
            "0.12",
            "--interval",
            "0.02",
            "--engine",
            "auto",
            "--output-dir",
            str(output_dir),
            "--format",
            "json",
        ],
    )
    assert result.exit_code == 2
    assert profile_server.chat_calls == 0
    assert "profile_preemptions_rising" in result.stdout

    rows = [json.loads(line) for line in (output_dir / "profile.jsonl").read_text().splitlines()]
    assert len(rows) >= 2
    assert rows[0]["schema_version"] == "inferguard-profile-sample/v1"
    assert rows[-1]["snapshot"]["endpoint"]["engine"] == "vllm"
    assert any(row["deltas"].get("preemptions_total_delta") == 2 for row in rows)

    summary = json.loads((output_dir / "profile_summary.json").read_text())
    assert summary["schema_version"] == "inferguard-profile-summary/v1"
    assert summary["highest_kv_cache_usage"] >= 0.96
    codes = {finding["code"] for finding in summary["findings"]}
    assert "profile_kv_cache_critical" in codes
    assert "profile_preemptions_rising" in codes
    assert (output_dir / "profile.md").exists()


@pytest.mark.parametrize(
    "profile_server",
    [[MetricFrame(kv=0.30, running=1, waiting=0), MetricFrame(kv=0.31, running=1, waiting=0)]],
    indirect=True,
)
def test_profile_live_happy_path_has_no_findings(profile_server, tmp_path: Path) -> None:
    output_dir = tmp_path / "healthy"
    result = CliRunner().invoke(
        app,
        [
            "profile",
            "live",
            "--endpoint",
            profile_server.base_url,
            "--duration",
            "0.08",
            "--interval",
            "0.02",
            "--output-dir",
            str(output_dir),
        ],
    )
    assert result.exit_code == 0
    summary = json.loads((output_dir / "profile_summary.json").read_text())
    assert summary["findings"] == []
    assert "Wrote InferGuard profile artifacts" in result.stdout


def test_profile_live_unreachable_endpoint(tmp_path: Path) -> None:
    output_dir = tmp_path / "unreachable"
    result = CliRunner().invoke(
        app,
        [
            "profile",
            "live",
            "--endpoint",
            "http://127.0.0.1:1",
            "--duration",
            "0.01",
            "--interval",
            "0.01",
            "--timeout",
            "0.1",
            "--output-dir",
            str(output_dir),
        ],
    )
    assert result.exit_code == 2
    summary = json.loads((output_dir / "profile_summary.json").read_text())
    codes = {finding["code"] for finding in summary["findings"]}
    assert "profile_metrics_unavailable" in codes


def _metrics_text(frame: MetricFrame) -> str:
    lines = [
        "# HELP vllm:gpu_cache_usage_perc Mock GPU KV cache usage.",
        "# TYPE vllm:gpu_cache_usage_perc gauge",
        f"vllm:gpu_cache_usage_perc {frame.kv}",
        f"vllm:num_requests_running {frame.running}",
        f"vllm:num_requests_waiting {frame.waiting}",
        "vllm:num_requests_swapped 0",
        f"vllm:num_preemptions_total {frame.preemptions}",
        f"vllm:prefix_cache_hits_total {frame.prefix_hits}",
        f"vllm:prefix_cache_queries_total {frame.prefix_queries}",
        f"vllm:kv_offload_bytes_gpu_to_cpu {frame.offload_bytes}",
        "vllm:kv_offload_bytes_cpu_to_gpu 0",
        f"vllm:kv_offload_time_gpu_to_cpu {frame.offload_time}",
        "vllm:kv_offload_time_cpu_to_gpu 0",
    ]
    return "\n".join(lines)

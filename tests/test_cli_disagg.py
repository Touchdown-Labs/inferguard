"""End-to-end CLI test using the offline mock endpoint."""

import asyncio
import json
import socket
import threading
import time

import pytest
from aiohttp import web
from typer.testing import CliRunner

from demo.mock_endpoint import make_app  # noqa: E402 — project-root module added by conftest
from inferguard.cli import app


def _pick_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class _ServerThread(threading.Thread):
    def __init__(self, *, engine: str, scenario: str, connector: str, port: int) -> None:
        super().__init__(daemon=True)
        self.port = port
        self._engine = engine
        self._scenario = scenario
        self._connector = connector
        self._ready = threading.Event()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._runner: web.AppRunner | None = None

    def run(self) -> None:
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        app_instance = make_app(
            engine=self._engine, scenario=self._scenario, connector=self._connector
        )
        runner = web.AppRunner(app_instance)
        self._runner = runner
        self._loop.run_until_complete(runner.setup())
        site = web.TCPSite(runner, "127.0.0.1", self.port)
        self._loop.run_until_complete(site.start())
        self._ready.set()
        self._loop.run_forever()

    def stop(self) -> None:
        assert self._loop is not None
        assert self._runner is not None

        async def _cleanup() -> None:
            await self._runner.cleanup()

        fut = asyncio.run_coroutine_threadsafe(_cleanup(), self._loop)
        try:
            fut.result(timeout=5)
        except Exception:
            pass
        self._loop.call_soon_threadsafe(self._loop.stop)

    def wait_ready(self, timeout: float = 5.0) -> None:
        if not self._ready.wait(timeout=timeout):
            raise RuntimeError("mock server did not become ready")
        # Wait for actual socket to accept.
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                with socket.create_connection(("127.0.0.1", self.port), timeout=0.5):
                    return
            except OSError:
                time.sleep(0.05)
        raise RuntimeError("mock server socket not accepting")


@pytest.fixture
def mock_pair():
    prefill = _ServerThread(
        engine="vllm", scenario="prefill_pressure", connector="nixl", port=_pick_port()
    )
    decode = _ServerThread(
        engine="vllm", scenario="decode_pressure", connector="nixl", port=_pick_port()
    )
    prefill.start()
    decode.start()
    prefill.wait_ready()
    decode.wait_ready()
    try:
        yield prefill, decode
    finally:
        prefill.stop()
        decode.stop()


def test_cli_status_returns_json(mock_pair) -> None:
    prefill, decode = mock_pair
    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "disagg",
            "status",
            "--prefill",
            f"http://127.0.0.1:{prefill.port}",
            "--decode",
            f"http://127.0.0.1:{decode.port}",
            "--json",
        ],
    )
    # Exit code is nonzero because prefill_pressure + decode_pressure
    # scenarios trigger the imbalance rule. That's expected.
    payload = json.loads(result.stdout)
    assert payload["schema_version"] == "disagg-status/v1"
    assert payload["prefill"]["endpoint"]["engine"] == "vllm"
    assert payload["decode"]["endpoint"]["engine"] == "vllm"
    assert isinstance(payload["findings"], list)


def test_cli_status_table_mode(mock_pair) -> None:
    prefill, decode = mock_pair
    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "disagg",
            "status",
            "--prefill",
            f"http://127.0.0.1:{prefill.port}",
            "--decode",
            f"http://127.0.0.1:{decode.port}",
        ],
    )
    # Table mode prints "role", "engine", etc. in the header.
    assert "role" in result.stdout
    assert "engine" in result.stdout


def test_cli_status_unreachable_exits_nonzero() -> None:
    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "disagg",
            "status",
            "--prefill",
            "http://127.0.0.1:1",  # almost certainly not listening
            "--decode",
            "http://127.0.0.1:2",
            "--json",
            "--timeout",
            "0.2",
        ],
    )
    assert result.exit_code == 2
    payload = json.loads(result.stdout)
    codes = [f["code"] for f in payload["findings"]]
    assert "endpoint_unreachable" in codes


def test_cli_version() -> None:
    runner = CliRunner()
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert "inferguard" in result.stdout.lower()


def test_cli_help() -> None:
    runner = CliRunner()
    result = runner.invoke(app, ["disagg", "status", "--help"])
    assert result.exit_code == 0
    assert "--prefill" in result.stdout
    assert "--decode" in result.stdout

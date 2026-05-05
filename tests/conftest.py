"""Shared test configuration and outbound-network guard."""

from __future__ import annotations

import ipaddress
import os
import shlex
import socket
import subprocess
import sys
import urllib.request
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import httpx
import pytest

_ROOT = Path(__file__).resolve().parents[1]
_SRC = _ROOT / "src"
for _path in (str(_SRC), str(_ROOT)):
    if _path not in sys.path:
        sys.path.insert(0, _path)

_LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1", "test"}
_OUTBOUND_SUBPROCESS_TOOLS = {"curl", "wget", "http", "grpc-cli"}
_ALLOW_OUTBOUND_NETWORK = False


class OutboundCallBlocked(AssertionError):
    """Raised when a test attempts outbound network access without opt-in."""


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line("markers", "harness: tests for the v0.5 harness layer")
    config.addinivalue_line("markers", "allow_network: permit non-loopback HTTP for this test")
    config.addinivalue_line(
        "markers", "allow_outbound_network: permit outbound network for this test"
    )
    config.addinivalue_line("markers", "integration: integration tests")


@pytest.fixture(autouse=True)
def block_outbound_network(monkeypatch: pytest.MonkeyPatch, request: pytest.FixtureRequest):
    """Fail any outbound network call unless a test explicitly opts in.

    Mock transports and localhost integration fixtures remain allowed; real outbound
    network calls to the internet are blocked across the entire test suite.
    """

    global _ALLOW_OUTBOUND_NETWORK
    marker_allows_network = (
        request.node.get_closest_marker("allow_network") is not None
        or request.node.get_closest_marker("allow_outbound_network") is not None
    )
    _ALLOW_OUTBOUND_NETWORK = marker_allows_network

    original_async_send = httpx.AsyncClient.send
    original_sync_send = httpx.Client.send
    original_urlopen = urllib.request.urlopen
    original_create_connection = socket.create_connection
    original_socket_connect = socket.socket.connect
    original_run = subprocess.run
    original_popen_init = subprocess.Popen.__init__

    def allowed_for_httpx(client: Any, url: Any) -> bool:
        if _network_allowed():
            return True
        transport = getattr(client, "_transport", None)
        if transport is not None and transport.__class__.__name__ == "MockTransport":
            return True
        host = urlsplit(str(url)).hostname
        return _is_loopback_host(host)

    async def guarded_async_send(
        self: httpx.AsyncClient, request: httpx.Request, *args: Any, **kwargs: Any
    ):
        if not allowed_for_httpx(self, request.url):
            raise OutboundCallBlocked(f"unmocked outbound HTTP blocked: {request.url}")
        return await original_async_send(self, request, *args, **kwargs)

    def guarded_sync_send(self: httpx.Client, request: httpx.Request, *args: Any, **kwargs: Any):
        if not allowed_for_httpx(self, request.url):
            raise OutboundCallBlocked(f"unmocked outbound HTTP blocked: {request.url}")
        return original_sync_send(self, request, *args, **kwargs)

    monkeypatch.setattr(httpx.AsyncClient, "send", guarded_async_send)
    monkeypatch.setattr(httpx.Client, "send", guarded_sync_send)

    try:
        import requests
    except ImportError:
        requests = None

    if requests is not None:
        original_requests_request = requests.Session.request

        def guarded_requests_request(
            self: requests.Session, method: str, url: str, *args: Any, **kwargs: Any
        ):
            _raise_if_blocked_url(url, "requests")
            return original_requests_request(self, method, url, *args, **kwargs)

        monkeypatch.setattr(requests.Session, "request", guarded_requests_request)

    try:
        import aiohttp
    except ImportError:
        aiohttp = None

    if aiohttp is not None:
        original_aiohttp_request = aiohttp.ClientSession._request

        async def guarded_aiohttp_request(
            self: aiohttp.ClientSession, method: str, str_or_url: Any, *args: Any, **kwargs: Any
        ):
            _raise_if_blocked_url(str_or_url, "aiohttp")
            return await original_aiohttp_request(self, method, str_or_url, *args, **kwargs)

        monkeypatch.setattr(aiohttp.ClientSession, "_request", guarded_aiohttp_request)

    def guarded_urlopen(url: Any, *args: Any, **kwargs: Any):
        target = getattr(url, "full_url", url)
        _raise_if_blocked_url(target, "urllib")
        return original_urlopen(url, *args, **kwargs)

    monkeypatch.setattr(urllib.request, "urlopen", guarded_urlopen)

    try:
        import urllib3
    except ImportError:
        urllib3 = None

    if urllib3 is not None:
        original_urllib3_request = urllib3.PoolManager.request

        def guarded_urllib3_request(
            self: urllib3.PoolManager, method: str, url: str, *args: Any, **kwargs: Any
        ):
            _raise_if_blocked_url(url, "urllib3")
            return original_urllib3_request(self, method, url, *args, **kwargs)

        monkeypatch.setattr(urllib3.PoolManager, "request", guarded_urllib3_request)

    def guarded_create_connection(address: Any, *args: Any, **kwargs: Any):
        _raise_if_blocked_socket_address(address, "socket.create_connection")
        return original_create_connection(address, *args, **kwargs)

    def guarded_socket_connect(self: socket.socket, address: Any):
        _raise_if_blocked_socket_address(address, "socket.socket.connect")
        return original_socket_connect(self, address)

    monkeypatch.setattr(socket, "create_connection", guarded_create_connection)
    monkeypatch.setattr(socket.socket, "connect", guarded_socket_connect)

    def guarded_run(args: Any, *posargs: Any, **kwargs: Any):
        _raise_if_blocked_subprocess(args)
        return original_run(args, *posargs, **kwargs)

    def guarded_popen_init(self: subprocess.Popen, args: Any, *posargs: Any, **kwargs: Any):
        _raise_if_blocked_subprocess(args)
        return original_popen_init(self, args, *posargs, **kwargs)

    monkeypatch.setattr(subprocess, "run", guarded_run)
    monkeypatch.setattr(subprocess.Popen, "__init__", guarded_popen_init)

    try:
        yield
    finally:
        _ALLOW_OUTBOUND_NETWORK = False


@pytest.fixture
def allow_outbound_network(monkeypatch: pytest.MonkeyPatch) -> bool:
    """Opt a test into real outbound network access at call time."""

    monkeypatch.setattr(sys.modules[__name__], "_ALLOW_OUTBOUND_NETWORK", True)
    return True


def _network_allowed() -> bool:
    return _ALLOW_OUTBOUND_NETWORK


def _raise_if_blocked_url(url: Any, source: str) -> None:
    if _network_allowed():
        return
    host = urlsplit(str(url)).hostname
    if not _is_loopback_host(host):
        raise OutboundCallBlocked(f"{source} outbound blocked: {url}")


def _raise_if_blocked_socket_address(address: Any, source: str) -> None:
    if _network_allowed():
        return
    if not isinstance(address, tuple) or not address:
        return
    host = str(address[0])
    port = address[1] if len(address) > 1 else "unknown"
    if not _is_loopback_host(host):
        raise OutboundCallBlocked(f"{source} to {host}:{port}")


def _raise_if_blocked_subprocess(args: Any) -> None:
    if _network_allowed():
        return
    argv = _normalize_subprocess_args(args)
    if not argv:
        return
    executable = os.path.basename(argv[0])
    if executable not in _OUTBOUND_SUBPROCESS_TOOLS:
        return
    targets = _subprocess_network_targets(argv[1:])
    if targets and all(_is_loopback_host(target) for target in targets):
        return
    raise OutboundCallBlocked(f"subprocess outbound: {executable}")


def _normalize_subprocess_args(args: Any) -> list[str]:
    if isinstance(args, str):
        return shlex.split(args)
    if isinstance(args, os.PathLike):
        return [os.fspath(args)]
    if isinstance(args, (list, tuple)):
        return [os.fspath(item) if isinstance(item, os.PathLike) else str(item) for item in args]
    return []


def _subprocess_network_targets(argv: list[str]) -> list[str]:
    targets: list[str] = []
    for token in argv:
        if token.startswith("-"):
            continue
        parsed = urlsplit(token)
        host = parsed.hostname
        if host:
            targets.append(host)
            continue
        if token in _LOOPBACK_HOSTS or _looks_like_host(token):
            targets.append(token)
    return targets


def _looks_like_host(token: str) -> bool:
    if "/" in token:
        return False
    try:
        ipaddress.ip_address(token.strip("[]"))
        return True
    except ValueError:
        return ("." in token or ":" in token) and any(char.isalpha() for char in token)


def _is_loopback_host(host: str | None) -> bool:
    if host is None:
        return False
    normalized = host.strip("[]").lower()
    if normalized in _LOOPBACK_HOSTS:
        return True
    try:
        return ipaddress.ip_address(normalized).is_loopback
    except ValueError:
        return False

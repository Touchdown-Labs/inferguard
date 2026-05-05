"""Long-running InferGuard harness sidecar primitives."""

from __future__ import annotations

import threading
import time
from collections import Counter, deque
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from statistics import median
from typing import Any

from inferguard.harness.permissions import PermissionPolicy
from inferguard.io import atomic_write_json
from inferguard.schemas.agent_trace import iter_agent_trace_jsonl

DEFAULT_DAEMON_HOST = "127.0.0.1"
DEFAULT_DAEMON_PORT = 9466
LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1"}


@dataclass(frozen=True)
class DaemonSnapshot:
    window_seconds: float
    events_total: int
    model_calls: int
    tool_calls: int
    ttft_p50_ms: float
    ttft_p99_ms: float
    tool_stall_total_seconds: float
    tool_stall_pct: float
    node_counts: dict[str, int]
    kv_by_customer: dict[str, dict[str, float]] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "window_seconds": self.window_seconds,
            "events_total": self.events_total,
            "model_calls": self.model_calls,
            "tool_calls": self.tool_calls,
            "ttft_p50_ms": self.ttft_p50_ms,
            "ttft_p99_ms": self.ttft_p99_ms,
            "tool_stall_total_seconds": self.tool_stall_total_seconds,
            "tool_stall_pct": self.tool_stall_pct,
            "node_counts": dict(self.node_counts),
            "kv_by_customer": {
                customer: dict(values) for customer, values in self.kv_by_customer.items()
            },
        }


@dataclass
class SlidingWindow:
    window_seconds: float = 300.0
    events: deque[tuple[float, dict[str, Any]]] = field(default_factory=deque)

    def append(self, event: dict[str, Any], *, observed_at: float | None = None) -> None:
        now = time.time() if observed_at is None else observed_at
        self.events.append((now, event))
        self.prune(now=now)

    def prune(self, *, now: float | None = None) -> None:
        current = time.time() if now is None else now
        cutoff = current - self.window_seconds
        while self.events and self.events[0][0] < cutoff:
            self.events.popleft()

    def values(self) -> list[dict[str, Any]]:
        self.prune()
        return [event for _, event in self.events]


class Daemon:
    """In-process daemon core with a Prometheus-compatible loopback endpoint."""

    def __init__(
        self,
        *,
        window_seconds: float = 300.0,
        permission_policy: PermissionPolicy | None = None,
    ) -> None:
        self.window = SlidingWindow(window_seconds=window_seconds)
        self.permission_policy = permission_policy or PermissionPolicy()
        self._lock = threading.Lock()
        self._server: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None

    def record_event(self, event: dict[str, Any], *, observed_at: float | None = None) -> None:
        with self._lock:
            self.window.append(event, observed_at=observed_at)

    def record_agent_trace_file(self, path: Path | str) -> int:
        self.permission_policy.check_filesystem(path).raise_if_denied()
        count = 0
        for event in iter_agent_trace_jsonl(path):
            self.record_event(event.as_dict())
            count += 1
        return count

    def record_bench_summary(self, summary: dict[str, Any]) -> None:
        self.record_event({"event_type": "bench-summary", "summary": dict(summary)})

    def watch_directory_once(self, directory: Path | str, *, pattern: str = "*.jsonl") -> int:
        root = Path(directory)
        self.permission_policy.check_filesystem(root).raise_if_denied()
        count = 0
        for path in sorted(root.glob(pattern)):
            try:
                count += self.record_agent_trace_file(path)
            except ValueError:
                continue
        return count

    def snapshot(self) -> DaemonSnapshot:
        with self._lock:
            events = self.window.values()
        node_counts: Counter[str] = Counter()
        ttfts: list[float] = []
        stall_seconds = 0.0
        wall_seconds = 0.0
        model_calls = 0
        tool_calls = 0
        kv_by_customer: dict[str, Counter[str]] = {}
        for event in events:
            if event.get("event_type") != "node":
                continue
            kind = str(event.get("kind"))
            node_counts[kind] += 1
            if kind == "model_call":
                model_calls += 1
                model_call = event.get("model_call") or {}
                _accumulate_customer_kv(kv_by_customer, event, model_call)
                ttft = model_call.get("ttft_seconds")
                if isinstance(ttft, int | float):
                    ttfts.append(float(ttft) * 1000.0)
            if kind == "tool_call":
                tool_calls += 1
                tool_call = event.get("tool_call") or {}
                stall = tool_call.get("stall_seconds")
                wall = tool_call.get("wall_time_seconds")
                if isinstance(stall, int | float):
                    stall_seconds += float(stall)
                if isinstance(wall, int | float):
                    wall_seconds += float(wall)
        return DaemonSnapshot(
            window_seconds=self.window.window_seconds,
            events_total=len(events),
            model_calls=model_calls,
            tool_calls=tool_calls,
            ttft_p50_ms=_percentile(ttfts, 50),
            ttft_p99_ms=_percentile(ttfts, 99),
            tool_stall_total_seconds=stall_seconds,
            tool_stall_pct=(stall_seconds / wall_seconds) if wall_seconds > 0 else 0.0,
            node_counts=dict(node_counts),
            kv_by_customer={
                customer: {key: float(value) for key, value in values.items()}
                for customer, values in kv_by_customer.items()
            },
        )

    def prometheus_metrics_text(self) -> str:
        snapshot = self.snapshot()
        lines = [
            "# HELP inferguard_daemon_events_total Events retained in the daemon sliding window.",
            "# TYPE inferguard_daemon_events_total gauge",
            f"inferguard_daemon_events_total {snapshot.events_total}",
            "# HELP inferguard_model_calls_total Model-call nodes retained in the daemon window.",
            "# TYPE inferguard_model_calls_total gauge",
            f"inferguard_model_calls_total {snapshot.model_calls}",
            "# HELP inferguard_tool_calls_total Tool-call nodes retained in the daemon window.",
            "# TYPE inferguard_tool_calls_total gauge",
            f"inferguard_tool_calls_total {snapshot.tool_calls}",
            "# HELP inferguard_ttft_p50_ms Median time to first token in milliseconds.",
            "# TYPE inferguard_ttft_p50_ms gauge",
            f"inferguard_ttft_p50_ms {snapshot.ttft_p50_ms:.6f}",
            "# HELP inferguard_ttft_p99_ms P99 time to first token in milliseconds.",
            "# TYPE inferguard_ttft_p99_ms gauge",
            f"inferguard_ttft_p99_ms {snapshot.ttft_p99_ms:.6f}",
            "# HELP inferguard_tool_stall_pct Fraction of tool wall time spent stalled.",
            "# TYPE inferguard_tool_stall_pct gauge",
            f"inferguard_tool_stall_pct {snapshot.tool_stall_pct:.6f}",
        ]
        for kind, count in sorted(snapshot.node_counts.items()):
            lines.append(f'inferguard_node_count{{kind="{kind}"}} {count}')
        for customer, values in sorted(snapshot.kv_by_customer.items()):
            label = _prom_label(str(customer))
            # Implements S-21 per-customer KV footprint accounting (see docs/inferguard/24).
            for tier in ("hbm_bytes", "ram_bytes", "ssd_bytes", "evictions"):
                value = values.get(tier, 0.0)
                metric = (
                    "inferguard_customer_kv_evictions_total"
                    if tier == "evictions"
                    else f"inferguard_customer_kv_{tier}"
                )
                lines.append(f'{metric}{{customer_id="{label}"}} {value}')
        lines.append("")
        return "\n".join(lines)

    def start_metrics_server(
        self,
        *,
        host: str = DEFAULT_DAEMON_HOST,
        port: int = DEFAULT_DAEMON_PORT,
        allow_remote: bool = False,
    ) -> str:
        if host not in LOOPBACK_HOSTS and not allow_remote:
            raise ValueError("daemon metrics server only binds loopback in v0.5")
        self.permission_policy.check_bind(host, port, opted_in=allow_remote).raise_if_denied()
        if self._server is not None:
            actual_port = self._server.server_address[1]
            return f"http://{host}:{actual_port}/metrics"
        daemon = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:  # noqa: N802 - stdlib callback name
                if self.path != "/metrics":
                    self.send_response(404)
                    self.end_headers()
                    return
                body = daemon.prometheus_metrics_text().encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/plain; version=0.0.4")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, _format: str, *args: Any) -> None:
                return

        self._server = ThreadingHTTPServer((host, port), Handler)
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()
        actual_port = self._server.server_address[1]
        return f"http://{host}:{actual_port}/metrics"

    def stop_metrics_server(self) -> None:
        if self._server is None:
            return
        self._server.shutdown()
        self._server.server_close()
        if self._thread is not None:
            self._thread.join(timeout=5)
        self._server = None
        self._thread = None

    def write_snapshot(self, path: Path | str) -> Path:
        output_path = Path(path)
        self.permission_policy.check_filesystem(output_path, write=True).raise_if_denied()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_json(output_path, self.snapshot().as_dict())
        return output_path


def _accumulate_customer_kv(
    out: dict[str, Counter[str]], event: dict[str, Any], model_call: dict[str, Any]
) -> None:
    metadata = event.get("metadata") if isinstance(event.get("metadata"), dict) else {}
    customer = (
        metadata.get("customer_id")
        or model_call.get("customer_id")
        or event.get("customer_id")
        or "unknown"
    )
    bucket = out.setdefault(str(customer), Counter())
    for source in (metadata, model_call, event):
        if not isinstance(source, dict):
            continue
        for key in ("hbm_bytes", "ram_bytes", "ssd_bytes", "evictions"):
            value = source.get(key) or source.get(f"kv_{key}")
            if isinstance(value, int | float):
                bucket[key] += float(value)
    input_tokens = model_call.get("input_tokens")
    output_tokens = model_call.get("output_tokens")
    if isinstance(input_tokens, int | float) or isinstance(output_tokens, int | float):
        bucket["hbm_bytes"] += float((input_tokens or 0) + (output_tokens or 0)) * 32.0


def _prom_label(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def _percentile(values: list[float], percentile: int) -> float:
    if not values:
        return 0.0
    if percentile == 50:
        return float(median(values))
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, round((percentile / 100.0) * (len(ordered) - 1))))
    return float(ordered[index])


__all__ = [
    "DEFAULT_DAEMON_HOST",
    "DEFAULT_DAEMON_PORT",
    "Daemon",
    "DaemonSnapshot",
    "SlidingWindow",
]

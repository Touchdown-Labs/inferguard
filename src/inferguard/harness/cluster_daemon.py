"""Multi-node InferGuard daemon fan-in for Slurm/K8s clusters.

``ClusterDaemon`` adds leader/follower modes around the local daemon:
followers POST privacy-gated aggregate snapshots to a leader, and the
leader exposes a merged Prometheus ``/metrics`` endpoint keyed by rank.

Docs stub for Item E: document ``inferguard daemon start --leader`` and
``inferguard daemon start --follower <leader-url>`` in ``docs/HARNESS.md``.
"""

from __future__ import annotations

import hmac
import json
import os
import socket
import threading
import time
from collections import deque
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urljoin

import httpx

from inferguard.harness.daemon import Daemon
from inferguard.harness.permissions import PermissionPolicy
from inferguard.harness.telemetry import default_config_dir

CLUSTER_SNAPSHOT_SCHEMA_VERSION = "inferguard-cluster-snapshot/v1"
CLUSTER_SNAPSHOT_PATH = "/cluster/v1/snapshots"
CLUSTER_FOLLOWERS_PATH = "/cluster/v1/followers"
DEFAULT_HEARTBEAT_SECONDS = 5.0
DEFAULT_STALE_AFTER_SECONDS = 30.0
DEFAULT_BUFFER_SECONDS = 300.0
DEFAULT_CLUSTER_TOKEN_NAME = "cluster.token"

ClusterMode = Literal["leader", "follower"]


class ClusterDaemonError(RuntimeError):
    """Base error for cluster fan-in failures."""


class ClusterFanInError(ClusterDaemonError):
    """Raised for non-retryable leader responses."""

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code

    @property
    def retryable(self) -> bool:
        return self.status_code is None or self.status_code >= 500


@dataclass(frozen=True)
class RankLabels:
    """Stable labels sent by every follower for rank-aware central merge."""

    slurm_procid: str
    slurm_nodeid: str
    cluster_node_name: str
    cluster_id: str
    rank: str

    def as_dict(self) -> dict[str, str]:
        return {
            "slurm_procid": self.slurm_procid,
            "slurm_nodeid": self.slurm_nodeid,
            "cluster_node_name": self.cluster_node_name,
            "cluster_id": self.cluster_id,
            "rank": self.rank,
        }


@dataclass(frozen=True)
class FollowerRecord:
    """Latest leader-side snapshot for one follower rank."""

    rank: str
    rank_labels: dict[str, str]
    snapshot: dict[str, Any]
    sequence: int
    first_seen: float
    last_seen: float
    stale_after_seconds: float

    def is_stale(self, *, now: float) -> bool:
        return (now - self.last_seen) > self.stale_after_seconds

    def as_dict(self, *, now: float) -> dict[str, Any]:
        return {
            "rank": self.rank,
            "rank_labels": dict(self.rank_labels),
            "snapshot": dict(self.snapshot),
            "sequence": self.sequence,
            "first_seen": self.first_seen,
            "last_seen": self.last_seen,
            "stale": self.is_stale(now=now),
        }


class ClusterDaemon:
    """Leader/follower coordination layer for multi-node daemon deployments."""

    def __init__(
        self,
        *,
        mode: ClusterMode,
        daemon: Daemon | None = None,
        leader_url: str | None = None,
        rank_labels: RankLabels | None = None,
        token: str | None = None,
        token_path: Path | str | None = None,
        permission_policy: PermissionPolicy | None = None,
        privacy_opt_in: bool = True,
        heartbeat_seconds: float = DEFAULT_HEARTBEAT_SECONDS,
        stale_after_seconds: float = DEFAULT_STALE_AFTER_SECONDS,
        buffer_seconds: float = DEFAULT_BUFFER_SECONDS,
        clock: Callable[[], float] = time.time,
        http_timeout_seconds: float = 5.0,
    ) -> None:
        if mode not in {"leader", "follower"}:
            raise ValueError("mode must be 'leader' or 'follower'")
        if mode == "follower" and not leader_url:
            raise ValueError("leader_url is required in follower mode")
        self.mode = mode
        self.permission_policy = permission_policy or PermissionPolicy()
        self.daemon = daemon or Daemon(permission_policy=self.permission_policy)
        self.leader_url = leader_url.rstrip("/") if leader_url else None
        self.rank_labels = rank_labels or detect_rank_labels()
        self.token_path = (
            Path(token_path) if token_path is not None else default_cluster_token_path()
        )
        self.token = (
            token
            if token is not None
            else load_cluster_token(self.token_path, self.permission_policy)
        )
        self.privacy_opt_in = privacy_opt_in
        self.heartbeat_seconds = heartbeat_seconds
        self.stale_after_seconds = stale_after_seconds
        self.buffer_seconds = buffer_seconds
        self.clock = clock
        self.http_timeout_seconds = http_timeout_seconds
        self._followers: dict[str, FollowerRecord] = {}
        self._buffer: deque[tuple[float, dict[str, Any]]] = deque()
        self._sequence = 0
        self._lock = threading.Lock()
        self._server: ThreadingHTTPServer | None = None
        self._server_thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._follower_thread: threading.Thread | None = None

    @classmethod
    def leader(cls, **kwargs: Any) -> ClusterDaemon:
        return cls(mode="leader", **kwargs)

    @classmethod
    def follower(cls, *, leader_url: str, **kwargs: Any) -> ClusterDaemon:
        return cls(mode="follower", leader_url=leader_url, **kwargs)

    def start_server(self, *, host: str = "127.0.0.1", port: int = 9466) -> str:
        """Start the leader HTTP server for snapshots and merged metrics."""

        if self.mode != "leader":
            raise ValueError("start_server is only valid in leader mode")
        if self._server is not None:
            actual_port = self._server.server_address[1]
            return f"http://{host}:{actual_port}/metrics"
        self.permission_policy.check_bind(
            host, port, opted_in=self.privacy_opt_in
        ).raise_if_denied()
        cluster = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self) -> None:  # noqa: N802 - stdlib callback name
                if self.path != CLUSTER_SNAPSHOT_PATH:
                    self.send_response(404)
                    self.end_headers()
                    return
                if not cluster._authorized(self.headers.get("Authorization")):
                    _write_json(self, 401, {"error": "missing or invalid bearer token"})
                    return
                length = int(self.headers.get("Content-Length", "0") or 0)
                try:
                    payload = json.loads(
                        self.rfile.read(length).decode("utf-8") if length else "{}"
                    )
                    record = cluster.receive_snapshot(payload)
                except PermissionError as exc:
                    _write_json(self, 403, {"error": str(exc)})
                    return
                except (ValueError, TypeError, json.JSONDecodeError) as exc:
                    _write_json(self, 400, {"error": str(exc)})
                    return
                _write_json(
                    self, 202, {"accepted": True, "record": record.as_dict(now=cluster.clock())}
                )

            def do_GET(self) -> None:  # noqa: N802 - stdlib callback name
                if self.path == "/metrics":
                    body = cluster.prometheus_metrics_text().encode("utf-8")
                    self.send_response(200)
                    self.send_header("Content-Type", "text/plain; version=0.0.4")
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                    return
                if self.path == CLUSTER_FOLLOWERS_PATH:
                    _write_json(self, 200, {"followers": cluster.follower_records()})
                    return
                self.send_response(404)
                self.end_headers()

            def log_message(self, _format: str, *args: Any) -> None:
                return

        self._server = ThreadingHTTPServer((host, port), Handler)
        self._server_thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._server_thread.start()
        actual_port = self._server.server_address[1]
        return f"http://{host}:{actual_port}/metrics"

    def stop_server(self) -> None:
        if self._server is None:
            return
        self._server.shutdown()
        self._server.server_close()
        if self._server_thread is not None:
            self._server_thread.join(timeout=5)
        self._server = None
        self._server_thread = None

    def start_follower(self) -> None:
        """Start the follower heartbeat loop."""

        if self.mode != "follower":
            raise ValueError("start_follower is only valid in follower mode")
        if self._follower_thread is not None:
            return
        self._stop_event.clear()
        self._follower_thread = threading.Thread(target=self._heartbeat_loop, daemon=True)
        self._follower_thread.start()

    def stop_follower(self) -> None:
        if self._follower_thread is None:
            return
        self._stop_event.set()
        self._follower_thread.join(timeout=max(5.0, self.heartbeat_seconds * 2))
        self._follower_thread = None

    def stop(self) -> None:
        self.stop_follower()
        self.stop_server()

    def receive_snapshot(self, payload: dict[str, Any]) -> FollowerRecord:
        """Merge a follower snapshot into leader state keyed by rank."""

        if self.mode != "leader":
            raise ValueError("receive_snapshot is only valid in leader mode")
        if not self.privacy_opt_in or payload.get("privacy_opt_in") is not True:
            raise PermissionError("cluster fan-in requires privacy opt-in on leader and follower")
        if payload.get("schema_version") != CLUSTER_SNAPSHOT_SCHEMA_VERSION:
            raise ValueError(f"schema_version must be {CLUSTER_SNAPSHOT_SCHEMA_VERSION}")
        rank_labels = _validated_rank_labels(payload.get("rank_labels"))
        snapshot = _validated_snapshot(payload.get("snapshot"))
        sequence = _non_negative_int(payload.get("sequence"), "sequence")
        rank = rank_labels["rank"]
        now = self.clock()
        with self._lock:
            previous = self._followers.get(rank)
            first_seen = previous.first_seen if previous is not None else now
            record = FollowerRecord(
                rank=rank,
                rank_labels=rank_labels,
                snapshot=snapshot,
                sequence=sequence,
                first_seen=first_seen,
                last_seen=now,
                stale_after_seconds=self.stale_after_seconds,
            )
            self._followers[rank] = record
            return record

    def follower_records(self) -> list[dict[str, Any]]:
        now = self.clock()
        with self._lock:
            return [
                record.as_dict(now=now)
                for record in sorted(self._followers.values(), key=lambda item: item.rank)
            ]

    def build_snapshot_payload(self) -> dict[str, Any]:
        """Build the JSON payload a follower sends to the leader."""

        if self.mode != "follower":
            raise ValueError("build_snapshot_payload is only valid in follower mode")
        self._sequence += 1
        return {
            "schema_version": CLUSTER_SNAPSHOT_SCHEMA_VERSION,
            "sent_at": self.clock(),
            "sequence": self._sequence,
            "privacy_opt_in": self.privacy_opt_in,
            "rank_labels": self.rank_labels.as_dict(),
            "snapshot": self.daemon.snapshot().as_dict(),
        }

    def send_snapshot(self) -> int:
        """Queue a current snapshot and drain buffered payloads to the leader."""

        if self.mode != "follower":
            raise ValueError("send_snapshot is only valid in follower mode")
        payload = self.build_snapshot_payload()
        self._append_buffer(payload)
        return self._drain_buffer()

    def buffered_count(self) -> int:
        self._prune_buffer()
        return len(self._buffer)

    def prometheus_metrics_text(self) -> str:
        """Render merged leader metrics, including per-rank labels."""

        now = self.clock()
        with self._lock:
            records = list(self._followers.values())
        stale_records = [record for record in records if record.is_stale(now=now)]
        active_records = [record for record in records if not record.is_stale(now=now)]
        event_total = sum(int(record.snapshot.get("events_total", 0)) for record in active_records)
        model_total = sum(int(record.snapshot.get("model_calls", 0)) for record in active_records)
        tool_total = sum(int(record.snapshot.get("tool_calls", 0)) for record in active_records)
        lines = [
            "# HELP inferguard_cluster_followers_total Followers known to the leader.",
            "# TYPE inferguard_cluster_followers_total gauge",
            f"inferguard_cluster_followers_total {len(records)}",
            "# HELP inferguard_cluster_stale_followers_total Followers stale by heartbeat age.",
            "# TYPE inferguard_cluster_stale_followers_total gauge",
            f"inferguard_cluster_stale_followers_total {len(stale_records)}",
            "# HELP inferguard_cluster_events_total Active follower events merged by rank.",
            "# TYPE inferguard_cluster_events_total gauge",
            f"inferguard_cluster_events_total {event_total}",
            "# HELP inferguard_cluster_model_calls_total Active follower model-call nodes merged by rank.",
            "# TYPE inferguard_cluster_model_calls_total gauge",
            f"inferguard_cluster_model_calls_total {model_total}",
            "# HELP inferguard_cluster_tool_calls_total Active follower tool-call nodes merged by rank.",
            "# TYPE inferguard_cluster_tool_calls_total gauge",
            f"inferguard_cluster_tool_calls_total {tool_total}",
        ]
        for record in sorted(records, key=lambda item: item.rank):
            labels = _prometheus_labels(record.rank_labels)
            stale = record.is_stale(now=now)
            up = 0 if stale else 1
            age = max(0.0, now - record.last_seen)
            snapshot = record.snapshot
            lines.extend(
                [
                    f"inferguard_cluster_follower_up{{{labels}}} {up}",
                    f"inferguard_cluster_follower_last_seen_age_seconds{{{labels}}} {age:.6f}",
                    f"inferguard_cluster_rank_events_total{{{labels}}} {int(snapshot.get('events_total', 0))}",
                    f"inferguard_cluster_rank_model_calls_total{{{labels}}} {int(snapshot.get('model_calls', 0))}",
                    f"inferguard_cluster_rank_tool_calls_total{{{labels}}} {int(snapshot.get('tool_calls', 0))}",
                    f"inferguard_cluster_rank_ttft_p50_ms{{{labels}}} {float(snapshot.get('ttft_p50_ms', 0.0)):.6f}",
                    f"inferguard_cluster_rank_tool_stall_pct{{{labels}}} {float(snapshot.get('tool_stall_pct', 0.0)):.6f}",
                ]
            )
        lines.append("")
        return "\n".join(lines)

    def _heartbeat_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                self.send_snapshot()
            except PermissionError:
                raise
            except ClusterDaemonError:
                pass
            self._stop_event.wait(self.heartbeat_seconds)

    def _append_buffer(self, payload: dict[str, Any]) -> None:
        self._prune_buffer()
        self._buffer.append((self.clock(), payload))

    def _prune_buffer(self) -> None:
        now = self.clock()
        while self._buffer and now - self._buffer[0][0] > self.buffer_seconds:
            self._buffer.popleft()

    def _drain_buffer(self) -> int:
        self._prune_buffer()
        sent = 0
        while self._buffer:
            queued_at, payload = self._buffer[0]
            if self.clock() - queued_at > self.buffer_seconds:
                self._buffer.popleft()
                continue
            try:
                self._post_payload(payload)
            except httpx.HTTPError:
                return sent
            except ClusterFanInError as exc:
                if exc.retryable:
                    return sent
                raise
            self._buffer.popleft()
            sent += 1
        return sent

    def _post_payload(self, payload: dict[str, Any]) -> None:
        if self.leader_url is None:
            raise ValueError("leader_url is required")
        url = urljoin(f"{self.leader_url}/", CLUSTER_SNAPSHOT_PATH.lstrip("/"))
        opted_in = self.privacy_opt_in and payload.get("privacy_opt_in") is True
        self.permission_policy.check_network(url, opted_in=opted_in).raise_if_denied()
        headers = {"Authorization": f"Bearer {self.token}"}
        with httpx.Client(timeout=self.http_timeout_seconds) as client:
            response = client.post(url, json=payload, headers=headers)
        if response.status_code == 403:
            raise PermissionError(response.text)
        if response.status_code == 401:
            raise ClusterFanInError("leader rejected cluster bearer token", status_code=401)
        if response.status_code >= 400:
            raise ClusterFanInError(
                f"leader returned HTTP {response.status_code}: {response.text}",
                status_code=response.status_code,
            )

    def _authorized(self, authorization: str | None) -> bool:
        if not authorization or not authorization.startswith("Bearer "):
            return False
        supplied = authorization.removeprefix("Bearer ").strip()
        return hmac.compare_digest(supplied, self.token)


def default_cluster_token_path(env: Mapping[str, str] | None = None) -> Path:
    return default_config_dir(dict(os.environ if env is None else env)) / DEFAULT_CLUSTER_TOKEN_NAME


def load_cluster_token(path: Path | str, permission_policy: PermissionPolicy | None = None) -> str:
    token_path = Path(path)
    policy = permission_policy or PermissionPolicy()
    policy.check_filesystem(token_path).raise_if_denied()
    if not token_path.exists():
        raise FileNotFoundError(
            f"cluster bearer token not found at {token_path}; create it out-of-band before cluster fan-in"
        )
    token = token_path.read_text(encoding="utf-8").strip()
    if not token:
        raise ValueError(f"cluster bearer token at {token_path} is empty")
    return token


def detect_rank_labels(
    env: Mapping[str, str] | None = None,
    *,
    hostname: str | None = None,
) -> RankLabels:
    environ = dict(os.environ if env is None else env)
    node_name = (
        environ.get("INFERGUARD_CLUSTER_NODE_NAME")
        or environ.get("CLUSTER_NODE_NAME")
        or environ.get("NODE_NAME")
        or environ.get("HOSTNAME")
        or hostname
        or socket.gethostname()
    )
    slurm_procid = (
        _first_env(environ, "SLURM_PROCID", "PMI_RANK", "OMPI_COMM_WORLD_RANK", "RANK") or "0"
    )
    slurm_nodeid = _first_env(environ, "SLURM_NODEID", "GROUP_RANK", "NODE_RANK") or "0"
    rank = environ.get("INFERGUARD_RANK") or environ.get("RANK") or slurm_procid
    cluster_id = (
        environ.get("INFERGUARD_CLUSTER_ID")
        or environ.get("SLURM_JOB_ID")
        or environ.get("MODAL_CLUSTER_ID")
        or environ.get("KUBERNETES_SERVICE_HOST")
        or "local"
    )
    return RankLabels(
        slurm_procid=str(slurm_procid),
        slurm_nodeid=str(slurm_nodeid),
        cluster_node_name=str(node_name),
        cluster_id=str(cluster_id),
        rank=str(rank),
    )


def _first_env(env: Mapping[str, str], *keys: str) -> str | None:
    for key in keys:
        value = env.get(key)
        if value not in {None, ""}:
            return value
    return None


def _validated_rank_labels(value: Any) -> dict[str, str]:
    if not isinstance(value, dict):
        raise ValueError("rank_labels must be an object")
    required = {"slurm_procid", "slurm_nodeid", "cluster_node_name", "cluster_id", "rank"}
    missing = sorted(required - set(value))
    if missing:
        raise ValueError(f"rank_labels missing required keys: {', '.join(missing)}")
    return {key: str(value[key]) for key in sorted(required)}


def _validated_snapshot(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("snapshot must be an object")
    required = {"events_total", "model_calls", "tool_calls", "ttft_p50_ms", "tool_stall_pct"}
    missing = sorted(required - set(value))
    if missing:
        raise ValueError(f"snapshot missing required keys: {', '.join(missing)}")
    return dict(value)


def _non_negative_int(value: Any, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{field_name} must be a non-negative integer")
    return value


def _prometheus_labels(labels: dict[str, str]) -> str:
    return ",".join(
        f'{key}="{_escape_prometheus_label(str(value))}"' for key, value in sorted(labels.items())
    )


def _escape_prometheus_label(value: str) -> str:
    return value.replace("\\", "\\\\").replace("\n", "\\n").replace('"', '\\"')


def _write_json(handler: BaseHTTPRequestHandler, status_code: int, payload: dict[str, Any]) -> None:
    body = json.dumps(payload, sort_keys=True).encode("utf-8")
    handler.send_response(status_code)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


__all__ = [
    "CLUSTER_FOLLOWERS_PATH",
    "CLUSTER_SNAPSHOT_PATH",
    "CLUSTER_SNAPSHOT_SCHEMA_VERSION",
    "ClusterDaemon",
    "ClusterDaemonError",
    "ClusterFanInError",
    "RankLabels",
    "default_cluster_token_path",
    "detect_rank_labels",
    "load_cluster_token",
]

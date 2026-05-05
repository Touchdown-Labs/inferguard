from __future__ import annotations

import json
import time
from pathlib import Path

import httpx
import pytest
from typer.testing import CliRunner

from inferguard.cli import app
from inferguard.harness.agent_trace import AgentTracer
from inferguard.harness.cluster_daemon import ClusterDaemon, RankLabels
from inferguard.harness.daemon import Daemon, SlidingWindow
from inferguard.harness.permissions import PermissionPolicy


@pytest.mark.harness
def test_sliding_window_prunes_old_events() -> None:
    now = time.time()
    window = SlidingWindow(window_seconds=10)
    window.append({"id": "old"}, observed_at=now - 20)
    window.append({"id": "new"}, observed_at=now)
    assert window.values() == [{"id": "new"}]


@pytest.mark.harness
def test_daemon_snapshot_empty() -> None:
    snapshot = Daemon().snapshot()
    assert snapshot.events_total == 0
    assert snapshot.ttft_p50_ms == 0.0


@pytest.mark.harness
def test_daemon_records_model_call_metrics(tmp_path: Path) -> None:
    tracer = AgentTracer(output_dir=tmp_path, framework="raw_openai")
    event = tracer.record_model_call(
        endpoint="http://localhost/v1/chat/completions",
        model="m",
        input_tokens=10,
        output_tokens=5,
        input_tokens_source="api",
        output_tokens_source="api",
        ttft_seconds=0.1,
        tpot_seconds=0.02,
        latency_seconds=0.2,
        tool_choice=None,
        stream=True,
        stop_reason="end_turn",
        request_id="r",
        kv_pressure_label="measured",
    )
    daemon = Daemon()
    daemon.record_event(event.as_dict())
    snapshot = daemon.snapshot()
    assert snapshot.model_calls == 1
    assert snapshot.ttft_p50_ms == 100.0


@pytest.mark.harness
def test_daemon_records_tool_stall_pct(tmp_path: Path) -> None:
    tracer = AgentTracer(output_dir=tmp_path, framework="raw_openai")
    event = tracer.record_tool_call(
        name="filesystem.read_file",
        wall_time_seconds=10.0,
        stall_seconds=2.5,
        result_size_bytes=4,
    )
    daemon = Daemon()
    daemon.record_event(event.as_dict())
    assert daemon.snapshot().tool_stall_pct == 0.25


@pytest.mark.harness
def test_prometheus_metrics_text_contains_inferguard_namespace(tmp_path: Path) -> None:
    tracer = AgentTracer(output_dir=tmp_path, framework="raw_openai")
    daemon = Daemon()
    daemon.record_event(
        tracer.record_tool_call(
            name="tool",
            wall_time_seconds=1,
            stall_seconds=0,
            result_size_bytes=1,
        ).as_dict()
    )
    text = daemon.prometheus_metrics_text()
    assert "inferguard_daemon_events_total 1" in text
    assert 'inferguard_node_count{kind="tool_call"} 1' in text


@pytest.mark.harness
def test_metrics_server_serves_loopback_endpoint() -> None:
    daemon = Daemon()
    url = daemon.start_metrics_server(port=0)
    try:
        response = httpx.get(url)
        assert response.status_code == 200
        assert "inferguard_model_calls_total" in response.text
    finally:
        daemon.stop_metrics_server()


@pytest.mark.harness
def test_metrics_server_rejects_non_loopback_bind() -> None:
    with pytest.raises(ValueError):
        Daemon().start_metrics_server(host="0.0.0.0", port=0)


@pytest.mark.harness
def test_record_agent_trace_file_loads_valid_jsonl(tmp_path: Path) -> None:
    tracer = AgentTracer(output_dir=tmp_path, framework="raw_openai")
    tracer.record_tool_call(name="tool", wall_time_seconds=1, stall_seconds=0, result_size_bytes=1)
    tracer.finalize()
    daemon = Daemon()
    assert daemon.record_agent_trace_file(tracer.trace_path) == 2
    assert daemon.snapshot().tool_calls == 1


@pytest.mark.harness
def test_watch_directory_once_skips_invalid_jsonl(tmp_path: Path) -> None:
    (tmp_path / "bad.jsonl").write_text("not json\n", encoding="utf-8")
    assert Daemon().watch_directory_once(tmp_path) == 0


@pytest.mark.harness
def test_write_snapshot_persists_json(tmp_path: Path) -> None:
    daemon = Daemon()
    path = daemon.write_snapshot(tmp_path / "snapshot.json")
    assert json.loads(path.read_text())["events_total"] == 0


@pytest.mark.harness
def test_sliding_window_values_prunes_relative_to_time(monkeypatch: pytest.MonkeyPatch) -> None:
    window = SlidingWindow(window_seconds=1)
    monkeypatch.setattr(time, "time", lambda: 10_000.0)
    window.append({"id": "a"}, observed_at=9990.0)
    window.events.append((9999.5, {"id": "b"}))
    assert window.values() == [{"id": "b"}]


@pytest.mark.harness
def test_daemon_help_surfaces_cluster_flags() -> None:
    result = CliRunner().invoke(app, ["daemon", "start", "--help"])

    assert result.exit_code == 0
    assert "--leader" in result.stdout
    assert "--follower" in result.stdout


@pytest.mark.harness
def test_daemon_record_agent_trace_file_uses_permission_policy(tmp_path: Path) -> None:
    path = tmp_path / "model-server-prod.jsonl"
    path.write_text("", encoding="utf-8")
    daemon = Daemon(permission_policy=PermissionPolicy())

    with pytest.raises(PermissionError):
        daemon.record_agent_trace_file(path)


@pytest.mark.harness
def test_daemon_write_snapshot_uses_permission_policy(tmp_path: Path) -> None:
    daemon = Daemon(permission_policy=PermissionPolicy(allow_filesystem=False))

    with pytest.raises(PermissionError):
        daemon.write_snapshot(tmp_path / "snapshot.json")


@pytest.mark.harness
def test_daemon_cluster_leader_follower_local_socket_integration(tmp_path: Path) -> None:
    token_path = tmp_path / "cluster.token"
    token_path.write_text("shared-token\n", encoding="utf-8")
    rank = RankLabels(
        slurm_procid="2",
        slurm_nodeid="1",
        cluster_node_name="node-b",
        cluster_id="slurm-42",
        rank="2",
    )
    leader = ClusterDaemon.leader(token_path=token_path)
    metrics_url = leader.start_server(host="127.0.0.1", port=0)
    base_url = metrics_url.removesuffix("/metrics")
    daemon = Daemon()
    daemon.record_event(
        {
            "event_type": "node",
            "kind": "tool_call",
            "tool_call": {"stall_seconds": 1.0, "wall_time_seconds": 4.0},
        }
    )
    follower = ClusterDaemon.follower(
        leader_url=base_url,
        daemon=daemon,
        rank_labels=rank,
        token_path=token_path,
    )
    try:
        assert follower.send_snapshot() == 1
        response = httpx.get(metrics_url)
    finally:
        leader.stop()

    assert response.status_code == 200
    assert 'rank="2"' in response.text
    assert "inferguard_cluster_tool_calls_total 1" in response.text

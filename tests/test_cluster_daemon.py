from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from inferguard.harness.cluster_daemon import (
    CLUSTER_SNAPSHOT_PATH,
    CLUSTER_SNAPSHOT_SCHEMA_VERSION,
    ClusterDaemon,
    RankLabels,
    detect_rank_labels,
    load_cluster_token,
)
from inferguard.harness.daemon import Daemon

pytestmark = pytest.mark.harness


def _token_path(tmp_path: Path, token: str = "cluster-secret") -> Path:
    path = tmp_path / "cluster.token"
    path.write_text(token + "\n", encoding="utf-8")
    return path


def _rank(rank: str = "0", *, cluster_id: str = "job-1", node: str = "node-a") -> RankLabels:
    return RankLabels(
        slurm_procid=rank,
        slurm_nodeid=rank,
        cluster_node_name=node,
        cluster_id=cluster_id,
        rank=rank,
    )


def _snapshot_payload(rank: str = "0", *, events: int = 1, models: int = 1, tools: int = 0) -> dict:
    return {
        "schema_version": CLUSTER_SNAPSHOT_SCHEMA_VERSION,
        "sent_at": 100.0,
        "sequence": int(rank) + 1,
        "privacy_opt_in": True,
        "rank_labels": _rank(rank).as_dict(),
        "snapshot": {
            "window_seconds": 300.0,
            "events_total": events,
            "model_calls": models,
            "tool_calls": tools,
            "ttft_p50_ms": 12.5,
            "ttft_p99_ms": 12.5,
            "tool_stall_total_seconds": 0.0,
            "tool_stall_pct": 0.0,
            "node_counts": {"model_call": models, "tool_call": tools},
        },
    }


def _record_model_call(daemon: Daemon, *, ttft_seconds: float = 0.1) -> None:
    daemon.record_event(
        {
            "event_type": "node",
            "kind": "model_call",
            "model_call": {"ttft_seconds": ttft_seconds},
        }
    )


def test_detect_rank_labels_from_slurm_env() -> None:
    labels = detect_rank_labels(
        {
            "SLURM_PROCID": "7",
            "SLURM_NODEID": "2",
            "SLURM_JOB_ID": "slurm-123",
            "HOSTNAME": "gpu-node-2",
        }
    )

    assert labels.as_dict() == {
        "slurm_procid": "7",
        "slurm_nodeid": "2",
        "cluster_node_name": "gpu-node-2",
        "cluster_id": "slurm-123",
        "rank": "7",
    }


def test_load_cluster_token_reads_operator_generated_file(tmp_path: Path) -> None:
    path = _token_path(tmp_path, "shared-token")

    assert load_cluster_token(path) == "shared-token"


def test_load_cluster_token_missing_file_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        load_cluster_token(tmp_path / "missing.token")


def test_leader_accepts_snapshot_and_merges_by_rank(tmp_path: Path) -> None:
    leader = ClusterDaemon.leader(token_path=_token_path(tmp_path), rank_labels=_rank("leader"))

    leader.receive_snapshot(_snapshot_payload("0", events=1, models=1))
    leader.receive_snapshot(_snapshot_payload("0", events=4, models=3))

    records = leader.follower_records()
    assert len(records) == 1
    assert records[0]["rank"] == "0"
    assert records[0]["snapshot"]["events_total"] == 4
    assert records[0]["snapshot"]["model_calls"] == 3


def test_leader_requires_follower_privacy_opt_in(tmp_path: Path) -> None:
    leader = ClusterDaemon.leader(token_path=_token_path(tmp_path), rank_labels=_rank("leader"))
    payload = _snapshot_payload("0")
    payload["privacy_opt_in"] = False

    with pytest.raises(PermissionError):
        leader.receive_snapshot(payload)


def test_leader_marks_follower_stale_after_30_seconds(tmp_path: Path) -> None:
    now = {"value": 1_000.0}
    leader = ClusterDaemon.leader(
        token_path=_token_path(tmp_path),
        rank_labels=_rank("leader"),
        clock=lambda: now["value"],
    )
    leader.receive_snapshot(_snapshot_payload("0"))

    now["value"] = 1_029.0
    assert leader.follower_records()[0]["stale"] is False
    now["value"] = 1_031.0
    assert leader.follower_records()[0]["stale"] is True


def test_prometheus_metrics_contains_rank_labels_and_totals(tmp_path: Path) -> None:
    leader = ClusterDaemon.leader(token_path=_token_path(tmp_path), rank_labels=_rank("leader"))
    leader.receive_snapshot(_snapshot_payload("0", events=2, models=2))
    leader.receive_snapshot(_snapshot_payload("1", events=3, models=1, tools=2))

    text = leader.prometheus_metrics_text()

    assert "inferguard_cluster_followers_total 2" in text
    assert "inferguard_cluster_events_total 5" in text
    assert 'rank="0"' in text
    assert 'cluster_node_name="node-a"' in text
    assert "inferguard_cluster_rank_tool_calls_total" in text


def test_follower_payload_has_required_rank_labels_and_no_token(tmp_path: Path) -> None:
    daemon = Daemon()
    _record_model_call(daemon)
    follower = ClusterDaemon.follower(
        leader_url="http://127.0.0.1:9466",
        daemon=daemon,
        rank_labels=_rank("3", cluster_id="cluster-a", node="node-c"),
        token_path=_token_path(tmp_path, "do-not-upload"),
    )

    payload = follower.build_snapshot_payload()

    assert payload["rank_labels"] == {
        "slurm_procid": "3",
        "slurm_nodeid": "3",
        "cluster_node_name": "node-c",
        "cluster_id": "cluster-a",
        "rank": "3",
    }
    assert payload["snapshot"]["model_calls"] == 1
    assert "do-not-upload" not in json.dumps(payload)


def test_follower_privacy_gate_blocks_without_opt_in(tmp_path: Path) -> None:
    follower = ClusterDaemon.follower(
        leader_url="http://example.com:9466",
        token_path=_token_path(tmp_path),
        rank_labels=_rank("0"),
        privacy_opt_in=False,
    )

    with pytest.raises(PermissionError):
        follower.send_snapshot()


def test_leader_http_rejects_missing_bearer_token(tmp_path: Path) -> None:
    leader = ClusterDaemon.leader(token_path=_token_path(tmp_path), rank_labels=_rank("leader"))
    metrics_url = leader.start_server(host="127.0.0.1", port=0)
    base_url = metrics_url.removesuffix("/metrics")
    try:
        response = httpx.post(f"{base_url}{CLUSTER_SNAPSHOT_PATH}", json=_snapshot_payload("0"))
    finally:
        leader.stop()

    assert response.status_code == 401


def test_follower_posts_to_leader_over_http_and_leader_merges(tmp_path: Path) -> None:
    token_path = _token_path(tmp_path)
    leader = ClusterDaemon.leader(token_path=token_path, rank_labels=_rank("leader"))
    metrics_url = leader.start_server(host="127.0.0.1", port=0)
    base_url = metrics_url.removesuffix("/metrics")
    daemon = Daemon()
    _record_model_call(daemon, ttft_seconds=0.2)
    follower = ClusterDaemon.follower(
        leader_url=base_url,
        daemon=daemon,
        token_path=token_path,
        rank_labels=_rank("4", node="node-d"),
    )
    try:
        assert follower.send_snapshot() == 1
        records = leader.follower_records()
    finally:
        leader.stop()

    assert len(records) == 1
    assert records[0]["rank_labels"]["rank"] == "4"
    assert records[0]["snapshot"]["model_calls"] == 1


def test_follower_buffers_when_leader_unavailable(tmp_path: Path) -> None:
    follower = ClusterDaemon.follower(
        leader_url="http://127.0.0.1:1",
        token_path=_token_path(tmp_path),
        rank_labels=_rank("0"),
    )

    assert follower.send_snapshot() == 0
    assert follower.buffered_count() == 1


def test_follower_replays_buffer_on_reconnect(tmp_path: Path) -> None:
    token_path = _token_path(tmp_path)
    follower = ClusterDaemon.follower(
        leader_url="http://127.0.0.1:1",
        token_path=token_path,
        rank_labels=_rank("0"),
    )
    assert follower.send_snapshot() == 0
    leader = ClusterDaemon.leader(token_path=token_path, rank_labels=_rank("leader"))
    metrics_url = leader.start_server(host="127.0.0.1", port=0)
    follower.leader_url = metrics_url.removesuffix("/metrics")
    try:
        assert follower.send_snapshot() == 2
        assert follower.buffered_count() == 0
        records = leader.follower_records()
    finally:
        leader.stop()

    assert records[0]["sequence"] == 2


def test_buffer_drops_payloads_older_than_five_minutes(tmp_path: Path) -> None:
    now = {"value": 0.0}
    follower = ClusterDaemon.follower(
        leader_url="http://127.0.0.1:1",
        token_path=_token_path(tmp_path),
        rank_labels=_rank("0"),
        clock=lambda: now["value"],
    )
    assert follower.send_snapshot() == 0

    now["value"] = 301.0

    assert follower.buffered_count() == 0

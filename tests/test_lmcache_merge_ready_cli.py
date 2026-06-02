from __future__ import annotations

import json
import subprocess
from pathlib import Path

from typer.testing import CliRunner

from inferguard.cli import app


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _write_packet_b(root: Path) -> Path:
    packet = root / "packet-b" / "20260518T221627Z"
    _write_json(
        packet / "packet-b-lifecycle-evidence.json",
        {
            "claim_status": "measured",
            "acceptance_status": "candidate_measured",
            "families": {
                "l0_lifecycle": {"status": "populated", "metric_count": 5},
                "l1_lifecycle": {"status": "populated", "metric_count": 20},
                "lookup_reuse": {"status": "populated", "metric_count": 2},
            },
        },
    )
    _write_json(
        packet / "workload_manifest.json",
        {"request_count": 48, "profile": "long_context_agent_kv_offload"},
    )
    _write_json(
        packet / "agent_kv_offload_report.json",
        {"claim_status": "measured", "compat_failure_reasons": []},
    )
    _write_json(packet / "lmcache_compat_report.json", {"failure_reasons": []})
    _write_json(
        packet / "lmcache_env.json",
        {"INFERGUARD_L0_BLOCK_BOUNDARY_EVIDENCE_PATH": "/tmp/boundary.jsonl"},
    )
    _write_json(
        packet / "vllm_command.json",
        [
            "vllm",
            "serve",
            "model",
            "--kv-transfer-config",
            json.dumps({"kv_connector": "LMCacheMPConnector", "kv_role": "kv_both"}),
        ],
    )
    _write_json(packet / "lmcache_command.json", ["lmcache", "server", "--l1-size-gb", "1"])
    _write_json(
        packet / "observability_coverage.json",
        {
            "families": [
                {"surface": "lmcache_mp", "family": "l0_lifecycle", "status": "populated"},
                {"surface": "lmcache_mp", "family": "l1_lifecycle", "status": "populated"},
                {"surface": "lmcache_mp", "family": "cacheblend_lifecycle", "status": "missing"},
            ],
            "coverage_gaps": [],
        },
    )
    (packet / "lmcache_metrics_loaded.prom").write_text(
        'lmcache_mp_l1_failures{operation="allocate"} 279\n'
        "lmcache_mp_l0_block_allocated_blocks_total 11\n"
        "lmcache_mp_lookup_hit_tokens_total 5\n",
        encoding="utf-8",
    )
    return packet


def _write_packet_c(root: Path) -> Path:
    packet = root / "packet-c" / "20260518T220212Z"
    _write_json(packet / "lmcache_compat_report.json", {"failure_reasons": []})
    _write_json(packet / "observability_coverage.json", {"coverage_gaps": []})
    _write_json(
        packet / "lmcache_l2_config.json",
        {"cli_argument": '{"type":"fs","base_path":"/tmp/l2-fs"}'},
    )
    _write_json(
        packet / "http" / "conf.json",
        {
            "storage_manager": {"l2_adapter_config": {"adapters": ["fs"]}},
            "observability": {"prometheus_port": 9090, "metrics_sample_rate": 1.0},
        },
    )
    _write_json(
        packet / "lmcache_env.json", {"LMCACHE_L2_ADAPTER": "fs", "LMCACHE_L2_PATH": "/tmp/l2-fs"}
    )
    _write_json(
        packet / "lmcache_command.json", ["lmcache", "server", "--l2-adapter", '{"type":"fs"}']
    )
    l2 = packet / "l2-fs"
    l2.mkdir(parents=True)
    (l2 / "abc.data").write_bytes(b"x" * 1024)
    (packet / "lmcache_metrics_loaded.prom").write_text(
        "lmcache_mp_l2_store_requests_total 14\nlmcache_mp_l2_prefetch_requests_total 3\n",
        encoding="utf-8",
    )
    return packet


def _git_repo(path: Path, branch: str = "main") -> Path:
    path.mkdir(parents=True)
    subprocess.run(["git", "init", "-b", branch], cwd=path, check=True, stdout=subprocess.DEVNULL)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=path, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=path, check=True)
    (path / "README.md").write_text("ok\n", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=path, check=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=path, check=True, stdout=subprocess.DEVNULL)
    return path


def _git_repo_behind_upstream(path: Path) -> Path:
    remote = _git_repo(path.parent / "remote", branch="main")
    repo = path
    subprocess.run(["git", "clone", str(remote), str(repo)], check=True, stdout=subprocess.DEVNULL)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=repo, check=True)
    (remote / "remote.txt").write_text("ahead\n", encoding="utf-8")
    subprocess.run(["git", "add", "remote.txt"], cwd=remote, check=True)
    subprocess.run(
        ["git", "commit", "-m", "remote ahead"], cwd=remote, check=True, stdout=subprocess.DEVNULL
    )
    subprocess.run(["git", "fetch", "origin"], cwd=repo, check=True, stdout=subprocess.DEVNULL)
    subprocess.run(["git", "branch", "--unset-upstream"], cwd=repo, check=True)
    return repo


def test_lmcache_merge_ready_cli_summarizes_packets_repos_and_blockers(tmp_path: Path) -> None:
    packet_b = _write_packet_b(tmp_path)
    packet_c = _write_packet_c(tmp_path)
    vllm = _git_repo(tmp_path / "vllm")
    lmcache = _git_repo(tmp_path / "LMCache", branch="dev")
    sglang = _git_repo_behind_upstream(tmp_path / "sglang")
    (lmcache / "dirty.txt").write_text("dirty\n", encoding="utf-8")

    output = tmp_path / "merge-ready.json"
    result = CliRunner().invoke(
        app,
        [
            "lmcache-merge-ready",
            "--packet-b-dir",
            str(packet_b),
            "--packet-c-dir",
            str(packet_c),
            "--repo",
            f"vllm={vllm}",
            "--repo",
            f"lmcache={lmcache}",
            "--repo",
            f"sglang={sglang}",
            "--output",
            str(output),
            "--json",
        ],
    )

    assert result.exit_code == 1, result.output
    payload = json.loads(result.output)
    assert payload["schema_version"] == "inferguard-lmcache-merge-ready/v1"
    assert payload["merge_ready"] is False
    assert payload["packets"]["packet_b"]["status"] == "measured"
    assert payload["packets"]["packet_b"]["kv_offload_claim_status"] == "measured"
    assert payload["packets"]["packet_b"]["metric_family_counts"]["l0"] == 1
    assert payload["packets"]["packet_b"]["metric_family_counts"]["l1"] == 1
    assert (
        payload["packets"]["packet_b"]["config"]["vllm_kv_transfer_config"]["kv_connector"]
        == "LMCacheMPConnector"
    )
    assert payload["packets"]["packet_c"]["status"] == "measured"
    assert payload["packets"]["packet_c"]["l2_configured"] is True
    assert payload["packets"]["packet_c"]["metric_family_counts"]["l2"] == 2
    assert payload["packets"]["packet_c"]["config"]["lmcache_env"]["LMCACHE_L2_ADAPTER"] == "fs"
    assert payload["packets"]["packet_c"]["config"]["http_conf_l2_adapter_config"]["adapters"] == [
        "fs"
    ]
    blocker_codes = {item["code"] for item in payload["blockers"]}
    assert "cacheblend_not_measured" in blocker_codes
    assert "repo_dirty" in blocker_codes
    assert "repo_behind_upstream" in blocker_codes
    assert "lmcache_mp_l1_failures_observed" in blocker_codes
    assert {item["code"] for item in payload["blocking_blockers"]} == {
        "cacheblend_not_measured",
        "repo_dirty",
        "repo_behind_upstream",
    }
    assert {item["code"] for item in payload["diagnostic_findings"]} == {
        "lmcache_mp_l1_failures_observed"
    }
    assert payload["repos"]["lmcache"]["dirty"] is True
    assert payload["repos"]["sglang"]["behind"] == 1
    assert output.exists()


def test_lmcache_merge_ready_cli_treats_l1_capacity_failures_as_diagnostic(
    tmp_path: Path,
) -> None:
    packet_b = _write_packet_b(tmp_path)
    packet_c = _write_packet_c(tmp_path)
    _write_json(
        packet_b / "lmcache-packet" / "lmcache_cacheblend_boundary_evidence.json",
        {
            "present": True,
            "claim_status": "measured",
            "row_count": 672,
            "event_counts": {
                "report_block_allocation_received": 336,
                "l0_lifecycle_subscriber_processed": 336,
            },
            "stages": [
                "report_block_allocation_received",
                "l0_lifecycle_subscriber_processed",
            ],
        },
    )
    repo = _git_repo(tmp_path / "repo")

    result = CliRunner().invoke(
        app,
        [
            "lmcache-merge-ready",
            "--packet-b-dir",
            str(packet_b),
            "--packet-c-dir",
            str(packet_c),
            "--repo",
            f"repo={repo}",
            "--require-cacheblend",
            "--json",
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["merge_ready"] is True
    assert payload["blocking_blockers"] == []
    assert {item["code"] for item in payload["diagnostic_findings"]} == {
        "lmcache_mp_l1_failures_observed"
    }
    assert payload["packets"]["packet_b"]["l1_failures"] == 279.0


def test_lmcache_merge_ready_cli_accepts_cacheblend_boundary_evidence(tmp_path: Path) -> None:
    packet_b = _write_packet_b(tmp_path)
    packet_c = _write_packet_c(tmp_path)
    _write_json(
        packet_b / "lmcache-packet" / "lmcache_cacheblend_boundary_evidence.json",
        {
            "present": True,
            "claim_status": "measured",
            "row_count": 672,
            "event_counts": {"l0_lifecycle_subscriber_processed": 336},
            "stages": ["l0_lifecycle_subscriber_processed"],
        },
    )
    (packet_b / "lmcache_metrics_loaded.prom").write_text(
        "lmcache_mp_l0_block_allocated_blocks_total 11\nlmcache_mp_lookup_hit_tokens_total 5\n",
        encoding="utf-8",
    )
    repo = _git_repo(tmp_path / "repo")

    result = CliRunner().invoke(
        app,
        [
            "lmcache-merge-ready",
            "--packet-b-dir",
            str(packet_b),
            "--packet-c-dir",
            str(packet_c),
            "--repo",
            f"repo={repo}",
            "--require-cacheblend",
            "--json",
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    packet_b_payload = payload["packets"]["packet_b"]
    assert packet_b_payload["cacheblend_measured"] is True
    assert packet_b_payload["cacheblend_boundary_evidence"]["claim_status"] == "measured"
    assert packet_b_payload["cacheblend_boundary_evidence"]["row_count"] == 672


def test_lmcache_merge_ready_cli_passes_when_required_evidence_is_clean(tmp_path: Path) -> None:
    packet_b = _write_packet_b(tmp_path)
    packet_c = _write_packet_c(tmp_path)
    (packet_b / "lmcache_metrics_loaded.prom").write_text(
        "lmcache_mp_l0_block_allocated_blocks_total 11\n"
        "lmcache_mp_lookup_hit_tokens_total 5\n"
        "lmcache_blend_l0_gpu_transfer_tokens_total 17\n",
        encoding="utf-8",
    )
    repo = _git_repo(tmp_path / "repo")

    result = CliRunner().invoke(
        app,
        [
            "lmcache-merge-ready",
            "--packet-b-dir",
            str(packet_b),
            "--packet-c-dir",
            str(packet_c),
            "--repo",
            f"repo={repo}",
            "--require-cacheblend",
            "--json",
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["merge_ready"] is True
    assert payload["blockers"] == []
    assert payload["packets"]["packet_b"]["cacheblend_measured"] is True

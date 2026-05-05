import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
RUNNER = REPO_ROOT / "scripts" / "run_neocloud_nvidia_profile.py"
FIXTURES = Path(__file__).resolve().parent / "fixtures" / "run_dirs"
OVERRIDES = Path(__file__).resolve().parent / "fixtures" / "overrides" / "operator_supplied.json"
BUNDLE = REPO_ROOT / "docs" / "customer-packages" / "02-2026-05-04-gmi-engineer-turnkey-measurement-bundle"


def copy_fixture(tmp_path: Path, name: str) -> Path:
    src = FIXTURES / name
    dst = tmp_path / name
    shutil.copytree(src, dst)
    return dst


def run_validate(root: Path, *extra: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            str(RUNNER),
            "validate-completed",
            "--results-root",
            str(root),
            *extra,
        ],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )


def load_report(root: Path) -> dict:
    return json.loads((root / "validation_report.json").read_text(encoding="utf-8"))


def iter_downgrades(report: dict) -> list[dict]:
    return [downgrade for job in report["jobs"] for downgrade in job["downgrades"]]


def read_bundle_text(*parts: str) -> str:
    path = BUNDLE.joinpath(*parts)
    if not path.exists():
        pytest.skip(f"sibling FIX-1 owns missing GMI bundle artifact: {path}")
    return path.read_text(encoding="utf-8")


def test_simulate_only_run_is_synthetic(tmp_path: Path) -> None:
    root = copy_fixture(tmp_path, "synthetic_only")
    completed = run_validate(root)

    assert completed.returncode == 0, completed.stderr
    report = load_report(root)
    assert report["status"] == "synthetic_only"
    assert report["summary"]["synthetic_only"] >= 1
    assert all(job["claim_status"] == "synthetic" for job in report["jobs"])


def test_complete_live_run(tmp_path: Path) -> None:
    root = copy_fixture(tmp_path, "live_complete")
    completed = run_validate(root)

    assert completed.returncode == 0, completed.stderr
    report = load_report(root)
    assert report["status"] == "live_complete"
    assert all(job["claim_status"] == "measured" for job in report["jobs"])


def test_missing_engine_metrics(tmp_path: Path) -> None:
    root = copy_fixture(tmp_path, "live_incomplete_no_engine_metrics")
    completed = run_validate(root)

    assert completed.returncode == 0, completed.stderr
    report = load_report(root)
    assert report["status"] == "live_incomplete"
    assert all(job["claim_status"] == "not_proven" for job in report["jobs"])
    assert any(
        downgrade["claim_id"] == "engine_metrics" and downgrade["to"] == "not_proven"
        for downgrade in iter_downgrades(report)
    )


def test_missing_contract(tmp_path: Path) -> None:
    root = copy_fixture(tmp_path, "missing_contract")
    completed = run_validate(root)

    assert completed.returncode == 0, completed.stderr
    report = load_report(root)
    assert report["status"] == "missing_required_artifacts"
    assert all(job["claim_status"] == "not_proven" for job in report["jobs"])


@pytest.mark.parametrize(
    "payload",
    [
        '{"schema_version":"inferguard-gmi-dsv4-artifact-contract/v1","per_job":[{"job_id":"job-live"',
        '{"schema_version":"inferguard-gmi-dsv4-artifact-contract/v1","per_job":[',
        '{"schema_version":"inferguard-gmi-dsv4-artifact-contract/v1","mvp_required_paths":{"request_profile":',
    ],
)
def test_validate_completed_truncated_contract_downgrades_without_crash(
    tmp_path: Path,
    payload: str,
) -> None:
    root = copy_fixture(tmp_path, "live_complete")
    (root / "expected_artifact_contract.json").write_text(payload, encoding="utf-8")

    completed = run_validate(root)

    assert completed.returncode == 0, completed.stderr
    report = load_report(root)
    assert report["status"] == "not_publishable"
    assert any(
        downgrade["claim_id"] == "artifact_contract" and downgrade["to"] == "not_proven"
        for downgrade in iter_downgrades(report)
    )
    assert all(job["claim_status"] == "not_proven" for job in report["jobs"])


def test_empty_request_profile_blocks_live_complete(tmp_path: Path) -> None:
    root = copy_fixture(tmp_path, "live_complete")
    for path in root.glob("jobs/*/request_profile/requests_profile.jsonl"):
        path.write_text("", encoding="utf-8")

    completed = run_validate(root)

    assert completed.returncode == 0, completed.stderr
    report = load_report(root)
    assert report["status"] == "live_incomplete"
    assert all(job["claim_status"] == "not_proven" for job in report["jobs"])
    assert any(
        downgrade["claim_id"] == "request_profile"
        and downgrade["reason"] == "no_successful_request_profile_rows"
        for downgrade in iter_downgrades(report)
    )


def test_failed_healthcheck_blocks_live_complete(tmp_path: Path) -> None:
    root = copy_fixture(tmp_path, "live_complete")
    for path in root.glob("jobs/*/launch/healthcheck.json"):
        payload = json.loads(path.read_text(encoding="utf-8"))
        payload.update({"ok": False, "status": "failed", "status_code": 500})
        path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    completed = run_validate(root)

    assert completed.returncode == 0, completed.stderr
    report = load_report(root)
    assert report["status"] == "live_incomplete"
    assert all(job["claim_status"] == "not_proven" for job in report["jobs"])
    assert any(
        downgrade["claim_id"] == "launch_healthcheck"
        and downgrade["reason"] == "launch_healthcheck_not_successful"
        for downgrade in iter_downgrades(report)
    )


def test_multi_node_no_nccl(tmp_path: Path) -> None:
    root = copy_fixture(tmp_path, "multi_node_no_nccl")
    plan_path = root / "matrix_plan.json"
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    plan["jobs"][0]["env"] = {"GMI_SLURM_NODES": "2"}
    plan_path.write_text(json.dumps(plan, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (root / "jobs" / "job-live" / "operator_profile.json").unlink()
    (root / "jobs" / "job-live" / "manifests" / "operator_profile.json").unlink()
    completed = run_validate(root)

    assert completed.returncode == 0, completed.stderr
    report = load_report(root)
    assert any(
        downgrade["claim_id"] == "multi_node_throughput" and downgrade["to"] == "not_proven"
        for downgrade in iter_downgrades(report)
    )


def test_synthetic_marker_blocks_live(tmp_path: Path) -> None:
    root = copy_fixture(tmp_path, "mixed_synthetic_marker")
    completed = run_validate(root)

    assert completed.returncode == 0, completed.stderr
    report = load_report(root)
    assert report["status"] in {"synthetic_only", "not_publishable"}
    if report["status"] == "not_publishable":
        assert all(job["claim_status"] == "not_proven" for job in report["jobs"])


def test_stdout_summary_format(tmp_path: Path) -> None:
    root = copy_fixture(tmp_path, "live_complete")
    completed = run_validate(root, "--json-only")

    assert completed.returncode == 0, completed.stderr
    assert re.match(
        r"^inferguard validate-completed: status=\w+ jobs=\d+ live=\d+ synthetic=\d+ incomplete=\d+ missing=\d+\n$",
        completed.stdout,
    )


def test_strict_exit_code(tmp_path: Path) -> None:
    root = copy_fixture(tmp_path, "live_incomplete_no_engine_metrics")
    completed = run_validate(root, "--strict")

    assert completed.returncode == 1


def test_schema_version_locked(tmp_path: Path) -> None:
    root = copy_fixture(tmp_path, "live_complete")
    completed = run_validate(root)

    assert completed.returncode == 0, completed.stderr
    report = load_report(root)
    assert report["schema_version"] == "inferguard-validation-report/v1"


def test_label_overrides(tmp_path: Path) -> None:
    root = copy_fixture(tmp_path, "live_complete")
    completed = run_validate(root, "--label-overrides", str(OVERRIDES))

    assert completed.returncode == 0, completed.stderr
    report = load_report(root)
    assert any(
        downgrade["claim_id"] == "kv_cache_benefit"
        and downgrade["from"] == "measured"
        and downgrade["to"] == "inferred"
        and downgrade["reason"] == "operator_review_pending"
        for downgrade in iter_downgrades(report)
    )


def test_review_blocker_1_rdma_fabric_gating(tmp_path: Path) -> None:
    root = copy_fixture(tmp_path, "live_complete")
    job_dir = root / "jobs" / "job-live"
    for rel in ("operator_profile.json", "manifests/operator_profile.json"):
        path = job_dir / rel
        profile = json.loads(path.read_text(encoding="utf-8"))
        profile["network_fabric"] = "eth"
        path.write_text(json.dumps(profile, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (job_dir / "preflight" / "ib_state.txt").unlink()

    completed = run_validate(root)

    assert completed.returncode == 0, completed.stderr
    report = load_report(root)
    assert report["status"] == "live_complete"
    assert not any(downgrade["claim_id"] == "rdma_health" for downgrade in iter_downgrades(report))


def test_review_blocker_2_slurm_job_num_nodes_triggers_multi_node_checks(tmp_path: Path) -> None:
    root = copy_fixture(tmp_path, "live_complete")
    plan_path = root / "matrix_plan.json"
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    plan["jobs"][0]["env"] = {"SLURM_JOB_NUM_NODES": "4"}
    plan_path.write_text(json.dumps(plan, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    completed = run_validate(root)

    assert completed.returncode == 0, completed.stderr
    report = load_report(root)
    downgrades = iter_downgrades(report)
    assert any(downgrade["claim_id"] == "multi_node_throughput" for downgrade in downgrades)
    assert any(
        downgrade["claim_id"] == "node_count_detection"
        and downgrade["to"] == "inferred"
        and "SLURM_JOB_NUM_NODES=4" in downgrade["reason"]
        for downgrade in downgrades
    )


def test_review_blocker_3_status_precedence_keeps_not_publishable(tmp_path: Path) -> None:
    root = copy_fixture(tmp_path, "mixed_synthetic_marker")
    contract_path = root / "expected_artifact_contract.json"
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    contract["matrix_level"].append("handoff.md")
    contract_path.write_text(json.dumps(contract, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    completed = run_validate(root)

    assert completed.returncode == 0, completed.stderr
    report = load_report(root)
    assert report["status"] == "not_publishable"
    assert any(downgrade["claim_id"] == "matrix_level" for downgrade in iter_downgrades(report))


def test_review_blocker_4_slurm_env_matrix_row(tmp_path: Path) -> None:
    root = copy_fixture(tmp_path, "live_complete")
    (root / "jobs" / "job-live" / "slurm_env.json").unlink()

    completed = run_validate(root)

    assert completed.returncode == 0, completed.stderr
    report = load_report(root)
    assert any(downgrade["claim_id"] == "slurm_env" for downgrade in iter_downgrades(report))


def test_review_blocker_4_gpu_inventory_matrix_row(tmp_path: Path) -> None:
    root = copy_fixture(tmp_path, "live_complete")
    (root / "jobs" / "job-live" / "gpu_inventory.json").unlink()

    completed = run_validate(root)

    assert completed.returncode == 0, completed.stderr
    report = load_report(root)
    assert any(downgrade["claim_id"] == "gpu_inventory" for downgrade in iter_downgrades(report))


def test_review_blocker_4_gpu_topology_matrix_row(tmp_path: Path) -> None:
    root = copy_fixture(tmp_path, "live_complete")
    (root / "jobs" / "job-live" / "gpu_topology.txt").unlink()

    completed = run_validate(root)

    assert completed.returncode == 0, completed.stderr
    report = load_report(root)
    assert any(downgrade["claim_id"] == "gpu_topology" for downgrade in iter_downgrades(report))


def test_review_blocker_4_agentx_ingest_summary_matrix_row(tmp_path: Path) -> None:
    root = copy_fixture(tmp_path, "live_complete")
    (root / "jobs" / "job-live" / "agentx_ingest_summary.json").unlink()

    completed = run_validate(root)

    assert completed.returncode == 0, completed.stderr
    report = load_report(root)
    assert any(downgrade["claim_id"] == "agentx_ingest_summary" for downgrade in iter_downgrades(report))


def test_review_blocker_5_long_context_templates_fail_loud() -> None:
    for name in (
        "h200-vllm-dsv4-flash-long-context.sbatch",
        "h200-sglang-dsv4-flash-long-context.sbatch",
        "b200-vllm-dsv4-pro-long-context.sbatch",
        "b200-sglang-dsv4-pro-long-context.sbatch",
    ):
        text = read_bundle_text("slurm", name)
        assert 'EXPECTED_INPUT_TOKENS="${EXPECTED_INPUT_TOKENS:-131072}"' in text
        assert "median_input_tokens" in text
        assert "LONG_CONTEXT_SANITY_FAILED" in text


def test_review_drift_6_gb200_sglang_template_flags() -> None:
    text = read_bundle_text("slurm", "gb200-sglang-dsv4-fp4.sbatch")
    assert "--tool-call-parser deepseekv31" in text
    assert "--reasoning-parser deepseek-v3" in text
    assert "deepseekv4" not in text
    assert "deepseek-v4" not in text
    assert "GMI commonly exposes GB200 NVL72 as 9 Slurm nodes x 8 GPUs" in text


def test_review_drift_7_b200_vllm_templates_enable_chunked_prefill() -> None:
    paths = sorted((BUNDLE / "slurm").glob("b200-vllm-*.sbatch"))
    if not paths:
        pytest.skip("sibling FIX-1 owns missing GMI bundle b200-vllm sbatch artifacts")
    for path in paths:
        assert "--enable-chunked-prefill" in path.read_text(encoding="utf-8")


def test_review_drift_8_prometheus_has_no_phantom_lmcache_scrape() -> None:
    text = read_bundle_text("monitoring", "prometheus.yaml")
    assert "lmcache-internal" not in text
    assert "127.0.0.1:8080" not in text
    assert "LMCacheConnectorV1 metrics surface here with the lmcache: prefix" in text


def test_review_drift_9_gmi_go_propagates_validate_exit_code() -> None:
    text = read_bundle_text("gmi-go.sh")
    assert "validate-completed" in text
    assert "--strict" in text
    assert "VALIDATE_EXIT=$?" in text
    assert "validation_report.md" in text
    assert "validate-completed --provider gmi --results-root \"$RESULTS_ROOT\" --output-dir \"$RESULTS_ROOT/analysis\" --json-only || true" not in text

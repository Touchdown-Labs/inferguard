import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

from inferguard.diagnose_bottleneck import (
    BOTTLENECK_DIAGNOSIS_SCHEMA_VERSION,
    diagnose,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
RUNNER = REPO_ROOT / "scripts" / "run_neocloud_nvidia_profile.py"
FIXTURES = Path(__file__).resolve().parent / "fixtures" / "job_dirs"


def _diagnosis(name: str) -> dict:
    return diagnose(FIXTURES / name).to_dict()


def test_prefill_bound_fixture() -> None:
    diagnosis = _diagnosis("prefill_bound")

    assert diagnosis["verdict"] == "prefill_bound"
    assert diagnosis["claim_status"] == "measured"


def test_decode_bound_fixture() -> None:
    diagnosis = _diagnosis("decode_bound")

    assert diagnosis["verdict"] == "decode_bound"


def test_queue_bound_fixture() -> None:
    diagnosis = _diagnosis("queue_bound")

    assert diagnosis["verdict"] == "queue_bound"


def test_kv_bound_fixture() -> None:
    diagnosis = _diagnosis("kv_bound")

    assert diagnosis["verdict"] == "kv_bound"


def test_network_bound_fixture() -> None:
    diagnosis = _diagnosis("network_bound")

    assert diagnosis["verdict"] == "network_bound"
    assert any("nccl" in path for path in diagnosis["evidence_paths"])


def test_network_bound_reads_locked_nccl_text_path(tmp_path: Path) -> None:
    root = tmp_path / "network_text"
    shutil.copytree(FIXTURES / "network_bound", root)
    shutil.rmtree(root / "nccl")
    preflight = root / "preflight"
    preflight.mkdir()
    (preflight / "nccl_all_reduce.txt").write_text(
        "# all_reduce_perf\nbusbw: 220\nexpected_busbw_gbps: 500\n",
        encoding="utf-8",
    )

    diagnosis = diagnose(root).to_dict()

    assert diagnosis["verdict"] == "network_bound"
    assert any("preflight/nccl_all_reduce.txt" in path for path in diagnosis["evidence_paths"])


def test_host_bound_fixture() -> None:
    diagnosis = _diagnosis("host_bound")

    assert diagnosis["verdict"] == "host_bound"


def test_missing_engine_metrics_no_verdict() -> None:
    diagnosis = _diagnosis("no_engine_metrics")

    assert diagnosis["verdict"] == "not_enough_evidence"
    assert diagnosis["claim_status"] == "not_proven"


def test_multi_node_no_nccl_no_network_verdict() -> None:
    diagnosis = _diagnosis("multi_node_no_nccl")

    assert diagnosis["verdict"] != "network_bound"
    assert diagnosis["verdict"] == "not_enough_evidence"
    assert diagnosis["claim_status"] == "not_proven"


def test_sglang_b200_fp8_no_prefill_verdict() -> None:
    diagnosis = _diagnosis("sglang_b200_fp8_high_ttft")

    assert diagnosis["verdict"] != "prefill_bound"
    assert any(
        downgrade["reason"].startswith("sglang_chunked_prefill_bug")
        for downgrade in diagnosis.get("downgrades", [])
    )


def test_failed_launch_overrides() -> None:
    diagnosis = _diagnosis("model_launch_bound")

    assert diagnosis["verdict"] == "model_launch_bound"


def test_external_validated_healthcheck_is_not_launch_bound(tmp_path: Path) -> None:
    root = tmp_path / "external_validated"
    shutil.copytree(FIXTURES / "prefill_bound", root)
    healthcheck_path = root / "launch" / "healthcheck.json"
    healthcheck = json.loads(healthcheck_path.read_text(encoding="utf-8"))
    healthcheck["status"] = "external_validated"
    healthcheck_path.write_text(json.dumps(healthcheck, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    diagnosis = diagnose(root).to_dict()

    assert diagnosis["verdict"] == "prefill_bound"


def test_not_enough_fixture() -> None:
    diagnosis = _diagnosis("not_enough_evidence")

    assert diagnosis["verdict"] == "not_enough_evidence"


def test_schema_version_locked() -> None:
    diagnosis = _diagnosis("prefill_bound")

    assert diagnosis["schema_version"] == BOTTLENECK_DIAGNOSIS_SCHEMA_VERSION


def test_stdout_summary_format(tmp_path: Path) -> None:
    output_dir = tmp_path / "diagnosis"
    completed = subprocess.run(
        [
            sys.executable,
            str(RUNNER),
            "diagnose-bottleneck",
            "--job-dir",
            str(FIXTURES / "prefill_bound"),
            "--output-dir",
            str(output_dir),
        ],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    assert re.match(
        r"^inferguard diagnose-bottleneck: verdict=\w+ confidence=[\d.]+ evidence_paths=\d+ claim=\w+\n$",
        completed.stdout,
    )
    diagnosis = json.loads((output_dir / "bottleneck_diagnosis.json").read_text(encoding="utf-8"))
    assert diagnosis["verdict"] == "prefill_bound"


def test_evidence_attached() -> None:
    diagnosis = _diagnosis("prefill_bound")

    assert diagnosis["evidence_paths"]
    assert diagnosis["metric_values"]
    assert len(diagnosis["primary_evidence"]) >= 1
    for entry in diagnosis["primary_evidence"]:
        assert entry["metric"]
        assert entry["source"]
        assert "value" in entry or "value_p95" in entry

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

from inferguard.report_completed import build_recommendation
from inferguard.report_completed.render import render_markdown
from inferguard.report_completed.types import OPERATOR_RECOMMENDATION_SCHEMA_VERSION

REPO_ROOT = Path(__file__).resolve().parents[3]
RUNNER = REPO_ROOT / "scripts" / "run_neocloud_nvidia_profile.py"
FIXTURES = Path(__file__).resolve().parent / "fixtures" / "run_dirs"


def copy_fixture(tmp_path: Path, name: str) -> Path:
    src = FIXTURES / name
    dst = tmp_path / name
    shutil.copytree(src, dst)
    return dst


def recommendation(root: Path) -> dict:
    return build_recommendation(root).to_dict()


def run_report_completed(root: Path, *extra: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            str(RUNNER),
            "report-completed",
            "--results-root",
            str(root),
            *extra,
        ],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )


def test_synthetic_only_refuses(tmp_path: Path) -> None:
    root = copy_fixture(tmp_path, "synthetic_only")
    rec = recommendation(root)

    assert rec["executive_verdict"] == "harness validation only — no live evidence"
    assert rec["executive_verdict_status"] == "synthetic_only"
    assert rec["best_gpu_sku"]["value"] is None
    assert rec["best_engine"]["value"] is None
    assert rec["best_gpu_sku"]["claim_status"] in {"synthetic", "not_proven"}


def test_single_sku_no_recommendation(tmp_path: Path) -> None:
    root = copy_fixture(tmp_path, "live_complete_h200_only")
    rec = recommendation(root)

    assert rec["best_gpu_sku"]["value"] is None
    assert rec["best_gpu_sku"]["claim_status"] == "not_proven"


def test_two_sku_comparison(tmp_path: Path) -> None:
    root = copy_fixture(tmp_path, "live_complete_h200_vs_b200")
    rec = recommendation(root)

    assert rec["best_gpu_sku"]["value"] in {"H200", "B200"}
    assert rec["best_gpu_sku"]["claim_status"] == "measured"


def test_no_lmcache_metrics_no_verdict(tmp_path: Path) -> None:
    root = copy_fixture(tmp_path, "live_complete")
    rec = recommendation(root)

    assert rec["lmcache_verdict"]["value"] is None
    assert rec["lmcache_verdict"]["claim_status"] == "not_proven"


def test_sglang_only_no_lmcache_verdict(tmp_path: Path) -> None:
    root = copy_fixture(tmp_path, "sglang_only")
    rec = recommendation(root)

    assert rec["lmcache_verdict"]["value"] is None
    assert rec["lmcache_verdict"]["claim_status"] == "not_proven"


def test_lmcache_verdict_with_metrics(tmp_path: Path) -> None:
    root = copy_fixture(tmp_path, "live_complete_with_lmcache")
    rec = recommendation(root)

    assert rec["lmcache_verdict"]["value"] in {"helpful", "harmful"}
    assert rec["lmcache_verdict"]["claim_status"] == "measured"


def test_no_cost_input_refuses_cost(tmp_path: Path) -> None:
    root = copy_fixture(tmp_path, "live_complete")
    rec = recommendation(root)

    assert rec["cost_notes"]["cost_per_million_completion_tokens_usd"] is None
    assert rec["cost_notes"]["claim_status"] == "not_proven"


def test_truncated_validation_report_downgrades_without_crash(tmp_path: Path) -> None:
    root = copy_fixture(tmp_path, "live_complete")
    (root / "validation_report.json").write_text(
        '{"status":"live_complete","jobs":[', encoding="utf-8"
    )

    rec = recommendation(root)

    assert rec["executive_verdict_status"] == "not_enough_evidence"
    assert rec["claim_status"] == "not_proven"


def test_gb200_no_nccl_refuses(tmp_path: Path) -> None:
    root = copy_fixture(tmp_path, "gb200_no_nccl")
    rec = recommendation(root)

    assert rec["gb200_justification"]["claim_status"] == "not_proven"


def test_claim_table_completeness(tmp_path: Path) -> None:
    root = copy_fixture(tmp_path, "live_complete")
    rec = recommendation(root)
    claims = {claim["claim_id"]: claim for claim in rec["claim_table"]}

    assert {
        "executive_verdict",
        "best_gpu_sku",
        "best_engine",
        "best_model_config",
        "bottleneck",
        "capacity_envelope",
        "failure_summary",
        "cost_notes",
        "lmcache_verdict",
        "gb200_justification",
    } <= set(claims)
    assert all(
        claim["evidence_paths"] for claim in claims.values() if claim["status"] == "measured"
    )


def test_strict_exit_code(tmp_path: Path) -> None:
    root = copy_fixture(tmp_path, "missing_metrics")
    completed = run_report_completed(root, "--strict")

    assert completed.returncode == 1


def test_stdout_summary_format(tmp_path: Path) -> None:
    root = copy_fixture(tmp_path, "live_complete")
    completed = run_report_completed(root)

    assert completed.returncode == 0, completed.stderr
    assert re.match(
        r"^inferguard report-completed: status=\w+ sku=\S+ engine=\S+ bottleneck=\w+ claim=\w+\n$",
        completed.stdout,
    )


def test_schema_version_locked(tmp_path: Path) -> None:
    root = copy_fixture(tmp_path, "live_complete")
    completed = run_report_completed(root)

    assert completed.returncode == 0, completed.stderr
    rec = json.loads((root / "report" / "operator_recommendation.json").read_text(encoding="utf-8"))
    assert rec["schema_version"] == OPERATOR_RECOMMENDATION_SCHEMA_VERSION


def test_live_complete_fixture_recommends_sku_and_engine(tmp_path: Path) -> None:
    root = copy_fixture(tmp_path, "live_complete")
    rec = recommendation(root)

    assert rec["executive_verdict_status"] == "live_complete"
    assert rec["best_gpu_sku"]["value"] in {"H200", "B200"}
    assert rec["best_engine"]["value"] in {"vllm", "sglang"}
    assert rec["cost_notes"]["claim_status"] == "not_proven"


def test_markdown_has_eleven_sections_and_evidence_appendix(tmp_path: Path) -> None:
    root = copy_fixture(tmp_path, "live_complete_with_artifacts")
    rec = build_recommendation(root)
    data = rec.to_dict()
    md = render_markdown(rec)

    assert len(data["sections"]) == 11
    assert "## Evidence artifacts" in md
    assert data["evidence_artifacts"]
    assert "[measured]" in md

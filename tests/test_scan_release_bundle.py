import json
import shutil
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from scan_release_bundle import scan_release_bundle  # noqa: E402

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "run_dirs"


def copy_fixture(tmp_path: Path, name: str) -> Path:
    dst = tmp_path / name
    shutil.copytree(FIXTURES / name, dst)
    return dst


def test_accepts_live_complete_proof_bundle(tmp_path: Path) -> None:
    root = copy_fixture(tmp_path, "live_complete")

    result = scan_release_bundle(root)

    assert result.ok, result.format_errors()
    assert result.status == "live_complete"


def test_rejects_synthetic_only(tmp_path: Path) -> None:
    root = copy_fixture(tmp_path, "synthetic_only")

    result = scan_release_bundle(root)

    assert not result.ok
    assert result.status == "synthetic_only"


def test_rejects_live_incomplete(tmp_path: Path) -> None:
    root = copy_fixture(tmp_path, "live_incomplete_no_engine_metrics")

    result = scan_release_bundle(root)

    assert not result.ok
    assert result.status == "live_incomplete"


def test_rejects_missing_required_artifacts(tmp_path: Path) -> None:
    root = copy_fixture(tmp_path, "missing_metrics")

    result = scan_release_bundle(root)

    assert not result.ok
    assert result.status == "missing_required_artifacts"
    assert result.missing_artifacts


def test_rejects_not_publishable(tmp_path: Path) -> None:
    root = copy_fixture(tmp_path, "mixed_synthetic_marker")
    contract_path = root / "expected_artifact_contract.json"
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    contract["matrix_level"].append("handoff.md")
    contract_path.write_text(
        json.dumps(contract, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    result = scan_release_bundle(root)

    assert not result.ok
    assert result.status == "not_publishable"

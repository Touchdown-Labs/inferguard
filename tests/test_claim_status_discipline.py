from __future__ import annotations

import json
import re
import shutil
from pathlib import Path
from typing import Any

from inferguard.cost_model import compute_cost
from inferguard.find_cliffs import find_cliffs
from inferguard.validate import validate_run

REPO_ROOT = Path(__file__).resolve().parents[3]
PACKAGE_ROOT = REPO_ROOT / "oss" / "inferguard"
SRC_ROOT = PACKAGE_ROOT / "src" / "inferguard"
FIXTURES = PACKAGE_ROOT / "tests" / "fixtures"
ALLOWED_CLAIM_STATUS = {"synthetic", "inferred", "measured", "not_proven"}


def test_source_claim_status_literals_are_canonical() -> None:
    bad: list[str] = []
    for py in SRC_ROOT.rglob("*.py"):
        text = py.read_text(encoding="utf-8")
        for match in re.finditer(r"claim_status\s*[=:]\s*['\"](\w+)['\"]", text):
            value = match.group(1)
            if value not in ALLOWED_CLAIM_STATUS:
                line = text[: match.start()].count("\n") + 1
                bad.append(f"{py.relative_to(REPO_ROOT)}:{line}: claim_status={value!r}")

    assert bad == []


def test_emitted_artifact_claim_status_values_are_canonical(tmp_path: Path) -> None:
    live_root = _copy_fixture(tmp_path, "run_dirs/live_complete")
    validation = validate_run(live_root).to_dict()
    (live_root / "validation_report.json").write_text(
        json.dumps(validation, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    cost_report = compute_cost(
        live_root,
        FIXTURES / "cost_inputs" / "gmi_b200_per_hour.json",
        slo_ttft_ms=500,
        slo_e2e_ms=5000,
    ).to_dict()

    not_publishable_root = _copy_fixture(tmp_path, "run_dirs/mixed_synthetic_marker")
    not_publishable_validation = validate_run(not_publishable_root).to_dict()

    cliffs_root = _copy_fixture(tmp_path, "sweep_dirs/concurrency_p99_sweep")
    (cliffs_root / "validation_report.json").write_text(
        json.dumps({"status": "live_complete"}, indent=2) + "\n",
        encoding="utf-8",
    )
    cliffs = find_cliffs(cliffs_root).to_dict()

    bad = []
    for label, artifact in (
        ("validation_live", validation),
        ("cost_report", cost_report),
        ("validation_not_publishable", not_publishable_validation),
        ("capacity_cliffs", cliffs),
    ):
        bad.extend(_noncanonical_claim_statuses(artifact, label))

    assert bad == []


def _copy_fixture(tmp_path: Path, rel: str) -> Path:
    src = FIXTURES / rel
    dst = tmp_path / rel.replace("/", "_")
    shutil.copytree(src, dst)
    return dst


def _noncanonical_claim_statuses(value: Any, path: str) -> list[str]:
    bad: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = f"{path}.{key}"
            if key == "claim_status" and child not in ALLOWED_CLAIM_STATUS:
                bad.append(f"{child_path}={child!r}")
            bad.extend(_noncanonical_claim_statuses(child, child_path))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            bad.extend(_noncanonical_claim_statuses(child, f"{path}[{index}]"))
    return bad

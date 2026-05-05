"""Public entry point for PRD §4.8 ``find-cliffs``."""

from __future__ import annotations

from dataclasses import dataclass
from dataclasses import replace
from pathlib import Path
from typing import Any

from inferguard.io import atomic_write_json, load_json_object

from .detectors import SweepCell, detect_all_cliffs, summary_from_cliffs
from .render import render_capacity_cliffs_markdown
from .types import (
    CAPACITY_CLIFF_NAMES,
    CAPACITY_CLIFFS_SCHEMA_VERSION,
    CapacityCliffs,
    Cliff,
    EvidenceRef,
)

CAPACITY_CLIFFS_JSON = "capacity_cliffs.json"
CAPACITY_CLIFFS_MARKDOWN = "capacity_cliffs.md"
_LIVE_COMPLETE_REQUIRED_REASON = (
    "validation_report.status is not live_complete; capacity cliffs are inferred until "
    "validate-completed proves live request, healthcheck, engine, and GPU evidence"
)


@dataclass(frozen=True)
class FindCliffsOptions:
    """Operator-supplied `find-cliffs` options."""

    cliffs: tuple[str, ...] = CAPACITY_CLIFF_NAMES
    ttft_p99_floor_ms: float = 1000.0
    success_rate_floor: float = 0.95


def find_cliffs(
    results_root: str | Path,
    opts: FindCliffsOptions | None = None,
) -> CapacityCliffs:
    """Aggregate completed sweep job artifacts into six capacity cliff verdicts."""

    root = Path(results_root).resolve()
    options = opts or FindCliffsOptions()
    _validate_options(options)
    cells = _load_sweep_cells(root)
    cliffs = detect_all_cliffs(
        cells,
        names=options.cliffs,
        ttft_p99_floor_ms=options.ttft_p99_floor_ms,
        success_rate_floor=options.success_rate_floor,
    )
    validation_status = _validation_status(root)
    claim_reason = None
    if validation_status != "live_complete":
        claim_reason = f"{_LIVE_COMPLETE_REQUIRED_REASON} (status={validation_status})"
        cliffs = tuple(_downgrade_measured_cliff(cliff, claim_reason) for cliff in cliffs)
    return CapacityCliffs(
        results_root=str(root),
        cliffs=cliffs,
        summary=summary_from_cliffs(cliffs),
        claim_reason=claim_reason,
    )


def write_capacity_cliffs(
    capacity: CapacityCliffs,
    output_dir: str | Path,
    *,
    write_markdown: bool = True,
) -> tuple[Path, ...]:
    """Write `capacity_cliffs.json` and optional Markdown."""

    target = Path(output_dir)
    target.mkdir(parents=True, exist_ok=True)
    json_path = target / CAPACITY_CLIFFS_JSON
    atomic_write_json(json_path, capacity.to_dict())
    written = [json_path]
    if write_markdown:
        md_path = target / CAPACITY_CLIFFS_MARKDOWN
        md_path.write_text(render_capacity_cliffs_markdown(capacity), encoding="utf-8")
        written.append(md_path)
    return tuple(written)


def format_stdout_summary(capacity: CapacityCliffs) -> str:
    """Return the locked stdout summary line without a trailing newline."""

    summary = capacity.summary
    return (
        "inferguard find-cliffs: "
        f"cliffs_found={summary.get('cliffs_found', 0)} "
        f"max_concurrency={_stdout_value(summary.get('max_concurrency'))} "
        f"max_context={_stdout_value(summary.get('max_context'))} "
        f"claim={capacity.claim_status}"
    )


def _load_sweep_cells(root: Path) -> list[SweepCell]:
    jobs_dir = root / "jobs"
    job_dirs = [path for path in sorted(jobs_dir.iterdir()) if path.is_dir()] if jobs_dir.exists() else []
    cells: list[SweepCell] = []
    for job_dir in job_dirs:
        paths = _artifact_paths(root, job_dir)
        operator_path = _first_existing(job_dir / "operator_profile.json", job_dir / "manifests" / "operator_profile.json")
        request_path = _first_existing(
            job_dir / "request_profile" / "requests_summary.json",
            job_dir / "request_profile" / "request_summary.json",
        )
        metrics_path = _first_existing(
            job_dir / "metrics" / "metrics_summary.json",
            job_dir / "collect_metrics" / "metrics_summary.json",
        )
        failure_path = _first_existing(
            job_dir / "diagnosis" / "failure_classification.json",
            job_dir / "classify_failures" / "failure_classification.json",
        )
        diagnosis_path = _first_existing(
            job_dir / "diagnosis" / "bottleneck_diagnosis.json",
            job_dir / "diagnose_bottleneck" / "bottleneck_diagnosis.json",
        )
        paths.update(
            {
                "operator_profile": _maybe_rel(operator_path, root),
                "request_summary": _maybe_rel(request_path, root),
                "metrics_summary": _maybe_rel(metrics_path, root),
                "failure_classification": _maybe_rel(failure_path, root),
                "bottleneck_diagnosis": _maybe_rel(diagnosis_path, root),
            }
        )
        paths = {key: value for key, value in paths.items() if value}
        cells.append(
            SweepCell(
                job_id=_job_id(job_dir, operator_path, request_path),
                job_dir=job_dir,
                rel_dir=_rel(job_dir, root),
                operator_profile=_read_json(operator_path),
                request_summary=_read_json(request_path),
                metrics_summary=_read_json(metrics_path),
                failure_classification=_read_json(failure_path),
                bottleneck_diagnosis=_read_json(diagnosis_path),
                paths=paths,
            )
        )
    return cells


def _artifact_paths(root: Path, job_dir: Path) -> dict[str, str]:
    paths: dict[str, str] = {}
    for key, rel in (
        ("requests_profile", "request_profile/requests_profile.jsonl"),
        ("engine_metrics_timeline", "metrics/engine_metrics_timeline.jsonl"),
        ("gpu_metrics_timeline", "metrics/gpu_metrics_timeline.jsonl"),
    ):
        path = job_dir / rel
        if path.exists():
            paths[key] = _rel(path, root)
    return paths


def _job_id(job_dir: Path, operator_path: Path | None, request_path: Path | None) -> str:
    for path in (operator_path, request_path):
        data = _read_json(path)
        job_id = data.get("job_id")
        if job_id:
            return str(job_id)
    return job_dir.name


def _read_json(path: Path | None) -> dict[str, Any]:
    return load_json_object(path) or {}


def _validation_status(root: Path) -> str:
    for path in (
        root / "validation_report.json",
        root / "validate" / "validation_report.json",
        root / "validation" / "validation_report.json",
    ):
        data = load_json_object(path)
        if isinstance(data, dict):
            return str(data.get("status") or "missing_required_artifacts")
    return "missing_required_artifacts"


def _downgrade_measured_cliff(cliff: Cliff, reason: str) -> Cliff:
    if cliff.claim_status != "measured":
        return cliff
    reasoning = f"{cliff.reasoning} claim_caveat={reason}" if cliff.reasoning else reason
    return replace(cliff, claim_status="inferred", reasoning=reasoning)


def _validate_options(options: FindCliffsOptions) -> None:
    unknown = [name for name in options.cliffs if name not in CAPACITY_CLIFF_NAMES]
    if unknown:
        raise ValueError(f"unsupported cliff name(s): {', '.join(unknown)}")
    if options.ttft_p99_floor_ms <= 0:
        raise ValueError("ttft_p99_floor_ms must be positive")
    if not 0 < options.success_rate_floor <= 1:
        raise ValueError("success_rate_floor must be > 0 and <= 1")


def _first_existing(*paths: Path) -> Path | None:
    for path in paths:
        if path.exists():
            return path
    return None


def _maybe_rel(path: Path | None, root: Path) -> str | None:
    return _rel(path, root) if path else None


def _rel(path: Path, root: Path) -> str:
    resolved = path.resolve()
    try:
        return str(resolved.relative_to(root))
    except ValueError:
        return str(resolved)


def _stdout_value(value: Any) -> str:
    return "null" if value is None else str(value)


__all__ = [
    "CAPACITY_CLIFFS_JSON",
    "CAPACITY_CLIFFS_MARKDOWN",
    "CAPACITY_CLIFFS_SCHEMA_VERSION",
    "FindCliffsOptions",
    "CapacityCliffs",
    "Cliff",
    "EvidenceRef",
    "find_cliffs",
    "format_stdout_summary",
    "write_capacity_cliffs",
]

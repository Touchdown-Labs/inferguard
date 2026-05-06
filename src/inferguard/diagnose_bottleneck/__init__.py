"""Public entry point for PRD §4.5 `diagnose-bottleneck`."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from inferguard.diagnose_bottleneck.render import (
    render_bottleneck_diagnosis_markdown,
    render_diagnosis_markdown,
)
from inferguard.diagnose_bottleneck.rules import REQUIRED_INPUT_KEYS, EvidenceBundle, apply_rules
from inferguard.diagnose_bottleneck.types import (
    BOTTLENECK_DIAGNOSIS_SCHEMA_VERSION,
    VERDICT_VALUES,
    BottleneckDiagnosis,
    Downgrade,
    Evidence,
    Verdict,
)
from inferguard.io import atomic_write_json

DIAGNOSIS_JSON_FILENAME = "bottleneck_diagnosis.json"
DIAGNOSIS_MARKDOWN_FILENAME = "bottleneck_diagnosis.md"


def diagnose(
    job_dir: str | Path,
    *,
    validation_report: str | Path | None = None,
    rule_config: str | Path | None = None,
) -> BottleneckDiagnosis:
    """Read a completed job directory and return one bottleneck diagnosis."""

    bundle = _load_evidence_bundle(
        Path(job_dir),
        validation_report=Path(validation_report) if validation_report is not None else None,
        rule_config=Path(rule_config) if rule_config is not None else None,
    )
    return apply_rules(bundle)


def diagnose_job(
    job_dir: str | Path,
    *,
    validation_report: str | Path | None = None,
    rule_config: str | Path | None = None,
) -> BottleneckDiagnosis:
    """Compatibility alias for callers using the PRD prose name."""

    return diagnose(job_dir, validation_report=validation_report, rule_config=rule_config)


def write_diagnosis(
    diagnosis: BottleneckDiagnosis,
    output_dir: str | Path,
    *,
    json_only: bool = False,
) -> tuple[Path, Path | None]:
    """Write JSON and optional markdown diagnosis artifacts."""

    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    json_path = out / DIAGNOSIS_JSON_FILENAME
    atomic_write_json(json_path, diagnosis.to_dict())
    if json_only:
        return json_path, None
    md_path = out / DIAGNOSIS_MARKDOWN_FILENAME
    md_path.write_text(render_diagnosis_markdown(diagnosis), encoding="utf-8")
    return json_path, md_path


def _load_evidence_bundle(
    job_dir: Path,
    *,
    validation_report: Path | None,
    rule_config: Path | None,
) -> EvidenceBundle:
    paths = _paths(job_dir, validation_report)
    parse_errors: dict[str, str] = {}
    request_summary = _read_json(paths["requests_summary"], parse_errors)
    request_rows = _read_jsonl(paths["requests_profile"], parse_errors)
    metrics_summary = _read_json(paths["metrics_summary"], parse_errors)
    lmcache_compat_report = _read_json(
        paths["lmcache_compat_report"], parse_errors, required=False
    )
    engine_rows = _read_jsonl(paths["engine_metrics_timeline"], parse_errors)
    gpu_rows = _read_jsonl(paths["gpu_metrics_timeline"], parse_errors)
    healthcheck = _read_json(paths["healthcheck"], parse_errors, required=False)
    launch_command = _read_json(paths["launch_command"], parse_errors, required=False)
    operator_profile = _read_first_existing_json(
        [
            paths["operator_profile"],
            paths["manifest_operator_profile"],
        ],
        parse_errors,
    )
    validation = _read_json(paths["validation_report"], parse_errors, required=False)
    nccl_summary, nccl_paths = _read_nccl_evidence(job_dir, parse_errors)
    cpu_summary, cpu_path = _read_cpu_summary(job_dir, parse_errors)
    missing = [paths[key] for key in REQUIRED_INPUT_KEYS if not paths[key].exists()]
    for key in REQUIRED_INPUT_KEYS:
        if key in parse_errors and paths[key] not in missing:
            missing.append(paths[key])
    config = _read_json(rule_config, parse_errors, required=False) if rule_config else {}
    return EvidenceBundle(
        job_dir=job_dir,
        paths=paths,
        request_summary=request_summary,
        request_rows=request_rows,
        metrics_summary=metrics_summary,
        engine_rows=engine_rows,
        gpu_rows=gpu_rows,
        healthcheck=healthcheck,
        launch_command=launch_command,
        operator_profile=operator_profile,
        validation_report=validation,
        nccl_summary=nccl_summary,
        nccl_evidence_paths=nccl_paths,
        cpu_summary=cpu_summary,
        cpu_summary_path=cpu_path,
        lmcache_compat_report=lmcache_compat_report,
        missing_required_paths=missing,
        parse_errors=parse_errors,
        rule_config=config,
    )


def _paths(job_dir: Path, validation_report: Path | None) -> dict[str, Path]:
    results_root = _results_root_for_job(job_dir)
    validation = validation_report or (results_root / "validation_report.json")
    return {
        "job_dir": job_dir,
        "requests_profile": job_dir / "request_profile" / "requests_profile.jsonl",
        "requests_summary": job_dir / "request_profile" / "requests_summary.json",
        "engine_metrics_timeline": job_dir / "metrics" / "engine_metrics_timeline.jsonl",
        "gpu_metrics_timeline": job_dir / "metrics" / "gpu_metrics_timeline.jsonl",
        "metrics_summary": job_dir / "metrics" / "metrics_summary.json",
        "lmcache_compat_report": job_dir / "metrics" / "lmcache_compat_report.json",
        "healthcheck": job_dir / "launch" / "healthcheck.json",
        "launch_command": job_dir / "launch" / "command.json",
        "operator_profile": job_dir / "operator_profile.json",
        "manifest_operator_profile": job_dir / "manifests" / "operator_profile.json",
        "validation_report": validation,
    }


def _results_root_for_job(job_dir: Path) -> Path:
    if job_dir.parent.name == "jobs":
        return job_dir.parent.parent
    return job_dir.parent


def _read_json(
    path: Path | None,
    parse_errors: dict[str, str],
    *,
    required: bool = True,
) -> dict[str, Any]:
    if path is None or not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        parse_errors[str(path)] = f"json_decode_error:{exc.msg}"
        return {}
    if not isinstance(data, dict):
        if required:
            parse_errors[str(path)] = "expected_json_object"
        return {}
    return data


def _read_jsonl(path: Path, parse_errors: dict[str, str]) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            data = json.loads(line)
        except json.JSONDecodeError as exc:
            parse_errors[f"{path}:{line_number}"] = f"json_decode_error:{exc.msg}"
            continue
        if isinstance(data, dict):
            rows.append(data)
        else:
            parse_errors[f"{path}:{line_number}"] = "expected_json_object"
    return rows


def _read_first_existing_json(
    candidates: list[Path],
    parse_errors: dict[str, str],
) -> dict[str, Any]:
    for path in candidates:
        if path.exists():
            return _read_json(path, parse_errors, required=False)
    return {}


def _read_nccl_evidence(
    job_dir: Path,
    parse_errors: dict[str, str],
) -> tuple[dict[str, Any], list[Path]]:
    candidates = [
        job_dir / "nccl" / "summary.json",
        job_dir / "nccl_summary.json",
        job_dir / "preflight" / "nccl_summary.json",
        job_dir / "preflight" / "nccl.json",
        job_dir / "preflight" / "nccl_all_reduce.txt",
        job_dir / "preflight" / "all_reduce_perf.txt",
        job_dir / "nccl" / "all_reduce_perf.txt",
    ]
    existing = [path for path in candidates if path.exists()]
    for path in existing:
        if path.suffix == ".json":
            return _read_json(path, parse_errors, required=False), existing
    for path in existing:
        if path.suffix == ".txt":
            parsed = _parse_nccl_text(path, parse_errors)
            if parsed:
                return parsed, existing
    return {}, existing


def _parse_nccl_text(path: Path, parse_errors: dict[str, str]) -> dict[str, Any]:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        parse_errors[str(path)] = f"read_error:{type(exc).__name__}"
        return {}
    expected = _first_number(
        text,
        r"(?:expected|baseline)[_\s-]*busbw(?:[_\s-]*gbps)?\s*[:=]\s*([0-9]+(?:\.[0-9]+)?)",
    )
    busbw_values: list[float] = []
    saw_busbw_header = False
    for line in text.splitlines():
        lowered = line.lower()
        if "busbw" in lowered:
            saw_busbw_header = True
            busbw_values.extend(
                float(match)
                for match in re.findall(
                    r"(?<!expected[_\s-])(?<!baseline[_\s-])busbw(?:[_\s-]*gbps)?\s*[:=]\s*([0-9]+(?:\.[0-9]+)?)",
                    lowered,
                )
            )
            busbw_values.extend(
                float(match)
                for match in re.findall(r"([0-9]+(?:\.[0-9]+)?)\s*(?:gb/s|gbps)?\s+busbw", lowered)
            )
            continue
        if not saw_busbw_header or line.lstrip().startswith("#"):
            continue
        numbers = [float(match) for match in re.findall(r"-?[0-9]+(?:\.[0-9]+)?", line)]
        if len(numbers) >= 4:
            busbw_values.append(numbers[-2])
    if not busbw_values:
        return {}
    out: dict[str, Any] = {"busbw_gbps": max(busbw_values), "source": str(path)}
    if expected is not None:
        out["expected_busbw_gbps"] = expected
    return out


def _first_number(text: str, pattern: str) -> float | None:
    match = re.search(pattern, text, flags=re.IGNORECASE)
    if not match:
        return None
    try:
        return float(match.group(1))
    except ValueError:
        return None


def _read_cpu_summary(
    job_dir: Path,
    parse_errors: dict[str, str],
) -> tuple[dict[str, Any], Path | None]:
    candidates = [
        job_dir / "cpu_trace" / "summary.json",
        job_dir / "metrics" / "cpu_summary.json",
        job_dir / "cpu_trace.json",
    ]
    for path in candidates:
        if path.exists():
            return _read_json(path, parse_errors, required=False), path
    return {}, None


__all__ = [
    "BOTTLENECK_DIAGNOSIS_SCHEMA_VERSION",
    "DIAGNOSIS_JSON_FILENAME",
    "DIAGNOSIS_MARKDOWN_FILENAME",
    "VERDICT_VALUES",
    "BottleneckDiagnosis",
    "Downgrade",
    "Evidence",
    "Verdict",
    "diagnose",
    "diagnose_job",
    "render_bottleneck_diagnosis_markdown",
    "render_diagnosis_markdown",
    "write_diagnosis",
]

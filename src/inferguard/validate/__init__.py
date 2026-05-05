"""Completed-run publishability validation for NeoCloud/GMI artifacts."""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from json import JSONDecodeError
from pathlib import Path
from typing import Any

from inferguard import __version__
from inferguard.validate.report import Downgrade, JobValidation, ValidationReport

LOGGER = logging.getLogger(__name__)
SYNTHETIC_MARKER = "synthetic_gpu_mimic"
ENGINE_LIVE_METRICS = (
    "vllm:request_success_total",
    "sglang:prompt_tokens_total",
    "lmcache:num_lookup_hits",
)
GPU_REQUIRED_METRICS = (
    ("DCGM_FI_DEV_GPU_UTIL", "203"),
    ("DCGM_FI_DEV_FB_USED", "252"),
)
MATRIX_EVIDENCE_REQUIRED_PATHS: dict[str, list[str]] = {
    "slurm_env": ["slurm_env.json"],
    "gpu_inventory": ["gpu_inventory.json"],
    "gpu_topology": ["gpu_topology.txt"],
    "agentx_ingest_summary": ["agentx_ingest_summary.json"],
}
DEFAULT_MVP_REQUIRED_PATHS: dict[str, list[str]] = {
    "request_profile": [
        "request_profile/requests_profile.jsonl",
        "request_profile/requests_summary.json",
    ],
    **MATRIX_EVIDENCE_REQUIRED_PATHS,
    "engine_metrics": ["metrics/engine_metrics_timeline.jsonl"],
    "gpu_metrics": ["metrics/gpu_metrics_timeline.jsonl"],
    "metrics_summary": ["metrics/metrics_summary.json"],
    "bottleneck_diagnosis": [
        "diagnosis/bottleneck_diagnosis.json",
        "diagnosis/bottleneck_diagnosis.md",
    ],
    "failure_classification": [
        "diagnosis/failure_classification.json",
        "diagnosis/failure_classification.md",
    ],
    "operator_recommendation": [
        "report/operator_recommendation.json",
        "report/operator_recommendation.md",
    ],
    "launch": [
        "launch/command.json",
        "launch/stdout.log",
        "launch/stderr.log",
        "launch/healthcheck.json",
    ],
    "rdma_health": ["preflight/ib_state.txt"],
    "network_topology": ["preflight/nccl_all_reduce.txt"],
    "multi_node_throughput": ["preflight/nccl_all_reduce.txt"],
}


def validate_run(
    results_root: str | Path,
    contract: str | Path | dict[str, Any] | None = None,
    plan: str | Path | dict[str, Any] | None = None,
    overrides: str | Path | dict[str, Any] | None = None,
) -> ValidationReport:
    """Validate a completed run directory and return a report contract."""
    root = Path(results_root).resolve()
    plan_path = (
        root / "matrix_plan.json"
        if plan is None or isinstance(plan, dict)
        else Path(plan).resolve()
    )
    contract_path = (
        root / "expected_artifact_contract.json"
        if contract is None or isinstance(contract, dict)
        else Path(contract).resolve()
    )
    load_downgrades: list[Downgrade] = []
    plan_data = _load_object(plan, plan_path, downgrades=load_downgrades, claim_id="matrix_plan")
    contract_data = _load_object(
        contract,
        contract_path,
        downgrades=load_downgrades,
        claim_id="artifact_contract",
    )
    override_data = _load_optional_object(
        overrides,
        downgrades=load_downgrades,
        claim_id="label_overrides",
    )

    if contract_data is None:
        jobs = _jobs_from_plan_or_contract(plan_data, {})
        invalid_required_input = _has_invalid_input_downgrade(load_downgrades)
        status = "not_publishable" if invalid_required_input else "missing_required_artifacts"
        claim_status = "not_proven"
        reason = (
            "invalid_expected_artifact_contract_json"
            if invalid_required_input
            else "missing_expected_artifact_contract"
        )
        base_downgrades = [
            Downgrade(
                claim_id="artifact_contract",
                from_label="measured",
                to=claim_status,
                reason=reason,
            ),
            *load_downgrades,
        ]
        job_reports = [
            JobValidation(
                job_id=str(job.get("job_id") or "unknown"),
                status=status,
                claim_status=claim_status,
                required_paths_missing=["expected_artifact_contract.json"],
                downgrades=_dedupe_downgrades(base_downgrades),
            )
            for job in jobs
        ] or [
            JobValidation(
                job_id="unknown",
                status=status,
                claim_status=claim_status,
                required_paths_missing=["expected_artifact_contract.json"],
                downgrades=_dedupe_downgrades(base_downgrades),
            )
        ]
        return _build_report(root, plan_path, contract_path, job_reports, status)

    jobs = _jobs_from_plan_or_contract(plan_data, contract_data)
    matrix_downgrades = [*load_downgrades, *_validate_matrix_level(root, contract_data)]
    job_reports = [
        _validate_job(root, job, contract_data, override_data, matrix_downgrades) for job in jobs
    ]
    overall = _compose_overall_status(job_reports, matrix_downgrades)
    return _build_report(root, plan_path, contract_path, job_reports, overall)


def _build_report(
    root: Path,
    plan_path: Path,
    contract_path: Path,
    jobs: list[JobValidation],
    status: str,
) -> ValidationReport:
    return ValidationReport(
        status=status,
        results_root=str(root),
        matrix_plan_ref=str(plan_path),
        artifact_contract_ref=str(contract_path),
        validated_at=datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        harness_version=__version__,
        jobs=jobs,
    )


def _load_object(
    source: str | Path | dict[str, Any] | None,
    default_path: Path,
    *,
    downgrades: list[Downgrade] | None = None,
    claim_id: str,
) -> dict[str, Any] | None:
    if isinstance(source, dict):
        return source
    path = Path(source) if isinstance(source, str | Path) else default_path
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (JSONDecodeError, OSError, UnicodeDecodeError) as exc:
        _record_load_downgrade(downgrades, claim_id, path, exc)
        return None
    if not isinstance(data, dict):
        _record_load_downgrade(downgrades, claim_id, path, ValueError("expected JSON object"))
        return None
    return data


def _load_optional_object(
    source: str | Path | dict[str, Any] | None,
    *,
    downgrades: list[Downgrade] | None = None,
    claim_id: str,
) -> dict[str, Any]:
    if source is None:
        return {}
    if isinstance(source, dict):
        return source
    path = Path(source)
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (JSONDecodeError, OSError, UnicodeDecodeError) as exc:
        _record_load_downgrade(downgrades, claim_id, path, exc)
        return {}
    if not isinstance(data, dict):
        _record_load_downgrade(downgrades, claim_id, path, ValueError("expected JSON object"))
        return {}
    return data


def _record_load_downgrade(
    downgrades: list[Downgrade] | None,
    claim_id: str,
    path: Path,
    exc: BaseException,
) -> None:
    reason = f"invalid_json:{path}:{type(exc).__name__}:{exc}"
    LOGGER.warning("downgrading %s because %s", claim_id, reason)
    if downgrades is not None:
        downgrades.append(
            Downgrade(
                claim_id=claim_id,
                from_label="measured",
                to="not_proven",
                reason=reason,
            )
        )


def _jobs_from_plan_or_contract(
    plan: dict[str, Any] | None,
    contract: dict[str, Any],
) -> list[dict[str, Any]]:
    plan_jobs = plan.get("jobs") if isinstance(plan, dict) else None
    if isinstance(plan_jobs, list) and plan_jobs:
        return [job for job in plan_jobs if isinstance(job, dict)]
    contract_jobs = contract.get("per_job")
    if isinstance(contract_jobs, list):
        return [job for job in contract_jobs if isinstance(job, dict)]
    return []


def _validate_job(
    root: Path,
    job: dict[str, Any],
    contract: dict[str, Any],
    overrides: dict[str, Any],
    matrix_downgrades: list[Downgrade] | None = None,
) -> JobValidation:
    job_id = str(job.get("job_id") or "unknown")
    job_dir = _job_dir(root, job)
    required_paths = _required_paths(contract)
    operator_profile = _operator_profile(job_dir)
    node_count, node_count_downgrades = _node_count(job_dir, job, operator_profile)
    network_fabric = _network_fabric(operator_profile)
    synthetic_markers = _synthetic_markers(job_dir)
    live_evidence_present = _has_live_evidence(job_dir)
    present: list[str] = []
    missing: list[str] = []
    downgrades: list[Downgrade] = list(matrix_downgrades or [])
    downgrades.extend(node_count_downgrades)

    if not job_dir.exists():
        return JobValidation(
            job_id=job_id,
            status="missing_required_artifacts",
            claim_status="not_proven",
            required_paths_missing=[str(job_dir)],
            synthetic_markers=synthetic_markers,
            downgrades=[
                Downgrade(
                    claim_id="job_directory",
                    from_label="measured",
                    to="not_proven",
                    reason="missing_job_directory",
                )
            ],
        )

    for claim_id, rel_path in required_paths:
        if _skip_claim(claim_id, node_count, network_fabric):
            continue
        path = job_dir / rel_path
        if path.exists():
            present.append(rel_path)
        else:
            missing.append(rel_path)
            downgrades.append(
                Downgrade(
                    claim_id=claim_id,
                    from_label="measured",
                    to="not_proven",
                    reason=f"missing_required_path:{rel_path}",
                )
            )

    _validate_request_profile(job_dir, downgrades)
    _validate_healthcheck(job_dir, downgrades)
    _validate_engine_metrics(job_dir, downgrades)
    _validate_gpu_metrics(job_dir, downgrades)
    _validate_multi_node_network(job_dir, node_count, downgrades)
    _validate_rdma(job_dir, network_fabric, downgrades)
    _apply_overrides(overrides, downgrades)

    status = _job_status(synthetic_markers, live_evidence_present, missing, downgrades)
    claim_status = _claim_status(status, downgrades)
    return JobValidation(
        job_id=job_id,
        status=status,
        claim_status=claim_status,
        required_paths_present=present,
        required_paths_missing=missing,
        synthetic_markers=synthetic_markers,
        downgrades=_dedupe_downgrades(downgrades),
    )


def _job_dir(root: Path, job: dict[str, Any]) -> Path:
    output_dir = Path(
        str(job.get("output_dir") or root / "jobs" / str(job.get("job_id") or "unknown"))
    )
    if output_dir.is_absolute():
        return output_dir
    return root / output_dir


def _required_paths(contract: dict[str, Any]) -> list[tuple[str, str]]:
    raw = contract.get("mvp_required_paths") or DEFAULT_MVP_REQUIRED_PATHS
    paths: list[tuple[str, str]] = []
    if not isinstance(raw, dict):
        return [
            (claim_id, rel_path)
            for claim_id, rels in DEFAULT_MVP_REQUIRED_PATHS.items()
            for rel_path in rels
        ]
    for claim_id, spec in raw.items():
        for rel_path in _paths_from_spec(spec):
            paths.append((str(claim_id), rel_path))
    for claim_id, rels in MATRIX_EVIDENCE_REQUIRED_PATHS.items():
        for rel_path in rels:
            paths.append((claim_id, rel_path))
    return sorted(set(paths))


def _paths_from_spec(spec: Any) -> list[str]:
    if isinstance(spec, str):
        return [spec]
    if isinstance(spec, list):
        paths: list[str] = []
        for item in spec:
            if isinstance(item, str):
                paths.append(item)
            elif isinstance(item, dict):
                paths.extend(_paths_from_spec(item.get("paths") or item.get("path")))
        return paths
    if isinstance(spec, dict):
        return _paths_from_spec(spec.get("paths") or spec.get("path") or [])
    return []


def _skip_claim(claim_id: str, node_count: int, network_fabric: str | None) -> bool:
    if node_count <= 1 and claim_id in {"network_topology", "multi_node_throughput"}:
        return True
    return claim_id == "rdma_health" and network_fabric != "ib"


def _node_count(
    job_dir: Path,
    job: dict[str, Any],
    operator_profile: dict[str, Any],
) -> tuple[int, list[Downgrade]]:
    values: list[tuple[str, int]] = []
    for key in ("node_count", "nodes"):
        _add_node_count_value(values, f"job.{key}", job.get(key))
    env = job.get("env")
    if isinstance(env, dict):
        for key in ("GMI_SLURM_NODES", "SLURM_JOB_NUM_NODES", "SLURM_NNODES"):
            _add_node_count_value(values, f"job.env.{key}", env.get(key))
    for key, raw in _environment_values(job_dir).items():
        _add_node_count_value(values, f"environment.{key}", raw)
    for key in ("node_count", "nodes"):
        _add_node_count_value(values, f"operator_profile.{key}", operator_profile.get(key))
    if not values:
        return 1, []
    node_count = max(value for _, value in values)
    unique_values = {value for _, value in values}
    if len(unique_values) == 1:
        return node_count, []
    reason = "node_count_sources_disagree:" + ",".join(
        f"{source}={value}" for source, value in values
    )
    return node_count, [
        Downgrade(
            claim_id="node_count_detection",
            from_label="measured",
            to="inferred",
            reason=reason,
        )
    ]


def _add_node_count_value(values: list[tuple[str, int]], source: str, raw: Any) -> None:
    parsed = _positive_int(raw)
    if parsed is not None:
        values.append((source, parsed))


def _environment_values(job_dir: Path) -> dict[str, str]:
    env_values: dict[str, str] = {}
    for rel in ("raw/environment.env", "preflight/environment.env"):
        text = _safe_text(job_dir / rel)
        if text is None:
            continue
        for line in text.splitlines():
            key, sep, value = line.partition("=")
            if sep and key in {"GMI_SLURM_NODES", "SLURM_JOB_NUM_NODES", "SLURM_NNODES"}:
                env_values[key] = value.strip()
    return env_values


def _operator_profile(job_dir: Path) -> dict[str, Any]:
    for rel in ("operator_profile.json", "manifests/operator_profile.json"):
        path = job_dir / rel
        if not path.exists():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (JSONDecodeError, OSError, UnicodeDecodeError):
            continue
        if isinstance(data, dict):
            return data
    return {}


def _network_fabric(operator_profile: dict[str, Any]) -> str | None:
    raw = operator_profile.get("network_fabric")
    if not isinstance(raw, str):
        network = operator_profile.get("network")
        if isinstance(network, dict):
            raw = network.get("fabric")
    if not isinstance(raw, str):
        return None
    return raw.strip().lower() or None


def _synthetic_markers(job_dir: Path) -> list[str]:
    if not job_dir.exists():
        return []
    markers: list[str] = []
    for path in sorted(item for item in job_dir.rglob("*") if item.is_file()):
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        if SYNTHETIC_MARKER in text:
            rel = path.relative_to(job_dir)
            markers.append(f"{rel}:{SYNTHETIC_MARKER}")
    return markers


def _has_live_evidence(job_dir: Path) -> bool:
    return (
        _request_profile_live(job_dir / "request_profile" / "requests_profile.jsonl")
        and _healthcheck_succeeded(job_dir / "launch" / "healthcheck.json")
        and _engine_metrics_live(job_dir / "metrics" / "engine_metrics_timeline.jsonl")
        and _gpu_metrics_live(job_dir / "metrics" / "gpu_metrics_timeline.jsonl")
    )


def _validate_request_profile(job_dir: Path, downgrades: list[Downgrade]) -> None:
    path = job_dir / "request_profile" / "requests_profile.jsonl"
    if path.exists() and not _request_profile_live(path):
        downgrades.append(
            Downgrade(
                claim_id="request_profile",
                from_label="measured",
                to="not_proven",
                reason="no_successful_request_profile_rows",
            )
        )


def _validate_healthcheck(job_dir: Path, downgrades: list[Downgrade]) -> None:
    path = job_dir / "launch" / "healthcheck.json"
    if path.exists() and not _healthcheck_succeeded(path):
        downgrades.append(
            Downgrade(
                claim_id="launch_healthcheck",
                from_label="measured",
                to="not_proven",
                reason="launch_healthcheck_not_successful",
            )
        )


def _validate_engine_metrics(job_dir: Path, downgrades: list[Downgrade]) -> None:
    path = job_dir / "metrics" / "engine_metrics_timeline.jsonl"
    if path.exists() and not _engine_metrics_live(path):
        downgrades.append(
            Downgrade(
                claim_id="engine_metrics",
                from_label="measured",
                to="not_proven",
                reason="no_live_engine_metric_sample",
            )
        )


def _validate_gpu_metrics(job_dir: Path, downgrades: list[Downgrade]) -> None:
    path = job_dir / "metrics" / "gpu_metrics_timeline.jsonl"
    if path.exists() and not _gpu_metrics_live(path):
        downgrades.append(
            Downgrade(
                claim_id="gpu_metrics",
                from_label="measured",
                to="not_proven",
                reason="missing_required_dcgm_metrics",
            )
        )


def _engine_metrics_live(path: Path) -> bool:
    if not path.exists() or path.stat().st_size == 0:
        return False
    names = _metric_names(path)
    return any(metric in names for metric in ENGINE_LIVE_METRICS)


def _gpu_metrics_live(path: Path) -> bool:
    if not path.exists() or path.stat().st_size == 0:
        return False
    names = _metric_names(path)
    return all(any(token in names for token in aliases) for aliases in GPU_REQUIRED_METRICS)


def _request_profile_live(path: Path) -> bool:
    if not path.exists() or path.stat().st_size == 0:
        return False
    for row in _jsonl_rows(path):
        if _successful_request_row(row):
            return True
    return False


def _healthcheck_succeeded(path: Path) -> bool:
    if not path.exists() or path.stat().st_size == 0:
        return False
    data = _load_object(path, path, claim_id="launch_healthcheck") or {}
    status_code = data.get("status_code")
    if status_code == 200:
        return True
    status = str(data.get("status") or "").strip().lower()
    return bool(
        data.get("ok") is True or status in {"healthy", "external_validated", "ok", "success"}
    )


def _validate_multi_node_network(
    job_dir: Path, node_count: int, downgrades: list[Downgrade]
) -> None:
    if node_count <= 1:
        return
    path = job_dir / "preflight" / "nccl_all_reduce.txt"
    text = _safe_text(path)
    if text is None or "busbw" not in text:
        for claim_id in ("network_topology", "multi_node_throughput"):
            downgrades.append(
                Downgrade(
                    claim_id=claim_id,
                    from_label="measured",
                    to="not_proven",
                    reason="missing_nccl_busbw_evidence",
                )
            )


def _validate_rdma(job_dir: Path, network_fabric: str | None, downgrades: list[Downgrade]) -> None:
    if network_fabric != "ib":
        return
    path = job_dir / "preflight" / "ib_state.txt"
    text = _safe_text(path)
    if text is None or "State: Active" not in text:
        downgrades.append(
            Downgrade(
                claim_id="rdma_health",
                from_label="measured",
                to="not_proven",
                reason="missing_or_inactive_ib_state",
            )
        )


def _validate_matrix_level(root: Path, contract: dict[str, Any]) -> list[Downgrade]:
    downgrades: list[Downgrade] = []
    for spec in contract.get("matrix_level") or []:
        if not isinstance(spec, str):
            continue
        if _matrix_path_present(root, spec):
            continue
        downgrades.append(
            Downgrade(
                claim_id="matrix_level",
                from_label="measured",
                to="not_proven",
                reason=f"missing_matrix_artifact:{spec}",
            )
        )
    return downgrades


def _matrix_path_present(root: Path, spec: str) -> bool:
    if any(char in spec for char in "*?["):
        return any(root.glob(spec))
    return (root / spec).exists()


def _positive_int(raw: Any) -> int | None:
    if isinstance(raw, int) and raw > 0:
        return raw
    if isinstance(raw, str):
        try:
            parsed = int(raw)
        except ValueError:
            return None
        if parsed > 0:
            return parsed
    return None


def _safe_text(path: Path) -> str | None:
    if not path.exists():
        return None
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None


def _metric_names(path: Path) -> set[str]:
    text = _safe_text(path)
    if text is None:
        return set()
    names: set[str] = set()
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        names.update(_json_metric_names(stripped))
        if not stripped.startswith("{"):
            names.add(stripped.split(None, 1)[0].split("{", 1)[0])
    return names


def _jsonl_rows(path: Path) -> list[dict[str, Any]]:
    text = _safe_text(path)
    if text is None:
        return []
    rows: list[dict[str, Any]] = []
    for line in text.splitlines():
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except JSONDecodeError:
            continue
        if isinstance(row, dict):
            rows.append(row)
    return rows


def _successful_request_row(row: dict[str, Any]) -> bool:
    status = str(row.get("status") or "").strip().lower()
    if status in {"ok", "success", "succeeded"}:
        return True
    success = row.get("success")
    if isinstance(success, bool):
        return success
    if isinstance(success, int | float):
        return success != 0
    if isinstance(success, str):
        return success.strip().lower() in {"1", "true", "yes", "ok", "success", "succeeded"}
    return False


def _json_metric_names(line: str) -> set[str]:
    try:
        record = json.loads(line)
    except JSONDecodeError:
        return set()
    names: set[str] = set()
    _collect_metric_names(record, names)
    return names


def _collect_metric_names(value: Any, names: set[str]) -> None:
    if isinstance(value, dict):
        metrics = value.get("metrics")
        if isinstance(metrics, dict):
            names.update(str(key) for key in metrics)
        for key in ("name", "metric", "metric_name", "field", "field_id"):
            raw = value.get(key)
            if isinstance(raw, str | int):
                names.add(str(raw))
        for child in value.values():
            _collect_metric_names(child, names)
    elif isinstance(value, list):
        for child in value:
            _collect_metric_names(child, names)


def _apply_overrides(overrides: dict[str, Any], downgrades: list[Downgrade]) -> None:
    for claim_id, spec in sorted(overrides.items()):
        to_status, reason = _override_status_and_reason(spec)
        downgrades.append(
            Downgrade(
                claim_id=str(claim_id),
                from_label="measured",
                to=to_status,
                reason=reason,
            )
        )


def _override_status_and_reason(spec: Any) -> tuple[str, str]:
    if isinstance(spec, str):
        return spec, "operator_supplied"
    if isinstance(spec, dict):
        to_status = str(
            spec.get("to") or spec.get("claim_status") or spec.get("status") or "inferred"
        )
        reason = str(spec.get("reason") or "operator_supplied")
        return to_status, reason
    return "inferred", "operator_supplied"


def _job_status(
    synthetic_markers: list[str],
    live_evidence_present: bool,
    missing: list[str],
    downgrades: list[Downgrade],
) -> str:
    if _has_invalid_input_downgrade(downgrades):
        return "not_publishable"
    if synthetic_markers:
        return "not_publishable" if live_evidence_present else "synthetic_only"
    if not live_evidence_present:
        return "live_incomplete"
    if any(downgrade.to == "not_proven" for downgrade in downgrades) or missing:
        return "live_incomplete"
    return "live_complete"


def _claim_status(status: str, downgrades: list[Downgrade]) -> str:
    if status == "not_publishable":
        return "not_proven"
    if status == "synthetic_only":
        return "synthetic"
    if any(downgrade.to == "not_proven" for downgrade in downgrades):
        return "not_proven"
    if any(downgrade.to == "synthetic" for downgrade in downgrades):
        return "synthetic"
    if any(downgrade.to == "inferred" for downgrade in downgrades):
        return "inferred"
    return "measured"


def _dedupe_downgrades(downgrades: list[Downgrade]) -> list[Downgrade]:
    seen: set[tuple[str, str, str]] = set()
    deduped: list[Downgrade] = []
    for downgrade in downgrades:
        key = (downgrade.claim_id, downgrade.to, downgrade.reason)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(downgrade)
    return deduped


def _compose_overall_status(jobs: list[JobValidation], matrix_downgrades: list[Downgrade]) -> str:
    if not jobs:
        return "missing_required_artifacts"
    statuses = {job.status for job in jobs}
    if _has_invalid_input_downgrade(matrix_downgrades):
        return "not_publishable"
    if "not_publishable" in statuses:
        return "not_publishable"
    if matrix_downgrades or "missing_required_artifacts" in statuses:
        return "missing_required_artifacts"
    if "live_incomplete" in statuses:
        return "live_incomplete"
    if "synthetic_only" in statuses:
        return "synthetic_only"
    return "live_complete"


def _has_invalid_input_downgrade(downgrades: list[Downgrade]) -> bool:
    return any(
        downgrade.reason.startswith("invalid_json:")
        or downgrade.reason.startswith("invalid_expected_artifact_contract_json")
        for downgrade in downgrades
    )


__all__ = ["validate_run", "ValidationReport", "JobValidation", "Downgrade"]

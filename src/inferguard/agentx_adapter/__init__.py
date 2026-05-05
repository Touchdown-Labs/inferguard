"""AgentX replay result adapter for canonical InferGuard artifacts."""

from __future__ import annotations

import csv
import json
import uuid
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from statistics import mean
from typing import Any

from inferguard.agentx_adapter.mappers import (
    AGENTX_NOT_EMITTED_REQUEST_FIELDS,
    agentx_to_engine_metrics,
    agentx_to_gpu_metrics,
    agentx_to_request_profile,
    count_mapped_metric_values,
    missing_required_columns,
    total_tokens_crosscheck,
)
from inferguard.agentx_adapter.render import render_ingest_summary
from inferguard.agentx_adapter.types import AgentXIngestSummary, CanonicalArtifacts
from inferguard.io import atomic_write_json
from inferguard.request_profile.types import RequestProfileRow, RequestProfileSummary

MARKER_FILENAME = "agentx_run_metadata.json"


def convert_agentx_result_to_canonical(
    agentx_csv_path: str | Path,
    gmi_job_metadata: dict[str, Any] | None = None,
) -> CanonicalArtifacts:
    """Convert an AgentX result CSV into canonical InferGuard job artifacts."""

    metadata = dict(gmi_job_metadata or {})
    csv_path = Path(agentx_csv_path)
    output_dir = Path(metadata.get("output_dir") or csv_path.parent)
    job_id = str(metadata.get("job_id") or f"agentx-{uuid.uuid4()}")
    engine = str(metadata.get("engine") or "vllm")
    workload_label = str(metadata.get("workload_label") or "agentx-replay")
    model_profile = str(metadata.get("model_profile") or metadata.get("model") or "agentx-replay")
    concurrency = _positive_int(metadata.get("concurrency"), 1)
    return _convert_csv(
        csv_path,
        output_dir=output_dir,
        job_id=job_id,
        engine=engine,
        workload_label=workload_label,
        model_profile=model_profile,
        concurrency=concurrency,
        metadata=metadata,
    )


def ingest_agentx_results_dir(
    results_dir: str | Path,
    *,
    output_dir: str | Path,
    job_id: str | None = None,
    engine: str | None = None,
    workload_label: str | None = None,
) -> CanonicalArtifacts:
    """Ingest an AgentX results directory that carries the required marker file."""

    source_dir = Path(results_dir)
    marker_path = source_dir / MARKER_FILENAME
    if not marker_path.exists():
        raise ValueError(f"AgentX ingest requires marker file: {marker_path}")
    metadata = _load_json(marker_path)
    csv_path = _csv_from_metadata(source_dir, metadata)
    merged = {
        **metadata,
        "output_dir": str(output_dir),
        "job_id": job_id or metadata.get("job_id"),
        "engine": engine or metadata.get("engine") or "vllm",
        "workload_label": workload_label or metadata.get("workload_label") or "agentx-replay",
        "raw_metadata_path": str(marker_path),
    }
    return convert_agentx_result_to_canonical(csv_path, merged)


def _convert_csv(
    csv_path: Path,
    *,
    output_dir: Path,
    job_id: str,
    engine: str,
    workload_label: str,
    model_profile: str,
    concurrency: int,
    metadata: dict[str, Any],
) -> CanonicalArtifacts:
    paths = _artifact_paths(output_dir)
    paths["request_profile_dir"].mkdir(parents=True, exist_ok=True)
    paths["metrics_dir"].mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)
    raw_paths = _raw_artifact_paths(csv_path, metadata)
    generated_at = _now_iso()

    if not csv_path.exists():
        summary = _failure_summary(
            job_id=job_id,
            engine=engine,
            workload_label=workload_label,
            model_profile=model_profile,
            raw_paths=raw_paths,
            canonical_paths=_canonical_paths(paths),
            error_type="agentx_csv_missing",
            error_message=f"AgentX result CSV does not exist: {csv_path}",
            generated_at=generated_at,
        )
        return _write_summary_only(paths, summary)

    try:
        rows, fieldnames = _read_csv(csv_path)
    except csv.Error as exc:
        summary = _failure_summary(
            job_id=job_id,
            engine=engine,
            workload_label=workload_label,
            model_profile=model_profile,
            raw_paths=raw_paths,
            canonical_paths=_canonical_paths(paths),
            error_type="csv_parse_error",
            error_message=str(exc),
            generated_at=generated_at,
        )
        return _write_summary_only(paths, summary)

    missing = missing_required_columns(fieldnames)
    if missing:
        summary = _failure_summary(
            job_id=job_id,
            engine=engine,
            workload_label=workload_label,
            model_profile=model_profile,
            raw_paths=raw_paths,
            canonical_paths=_canonical_paths(paths),
            error_type="missing_required_columns",
            error_message="AgentX CSV is missing required columns: " + ", ".join(missing),
            generated_at=generated_at,
            missing_required_columns=missing,
        )
        return _write_summary_only(paths, summary)

    request_rows: list[RequestProfileRow] = []
    engine_rows = []
    gpu_rows = []
    warnings = _metadata_warnings(metadata)
    for sequence, row in enumerate(rows):
        request = agentx_to_request_profile(
            row,
            sequence=sequence,
            source_csv_path=csv_path,
            job_id=job_id,
            engine=engine,
            workload_label=workload_label,
            model_profile=model_profile,
            concurrency=concurrency,
        )
        request_rows.append(request)
        observed_at = request.done_ts
        engine_metric = agentx_to_engine_metrics(
            row,
            sequence=sequence,
            observed_at=observed_at,
            engine=engine,
            job_id=job_id,
        )
        if engine_metric is not None:
            engine_rows.append(engine_metric)
        gpu_metric = agentx_to_gpu_metrics(
            row,
            sequence=sequence,
            observed_at=observed_at,
            job_id=job_id,
        )
        if gpu_metric is not None:
            gpu_rows.append(gpu_metric)
        crosscheck = total_tokens_crosscheck(row)
        if crosscheck is False:
            warnings.append(
                f"row {sequence}: total_tokens did not equal prompt_tokens + completion_tokens"
            )

    _write_jsonl(paths["request_profile_jsonl"], [row.to_dict() for row in request_rows])
    request_summary = _summary_from_rows(
        request_rows,
        job_id=job_id,
        workload_label=workload_label,
        engine=engine,
        concurrency=concurrency,
    )
    _write_json(paths["requests_summary_json"], request_summary.to_dict())
    _write_jsonl(paths["engine_metrics_timeline_jsonl"], [row.as_dict() for row in engine_rows])
    _write_jsonl(paths["gpu_metrics_timeline_jsonl"], [row.as_dict() for row in gpu_rows])

    summary = AgentXIngestSummary(
        job_id=job_id,
        status="ingested",
        request_count=len(request_rows),
        success_count=sum(1 for row in request_rows if row.success),
        mapped_metrics_count=count_mapped_metric_values(engine_rows, gpu_rows),
        claim_status="measured",
        raw_artifact_paths=raw_paths,
        canonical_artifact_paths=_canonical_paths(paths),
        engine=engine,
        workload_label=workload_label,
        model_profile=model_profile,
        inputs_under_target_warning=_inputs_under_target_warning(metadata),
        warnings=warnings,
        field_claim_status={field: "not_proven" for field in AGENTX_NOT_EMITTED_REQUEST_FIELDS},
        field_evidence_paths={
            field: [str(csv_path)] for field in AGENTX_NOT_EMITTED_REQUEST_FIELDS
        },
        generated_at=generated_at,
    )
    _write_json(paths["agentx_ingest_summary_json"], summary.to_dict())
    paths["agentx_ingest_summary_md"].write_text(render_ingest_summary(summary), encoding="utf-8")
    return _artifacts(paths, summary)


def _summary_from_rows(
    rows: list[RequestProfileRow],
    *,
    job_id: str,
    workload_label: str,
    engine: str,
    concurrency: int,
) -> RequestProfileSummary:
    successes = [row for row in rows if row.success]
    failures = [row for row in rows if not row.success]
    prompt_total = sum(row.prompt_tokens for row in rows)
    completion_total = sum(row.completion_tokens for row in rows)
    runtime_seconds = _runtime_seconds(rows)
    decode_tps = [
        row.decode_tokens_per_sec for row in successes if row.decode_tokens_per_sec is not None
    ]
    return RequestProfileSummary(
        job_id=job_id,
        workload_label=workload_label,
        engine=rows[0].engine if rows else "agentx-replay",
        concurrency=concurrency,
        request_count=len(rows),
        success_count=len(successes),
        failure_count=len(failures),
        ttft_ms=_percentile_block([]),
        tpot_ms=_percentile_block([]),
        e2e_latency_ms=_percentile_block([row.e2e_latency_ms for row in successes]),
        decode_tokens_per_sec={
            "p50": _percentile(decode_tps, 50),
            "p95": _percentile(decode_tps, 95),
            "mean": mean(decode_tps) if decode_tps else None,
        },
        prompt_tokens_total=prompt_total,
        completion_tokens_total=completion_total,
        tokens_per_sec_aggregate=(completion_total / runtime_seconds)
        if runtime_seconds > 0
        else None,
        failure_breakdown=dict(Counter(row.error_type or "unknown" for row in failures)),
        claim_status="measured" if rows else "not_proven",
        success_rate=(len(successes) / len(rows)) if rows else 0.0,
    )


def _runtime_seconds(rows: list[RequestProfileRow]) -> float:
    if not rows:
        return 0.0
    starts = [_parse_iso(row.send_ts) for row in rows]
    ends = [_parse_iso(row.done_ts) for row in rows]
    return (max(ends) - min(starts)).total_seconds()


def _percentile_block(values: list[float]) -> dict[str, float | None]:
    return {
        "p50": _percentile(values, 50),
        "p95": _percentile(values, 95),
        "p99": _percentile(values, 99),
    }


def _percentile(values: list[float], percentile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    rank = (len(ordered) - 1) * percentile / 100.0
    lower = int(rank)
    upper = min(lower + 1, len(ordered) - 1)
    weight = rank - lower
    return ordered[lower] * (1 - weight) + ordered[upper] * weight


def _read_csv(path: Path) -> tuple[list[dict[str, str]], list[str] | None]:
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        return list(reader), reader.fieldnames


def _artifact_paths(output_dir: Path) -> dict[str, Path]:
    request_profile_dir = output_dir / "request_profile"
    metrics_dir = output_dir / "metrics"
    return {
        "request_profile_dir": request_profile_dir,
        "metrics_dir": metrics_dir,
        "request_profile_jsonl": request_profile_dir / "requests_profile.jsonl",
        "requests_summary_json": request_profile_dir / "requests_summary.json",
        "engine_metrics_timeline_jsonl": metrics_dir / "engine_metrics_timeline.jsonl",
        "gpu_metrics_timeline_jsonl": metrics_dir / "gpu_metrics_timeline.jsonl",
        "agentx_ingest_summary_json": output_dir / "agentx_ingest_summary.json",
        "agentx_ingest_summary_md": output_dir / "agentx_ingest_summary.md",
    }


def _canonical_paths(paths: dict[str, Path]) -> dict[str, str]:
    return {
        "requests_profile_jsonl": str(paths["request_profile_jsonl"]),
        "requests_summary_json": str(paths["requests_summary_json"]),
        "engine_metrics_timeline_jsonl": str(paths["engine_metrics_timeline_jsonl"]),
        "gpu_metrics_timeline_jsonl": str(paths["gpu_metrics_timeline_jsonl"]),
        "agentx_ingest_summary_json": str(paths["agentx_ingest_summary_json"]),
        "agentx_ingest_summary_md": str(paths["agentx_ingest_summary_md"]),
    }


def _raw_artifact_paths(csv_path: Path, metadata: dict[str, Any]) -> dict[str, str]:
    paths = {"agentx_result_csv": str(csv_path)}
    raw_metadata_path = metadata.get("raw_metadata_path")
    if raw_metadata_path:
        paths["agentx_run_metadata_json"] = str(raw_metadata_path)
    for key in ("agentx_result_json", "server_metrics", "debug_traces"):
        if metadata.get(key):
            paths[key] = str(metadata[key])
    return paths


def _failure_summary(
    *,
    job_id: str,
    engine: str,
    workload_label: str,
    model_profile: str,
    raw_paths: dict[str, str],
    canonical_paths: dict[str, str],
    error_type: str,
    error_message: str,
    generated_at: str,
    missing_required_columns: list[str] | None = None,
) -> AgentXIngestSummary:
    return AgentXIngestSummary(
        job_id=job_id,
        status="ingest_failed",
        request_count=0,
        success_count=0,
        mapped_metrics_count=0,
        claim_status="not_proven",
        raw_artifact_paths=raw_paths,
        canonical_artifact_paths=canonical_paths,
        engine=engine,
        workload_label=workload_label,
        model_profile=model_profile,
        error_type=error_type,
        error_message=error_message,
        missing_required_columns=missing_required_columns or [],
        field_claim_status={field: "not_proven" for field in AGENTX_NOT_EMITTED_REQUEST_FIELDS},
        field_evidence_paths={
            field: [raw_paths["agentx_result_csv"]] for field in AGENTX_NOT_EMITTED_REQUEST_FIELDS
        },
        generated_at=generated_at,
    )


def _write_summary_only(paths: dict[str, Path], summary: AgentXIngestSummary) -> CanonicalArtifacts:
    _write_json(paths["agentx_ingest_summary_json"], summary.to_dict())
    paths["agentx_ingest_summary_md"].write_text(render_ingest_summary(summary), encoding="utf-8")
    return _artifacts(paths, summary)


def _artifacts(paths: dict[str, Path], summary: AgentXIngestSummary) -> CanonicalArtifacts:
    return CanonicalArtifacts(
        request_profile_jsonl=paths["request_profile_jsonl"],
        requests_summary_json=paths["requests_summary_json"],
        engine_metrics_timeline_jsonl=paths["engine_metrics_timeline_jsonl"],
        gpu_metrics_timeline_jsonl=paths["gpu_metrics_timeline_jsonl"],
        agentx_ingest_summary_json=paths["agentx_ingest_summary_json"],
        agentx_ingest_summary_md=paths["agentx_ingest_summary_md"],
        summary=summary,
    )


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_json(path, data)


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows), encoding="utf-8"
    )


def _load_json(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"expected JSON object: {path}")
    return data


def _csv_from_metadata(source_dir: Path, metadata: dict[str, Any]) -> Path:
    configured = metadata.get("result_csv") or metadata.get("agentx_result_csv")
    if configured:
        path = Path(str(configured))
        return path if path.is_absolute() else source_dir / path
    candidates = [
        source_dir / "result.csv",
        source_dir / "detailed_results.csv",
        source_dir / "trace_replay" / "detailed_results.csv",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[0]


def _inputs_under_target_warning(metadata: dict[str, Any]) -> bool:
    checks = (
        ("target_isl", "observed_average_isl"),
        ("target_osl", "observed_average_osl"),
        ("target_input_tokens", "average_input_tokens"),
        ("target_output_tokens", "average_output_tokens"),
    )
    for target_key, observed_key in checks:
        target = _float_or_none(metadata.get(target_key))
        observed = _float_or_none(metadata.get(observed_key))
        if target and observed is not None and observed < target * 0.95:
            return True
    return False


def _metadata_warnings(metadata: dict[str, Any]) -> list[str]:
    if _inputs_under_target_warning(metadata):
        return ["AgentX source average ISL/OSL is below 0.95 of the claimed target."]
    return []


def _positive_int(value: Any, default: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed > 0 else default


def _float_or_none(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _parse_iso(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)


def _now_iso() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


__all__ = [
    "MARKER_FILENAME",
    "convert_agentx_result_to_canonical",
    "ingest_agentx_results_dir",
]

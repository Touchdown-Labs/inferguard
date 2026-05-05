"""Row-level AgentX to canonical InferGuard mappers."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, cast

from inferguard.collect_metrics.types import EngineMetricsSample, GpuMetricsSample
from inferguard.request_profile.types import EngineName, RequestProfileRow

AGENTX_REQUIRED_COLUMNS: tuple[str, ...] = ("prompt_tokens", "completion_tokens", "latency_ms")
AGENTX_NOT_EMITTED_REQUEST_FIELDS: tuple[str, ...] = (
    "ttft_ms",
    "tpot_ms",
    "cached_tokens",
    "first_token_ts",
    "inter_token_latency_ms_p50",
    "inter_token_latency_ms_p95",
)

_BASE_TS = datetime(2026, 5, 4, tzinfo=UTC)
_GPU_FIELD_MAP = {
    "gpu_utilization_percent": "DCGM_FI_DEV_GPU_UTIL",
    "memory_utilization_gb": "DCGM_FI_DEV_FB_USED",
    "power_consumption_watts": "DCGM_FI_DEV_POWER_USAGE",
}


def missing_required_columns(fieldnames: list[str] | None) -> list[str]:
    names = set(fieldnames or [])
    return [column for column in AGENTX_REQUIRED_COLUMNS if column not in names]


def agentx_to_request_profile(
    row: dict[str, str],
    *,
    sequence: int,
    source_csv_path: Path,
    job_id: str,
    engine: str,
    workload_label: str,
    model_profile: str,
    concurrency: int,
) -> RequestProfileRow:
    prompt_tokens = _required_int(row, "prompt_tokens")
    completion_tokens = _required_int(row, "completion_tokens")
    latency_ms = _required_float(row, "latency_ms")
    send_ts = _timestamp_from_row(row, "send_ts", "request_start_time", fallback_sequence=sequence)
    done_ts = _timestamp_from_row(row, "done_ts", "request_complete_time")
    if done_ts is None or done_ts < send_ts:
        done_ts = send_ts + timedelta(milliseconds=latency_ms)
    throughput = _float_or_none(row.get("throughput_tokens_per_sec"))
    if throughput is None and latency_ms > 0:
        throughput = completion_tokens / (latency_ms / 1000.0)

    return RequestProfileRow(
        request_id=_request_id(row, job_id=job_id, sequence=sequence),
        job_id=job_id,
        workload_label=workload_label,
        model_profile=model_profile,
        engine=_engine_name(engine),
        context_length=prompt_tokens,
        concurrency=_int_or_default(row.get("concurrency"), concurrency),
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        prompt_tokens_source="server",
        send_ts=_iso(send_ts),
        first_token_ts=None,
        done_ts=_iso(done_ts),
        ttft_ms=None,
        e2e_latency_ms=latency_ms,
        tpot_ms=None,
        inter_token_latency_ms_p50=None,
        inter_token_latency_ms_p95=None,
        decode_tokens_per_sec=throughput,
        streaming=False,
        success=_bool_or_default(row.get("success"), True),
        http_status=_int_or_none(row.get("http_status")),
        error_type=_error_type(row),
        error_message=row.get("error_message") or None,
        cached_tokens=None,
        claim_status="measured",
        raw_response_ref=str(source_csv_path),
        claim_status_per_field={
            "prompt_tokens": "measured",
            "completion_tokens": "measured",
            "e2e_latency_ms": "measured",
            "decode_tokens_per_sec": "measured" if throughput is not None else "not_proven",
            **{field: "not_proven" for field in AGENTX_NOT_EMITTED_REQUEST_FIELDS},
        },
    )


def agentx_to_engine_metrics(
    row: dict[str, str],
    *,
    sequence: int,
    observed_at: str,
    engine: str,
    job_id: str,
) -> EngineMetricsSample | None:
    throughput = _float_or_none(row.get("throughput_tokens_per_sec"))
    if throughput is None:
        return None
    return EngineMetricsSample(
        sequence=sequence,
        observed_at=observed_at,
        engine=engine,
        group="decode",
        metrics={"throughput_tokens_per_sec": throughput},
        normalized={"decode_tokens_per_sec": throughput},
        source_metrics=["agentx:throughput_tokens_per_sec"],
        claim_status="measured",
        claim_status_per_field={"decode_tokens_per_sec": "measured"},
        labels={"job_id": job_id, "source": "agentx"},
    )


def agentx_to_gpu_metrics(
    row: dict[str, str],
    *,
    sequence: int,
    observed_at: str,
    job_id: str,
) -> GpuMetricsSample | None:
    metrics: dict[str, float] = {}
    fields: dict[str, Any] = {}
    field_ids: dict[str, str] = {}
    for agentx_field, dcgm_field in _GPU_FIELD_MAP.items():
        value = _float_or_none(row.get(agentx_field))
        if value is None:
            continue
        normalized_value = value * 1024.0 if agentx_field == "memory_utilization_gb" else value
        metrics[dcgm_field] = normalized_value
        fields[dcgm_field] = normalized_value
        field_ids[dcgm_field] = f"agentx:{agentx_field}"
    if not metrics:
        return None
    return GpuMetricsSample(
        sequence=sequence,
        observed_at=observed_at,
        timestamp_window_seconds=1,
        gpu_uuid=None,
        gpu_index=None,
        fields=fields,
        metrics=metrics,
        field_ids=field_ids,
        labels={"job_id": job_id, "source": "agentx"},
    )


def count_mapped_metric_values(
    engine_rows: list[EngineMetricsSample],
    gpu_rows: list[GpuMetricsSample],
) -> int:
    return sum(len(row.metrics) for row in engine_rows) + sum(len(row.metrics) for row in gpu_rows)


def total_tokens_crosscheck(row: dict[str, str]) -> bool | None:
    total = _int_or_none(row.get("total_tokens"))
    if total is None:
        return None
    return total == (_required_int(row, "prompt_tokens") + _required_int(row, "completion_tokens"))


def _request_id(row: dict[str, str], *, job_id: str, sequence: int) -> str:
    for key in ("request_id", "id"):
        if row.get(key):
            return str(row[key])
    trace = row.get("trace_id") or "trace"
    user = row.get("user_id") or row.get("session_id") or "user"
    request_idx = row.get("request_idx") or str(sequence)
    return f"agentx:{job_id}:{trace}:{user}:{request_idx}"


def _timestamp_from_row(
    row: dict[str, str],
    *keys: str,
    fallback_sequence: int | None = None,
) -> datetime | None:
    for key in keys:
        value = row.get(key)
        if not value:
            continue
        parsed = _parse_timestamp(value)
        if parsed is not None:
            return parsed
    if fallback_sequence is None:
        return None
    return _BASE_TS + timedelta(milliseconds=fallback_sequence * 100)


def _parse_timestamp(value: str) -> datetime | None:
    try:
        seconds = float(value)
    except ValueError:
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)
        except ValueError:
            return None
    return datetime.fromtimestamp(seconds, tz=UTC)


def _iso(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _required_int(row: dict[str, str], key: str) -> int:
    value = _int_or_none(row.get(key))
    if value is None:
        raise ValueError(f"missing integer field: {key}")
    return value


def _required_float(row: dict[str, str], key: str) -> float:
    value = _float_or_none(row.get(key))
    if value is None:
        raise ValueError(f"missing float field: {key}")
    return value


def _float_or_none(value: str | None) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except ValueError:
        return None


def _int_or_none(value: str | None) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(float(value))
    except ValueError:
        return None


def _int_or_default(value: str | None, default: int) -> int:
    parsed = _int_or_none(value)
    return parsed if parsed is not None else default


def _bool_or_default(value: str | None, default: bool) -> bool:
    if value in (None, ""):
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "ok", "success"}


def _error_type(row: dict[str, str]) -> str | None:
    if _bool_or_default(row.get("success"), True):
        return None
    raw = (row.get("error_type") or "unknown").strip().lower()
    allowed = {
        "connect_error",
        "timeout",
        "http_4xx",
        "http_5xx",
        "stream_truncated",
        "tokenizer_error",
        "unknown",
    }
    return raw if raw in allowed else "unknown"


def _engine_name(value: str) -> EngineName:
    normalized = value.strip().lower()
    if normalized not in {"vllm", "sglang", "lmcache", "dynamo-sglang", "agentx-replay"}:
        normalized = "agentx-replay"
    return cast(EngineName, normalized)


__all__ = [
    "AGENTX_NOT_EMITTED_REQUEST_FIELDS",
    "AGENTX_REQUIRED_COLUMNS",
    "agentx_to_engine_metrics",
    "agentx_to_gpu_metrics",
    "agentx_to_request_profile",
    "count_mapped_metric_values",
    "missing_required_columns",
    "total_tokens_crosscheck",
]

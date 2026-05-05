"""Validators for the locked ``inferguard-telemetry/v1`` upload payload."""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Literal

TELEMETRY_SCHEMA_VERSION = "inferguard-telemetry/v1"

PAYLOAD_KINDS = {"bench-summary", "agent-trace-summary", "metrics-rollup"}
GPU_MODELS = {"H200", "B200", "GB200", "H100"}
GPU_COUNT_BUCKETS = {"8", "16", "32", "64+"}
ENGINES = {"vllm", "sglang", "dynamo-vllm"}
DP_MECHANISMS = {"stub", "laplace", "gaussian"}
DP_LIBRARIES = {"stub", "pipelinedp", "opendp", "google-dp"}
PAYLOAD_KEYS = {
    "schema_version",
    "consent_token",
    "anonymized_deployment_id",
    "uploaded_at",
    "payload_kind",
    "rig_fingerprint",
    "aggregates",
    "dp_params",
}
RIG_KEYS = {"gpu_model", "gpu_count_bucket", "engine", "engine_version_major_minor"}
AGGREGATE_KEYS = {
    "ttft_p50_ms_bucketed",
    "ttft_p99_ms_bucketed",
    "kv_pressure_p95_bucketed",
    "prefix_cache_hit_rate_bucketed",
    "tool_stall_pct_bucketed",
    "node_counts",
    "concurrency_cliff_estimate",
}
DP_KEYS = {"epsilon", "delta", "mechanism", "library"}
HEX16_RE = re.compile(r"^[0-9a-f]{16}$")
ENGINE_VERSION_RE = re.compile(r"^\d+\.\d+$")


class TelemetryValidationError(ValueError):
    """Raised when an ``inferguard-telemetry/v1`` payload is malformed."""


@dataclass(frozen=True)
class RigFingerprint:
    gpu_model: Literal["H200", "B200", "GB200", "H100"]
    gpu_count_bucket: Literal["8", "16", "32", "64+"]
    engine: Literal["vllm", "sglang", "dynamo-vllm"]
    engine_version_major_minor: str

    @classmethod
    def from_dict(cls, data: dict[str, Any], *, source: str = "rig_fingerprint") -> RigFingerprint:
        _require_object(data, source)
        _assert_keys(data, RIG_KEYS, source)
        _require_fields(data, RIG_KEYS, source)
        version = _str(data["engine_version_major_minor"], "engine_version_major_minor", source)
        if not ENGINE_VERSION_RE.match(version):
            raise TelemetryValidationError(
                f"{source}: engine_version_major_minor must look like '0.20'"
            )
        return cls(
            gpu_model=_enum(data["gpu_model"], GPU_MODELS, "gpu_model", source),
            gpu_count_bucket=_enum(
                data["gpu_count_bucket"], GPU_COUNT_BUCKETS, "gpu_count_bucket", source
            ),
            engine=_enum(data["engine"], ENGINES, "engine", source),
            engine_version_major_minor=version,
        )

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class TelemetryAggregates:
    ttft_p50_ms_bucketed: float
    ttft_p99_ms_bucketed: float
    kv_pressure_p95_bucketed: float
    prefix_cache_hit_rate_bucketed: float
    tool_stall_pct_bucketed: float
    node_counts: dict[str, int]
    concurrency_cliff_estimate: int

    @classmethod
    def from_dict(cls, data: dict[str, Any], *, source: str = "aggregates") -> TelemetryAggregates:
        _require_object(data, source)
        _assert_keys(data, AGGREGATE_KEYS, source)
        _require_fields(data, AGGREGATE_KEYS, source)
        return cls(
            ttft_p50_ms_bucketed=_non_negative_number(
                data["ttft_p50_ms_bucketed"], "ttft_p50_ms_bucketed", source
            ),
            ttft_p99_ms_bucketed=_non_negative_number(
                data["ttft_p99_ms_bucketed"], "ttft_p99_ms_bucketed", source
            ),
            kv_pressure_p95_bucketed=_bounded_unit(
                data["kv_pressure_p95_bucketed"], "kv_pressure_p95_bucketed", source
            ),
            prefix_cache_hit_rate_bucketed=_bounded_unit(
                data["prefix_cache_hit_rate_bucketed"], "prefix_cache_hit_rate_bucketed", source
            ),
            tool_stall_pct_bucketed=_bounded_unit(
                data["tool_stall_pct_bucketed"], "tool_stall_pct_bucketed", source
            ),
            node_counts=_int_map(data["node_counts"], "node_counts", source),
            concurrency_cliff_estimate=_non_negative_int(
                data["concurrency_cliff_estimate"], "concurrency_cliff_estimate", source
            ),
        )

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class DPParams:
    epsilon: float
    delta: float
    mechanism: Literal["stub", "laplace", "gaussian"]
    library: Literal["stub", "pipelinedp", "opendp", "google-dp"]

    @classmethod
    def from_dict(cls, data: dict[str, Any], *, source: str = "dp_params") -> DPParams:
        _require_object(data, source)
        _assert_keys(data, DP_KEYS, source)
        _require_fields(data, DP_KEYS, source)
        epsilon = _positive_number(data["epsilon"], "epsilon", source)
        delta = _positive_number(data["delta"], "delta", source)
        if delta >= 1:
            raise TelemetryValidationError(f"{source}: delta must be < 1")
        return cls(
            epsilon=epsilon,
            delta=delta,
            mechanism=_enum(data["mechanism"], DP_MECHANISMS, "mechanism", source),
            library=_enum(data["library"], DP_LIBRARIES, "library", source),
        )

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class TelemetryPayload:
    schema_version: Literal["inferguard-telemetry/v1"]
    consent_token: str
    anonymized_deployment_id: str
    uploaded_at: str
    payload_kind: Literal["bench-summary", "agent-trace-summary", "metrics-rollup"]
    rig_fingerprint: RigFingerprint
    aggregates: TelemetryAggregates
    dp_params: DPParams

    @classmethod
    def from_dict(cls, data: dict[str, Any], *, source: str = "payload") -> TelemetryPayload:
        _require_object(data, source)
        _assert_keys(data, PAYLOAD_KEYS, source)
        _require_fields(data, PAYLOAD_KEYS, source)
        if data["schema_version"] != TELEMETRY_SCHEMA_VERSION:
            raise TelemetryValidationError(
                f"{source}: schema_version must be {TELEMETRY_SCHEMA_VERSION!r}"
            )
        deployment_id = _str(data["anonymized_deployment_id"], "anonymized_deployment_id", source)
        if not HEX16_RE.match(deployment_id):
            raise TelemetryValidationError(
                f"{source}: anonymized_deployment_id must be 16 lowercase hex characters"
            )
        return cls(
            schema_version=TELEMETRY_SCHEMA_VERSION,
            consent_token=_str(data["consent_token"], "consent_token", source),
            anonymized_deployment_id=deployment_id,
            uploaded_at=_str(data["uploaded_at"], "uploaded_at", source),
            payload_kind=_enum(data["payload_kind"], PAYLOAD_KINDS, "payload_kind", source),
            rig_fingerprint=RigFingerprint.from_dict(
                data["rig_fingerprint"], source=f"{source}.rig_fingerprint"
            ),
            aggregates=TelemetryAggregates.from_dict(data["aggregates"], source=f"{source}.aggregates"),
            dp_params=DPParams.from_dict(data["dp_params"], source=f"{source}.dp_params"),
        )

    def as_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["rig_fingerprint"] = self.rig_fingerprint.as_dict()
        data["aggregates"] = self.aggregates.as_dict()
        data["dp_params"] = self.dp_params.as_dict()
        return data


def validate_telemetry_payload(data: dict[str, Any], *, source: str = "payload") -> TelemetryPayload:
    """Validate one locked ``inferguard-telemetry/v1`` payload."""

    return TelemetryPayload.from_dict(data, source=source)


def load_telemetry_payload(path: Path | str) -> TelemetryPayload:
    """Read and validate a telemetry payload JSON file."""

    payload_path = Path(path)
    try:
        data = json.loads(payload_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise TelemetryValidationError(f"{payload_path}: invalid JSON") from exc
    return validate_telemetry_payload(data, source=str(payload_path))


def _require_object(value: Any, source: str) -> None:
    if not isinstance(value, dict):
        raise TelemetryValidationError(f"{source}: must be a JSON object")


def _assert_keys(data: dict[str, Any], allowed: set[str], source: str) -> None:
    unknown = sorted(set(data) - allowed)
    if unknown:
        raise TelemetryValidationError(f"{source}: unknown field(s): {', '.join(unknown)}")


def _require_fields(data: dict[str, Any], required: set[str], source: str) -> None:
    missing = sorted(required - set(data))
    if missing:
        raise TelemetryValidationError(f"{source}: missing required field(s): {', '.join(missing)}")


def _str(value: Any, key: str, source: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise TelemetryValidationError(f"{source}: {key} must be a non-empty string")
    return value


def _non_negative_int(value: Any, key: str, source: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise TelemetryValidationError(f"{source}: {key} must be a non-negative integer")
    return value


def _non_negative_number(value: Any, key: str, source: str) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float) or value < 0:
        raise TelemetryValidationError(f"{source}: {key} must be a non-negative number")
    return float(value)


def _positive_number(value: Any, key: str, source: str) -> float:
    number = _non_negative_number(value, key, source)
    if number <= 0:
        raise TelemetryValidationError(f"{source}: {key} must be > 0")
    return number


def _bounded_unit(value: Any, key: str, source: str) -> float:
    number = _non_negative_number(value, key, source)
    if number > 1:
        raise TelemetryValidationError(f"{source}: {key} must be between 0 and 1")
    return number


def _int_map(value: Any, key: str, source: str) -> dict[str, int]:
    if not isinstance(value, dict):
        raise TelemetryValidationError(f"{source}: {key} must be an object")
    result: dict[str, int] = {}
    for item_key, item_value in value.items():
        if not isinstance(item_key, str):
            raise TelemetryValidationError(f"{source}: {key} keys must be strings")
        result[item_key] = _non_negative_int(item_value, f"{key}.{item_key}", source)
    return result


def _enum(value: Any, allowed: set[Any], key: str, source: str) -> Any:
    if value not in allowed:
        rendered = ", ".join(repr(item) for item in sorted(allowed, key=str))
        raise TelemetryValidationError(f"{source}: {key} must be one of {rendered}")
    return value

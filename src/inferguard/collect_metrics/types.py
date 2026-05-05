"""Contracts for the NeoCloud/GMI collect-metrics command."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

ENGINE_TIMELINE_SCHEMA_VERSION = "inferguard-engine-metrics-timeline/v1"
GPU_TIMELINE_SCHEMA_VERSION = "dcgm-correlated/v1"
METRICS_SUMMARY_SCHEMA_VERSION = "inferguard-metrics-summary/v1"
RAW_PROM_SAMPLES_SCHEMA_VERSION = "inferguard-raw-prom-samples/v1"

CLAIM_STATUSES = {"measured", "inferred", "synthetic", "not_proven"}
ENGINE_GROUPS: tuple[str, ...] = (
    "prefill",
    "decode",
    "queue",
    "kv_cache",
    "prefix_cache",
    "lmcache",
)
GPU_GROUPS: tuple[str, ...] = (
    "gpu_util",
    "hbm",
    "nvlink",
    "pcie",
    "power",
    "xid_ecc",
)
NORMALIZED_GROUPS: tuple[str, ...] = ENGINE_GROUPS + GPU_GROUPS


@dataclass(frozen=True)
class CollectMetricsOptions:
    """Options for ``collect-metrics``."""

    engine: str
    engine_metrics_url: str
    dcgm_metrics_url: str
    duration_seconds: float
    output_dir: Path
    interval_seconds: float = 1.0
    dcgm_interval_seconds: float = 5.0
    lmcache_metrics_url: str | None = None
    label_job_id: str | None = None
    label_engine_version: str | None = None
    label_hardware: str | None = None
    keep_raw_samples: bool = False
    timeout_seconds: float = 5.0

    def labels(self) -> dict[str, str]:
        """Return non-empty operator labels for timeline rows."""

        labels: dict[str, str] = {}
        if self.label_job_id:
            labels["job_id"] = self.label_job_id
        if self.label_engine_version:
            labels["engine_version"] = self.label_engine_version
        if self.label_hardware:
            labels["hardware"] = self.label_hardware
        return labels


@dataclass(frozen=True)
class EngineMetricsSample:
    """One normalized engine metrics row for one scrape interval and group."""

    sequence: int
    observed_at: str
    engine: str
    group: str
    metrics: dict[str, float] = field(default_factory=dict)
    normalized: dict[str, Any] = field(default_factory=dict)
    source_metrics: list[str] = field(default_factory=list)
    claim_status: str = "not_proven"
    claim_status_per_field: dict[str, str] = field(default_factory=dict)
    labels: dict[str, str] = field(default_factory=dict)
    model_name: str = ""
    scrape_error: str = ""
    schema_version: str = ENGINE_TIMELINE_SCHEMA_VERSION

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "sequence": self.sequence,
            "observed_at": self.observed_at,
            "engine": self.engine,
            "group": self.group,
            "model_name": self.model_name,
            "metrics": dict(sorted(self.metrics.items())),
            "source_metrics": sorted(self.source_metrics),
            "normalized": dict(self.normalized),
            "claim_status": self.claim_status,
            "claim_status_per_field": dict(sorted(self.claim_status_per_field.items())),
            "labels": dict(sorted(self.labels.items())),
            "scrape_error": self.scrape_error,
        }


@dataclass(frozen=True)
class GpuMetricsSample:
    """One ``dcgm-correlated/v1`` GPU metrics row."""

    sequence: int
    observed_at: str
    timestamp_window_seconds: int
    gpu_uuid: str | None
    gpu_index: int | None
    fields: dict[str, Any] = field(default_factory=dict)
    metrics: dict[str, float] = field(default_factory=dict)
    field_ids: dict[str, str] = field(default_factory=dict)
    labels: dict[str, str] = field(default_factory=dict)
    scrape_error: str = ""
    schema_version: str = GPU_TIMELINE_SCHEMA_VERSION

    def as_dict(self) -> dict[str, Any]:
        row = {
            "schema_version": self.schema_version,
            "sequence": self.sequence,
            "timestamp": self.observed_at,
            "observed_at": self.observed_at,
            "timestamp_window_seconds": self.timestamp_window_seconds,
            "gpu_uuid": self.gpu_uuid,
            "gpu_index": self.gpu_index,
            "metrics": dict(sorted(self.metrics.items())),
            "field_ids": dict(sorted(self.field_ids.items())),
            "labels": dict(sorted(self.labels.items())),
            "scrape_error": self.scrape_error,
        }
        row.update(dict(self.fields))
        return row


@dataclass(frozen=True)
class MetricsSummary:
    """Top-level normalized metrics summary."""

    engine: str
    duration_seconds: float
    sample_count: int
    dcgm_sample_count: int
    generated_at: str
    groups: dict[str, dict[str, Any]]
    labels: dict[str, str] = field(default_factory=dict)
    schema_version: str = METRICS_SUMMARY_SCHEMA_VERSION

    def as_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "schema_version": self.schema_version,
            "engine": self.engine,
            "duration_seconds": self.duration_seconds,
            "sample_count": self.sample_count,
            "dcgm_sample_count": self.dcgm_sample_count,
            "generated_at": self.generated_at,
            "labels": dict(sorted(self.labels.items())),
        }
        for group in NORMALIZED_GROUPS:
            data[group] = dict(self.groups.get(group, {"claim_status": "not_proven"}))
        return data


__all__ = [
    "CLAIM_STATUSES",
    "ENGINE_GROUPS",
    "ENGINE_TIMELINE_SCHEMA_VERSION",
    "GPU_GROUPS",
    "GPU_TIMELINE_SCHEMA_VERSION",
    "METRICS_SUMMARY_SCHEMA_VERSION",
    "NORMALIZED_GROUPS",
    "RAW_PROM_SAMPLES_SCHEMA_VERSION",
    "CollectMetricsOptions",
    "EngineMetricsSample",
    "GpuMetricsSample",
    "MetricsSummary",
]

"""Public entry point for PRD §4.3 collect-metrics."""

from __future__ import annotations

from .normalize import build_metrics_summary, normalize_dcgm_sample, normalize_engine_sample
from .runner import (
    ENGINE_TIMELINE_FILENAME,
    GPU_TIMELINE_FILENAME,
    METRICS_SUMMARY_FILENAME,
    RAW_SAMPLES_FILENAME,
    SUPPORTED_ENGINES,
    CollectMetricsError,
    collect_metrics,
    run_collect_metrics,
)
from .types import (
    ENGINE_TIMELINE_SCHEMA_VERSION,
    GPU_TIMELINE_SCHEMA_VERSION,
    METRICS_SUMMARY_SCHEMA_VERSION,
    RAW_PROM_SAMPLES_SCHEMA_VERSION,
    CollectMetricsOptions,
    EngineMetricsSample,
    GpuMetricsSample,
    MetricsSummary,
)

__all__ = [
    "ENGINE_TIMELINE_FILENAME",
    "ENGINE_TIMELINE_SCHEMA_VERSION",
    "GPU_TIMELINE_FILENAME",
    "GPU_TIMELINE_SCHEMA_VERSION",
    "METRICS_SUMMARY_FILENAME",
    "METRICS_SUMMARY_SCHEMA_VERSION",
    "RAW_PROM_SAMPLES_SCHEMA_VERSION",
    "RAW_SAMPLES_FILENAME",
    "SUPPORTED_ENGINES",
    "CollectMetricsError",
    "CollectMetricsOptions",
    "EngineMetricsSample",
    "GpuMetricsSample",
    "MetricsSummary",
    "build_metrics_summary",
    "collect_metrics",
    "normalize_dcgm_sample",
    "normalize_engine_sample",
    "run_collect_metrics",
]

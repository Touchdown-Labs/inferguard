"""AMD ROCm artifact parsers for the profiler bridge."""

from __future__ import annotations

import csv
from pathlib import Path

from inferguard.profilers.schema import CounterSample, KernelEvent, RooflinePoint


def parse_rocprofv3_kernel_trace_csv(path: str | Path) -> list[KernelEvent]:
    rows = _read_rows(path)
    events: list[KernelEvent] = []
    for row in rows:
        name = _field(row, "Kernel_Name", "KernelName", "Name", "Kernel")
        if not name:
            continue
        events.append(
            KernelEvent(
                source="rocprofv3_kernel_trace",
                vendor="amd",
                name=name,
                duration_ms=_to_duration_ms(row),
                calls=_to_int(_field(row, "Calls", "Count")) or 1,
                raw=dict(row),
            )
        )
    return events


def parse_rocprof_compute_pmc_perf_csv(path: str | Path) -> list[CounterSample]:
    rows = _read_rows(path)
    samples: list[CounterSample] = []
    for row in rows:
        metric = _field(row, "Metric", "Counter", "Name")
        value = _to_float(_field(row, "Value", "Mean", "Avg"))
        if not metric or value is None:
            continue
        samples.append(
            CounterSample(
                source="rocprof_compute_pmc_perf",
                vendor="amd",
                name=_normalize_amd_metric(metric),
                value=value,
                unit=_field(row, "Unit"),
                kernel_name=_field(row, "Kernel_Name", "Kernel"),
                raw_name=metric,
            )
        )
    return samples


def parse_rocprof_compute_roofline_csv(path: str | Path) -> list[RooflinePoint]:
    rows = _read_rows(path)
    points: list[RooflinePoint] = []
    for row in rows:
        kernel = _field(row, "Kernel_Name", "Kernel", "Name")
        if not kernel:
            continue
        points.append(
            RooflinePoint(
                source="rocprof_compute_roofline",
                vendor="amd",
                kernel_name=kernel,
                arithmetic_intensity=_to_float(_field(row, "Arithmetic_Intensity", "AI")),
                performance=_to_float(_field(row, "Performance", "GFLOPs", "TFLOPs")),
                bound=_field(row, "Bound", "Limiting_Factor"),
                raw=dict(row),
            )
        )
    return points


def _read_rows(path: str | Path) -> list[dict[str, str]]:
    with Path(path).open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _field(row: dict[str, str], *names: str) -> str | None:
    for name in names:
        value = row.get(name)
        if value not in (None, ""):
            return value.strip()
    return None


def _to_float(value: str | None) -> float | None:
    if value is None:
        return None
    try:
        return float(value.replace(",", ""))
    except ValueError:
        return None


def _to_int(value: str | None) -> int | None:
    parsed = _to_float(value)
    return int(parsed) if parsed is not None else None


def _to_duration_ms(row: dict[str, str]) -> float | None:
    duration = _to_float(_field(row, "DurationNs", "Duration (ns)", "Duration_ns"))
    if duration is not None:
        return duration / 1_000_000.0
    duration_us = _to_float(_field(row, "DurationUs", "Duration (us)", "Duration_us"))
    if duration_us is not None:
        return duration_us / 1_000.0
    return _to_float(_field(row, "DurationMs", "Duration (ms)", "Duration_ms"))


def _normalize_amd_metric(metric: str) -> str:
    lowered = metric.lower()
    if "mfma" in lowered or "valu" in lowered:
        return "mfma_valu_utilization_proxy"
    if "tcc" in lowered or "hbm" in lowered or "memory" in lowered:
        return "memory_bandwidth_proxy"
    if "occupancy" in lowered or "wave" in lowered:
        return "occupancy_proxy"
    return metric

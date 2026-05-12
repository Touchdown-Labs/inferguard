"""NVIDIA Nsight artifact parsers for the profiler bridge."""

from __future__ import annotations

import csv
from pathlib import Path

from inferguard.profilers.schema import CounterSample, KernelEvent


def parse_nsys_kernel_summary_csv(path: str | Path) -> list[KernelEvent]:
    rows = _read_rows(path)
    events: list[KernelEvent] = []
    for row in rows:
        name = _field(row, "Name", "Kernel Name", "Kernel")
        if not name:
            continue
        events.append(
            KernelEvent(
                source="nsys_stats_kernel_sum",
                vendor="nvidia",
                name=name,
                duration_ms=_to_float(_field(row, "Total Time (ns)", "Total Time", "Time"), scale=1_000_000.0),
                calls=_to_int(_field(row, "Instances", "Calls", "Count")),
                raw=dict(row),
            )
        )
    return events


def parse_ncu_csv(path: str | Path) -> list[CounterSample]:
    rows = _read_rows(path)
    samples: list[CounterSample] = []
    for row in rows:
        metric = _field(row, "Metric Name", "Metric", "Name")
        value = _to_float(_field(row, "Metric Value", "Value"))
        if not metric or value is None:
            continue
        samples.append(
            CounterSample(
                source="ncu_csv",
                vendor="nvidia",
                name=_normalize_nvidia_metric(metric),
                value=value,
                unit=_field(row, "Unit"),
                kernel_name=_field(row, "Kernel Name", "Kernel"),
                raw_name=metric,
            )
        )
    return samples


def _read_rows(path: str | Path) -> list[dict[str, str]]:
    with Path(path).open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _field(row: dict[str, str], *names: str) -> str | None:
    for name in names:
        value = row.get(name)
        if value not in (None, ""):
            return value.strip()
    return None


def _to_float(value: str | None, scale: float = 1.0) -> float | None:
    if value is None:
        return None
    try:
        return float(value.replace(",", "")) / scale
    except ValueError:
        return None


def _to_int(value: str | None) -> int | None:
    parsed = _to_float(value)
    return int(parsed) if parsed is not None else None


def _normalize_nvidia_metric(metric: str) -> str:
    lowered = metric.lower()
    if "tensor" in lowered:
        return "tensor_utilization_proxy"
    if "dram" in lowered or "memory" in lowered:
        return "memory_bandwidth_proxy"
    if "occupancy" in lowered or "warps_active" in lowered:
        return "occupancy_proxy"
    return metric

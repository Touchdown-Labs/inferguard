"""SVG plot generation for InferGuard analyze reports."""

from __future__ import annotations

from pathlib import Path
from typing import Any

PLOT_EXTRA_MESSAGE = "Install with: pip install 'inferguard[plot]'"


def render_plots(
    report_dict: dict[str, Any], output_dir: Path, logger: Any | None = None
) -> list[Path]:
    """Render all available report plots into ``output_dir``."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    written = [
        plot_ttft_vs_concurrency(report_dict, output_dir / "ttft_vs_concurrency.svg"),
        plot_throughput_per_gpu(report_dict, output_dir / "throughput_per_gpu.svg"),
    ]
    cost_plot = plot_cost_per_task(report_dict, output_dir / "cost_per_task.svg")
    if cost_plot is not None:
        written.append(cost_plot)
    elif logger is not None:
        logger.debug("Skipping cost_per_task.svg because no cost data is present")
    return written


def plot_ttft_vs_concurrency(report_dict: dict[str, Any], output_path: Path) -> Path:
    """Render TTFT p99 by concurrency as an SVG line plot."""
    plt = _pyplot()
    series: dict[str, list[tuple[float, float]]] = {}
    for cell in _sorted_cells(report_dict):
        concurrency = _number(cell.get("concurrency"))
        ttft = _number((cell.get("metrics") or {}).get("p99_ttft"))
        if concurrency is None or ttft is None:
            continue
        series.setdefault(_series_label(cell), []).append((concurrency, _ttft_ms(ttft)))

    fig, ax = plt.subplots(figsize=(7, 4), dpi=120)
    for label in sorted(series):
        points = sorted(series[label])
        ax.plot([p[0] for p in points], [p[1] for p in points], marker="o", label=label)
    ax.set_title("TTFT p99 vs concurrency")
    ax.set_xlabel("Concurrency")
    ax.set_ylabel("TTFT p99 (ms)")
    ax.grid(True, axis="y", alpha=0.25)
    if series:
        ax.legend(fontsize="small")
    fig.tight_layout()
    return _save_svg(fig, output_path, plt)


def plot_throughput_per_gpu(report_dict: dict[str, Any], output_path: Path) -> Path:
    """Render output throughput per GPU as an SVG bar chart."""
    plt = _pyplot()
    labels: list[str] = []
    values: list[float] = []
    for cell in _sorted_cells(report_dict):
        metrics = cell.get("metrics") or {}
        throughput_per_gpu = _number(
            metrics.get("output_tput_per_gpu") or metrics.get("tput_per_gpu")
        )
        gpu_count = _gpu_count(cell)
        if throughput_per_gpu is None:
            total_throughput = _number(metrics.get("output_tput_tps"))
            if total_throughput is None:
                continue
            throughput_per_gpu = total_throughput / gpu_count if gpu_count else total_throughput
        suffix = f"{_format_gpu_count(gpu_count)}GPUs" if gpu_count else "?GPUs"
        labels.append(f"{cell.get('cell_id', 'cell')}\n{suffix}")
        values.append(throughput_per_gpu)

    fig, ax = plt.subplots(figsize=(max(6, len(labels) * 1.5), 4), dpi=120)
    ax.bar(labels, values, color="#4C78A8")
    ax.set_title("Output throughput per GPU")
    ax.set_xlabel("Cell")
    ax.set_ylabel("Output tokens/sec/GPU")
    ax.grid(True, axis="y", alpha=0.25)
    ax.tick_params(axis="x", labelrotation=25)
    fig.tight_layout()
    return _save_svg(fig, output_path, plt)


def plot_cost_per_task(report_dict: dict[str, Any], output_path: Path) -> Path | None:
    """Render cost per completed session as an SVG bar chart, if cost data exists."""
    rows: list[tuple[str, float]] = []
    for cell in _sorted_cells(report_dict):
        cost_per_session = _number((cell.get("cost") or {}).get("cost_per_completed_session"))
        if cost_per_session is None:
            continue
        rows.append((str(cell.get("cell_id", "cell")), cost_per_session))
    if not rows:
        return None

    plt = _pyplot()
    labels = [row[0] for row in rows]
    values = [row[1] for row in rows]
    fig, ax = plt.subplots(figsize=(max(6, len(labels) * 1.5), 4), dpi=120)
    ax.bar(labels, values, color="#59A14F")
    ax.set_title("Cost per completed session")
    ax.set_xlabel("Cell")
    ax.set_ylabel("Cost per completed session (USD)")
    ax.grid(True, axis="y", alpha=0.25)
    ax.tick_params(axis="x", labelrotation=25)
    fig.tight_layout()
    return _save_svg(fig, output_path, plt)


def _pyplot() -> Any:
    try:
        import matplotlib

        matplotlib.use("Agg", force=True)
        from matplotlib import pyplot as plt
    except ImportError as exc:
        raise RuntimeError(PLOT_EXTRA_MESSAGE) from exc
    return plt


def _save_svg(fig: Any, output_path: Path, plt: Any) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, format="svg", metadata={"Date": None})
    plt.close(fig)
    return output_path


def _sorted_cells(report_dict: dict[str, Any]) -> list[dict[str, Any]]:
    cells = report_dict.get("cells") or []
    return sorted(
        (cell for cell in cells if isinstance(cell, dict)), key=lambda c: str(c.get("cell_id", ""))
    )


def _series_label(cell: dict[str, Any]) -> str:
    parts = [cell.get("source_format"), cell.get("hardware")]
    label = " / ".join(str(part) for part in parts if part)
    return label or str(cell.get("cell_id", "cell"))


def _gpu_count(cell: dict[str, Any]) -> float | None:
    for key in ("gpus", "gpu_count", "num_gpus"):
        value = _number(cell.get(key))
        if value:
            return value
    topology = cell.get("topology") or {}
    for key in ("num_gpus", "gpu_count", "num_gpu"):
        value = _number(topology.get(key))
        if value:
            return value
    prefill = _number(topology.get("num_prefill_gpu"))
    decode = _number(topology.get("num_decode_gpu"))
    if prefill or decode:
        return (prefill or 0) + (decode or 0)
    return None


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int | float):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return None
    return None


def _ttft_ms(value: float) -> float:
    return value * 1000 if value <= 10 else value


def _format_gpu_count(value: float) -> str:
    return str(int(value)) if value.is_integer() else f"{value:g}"

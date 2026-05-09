"""Markdown report renderer for profiler bridge runs."""

from __future__ import annotations

from inferguard.profilers.schema import NormalizedProfilerRun


def render_markdown_report(run: NormalizedProfilerRun) -> str:
    lines = [
        "# InferGuard Profiler Bridge Report",
        "",
        f"- Schema: `{run.schema_version}`",
        f"- Run: `{run.run_id}`",
        f"- Vendor/GPU: `{run.device.vendor}` `{run.device.model}`",
        f"- Architecture: `{run.device.architecture or 'unknown'}`",
        f"- Capture mode: `{run.capture_mode}`",
        f"- Confidence: `{run.confidence}`",
        "",
        "## Request metrics",
    ]
    if run.request_metrics:
        metrics = run.request_metrics
        lines.extend(
            [
                f"- TTFT seconds: `{_fmt(metrics.ttft_seconds)}`",
                f"- ITL seconds: `{_fmt(metrics.itl_seconds)}`",
                f"- Latency seconds: `{_fmt(metrics.latency_seconds)}`",
                f"- Queue depth: `{_fmt(metrics.queue_depth)}`",
            ]
        )
    else:
        lines.append("- `not_proven`: no vLLM Prometheus metrics artifact was imported.")
    lines.extend(["", "## Profiler artifacts", ""])
    lines.append(f"- Kernel events: `{len(run.kernel_events)}`")
    lines.append(f"- Counter samples: `{len(run.counter_samples)}`")
    lines.append(f"- Roofline points: `{len(run.roofline_points)}`")
    lines.extend(["", "## Findings", ""])
    if run.findings:
        for finding in run.findings:
            lines.append(f"- `{finding.confidence}` `{finding.code}`: {finding.message}")
    else:
        lines.append("- No findings from imported artifacts. This is not a performance claim.")
    lines.extend(
        [
            "",
            "## Live validation note",
            "",
            "Synthetic or sanitized fixtures prove parser behavior only. Move to `live_validated` only after real vLLM, Nsight, or ROCm artifacts are imported from target hardware.",
        ]
    )
    return "\n".join(lines) + "\n"


def _fmt(value: float | None) -> str:
    return "missing" if value is None else str(value)

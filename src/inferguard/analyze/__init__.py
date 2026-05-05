"""Read-only post-run analyzer for benchmark result directories."""

from .compare import CompareError, CompareOptions, compare_runs, render_compare_markdown
from .core import AnalyzeError, AnalyzeOptions, analyze_results, exit_code_for_report
from .operator_brief import (
    build_operator_brief,
    emit_operator_brief,
    render_operator_brief_markdown,
)
from .plots import (
    plot_cost_per_task,
    plot_throughput_per_gpu,
    plot_ttft_vs_concurrency,
    render_plots,
)

__all__ = [
    "AnalyzeError",
    "AnalyzeOptions",
    "CompareError",
    "CompareOptions",
    "analyze_results",
    "compare_runs",
    "exit_code_for_report",
    "build_operator_brief",
    "emit_operator_brief",
    "render_operator_brief_markdown",
    "render_compare_markdown",
    "plot_cost_per_task",
    "plot_throughput_per_gpu",
    "plot_ttft_vs_concurrency",
    "render_plots",
]

"""Cross-engine comparison report for InferGuard bench run directories."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from statistics import mean
from typing import Any

from inferguard import __version__
from inferguard.io import atomic_write_json

COMPARE_SCHEMA_VERSION = "inferguard-compare/v1"
IDENTITY_KEY_SEPARATOR = "#turn-"
TTFT_CLIFF_MULTIPLIER = 2.0
FAILURE_CLIFF_RATE = 0.10
BLUE_GREEN_P99_REGRESSION_FACTOR = 1.5
BLUE_GREEN_SIGNIFICANCE_P_VALUE = 0.05


class CompareError(RuntimeError):
    """Raised when benchmark comparison artifacts cannot be read or written."""


@dataclass(frozen=True)
class CompareOptions:
    output_dir: Path
    label_a: str | None = None
    label_b: str | None = None
    min_identity_overlap: float = 0.50
    strict_identity: bool = False
    cost_per_gpu_hour: float | None = None
    gpus: int | None = None
    blue_green: bool = False
    force: bool = False


@dataclass(frozen=True)
class _RunArtifacts:
    path: Path
    label: str
    summary: dict[str, Any]
    config: dict[str, Any]
    requests: list[dict[str, Any]]
    metrics: list[dict[str, Any]]
    engine: str


def compare_runs(run_a_dir: Path, run_b_dir: Path, options: CompareOptions) -> dict[str, Any]:
    """Compare two InferGuard bench run directories and write compare artifacts."""
    _validate_options(options)
    output_dir = options.output_dir
    if output_dir.exists() and any(output_dir.iterdir()) and not options.force:
        raise CompareError(
            f"output_dir is not empty: {output_dir} (choose a new directory or pass --force)"
        )
    output_dir.mkdir(parents=True, exist_ok=True)

    run_a = _load_run(run_a_dir, explicit_label=options.label_a, fallback_label="run_a")
    run_b = _load_run(run_b_dir, explicit_label=options.label_b, fallback_label="run_b")
    identity = _trace_identity(run_a, run_b, min_overlap=options.min_identity_overlap)
    findings = []
    if identity["status"] != "ok":
        findings.append(
            {
                "code": "trace_identity_overlap_low",
                "severity": "critical" if options.strict_identity else "warning",
                "message": (
                    f"Trace identity overlap is {identity['overlap_ratio']:.1%}; expected > "
                    f"{options.min_identity_overlap:.0%}. Compare the same ISB-1 trace pack for publishable claims."
                ),
                "evidence": identity,
            }
        )
    if options.strict_identity and identity["status"] != "ok":
        raise CompareError(findings[0]["message"])

    workload_rows = _compare_workloads(run_a, run_b, options)
    if options.blue_green:
        findings.extend(_blue_green_findings(run_a, run_b, workload_rows))
    report = {
        "schema_version": COMPARE_SCHEMA_VERSION,
        "generated_at": _now_iso(),
        "inferguard_version": __version__,
        "run_a": _run_identity(run_a),
        "run_b": _run_identity(run_b),
        "options": {
            "min_identity_overlap": options.min_identity_overlap,
            "strict_identity": options.strict_identity,
            "cost_per_gpu_hour": options.cost_per_gpu_hour,
            "gpus": options.gpus,
            "blue_green": options.blue_green,
        },
        "trace_identity": identity,
        "workload_classes": workload_rows,
        "findings": findings,
        "notes": [
            "Delta fields are run_b minus run_a.",
            "For TTFT, TPOT, and cost, negative deltas favor run_b; for cliff concurrency, positive deltas favor run_b.",
            "Cost-per-task is emitted only when --cost-per-gpu-hour and --gpus are provided.",
            "Blue/green findings treat run_a as blue/baseline and run_b as green/candidate.",
        ],
    }
    _write_json(output_dir / "compare.json", report)
    (output_dir / "compare.md").write_text(render_compare_markdown(report), encoding="utf-8")
    return report


def render_compare_markdown(report: dict[str, Any]) -> str:
    """Render a human-readable compare report."""
    run_a = report["run_a"]
    run_b = report["run_b"]
    identity = report["trace_identity"]
    lines = [
        "# InferGuard Bench Compare Report",
        "",
        f"- Schema: `{report['schema_version']}`",
        f"- Generated: `{report['generated_at']}`",
        f"- Run A: `{run_a['label']}` ({run_a['engine']}) — `{run_a['path']}`",
        f"- Run B: `{run_b['label']}` ({run_b['engine']}) — `{run_b['path']}`",
        f"- Trace identity overlap: {identity['overlap_count']} shared / min({identity['run_a_count']}, {identity['run_b_count']}) = {identity['overlap_ratio']:.1%} ({identity['status']})",
        "",
    ]
    if report.get("findings"):
        lines.extend(["## Findings", ""])
        for finding in report["findings"]:
            lines.append(
                f"- **{finding['severity'].upper()}** `{finding['code']}` — {finding['message']}"
            )
        lines.append("")

    blue_green = [
        finding
        for finding in report.get("findings", [])
        if finding.get("code") == "blue_green_p99_regression"
    ]
    if blue_green:
        lines.extend(
            [
                "## Blue/green comparison",
                "",
                "| Metric | Baseline p99 | Candidate p99 | Regression factor | p-value |",
                "|---|---:|---:|---:|---:|",
            ]
        )
        for finding in blue_green:
            evidence = finding.get("evidence") or {}
            lines.append(
                "| {metric} | {baseline} | {candidate} | {factor}× | {p_value} |".format(
                    metric=evidence.get("metric"),
                    baseline=_fmt_seconds(evidence.get("baseline_p99")),
                    candidate=_fmt_seconds(evidence.get("candidate_p99")),
                    factor=_fmt(evidence.get("regression_factor")),
                    p_value=_fmt(evidence.get("p_value")),
                )
            )
        lines.append("")

    lines.extend(
        [
            "## Workload-class parity",
            "",
            "| Workload | Best engine | A p99 TTFT | B p99 TTFT | Δ TTFT | A p99 TPOT | B p99 TPOT | Δ TPOT | A cliff | B cliff | Δ cliff | Δ cost/task |",
            "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for row in report["workload_classes"]:
        a = row["run_a"]
        b = row["run_b"]
        delta = row["delta"]
        lines.append(
            "| {workload} | {best} | {a_ttft} | {b_ttft} | {d_ttft} | {a_tpot} | {b_tpot} | {d_tpot} | {a_cliff} | {b_cliff} | {d_cliff} | {d_cost} |".format(
                workload=row["workload_class"],
                best=row["best_engine"],
                a_ttft=_fmt_seconds(a.get("p99_ttft_seconds")),
                b_ttft=_fmt_seconds(b.get("p99_ttft_seconds")),
                d_ttft=_fmt_seconds(delta.get("p99_ttft_seconds")),
                a_tpot=_fmt_seconds(a.get("p99_tpot_seconds")),
                b_tpot=_fmt_seconds(b.get("p99_tpot_seconds")),
                d_tpot=_fmt_seconds(delta.get("p99_tpot_seconds")),
                a_cliff=_fmt(a.get("cliff_concurrency")),
                b_cliff=_fmt(b.get("cliff_concurrency")),
                d_cliff=_fmt(delta.get("cliff_concurrency")),
                d_cost=_fmt_money(delta.get("cost_per_task")),
            )
        )
    lines.extend(
        [
            "",
            "## Interpretation notes",
            "",
            "- Delta columns are `run_b - run_a`.",
            "- Lower TTFT/TPOT/cost is better; higher cliff concurrency is better.",
            "- Cliff concurrency is the first level where p99 TTFT is at least 2× the baseline level or failure rate reaches 10%.",
        ]
    )
    return "\n".join(lines) + "\n"


def _load_run(path: Path, *, explicit_label: str | None, fallback_label: str) -> _RunArtifacts:
    if not path.exists() or not path.is_dir():
        raise CompareError(f"run directory does not exist: {path}")
    summary = _load_json_required(path / "summary.json")
    config = _load_json_optional(path / "config.json")
    requests = _read_jsonl_optional(path / "requests.jsonl")
    metrics = _read_jsonl_optional(path / "metrics.jsonl")
    if summary.get("schema_version") != "inferguard-bench-summary/v1":
        raise CompareError(
            f"unsupported summary schema in {path / 'summary.json'}: {summary.get('schema_version')!r}"
        )
    label = explicit_label or _derive_label(summary, config, path, fallback_label)
    engine = _derive_engine(summary, config, label)
    return _RunArtifacts(
        path=path,
        label=label,
        summary=summary,
        config=config,
        requests=requests,
        metrics=metrics,
        engine=engine,
    )


def _trace_identity(
    run_a: _RunArtifacts, run_b: _RunArtifacts, *, min_overlap: float
) -> dict[str, Any]:
    keys_a = _identity_keys(run_a.requests) or _identity_keys(run_a.metrics)
    keys_b = _identity_keys(run_b.requests) or _identity_keys(run_b.metrics)
    overlap = keys_a & keys_b
    denominator = min(len(keys_a), len(keys_b))
    ratio = (len(overlap) / denominator) if denominator else 0.0
    return {
        "run_a_count": len(keys_a),
        "run_b_count": len(keys_b),
        "overlap_count": len(overlap),
        "overlap_ratio": ratio,
        "min_required_overlap_ratio": min_overlap,
        "status": "ok" if denominator and ratio > min_overlap else "low_overlap",
        "sample_overlap_keys": sorted(overlap)[:10],
    }


def _compare_workloads(
    run_a: _RunArtifacts,
    run_b: _RunArtifacts,
    options: CompareOptions,
) -> list[dict[str, Any]]:
    workloads = sorted(_workload_names(run_a) | _workload_names(run_b))
    rows = []
    for workload in workloads:
        stats_a = _workload_stats(run_a, workload, options)
        stats_b = _workload_stats(run_b, workload, options)
        delta = {
            "p99_ttft_seconds": _delta(
                stats_b.get("p99_ttft_seconds"), stats_a.get("p99_ttft_seconds")
            ),
            "p99_tpot_seconds": _delta(
                stats_b.get("p99_tpot_seconds"), stats_a.get("p99_tpot_seconds")
            ),
            "p99_latency_seconds": _delta(
                stats_b.get("p99_latency_seconds"), stats_a.get("p99_latency_seconds")
            ),
            "cost_per_task": _delta(stats_b.get("cost_per_task"), stats_a.get("cost_per_task")),
            "cliff_concurrency": _delta(
                stats_b.get("cliff_concurrency"), stats_a.get("cliff_concurrency")
            ),
        }
        rows.append(
            {
                "workload_class": workload,
                "best_engine": _best_engine(run_a, stats_a, run_b, stats_b),
                "run_a": stats_a,
                "run_b": stats_b,
                "delta": delta,
            }
        )
    return rows


def _blue_green_findings(
    run_a: _RunArtifacts,
    run_b: _RunArtifacts,
    workload_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    for row in workload_rows:
        workload = row["workload_class"]
        for metric_key, label in (("p99_ttft_seconds", "ttft"), ("p99_tpot_seconds", "tpot")):
            baseline = _num(row["run_a"].get(metric_key))
            candidate = _num(row["run_b"].get(metric_key))
            if baseline is None or candidate is None or baseline <= 0:
                continue
            factor = candidate / baseline
            p_value = _metric_p_value(run_a, run_b, workload, label)
            if (
                factor > BLUE_GREEN_P99_REGRESSION_FACTOR
                and p_value is not None
                and p_value < BLUE_GREEN_SIGNIFICANCE_P_VALUE
            ):
                findings.append(
                    {
                        "code": "blue_green_p99_regression",
                        "severity": "critical",
                        "message": (
                            f"Green stack p99 {label.upper()} is {factor:.2f}× blue for workload {workload} "
                            f"(p={p_value:.4g})."
                        ),
                        "evidence": {
                            "stack_a_id": run_a.label,
                            "stack_b_id": run_b.label,
                            "workload_class": workload,
                            "metric": label,
                            "baseline_p99": baseline,
                            "candidate_p99": candidate,
                            "regression_factor": factor,
                            "p_value": p_value,
                        },
                    }
                )
    return findings


def _metric_p_value(
    run_a: _RunArtifacts, run_b: _RunArtifacts, workload: str, metric: str
) -> float | None:
    a_values = _metric_values(run_a, workload, metric)
    b_values = _metric_values(run_b, workload, metric)
    if len(a_values) < 2 or len(b_values) < 2:
        return 0.0 if a_values and b_values and mean(b_values) > mean(a_values) else None
    mean_a = mean(a_values)
    mean_b = mean(b_values)
    var_a = _sample_variance(a_values)
    var_b = _sample_variance(b_values)
    se = math.sqrt(var_a / len(a_values) + var_b / len(b_values))
    if se <= 0:
        return 0.0 if mean_a != mean_b else 1.0
    z = abs(mean_b - mean_a) / se
    return math.erfc(z / math.sqrt(2.0))


def _metric_values(run: _RunArtifacts, workload: str, metric: str) -> list[float]:
    rows = [
        row
        for row in run.metrics
        if row.get("workload_class") == workload
        and bool(row.get("success"))
        and _phase(row) != "warmup"
    ]
    if metric == "ttft":
        return [
            value for value in (_num(row.get("ttft_seconds")) for row in rows) if value is not None
        ]
    return [value for value in (_tpot(row) for row in rows) if value is not None]


def _sample_variance(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0
    avg = mean(values)
    return sum((value - avg) ** 2 for value in values) / (len(values) - 1)


def _workload_stats(run: _RunArtifacts, workload: str, options: CompareOptions) -> dict[str, Any]:
    rows = [
        row
        for row in run.metrics
        if row.get("workload_class") == workload and _phase(row) != "warmup"
    ]
    if rows:
        successes = [row for row in rows if bool(row.get("success"))]
        tpot_values = [_tpot(row) for row in successes]
        stats = {
            "total": len(rows),
            "success": len(successes),
            "failed": len(rows) - len(successes),
            "failed_rate": ((len(rows) - len(successes)) / len(rows)) if rows else 0.0,
            "p99_ttft_seconds": _percentile(
                [_num(row.get("ttft_seconds")) for row in successes], 99
            ),
            "p99_tpot_seconds": _percentile(tpot_values, 99),
            "p99_latency_seconds": _percentile(
                [_num(row.get("latency_seconds")) for row in successes], 99
            ),
            "cliff_concurrency": _cliff_concurrency(rows),
            "cost_per_task": _cost_per_task(successes, options),
        }
        stats["cliff_delta_basis"] = "first_concurrency_with_p99_ttft_2x_or_failed_rate_10pct"
        return stats

    summary_workload = run.summary.get("workloads", {}).get(workload, {})
    total = int(_num(summary_workload.get("total")) or 0)
    success = int(_num(summary_workload.get("success")) or 0)
    failed = int(_num(summary_workload.get("failed")) or max(total - success, 0))
    ttft_block = summary_workload.get("ttft_seconds") or run.summary.get("ttft_seconds") or {}
    latency_block = (
        summary_workload.get("latency_seconds") or run.summary.get("latency_seconds") or {}
    )
    return {
        "total": total,
        "success": success,
        "failed": failed,
        "failed_rate": (failed / total) if total else 0.0,
        "p99_ttft_seconds": _num(ttft_block.get("p99")),
        "p99_tpot_seconds": None,
        "p99_latency_seconds": _num(latency_block.get("p99")),
        "cliff_concurrency": None,
        "cliff_delta_basis": "metrics_jsonl_missing_or_no_rows_for_workload",
        "cost_per_task": _summary_cost_per_task(run.summary, success, options),
    }


def _cliff_concurrency(rows: list[dict[str, Any]]) -> int | None:
    by_level: dict[int, list[dict[str, Any]]] = {}
    for row in rows:
        level = int(_num(row.get("concurrency")) or 0)
        if level > 0:
            by_level.setdefault(level, []).append(row)
    if not by_level:
        return None
    levels = sorted(by_level)
    baseline_success = [row for row in by_level[levels[0]] if bool(row.get("success"))]
    baseline = _percentile([_num(row.get("ttft_seconds")) for row in baseline_success], 99)
    for level in levels:
        level_rows = by_level[level]
        successes = [row for row in level_rows if bool(row.get("success"))]
        failed_rate = (len(level_rows) - len(successes)) / len(level_rows) if level_rows else 0.0
        p99_ttft = _percentile([_num(row.get("ttft_seconds")) for row in successes], 99)
        if failed_rate >= FAILURE_CLIFF_RATE:
            return level
        if (
            baseline is not None
            and p99_ttft is not None
            and p99_ttft >= baseline * TTFT_CLIFF_MULTIPLIER
        ):
            return level
    return None


def _best_engine(
    run_a: _RunArtifacts,
    stats_a: dict[str, Any],
    run_b: _RunArtifacts,
    stats_b: dict[str, Any],
) -> str:
    for key in ("cost_per_task", "p99_ttft_seconds", "p99_tpot_seconds", "p99_latency_seconds"):
        a = _num(stats_a.get(key))
        b = _num(stats_b.get(key))
        if a is None or b is None:
            continue
        if a < b:
            return run_a.label
        if b < a:
            return run_b.label
    a_cliff = _num(stats_a.get("cliff_concurrency"))
    b_cliff = _num(stats_b.get("cliff_concurrency"))
    if a_cliff is not None and b_cliff is not None:
        if a_cliff > b_cliff:
            return run_a.label
        if b_cliff > a_cliff:
            return run_b.label
    return "tie_or_insufficient_data"


def _cost_per_task(successes: list[dict[str, Any]], options: CompareOptions) -> float | None:
    if options.cost_per_gpu_hour is None or options.gpus is None or not successes:
        return None
    latencies = [_num(row.get("latency_seconds")) for row in successes]
    latencies = [value for value in latencies if value is not None]
    if not latencies:
        return None
    return mean(latencies) * options.cost_per_gpu_hour * options.gpus / 3600.0


def _summary_cost_per_task(
    summary: dict[str, Any], success: int, options: CompareOptions
) -> float | None:
    if options.cost_per_gpu_hour is None or options.gpus is None or success <= 0:
        return None
    runtime = _num(summary.get("runtime_seconds"))
    if runtime is None:
        return None
    return runtime * options.cost_per_gpu_hour * options.gpus / 3600.0 / success


def _run_identity(run: _RunArtifacts) -> dict[str, Any]:
    return {
        "path": str(run.path),
        "label": run.label,
        "engine": run.engine,
        "run_id": run.summary.get("run_id"),
        "command": run.summary.get("command"),
        "model": run.summary.get("model"),
        "endpoint": run.summary.get("endpoint"),
        "request_count": run.summary.get("request_counts", {}).get("total"),
        "success_count": run.summary.get("request_counts", {}).get("success"),
    }


def _workload_names(run: _RunArtifacts) -> set[str]:
    names = {str(row.get("workload_class")) for row in run.metrics if row.get("workload_class")}
    names.update(str(name) for name in run.summary.get("workloads", {}))
    return names


def _identity_keys(rows: list[dict[str, Any]]) -> set[str]:
    keys = set()
    for row in rows:
        trace_id = row.get("trace_id")
        turn_index = row.get("turn_index")
        if trace_id is None or turn_index is None:
            continue
        keys.add(f"{trace_id}{IDENTITY_KEY_SEPARATOR}{turn_index}")
    return keys


def _tpot(row: dict[str, Any]) -> float | None:
    direct = _num(row.get("tpot_seconds"))
    if direct is not None:
        return direct
    output_tokens = _num(row.get("output_tokens"))
    if output_tokens is None or output_tokens <= 0:
        return None
    latency = _num(row.get("latency_seconds"))
    ttft = _num(row.get("ttft_seconds")) or 0.0
    if latency is not None and latency > ttft:
        return (latency - ttft) / output_tokens
    tokens_per_second = _num(row.get("tokens_per_second"))
    if tokens_per_second is not None and tokens_per_second > 0:
        return 1.0 / tokens_per_second
    return None


def _phase(row: dict[str, Any]) -> str | None:
    metadata = row.get("metadata")
    if isinstance(metadata, dict):
        value = metadata.get("phase")
        return str(value) if value is not None else None
    return None


def _derive_label(
    summary: dict[str, Any], config: dict[str, Any], path: Path, fallback_label: str
) -> str:
    engine = _derive_engine(summary, config, "")
    if engine != "unknown":
        return engine
    return path.name or fallback_label


def _derive_engine(summary: dict[str, Any], config: dict[str, Any], label: str) -> str:
    topology = config.get("topology") if isinstance(config.get("topology"), dict) else {}
    for value in (
        summary.get("engine"),
        topology.get("framework"),
        config.get("metrics_engine"),
        config.get("command"),
        label,
    ):
        if not value:
            continue
        text = str(value).lower()
        if "sglang" in text:
            return "sglang"
        if "vllm" in text:
            return "vllm"
        if text in {"dynamo", "llm-d"}:
            return text
    return "unknown"


def _load_json_required(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise CompareError(f"required artifact missing: {path}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise CompareError(f"invalid JSON artifact {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise CompareError(f"JSON artifact must be an object: {path}")
    return data


def _load_json_optional(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return _load_json_required(path)


def _read_jsonl_optional(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows = []
    for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise CompareError(f"invalid JSONL row {path}:{line_no}: {exc}") from exc
        if isinstance(row, dict):
            rows.append(row)
    return rows


def _write_json(path: Path, data: dict[str, Any]) -> None:
    atomic_write_json(path, data)


def _validate_options(options: CompareOptions) -> None:
    if not 0 <= options.min_identity_overlap < 1:
        raise CompareError("min_identity_overlap must be >= 0 and < 1")
    if options.cost_per_gpu_hour is not None and options.cost_per_gpu_hour < 0:
        raise CompareError("cost_per_gpu_hour must be non-negative")
    if options.gpus is not None and options.gpus <= 0:
        raise CompareError("gpus must be positive")


def _percentile(values: list[float | None], pct: int) -> float | None:
    clean = [value for value in values if value is not None]
    if not clean:
        return None
    ordered = sorted(clean)
    idx = min(len(ordered) - 1, max(0, round((pct / 100) * (len(ordered) - 1))))
    return ordered[idx]


def _delta(new_value: Any, old_value: Any) -> float | None:
    new_num = _num(new_value)
    old_num = _num(old_value)
    if new_num is None or old_num is None:
        return None
    return new_num - old_num


def _num(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _fmt(value: Any) -> str:
    number = _num(value)
    if number is None:
        return "-"
    if number.is_integer():
        return str(int(number))
    return f"{number:.3f}"


def _fmt_seconds(value: Any) -> str:
    number = _num(value)
    if number is None:
        return "-"
    return f"{number:.3f}s"


def _fmt_money(value: Any) -> str:
    number = _num(value)
    if number is None:
        return "-"
    return f"${number:.6f}"


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()

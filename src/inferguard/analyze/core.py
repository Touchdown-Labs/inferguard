"""Boring, read-only v0 implementation of ``inferguard analyze``."""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from statistics import mean, median, pstdev
from typing import Any

from inferguard import __version__
from inferguard.analyze.operator_brief import emit_operator_brief
from inferguard.harness.dcgm_correlate import detect_partial_gpu_degradation
from inferguard.io import atomic_write_json
from inferguard.preflight import check_hma_offload_compat

SCHEMA_VERSION = "inferguard-analyze/v1.1"
SUPPORTED_FINDING_CODES = {
    "hma_offload_incompatible",
    "prefill_decode_imbalance",
    "kv_transfer_stall",
    "kv_transfer_errors_present",
    "endpoint_unreachable",
    "engine_unidentified",
    "kv_footprint_imbalance",
    "prefix_eviction_cross_customer",
    "cold_start_ramp_extended",
    "engine_crash_recovery_slow",
    "multi_tenant_noisy_neighbor",
    "gpu_partial_degradation",
    "oom_giant_prefill_blast_radius",
    "cost_idle_underutilization_high",
    "retry_storm_engine_overload",
    "canary_quality_regression",
    "blue_green_p99_regression",
    "tokenizer_mismatch_silent_drift",
    "prompt_template_tool_parser_regression",
}
SEVERITY_RANK = {"info": 0, "warning": 1, "critical": 2}


@dataclass(frozen=True)
class AnalyzeOptions:
    output_dir: Path
    output_format: str = "both"
    strict: bool = False
    timeline_glob: str = "**/inferguard_timeline.jsonl"
    cost_per_gpu_hour: float | None = None
    gpus: int | None = None
    cost_currency: str = "USD"
    operator_brief: bool = False


class AnalyzeError(RuntimeError):
    """Raised when a report cannot be produced."""


class _CellBuilder:
    def __init__(self, cell_id: str, source_format: str) -> None:
        self.cell_id = cell_id
        self.source_format = source_format
        self.artifacts: dict[str, Any] = {}
        self.metrics: dict[str, Any] = {}
        self.completion: dict[str, Any] = {}
        self.findings: list[dict[str, Any]] = []
        self.timeline: dict[str, Any] | None = None
        self.cost: dict[str, Any] | None = None
        self.identity: dict[str, Any] = {
            "hardware": None,
            "model": None,
            "framework": None,
            "precision": None,
            "scenario_type": None,
            "is_multinode": None,
            "recipe_name": None,
            "isl": None,
            "osl": None,
            "concurrency": None,
            "topology": {},
        }

    def as_dict(self) -> dict[str, Any]:
        cell = {
            "cell_id": self.cell_id,
            "source_format": self.source_format,
            **self.identity,
            "artifacts": self.artifacts,
            "completion": self.completion,
            "metrics": self.metrics,
            "findings": self.findings,
        }
        if self.timeline is not None:
            cell["timeline"] = self.timeline
        if self.cost is not None:
            cell["cost"] = self.cost
        return cell


def analyze_results(results_dir: Path, options: AnalyzeOptions) -> dict[str, Any]:
    root = results_dir.resolve()
    if not root.exists() or not root.is_dir():
        raise AnalyzeError(f"results_dir does not exist or is not a directory: {results_dir}")

    cells: dict[str, _CellBuilder] = {}
    manifest: list[dict[str, Any]] = []
    parse_findings: list[dict[str, Any]] = []

    for path in sorted(root.rglob("agg_*.json")):
        _parse_agg(path, root, cells, manifest, parse_findings)

    for path in sorted(root.rglob("detailed_results.csv")):
        _parse_agentx_detail(path, root, cells, manifest, parse_findings)

    for path in sorted(root.rglob("metrics_server_metrics.csv")):
        _parse_agentx_metrics(path, root, cells, manifest, parse_findings)

    for path in sorted(root.rglob("results*.json")):
        if path.name.startswith("agg_"):
            continue
        _parse_eval_json(path, root, cells, manifest, parse_findings)

    for path in sorted(root.rglob("summary.json")):
        _parse_inferguard_bench_summary(path, root, cells, manifest, parse_findings)

    for path in sorted(root.rglob("compare.json")):
        _parse_compare_json(path, root, cells, manifest, parse_findings)

    for path in sorted(root.rglob("preflight*.json")):
        _parse_preflight_json(path, root, cells, manifest, parse_findings)

    for path in sorted(root.rglob("sample*.jsonl")):
        _register_eval_sample(path, root, cells, manifest)

    for path in sorted(root.rglob("meta_env.json")):
        _parse_meta_env(path, root, cells, manifest, parse_findings)

    for path in sorted(root.glob(options.timeline_glob)):
        _parse_timeline(path, root, cells, manifest, parse_findings)

    if not cells:
        raise AnalyzeError(f"no supported benchmark artifacts found under {root}")

    all_findings: list[dict[str, Any]] = []
    for cell in cells.values():
        _finalize_cell(cell)
        _apply_throughput_per_gpu(cell, options)
        _apply_cost_model(cell, root, options)
        all_findings.extend(cell.findings)
    all_findings.extend(parse_findings)

    missing = [
        f"{f.get('cell_id')}: {f['message']}"
        for f in all_findings
        if f.get("code") == "missing_required_artifact"
    ]
    if options.strict and missing:
        raise AnalyzeError("strict mode failed: " + "; ".join(missing))

    cell_dicts = [cells[key].as_dict() for key in sorted(cells)]
    failed_cells = sum(1 for c in cell_dicts if c["completion"].get("status") == "failed")
    partial_cells = sum(1 for c in cell_dicts if c["completion"].get("status") == "partial")
    status = "complete"
    if failed_cells:
        status = "failed"
    elif partial_cells or missing:
        status = "partial"

    run_summary = {
        "status": status,
        "total_cells": len(cell_dicts),
        "successful_cells": len(cell_dicts) - failed_cells,
        "failed_cells": failed_cells,
        "missing_artifacts": missing,
    }
    cost_summary = _run_cost_summary(cell_dicts)
    if cost_summary is not None:
        run_summary["cost"] = cost_summary

    report = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "input_root": str(root),
        "analyzer": {
            "inferguard_version": __version__,
            "capabilities": {
                "diagnosis": "on",
                "actuation": "off",
                "replay": "off",
                "recall": "off",
            },
        },
        "run_summary": run_summary,
        "cells": cell_dicts,
        "cross_run": _cross_run(cell_dicts),
        "findings": all_findings,
        "artifact_manifest": manifest,
    }
    written = write_report(report, options.output_dir, options.output_format)
    for path in written:
        report["artifact_manifest"].append(
            {
                "path": str(path),
                "kind": "inferguard_report",
                "cell_id": None,
                "required": False,
                "present": True,
            }
        )
    if options.operator_brief:
        brief_paths = emit_operator_brief(report, options.output_dir)
        for path in brief_paths:
            report["artifact_manifest"].append(
                {
                    "path": str(path),
                    "kind": "inferguard_operator_brief",
                    "cell_id": None,
                    "required": False,
                    "present": True,
                }
            )
    if written or options.operator_brief:
        write_report(report, options.output_dir, options.output_format)
    return report


def write_report(report: dict[str, Any], output_dir: Path, output_format: str) -> list[Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    if output_format in {"json", "both"}:
        path = output_dir / "report.json"
        atomic_write_json(path, report)
        written.append(path)
    if output_format in {"md", "both"}:
        path = output_dir / "report.md"
        path.write_text(render_markdown(report), encoding="utf-8")
        written.append(path)
    return written


def exit_code_for_report(report: dict[str, Any], fail_on: str) -> int:
    if fail_on == "never":
        return 0
    threshold = SEVERITY_RANK[fail_on]
    max_rank = max(
        (SEVERITY_RANK.get(f.get("severity", "info"), 0) for f in report["findings"]), default=0
    )
    if max_rank >= SEVERITY_RANK["critical"] and threshold <= SEVERITY_RANK["critical"]:
        return 2
    if max_rank >= SEVERITY_RANK["warning"] and threshold <= SEVERITY_RANK["warning"]:
        return 1
    return 0


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# InferGuard Analyze Report",
        "",
        "## Executive summary",
        f"- Schema: `{report['schema_version']}`",
        f"- Status: **{report['run_summary']['status']}**",
        f"- Cells: {report['run_summary']['total_cells']}",
        f"- Findings: {len(report['findings'])}",
    ]
    campaign_cost = (report["run_summary"].get("cost") or {}).get("compute_cost")
    if campaign_cost is not None:
        currency = report["run_summary"]["cost"].get("currency") or "USD"
        lines.append(f"- Campaign cost: {currency} {campaign_cost:.4f}")
    lines.extend(
        [
            "",
            "## Benchmark matrix",
            "| Cell | Source | Hardware | Concurrency | Success rate | p99 TTFT | Output tput |",
            "|---|---|---|---:|---:|---:|---:|",
        ]
    )
    for cell in report["cells"]:
        metrics = cell["metrics"]
        completion = cell["completion"]
        lines.append(
            "| {cell} | {source} | {hw} | {conc} | {success} | {ttft} | {tput} |".format(
                cell=cell["cell_id"],
                source=cell["source_format"],
                hw=_md(cell.get("hardware")),
                conc=_md(cell.get("concurrency")),
                success=_md(completion.get("success_rate")),
                ttft=_md(metrics.get("p99_ttft")),
                tput=_md(metrics.get("output_tput_tps")),
            )
        )
    lines.extend(["", "## Artifact completeness"])
    missing = report["run_summary"].get("missing_artifacts") or []
    if missing:
        lines.extend(f"- {item}" for item in missing)
    else:
        lines.append("- No required artifacts missing for discovered cells.")
    lines.extend(["", "## Per-cell results"])
    for cell in report["cells"]:
        lines.extend(
            [
                f"### {cell['cell_id']}",
                f"- Source: `{cell['source_format']}`",
                f"- Status: {cell['completion'].get('status', 'unknown')}",
            ]
        )
        if cell.get("timeline"):
            lines.append(f"- Timeline samples: {cell['timeline'].get('sample_count', 0)}")
        if cell.get("cost") and cell["cost"].get("compute_cost") is not None:
            cost = cell["cost"]
            currency = cost.get("currency") or "USD"
            lines.extend(
                [
                    "#### Cost",
                    f"- Compute cost: {currency} {cost['compute_cost']:.4f}",
                    f"- GPU-hours: {_md(cost.get('gpu_hours'))}",
                    f"- Completed sessions: {_md(cost.get('completed_sessions'))}",
                    f"- Cost / completed session: {currency} {_md(cost.get('cost_per_completed_session'))}",
                    f"- Cost / completed request: {currency} {_md(cost.get('cost_per_completed_request'))}",
                ]
            )
        if cell["findings"]:
            lines.append("- Findings:")
            for finding in cell["findings"]:
                lines.append(
                    f"  - **{finding['severity']}** `{finding['code']}`: {finding['message']}"
                )
    lines.extend(["", "## Live InferGuard timeline"])
    timeline_cells = [c for c in report["cells"] if c.get("timeline")]
    if timeline_cells:
        for cell in timeline_cells:
            lines.append(f"- {cell['cell_id']}: {cell['timeline'].get('sample_count', 0)} samples")
    else:
        lines.append("- No timeline artifact discovered.")
    lines.extend(
        [
            "",
            "## Bottleneck analysis",
            "- v0 report only surfaces observed metrics and findings; it does not recommend actuation.",
        ]
    )
    lines.extend(
        [
            "",
            "## Evidence-based next measurements",
            "- Re-run missing or partial cells before publishing comparative claims.",
        ]
    )
    lines.extend(["", "## Co-publish artifact manifest"])
    for artifact in report["artifact_manifest"]:
        lines.append(f"- `{artifact['kind']}`: `{artifact['path']}`")
    return "\n".join(lines) + "\n"


def _parse_agg(
    path: Path,
    root: Path,
    cells: dict[str, _CellBuilder],
    manifest: list[dict[str, Any]],
    parse_findings: list[dict[str, Any]],
) -> None:
    data = _load_json(path, parse_findings, root)
    if data is None:
        return
    cell = _cell(
        cells,
        _cell_id(path, root, data),
        "inferencex-srt-slurm"
        if data.get("is_multinode") or data.get("disagg")
        else "inferencex-static",
    )
    cell.artifacts["agg_json"] = _rel(path, root)
    _manifest(manifest, path, root, "agg_json", cell.cell_id, True)
    mapping = {
        "hardware": "hw",
        "model": "model",
        "infmax_model_prefix": "infmax_model_prefix",
        "framework": "framework",
        "precision": "precision",
        "image": "image",
        "scenario_type": "scenario_type",
        "disagg": "disagg",
        "is_multinode": "is_multinode",
        "isl": "isl",
        "osl": "osl",
        "concurrency": "conc",
    }
    for out_key, in_key in mapping.items():
        if in_key in data:
            cell.identity[out_key] = data[in_key]
    if "recipe_name" in data:
        cell.identity["recipe_name"] = data["recipe_name"]
    topology_keys = [
        "tp",
        "ep",
        "dp_attention",
        "prefill_tp",
        "prefill_ep",
        "prefill_dp_attention",
        "prefill_num_workers",
        "decode_tp",
        "decode_ep",
        "decode_dp_attention",
        "decode_num_workers",
        "num_prefill_gpu",
        "num_decode_gpu",
    ]
    cell.identity["topology"].update({k: data[k] for k in topology_keys if k in data})
    metric_keys = [
        "tput_per_gpu",
        "output_tput_per_gpu",
        "input_tput_per_gpu",
        "total_tput_tps",
        "output_tput_tps",
        "input_tput_tps",
        "mean_ttft",
        "p50_ttft",
        "p90_ttft",
        "p95_ttft",
        "p99_ttft",
        "mean_tpot",
        "p50_tpot",
        "p90_tpot",
        "p95_tpot",
        "p99_tpot",
        "mean_itl",
        "p99_itl",
        "intvty",
    ]
    for key in metric_keys:
        if key in data:
            cell.metrics[key] = _number_or_raw(data[key])
    total = _first(data, "num_requests_total", "num_prompts", "request_count", "requests")
    successful = _first(
        data, "num_requests_successful", "successful_requests", "completed", "success"
    )
    _set_completion(cell, total, successful)


def _parse_agentx_detail(
    path: Path,
    root: Path,
    cells: dict[str, _CellBuilder],
    manifest: list[dict[str, Any]],
    parse_findings: list[dict[str, Any]],
) -> None:
    rows = _read_csv(path, parse_findings, root)
    if rows is None:
        return
    cell = _cell(cells, _path_cell_id(path, root), "agentx-trace-replay")
    cell.artifacts["detailed_results_csv"] = _rel(path, root)
    _manifest(manifest, path, root, "detailed_results_csv", cell.cell_id, True)
    successful_rows = [r for r in rows if _truthy(r.get("success"))]
    _set_completion(cell, len(rows), len(successful_rows))

    ttft = [_to_float(r.get("ttft")) for r in successful_rows]
    e2el = []
    for row in successful_rows:
        start = _to_float(row.get("request_start_time"))
        end = _to_float(row.get("request_complete_time"))
        e2el.append(
            end - start if start is not None and end is not None else _to_float(row.get("ttlt"))
        )
    itl = [_to_float(r.get("itl")) for r in successful_rows]
    input_tokens = [_to_float(r.get("input_tokens")) for r in successful_rows]
    output_actual = [_to_float(r.get("output_tokens_actual")) for r in successful_rows]
    output_expected = [_to_float(r.get("output_tokens_expected")) for r in successful_rows]

    _series(cell.metrics, "ttft", ttft)
    _series(cell.metrics, "e2el", e2el)
    _series(cell.metrics, "itl", itl)
    _series(cell.metrics, "tpot", itl)
    _apply_intvty_from_tpot(cell.metrics)
    _series(cell.metrics, "input_tokens", input_tokens)
    _series(cell.metrics, "output_tokens_actual", output_actual)

    if any(v is not None for v in input_tokens):
        cell.metrics["input_tokens"] = sum(v for v in input_tokens if v is not None)
    if any(v is not None for v in output_expected):
        cell.metrics["output_tokens_expected"] = sum(v for v in output_expected if v is not None)
    if any(v is not None for v in output_actual):
        cell.metrics["output_tokens_actual"] = sum(v for v in output_actual if v is not None)

    starts = [_to_float(r.get("request_start_time")) for r in successful_rows]
    ends = [_to_float(r.get("request_complete_time")) for r in successful_rows]
    duration = _duration(starts, ends)
    if duration and duration > 0:
        total_input = sum(v for v in input_tokens if v is not None)
        total_output = sum(v for v in output_actual if v is not None)
        cell.metrics["duration_seconds"] = duration
        cell.metrics["qps"] = len(successful_rows) / duration
        cell.metrics["input_tput_tps"] = total_input / duration
        cell.metrics["output_tput_tps"] = total_output / duration
        cell.metrics["total_tput_tps"] = (total_input + total_output) / duration
        cell.metrics.update(_compute_qps_stats(ends))
    hits = sum(_to_float(r.get("cache_hit_blocks")) or 0 for r in rows)
    misses = sum(_to_float(r.get("cache_miss_blocks")) or 0 for r in rows)
    if hits + misses > 0:
        cell.metrics["theoretical_cache_hit_rate"] = hits / (hits + misses)


def _parse_agentx_metrics(
    path: Path,
    root: Path,
    cells: dict[str, _CellBuilder],
    manifest: list[dict[str, Any]],
    parse_findings: list[dict[str, Any]],
) -> None:
    rows = _read_csv(path, parse_findings, root)
    if rows is None:
        return
    cell = _cell(cells, _path_cell_id(path, root), "agentx-trace-replay")
    cell.artifacts["metrics_server_metrics_csv"] = _rel(path, root)
    _manifest(manifest, path, root, "metrics_server_metrics_csv", cell.cell_id, False)
    sums: dict[str, float] = {}
    for row in rows:
        for key, value in row.items():
            numeric = _to_float(value)
            if numeric is not None:
                sums[key] = sums.get(key, 0.0) + numeric
    hits = sums.get("prefix_cache_hits")
    queries = sums.get("prefix_cache_queries")
    if hits is not None and queries:
        cell.metrics["server_gpu_cache_hit_rate"] = hits / queries
    cpu_hits = sums.get("cpu_prefix_cache_hits")
    cpu_queries = sums.get("cpu_prefix_cache_queries")
    if cpu_hits is not None and cpu_queries:
        cell.metrics["server_cpu_cache_hit_rate"] = cpu_hits / cpu_queries
    for key in (
        "kv_offload_bytes_gpu_to_cpu",
        "kv_offload_bytes_cpu_to_gpu",
        "kv_offload_time_gpu_to_cpu",
        "kv_offload_time_cpu_to_gpu",
        "cpu_kv_cache_usage_pct",
        "prompt_tokens_total",
        "generation_tokens_total",
        "request_success_total",
    ):
        if key in sums:
            cell.metrics[key] = sums[key]


def _parse_eval_json(
    path: Path,
    root: Path,
    cells: dict[str, _CellBuilder],
    manifest: list[dict[str, Any]],
    parse_findings: list[dict[str, Any]],
) -> None:
    data = _load_json(path, parse_findings, root)
    if data is None:
        return
    cell = _cell(cells, _path_cell_id(path, root), "eval")
    cell.artifacts.setdefault("results_json", []).append(_rel(path, root))
    _manifest(manifest, path, root, "results_json", cell.cell_id, False)
    for key, value in data.items():
        if isinstance(value, str | int | float | bool) or value is None:
            cell.metrics[f"eval_{key}"] = value


def _parse_inferguard_bench_summary(
    path: Path,
    root: Path,
    cells: dict[str, _CellBuilder],
    manifest: list[dict[str, Any]],
    parse_findings: list[dict[str, Any]],
) -> None:
    data = _load_json(path, parse_findings, root)
    if data is None or data.get("schema_version") != "inferguard-bench-summary/v1":
        return
    cell = _cell(cells, data.get("run_id") or _path_cell_id(path, root), "inferguard-bench-native")
    cell.artifacts["inferguard_bench_summary_json"] = _rel(path, root)
    _manifest(manifest, path, root, "inferguard_bench_summary_json", cell.cell_id, True)
    metrics_path = path.parent / "metrics.jsonl"
    metrics_timeline_path = path.parent / "metrics_timeline.jsonl"
    dcgm_correlated_path = path.parent / "dcgm-correlated-v1.jsonl"
    config_path = path.parent / "config.json"
    _register_native_bench_companion(
        metrics_path,
        root,
        cell,
        manifest,
        parse_findings,
        "inferguard_bench_metrics_jsonl",
        required=True,
    )
    _register_native_bench_companion(
        metrics_timeline_path,
        root,
        cell,
        manifest,
        parse_findings,
        "inferguard_bench_metrics_timeline_jsonl",
        required=False,
    )
    _register_native_bench_companion(
        dcgm_correlated_path,
        root,
        cell,
        manifest,
        parse_findings,
        "dcgm_correlated_jsonl",
        required=False,
    )
    _register_native_bench_companion(
        path.parent / "requests.jsonl",
        root,
        cell,
        manifest,
        parse_findings,
        "inferguard_bench_requests_jsonl",
        required=True,
    )
    _register_native_bench_companion(
        path.parent / "run.json",
        root,
        cell,
        manifest,
        parse_findings,
        "inferguard_bench_run_json",
        required=True,
    )
    _register_native_bench_companion(
        config_path,
        root,
        cell,
        manifest,
        parse_findings,
        "inferguard_bench_config_json",
        required=True,
    )

    config_data = _load_json(config_path, parse_findings, root) if config_path.exists() else None
    topology = config_data.get("topology") if isinstance(config_data, dict) else None
    if isinstance(topology, dict):
        cell.identity["topology"].update(topology)
        _apply_topology_identity(cell, topology)
    if isinstance(config_data, dict):
        _apply_hma_preflight(cell, config_data)

    cell.identity["model"] = data.get("model")
    conc = [
        item.get("concurrency") for item in data.get("concurrency", []) if isinstance(item, dict)
    ]
    cell.identity["concurrency"] = conc[0] if len(conc) == 1 and isinstance(conc[0], int) else None
    cell.identity["topology"]["concurrency_levels"] = [c for c in conc if isinstance(c, int)]
    counts = data.get("request_counts", {})
    _set_completion(cell, counts.get("total"), counts.get("success"))
    cell.metrics["kvcast_mode"] = data.get("kvcast_mode")
    cell.metrics["requests_per_level"] = data.get("requests_per_level")
    cell.metrics["redact_prompts"] = data.get("redact_prompts")
    for key in (
        "customer_breakdown",
        "cache_lineage",
        "cold_start",
        "chaos_recovery",
        "oom_giant_prefill",
        "idle_active_mix",
        "retry_storm",
        "canary_quality",
        "tool_call_schema_eval",
    ):
        if data.get(key) is not None:
            cell.metrics[key] = data.get(key)
    cell.metrics["duration_seconds"] = data.get("runtime_seconds") or data.get("duration_seconds")
    cell.metrics["qps"] = data.get("throughput_req_per_second")
    cell.metrics["output_tput_tps"] = data.get("output_tokens_per_second_wall")
    cell.metrics["mean_output_tokens_per_second"] = data.get("average_tokens_per_second")
    _legacy_percentile_block(cell.metrics, "ttft", data.get("ttft_seconds") or {})
    _legacy_percentile_block(cell.metrics, "e2el", data.get("latency_seconds") or {})
    _legacy_percentile_block(cell.metrics, "latency", data.get("latency_seconds") or {})
    tokens = data.get("tokens", {})
    if isinstance(tokens, dict):
        for key in (
            "input_total",
            "output_total",
            "estimated_input_tokens",
            "estimated_output_tokens",
        ):
            if key in tokens:
                cell.metrics[key] = tokens[key]

    metric_rows = _read_jsonl_dicts(metrics_path) if metrics_path.exists() else []
    successes = [r for r in metric_rows if _truthy(r.get("success"))]
    if successes:
        ttft = [_to_float(r.get("ttft_seconds")) for r in successes]
        e2el = [_to_float(r.get("latency_seconds")) for r in successes]
        input_tokens = [_to_float(r.get("input_tokens")) for r in successes]
        output_tokens = [_to_float(r.get("output_tokens")) for r in successes]
        tpot = [_native_tpot(r) for r in successes]
        _series(cell.metrics, "ttft", ttft)
        _series(cell.metrics, "e2el", e2el)
        _series(cell.metrics, "itl", tpot)
        _series(cell.metrics, "tpot", tpot)
        _apply_intvty_from_tpot(cell.metrics)
        _series(cell.metrics, "input_tokens", input_tokens)
        _series(cell.metrics, "output_tokens_actual", output_tokens)
        starts = [_to_float(r.get("start_time")) for r in successes]
        ends = [_to_float(r.get("end_time")) for r in successes]
        duration = _duration(starts, ends)
        if duration and duration > 0:
            total_input = sum(v for v in input_tokens if v is not None)
            total_output = sum(v for v in output_tokens if v is not None)
            cell.metrics["duration_seconds"] = duration
            cell.metrics["input_tput_tps"] = total_input / duration
            cell.metrics["output_tput_tps"] = total_output / duration
            cell.metrics["total_tput_tps"] = (total_input + total_output) / duration
            cell.metrics.update(_compute_qps_stats(ends))
    _apply_native_metrics_timeline_metrics(cell, metrics_timeline_path)
    _apply_platform_scenario_findings(
        cell, metric_rows, metrics_timeline_path, dcgm_correlated_path
    )


def _parse_compare_json(
    path: Path,
    root: Path,
    cells: dict[str, _CellBuilder],
    manifest: list[dict[str, Any]],
    parse_findings: list[dict[str, Any]],
) -> None:
    data = _load_json(path, parse_findings, root)
    if data is None or data.get("schema_version") != "inferguard-compare/v1":
        return
    cell = _cell(cells, _path_cell_id(path, root), "inferguard-compare")
    cell.artifacts["inferguard_compare_json"] = _rel(path, root)
    _manifest(manifest, path, root, "inferguard_compare_json", cell.cell_id, False)
    cell.identity["model"] = (data.get("run_b") or {}).get("model") or (
        data.get("run_a") or {}
    ).get("model")
    cell.metrics["blue_green"] = bool((data.get("options") or {}).get("blue_green"))
    cell.metrics["compare_workload_classes"] = data.get("workload_classes") or []
    _set_completion(cell, 1, 1)
    for finding in data.get("findings") or []:
        if isinstance(finding, dict) and finding.get("code") in SUPPORTED_FINDING_CODES:
            cell.findings.append(
                _finding(
                    str(finding.get("code")),
                    str(finding.get("severity") or "warning"),
                    str(finding.get("message") or finding.get("code")),
                    cell.cell_id,
                    finding.get("evidence") if isinstance(finding.get("evidence"), dict) else {},
                )
            )


def _parse_preflight_json(
    path: Path,
    root: Path,
    cells: dict[str, _CellBuilder],
    manifest: list[dict[str, Any]],
    parse_findings: list[dict[str, Any]],
) -> None:
    data = _load_json(path, parse_findings, root)
    if data is None or data.get("schema_version") != "inferguard-preflight/v1":
        return
    cell = _cell(cells, _path_cell_id(path, root), "inferguard-preflight")
    cell.artifacts["inferguard_preflight_json"] = _rel(path, root)
    _manifest(manifest, path, root, "inferguard_preflight_json", cell.cell_id, False)
    cell.identity["model"] = data.get("model")
    if isinstance(data.get("tokenizer_probe"), dict):
        cell.metrics["tokenizer_probe"] = data.get("tokenizer_probe")
    _set_completion(cell, 1, 0 if data.get("findings") else 1)
    for finding in data.get("findings") or []:
        if isinstance(finding, dict) and finding.get("code") in SUPPORTED_FINDING_CODES:
            cell.findings.append(
                _finding(
                    str(finding.get("code")),
                    str(finding.get("severity") or "warning"),
                    str(finding.get("message") or finding.get("code")),
                    cell.cell_id,
                    finding.get("evidence") if isinstance(finding.get("evidence"), dict) else {},
                )
            )


def _apply_platform_scenario_findings(
    cell: _CellBuilder,
    metric_rows: list[dict[str, Any]],
    metrics_timeline_path: Path,
    dcgm_correlated_path: Path,
) -> None:
    # Implements S-21/S-13/S-07/S-05/S-01/S-03/S-09/S-11 scenario findings (see docs/inferguard/24).
    imbalance = _kv_footprint_imbalance(metrics_timeline_path)
    if imbalance is not None:
        cell.findings.append(
            _finding(
                "kv_footprint_imbalance",
                "warning",
                f"Customer {imbalance['customer_id']} held >70% of KV across multiple snapshots.",
                cell.cell_id,
                imbalance,
            )
        )
    cross_events = _cross_customer_events(metric_rows)
    if cross_events:
        cell.findings.append(
            _finding(
                "prefix_eviction_cross_customer",
                "warning",
                "Prefix-cache lineage shows cross-customer eviction/reuse pressure.",
                cell.cell_id,
                {"events": cross_events[:5], "event_count": len(cross_events)},
            )
        )
    noisy = _noisy_neighbor(metric_rows)
    if noisy is not None:
        cell.findings.append(
            _finding(
                "multi_tenant_noisy_neighbor",
                "warning",
                "One customer's p99 TTFT degraded >2x relative to another active customer.",
                cell.cell_id,
                noisy,
            )
        )
    cold = (
        cell.metrics.get("cold_start") if isinstance(cell.metrics.get("cold_start"), dict) else None
    )
    if cold:
        first = _to_float(cold.get("first_60s_p99_ttft_seconds"))
        steady = _to_float(cold.get("steady_state_p99_ttft_seconds"))
        if first is not None and steady is not None and steady > 0 and first > steady * 3:
            cell.findings.append(
                _finding(
                    "cold_start_ramp_extended",
                    "warning",
                    "First-60s p99 TTFT exceeded 3x steady-state p99 TTFT.",
                    cell.cell_id,
                    {
                        "model_load_seconds": cold.get("model_load_seconds"),
                        "cudagraph_capture_seconds": _first_value(
                            cold.get("cudagraph_capture_seconds"),
                            cold.get("cuda_graph_capture_seconds"),
                        ),
                        "cuda_graph_capture_seconds": _first_value(
                            cold.get("cuda_graph_capture_seconds"),
                            cold.get("cudagraph_capture_seconds"),
                        ),
                        "first_60s_p99_ttft_seconds": first,
                        "steady_state_p99_ttft_seconds": steady,
                        "first_successful_request_seconds": cold.get(
                            "first_successful_request_seconds"
                        ),
                    },
                )
            )
    chaos = (
        cell.metrics.get("chaos_recovery")
        if isinstance(cell.metrics.get("chaos_recovery"), dict)
        else None
    )
    if chaos:
        recovery = _to_float(chaos.get("recovery_time_seconds"))
        threshold = _to_float(chaos.get("threshold_seconds")) or 30.0
        if recovery is not None and recovery > threshold:
            cell.findings.append(
                _finding(
                    "engine_crash_recovery_slow",
                    "warning",
                    "Engine crash recovery exceeded threshold.",
                    cell.cell_id,
                    dict(chaos),
                )
            )
    gpu_degradation = _gpu_partial_degradation(metrics_timeline_path, dcgm_correlated_path)
    if gpu_degradation is not None:
        cell.findings.append(
            _finding(
                "gpu_partial_degradation",
                "warning",
                "One GPU diverged materially from cluster DCGM health median.",
                cell.cell_id,
                gpu_degradation,
            )
        )
    oom = (
        cell.metrics.get("oom_giant_prefill")
        if isinstance(cell.metrics.get("oom_giant_prefill"), dict)
        else None
    )
    if oom:
        cell.findings.append(
            _finding(
                "oom_giant_prefill_blast_radius",
                "warning",
                f"Giant-prefill OOM blast radius characterized for {oom.get('engine') or 'unknown'} engine.",
                cell.cell_id,
                {
                    "killed_batch_count": oom.get("killed_batch_count"),
                    "killed_in_flight_count": oom.get("killed_in_flight_count"),
                    "engine_recovery_seconds": oom.get("engine_recovery_seconds"),
                    "engine": oom.get("engine"),
                    **dict(oom),
                },
            )
        )
    retry = (
        cell.metrics.get("retry_storm")
        if isinstance(cell.metrics.get("retry_storm"), dict)
        else None
    )
    if retry:
        cell.findings.append(
            _finding(
                "retry_storm_engine_overload",
                "warning",
                "Retry-storm burst characterized engine queue/preemption recovery behavior.",
                cell.cell_id,
                {
                    "burst_peak_qps": retry.get("burst_peak_qps"),
                    "queue_depth_max": retry.get("queue_depth_max"),
                    "recovery_seconds": retry.get("recovery_seconds"),
                    "preemption_count": retry.get("preemption_count"),
                    **dict(retry),
                },
            )
        )
    quality = (
        cell.metrics.get("canary_quality")
        if isinstance(cell.metrics.get("canary_quality"), dict)
        else None
    )
    if quality:
        delta = _to_float(quality.get("accuracy_delta"))
        p_value = _to_float(quality.get("p_value"))
        if delta is not None and p_value is not None and delta > 0.02 and p_value < 0.05:
            cell.findings.append(
                _finding(
                    "canary_quality_regression",
                    "critical",
                    "Canary eval accuracy regressed by more than 2% with statistical significance.",
                    cell.cell_id,
                    {
                        "baseline_accuracy": quality.get("baseline_accuracy"),
                        "canary_accuracy": quality.get("canary_accuracy"),
                        "accuracy_delta": delta,
                        "eval_sample_count": quality.get("eval_sample_count"),
                        "p_value": p_value,
                        **dict(quality),
                    },
                )
            )
    tool_schema = (
        cell.metrics.get("tool_call_schema_eval")
        if isinstance(cell.metrics.get("tool_call_schema_eval"), dict)
        else None
    )
    if tool_schema:
        delta = _to_float(tool_schema.get("compliance_delta"))
        if delta is not None and delta > 0.05:
            cell.findings.append(
                _finding(
                    "prompt_template_tool_parser_regression",
                    "critical",
                    "Tool-call output structure compliance dropped by more than 5%.",
                    cell.cell_id,
                    {
                        "baseline_compliance_rate": tool_schema.get("baseline_compliance_rate"),
                        "candidate_compliance_rate": tool_schema.get("candidate_compliance_rate"),
                        "schema_id": tool_schema.get("schema_id"),
                        "divergent_field_paths": tool_schema.get("divergent_field_paths") or [],
                        **dict(tool_schema),
                    },
                )
            )


def _kv_footprint_imbalance(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    counts: dict[str, int] = {}
    max_share: dict[str, float] = {}
    for record in _read_jsonl_dicts(path):
        snapshot = record.get("customer_kv_snapshot")
        if not isinstance(snapshot, dict):
            continue
        for customer, values in snapshot.items():
            if not isinstance(values, dict):
                continue
            share = _to_float(values.get("share"))
            if share is not None and share > 0.70:
                counts[str(customer)] = counts.get(str(customer), 0) + 1
                max_share[str(customer)] = max(max_share.get(str(customer), 0.0), share)
    for customer, count in counts.items():
        if count >= 2:
            return {
                "customer_id": customer,
                "snapshot_count": count,
                "max_share": max_share.get(customer),
            }
    return None


def _gpu_partial_degradation(
    metrics_timeline_path: Path, dcgm_correlated_path: Path
) -> dict[str, Any] | None:
    rows: list[dict[str, Any]] = []
    if dcgm_correlated_path.exists():
        rows.extend(_read_jsonl_dicts(dcgm_correlated_path))
    if metrics_timeline_path.exists():
        for record in _read_jsonl_dicts(metrics_timeline_path):
            if record.get("schema_version") == "dcgm-correlated/v1" or "dcgm_gpu_util" in record:
                rows.append(record)
            dcgm_record = record.get("dcgm_correlated")
            if isinstance(dcgm_record, dict):
                rows.append(dcgm_record)
    findings = detect_partial_gpu_degradation(rows) if rows else []
    if not findings:
        return None
    finding = findings[0]
    return {
        "gpu_index": finding.get("gpu_index"),
        "gpu_uuid": finding.get("gpu_uuid"),
        "divergence_metric": finding.get("divergence_metric"),
        "divergence_value": finding.get("divergence_value"),
        **finding,
    }


def _cross_customer_events(metric_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for row in metric_rows:
        metadata = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
        lineage = (
            metadata.get("cache_lineage") if isinstance(metadata.get("cache_lineage"), dict) else {}
        )
        eviction = (
            metadata.get("prefix_eviction_event")
            if isinstance(metadata.get("prefix_eviction_event"), dict)
            else {}
        )
        if lineage.get("cross_customer") or eviction:
            events.append(
                {"request_id": row.get("request_id"), "lineage": lineage, "eviction": eviction}
            )
    return events


def _noisy_neighbor(metric_rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    by_customer: dict[str, list[float]] = {}
    for row in metric_rows:
        metadata = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
        customer = row.get("customer_id") or metadata.get("customer_id")
        ttft = _to_float(row.get("ttft_seconds"))
        if customer and ttft is not None:
            by_customer.setdefault(str(customer), []).append(ttft)
    if len(by_customer) < 2:
        return None
    p99s = {customer: _percentile(values, 99) for customer, values in by_customer.items() if values}
    if len(p99s) < 2:
        return None
    victim, victim_p99 = max(p99s.items(), key=lambda item: item[1])
    neighbor, neighbor_p99 = min(p99s.items(), key=lambda item: item[1])
    if neighbor_p99 > 0 and victim_p99 > neighbor_p99 * 2:
        return {
            "victim_customer_id": victim,
            "aggressor_candidate_customer_id": neighbor,
            "victim_p99_ttft_seconds": victim_p99,
            "neighbor_p99_ttft_seconds": neighbor_p99,
            "customers": sorted(by_customer),
        }
    return None


def _apply_hma_preflight(cell: _CellBuilder, config_data: dict[str, Any]) -> None:
    topology = config_data.get("topology") if isinstance(config_data.get("topology"), dict) else {}
    status: dict[str, Any] = {
        "engine": _first_value(config_data.get("framework"), topology.get("framework"), "vllm"),
        "topology": topology,
        "kv_offloading_backend": _first_value(
            config_data.get("kv_offloading_backend"),
            topology.get("kv_offloading_backend"),
            "native" if str(topology.get("offloading") or "").lower() == "cpu" else None,
        ),
        "disable_hybrid_kv_cache_manager": _first_value(
            config_data.get("disable_hybrid_kv_cache_manager"),
            topology.get("disable_hybrid_kv_cache_manager"),
        ),
    }
    model_family = _first_value(
        config_data.get("model_family"), config_data.get("model"), topology.get("model_prefix")
    )
    for finding in check_hma_offload_compat(status, str(model_family or "")):
        cell.findings.append(
            _finding(
                finding.code,
                finding.severity,
                finding.message,
                cell.cell_id,
                finding.evidence,
            )
        )


def _apply_native_metrics_timeline_metrics(cell: _CellBuilder, path: Path) -> None:
    if not path.exists():
        return
    sums: dict[str, float] = {}
    for record in _read_jsonl_dicts(path):
        snapshot = (
            record.get("disagg_snapshot")
            if isinstance(record.get("disagg_snapshot"), dict)
            else record
        )
        if not isinstance(snapshot, dict):
            continue
        for key in (
            "prefix_cache_hits",
            "prefix_cache_queries",
            "cpu_prefix_cache_hits",
            "cpu_prefix_cache_queries",
            "kv_offload_bytes_gpu_to_cpu",
            "kv_offload_bytes_cpu_to_gpu",
            "kv_offload_time_gpu_to_cpu",
            "kv_offload_time_cpu_to_gpu",
            "cpu_kv_cache_usage_pct",
        ):
            value = _to_float(snapshot.get(key))
            if value is not None:
                sums[key] = sums.get(key, 0.0) + value
    hits = sums.get("prefix_cache_hits")
    queries = sums.get("prefix_cache_queries")
    if hits is not None and queries:
        cell.metrics["server_gpu_cache_hit_rate"] = hits / queries
    cpu_hits = sums.get("cpu_prefix_cache_hits")
    cpu_queries = sums.get("cpu_prefix_cache_queries")
    if cpu_hits is not None and cpu_queries:
        cell.metrics["server_cpu_cache_hit_rate"] = cpu_hits / cpu_queries
    for key in (
        "kv_offload_bytes_gpu_to_cpu",
        "kv_offload_bytes_cpu_to_gpu",
        "kv_offload_time_gpu_to_cpu",
        "kv_offload_time_cpu_to_gpu",
        "cpu_kv_cache_usage_pct",
    ):
        if key in sums:
            cell.metrics[key] = sums[key]


def _register_native_bench_companion(
    path: Path,
    root: Path,
    cell: _CellBuilder,
    manifest: list[dict[str, Any]],
    parse_findings: list[dict[str, Any]],
    kind: str,
    *,
    required: bool,
) -> None:
    if path.exists():
        cell.artifacts[kind] = _rel(path, root)
        _manifest(manifest, path, root, kind, cell.cell_id, required)
        return
    rel = _rel(path, root)
    manifest.append(
        {"path": rel, "kind": kind, "cell_id": cell.cell_id, "required": required, "present": False}
    )
    if required:
        parse_findings.append(
            _finding(
                "missing_required_artifact",
                "critical",
                f"Native InferGuard bench artifact missing: {rel}",
                cell.cell_id,
                {"path": rel},
            )
        )


def _register_eval_sample(
    path: Path, root: Path, cells: dict[str, _CellBuilder], manifest: list[dict[str, Any]]
) -> None:
    cell = _cell(cells, _path_cell_id(path, root), "eval")
    cell.artifacts.setdefault("sample_jsonl", []).append(_rel(path, root))
    _manifest(manifest, path, root, "sample_jsonl", cell.cell_id, False)


def _parse_meta_env(
    path: Path,
    root: Path,
    cells: dict[str, _CellBuilder],
    manifest: list[dict[str, Any]],
    parse_findings: list[dict[str, Any]],
) -> None:
    data = _load_json(path, parse_findings, root)
    if data is None:
        return
    cell = _cell(cells, _path_cell_id(path, root), "eval")
    cell.artifacts["meta_env_json"] = _rel(path, root)
    _manifest(manifest, path, root, "meta_env_json", cell.cell_id, False)
    for key in ("hardware", "model", "framework", "precision"):
        if key in data:
            cell.identity[key] = data[key]


def _parse_timeline(
    path: Path,
    root: Path,
    cells: dict[str, _CellBuilder],
    manifest: list[dict[str, Any]],
    parse_findings: list[dict[str, Any]],
) -> None:
    cell = _cell_for_path(cells, path, root) or _cell(cells, _path_cell_id(path, root), "unknown")
    cell.artifacts["inferguard_timeline_jsonl"] = _rel(path, root)
    _manifest(manifest, path, root, "inferguard_timeline_jsonl", cell.cell_id, False)
    sample_count = 0
    first_observed = None
    last_observed = None
    first_finding = None
    first_critical = None
    counts: dict[str, int] = {}
    for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError as exc:
            parse_findings.append(
                _parse_finding(path, root, f"invalid timeline JSONL line {line_no}: {exc}")
            )
            continue
        sample_count += 1
        observed = record.get("observed_at") or record.get("timestamp")
        first_observed = first_observed or observed
        last_observed = observed or last_observed
        status = (
            record.get("disagg_status")
            if record.get("schema_version") == "inferguard-timeline/v1"
            else record
        )
        for finding in status.get("findings", []) if isinstance(status, dict) else []:
            code = finding.get("code")
            if code in SUPPORTED_FINDING_CODES:
                counts[code] = counts.get(code, 0) + 1
                first_finding = first_finding or observed
                if finding.get("severity") == "critical":
                    first_critical = first_critical or observed
                copied = {
                    "code": code,
                    "severity": finding.get("severity", "info"),
                    "message": finding.get("message", code),
                    "cell_id": cell.cell_id,
                    "evidence": {**finding.get("evidence", {}), "path": _rel(path, root)},
                }
                cell.findings.append(copied)
    cell.timeline = {
        "sample_count": sample_count,
        "first_observed_at": first_observed,
        "last_observed_at": last_observed,
        "finding_counts_by_code": counts,
        "first_finding_at": first_finding,
        "first_critical_finding_at": first_critical,
    }


def _finalize_cell(cell: _CellBuilder) -> None:
    if (
        cell.source_format == "agentx-trace-replay"
        and "metrics_server_metrics_csv" not in cell.artifacts
    ):
        cell.findings.append(
            _finding(
                "metrics_unavailable",
                "warning",
                "AgentX server metrics CSV not found",
                cell.cell_id,
                {},
            )
        )
    total = cell.completion.get("num_requests_total")
    successful = cell.completion.get("num_requests_successful")
    if total is not None and successful == 0:
        cell.findings.append(
            _finding(
                "invalid_run_no_successful_requests",
                "critical",
                "Run completed with zero successful requests",
                cell.cell_id,
                {"num_requests_total": total},
            )
        )
    elif cell.completion.get("success_rate") is not None and cell.completion["success_rate"] < 0.95:
        cell.findings.append(
            _finding(
                "partial_run",
                "warning",
                "Success rate below 95%",
                cell.cell_id,
                {"success_rate": cell.completion["success_rate"]},
            )
        )
    if not cell.completion:
        cell.completion.update(
            {
                "status": "unknown",
                "num_requests_total": None,
                "num_requests_successful": None,
                "success_rate": None,
            }
        )


def _apply_cost_model(cell: _CellBuilder, root: Path, options: AnalyzeOptions) -> None:
    if options.cost_per_gpu_hour is None:
        return
    gpus = _derive_gpus(cell, options.gpus)
    duration_seconds = _cell_duration_seconds(cell)
    completed_requests = cell.completion.get("num_requests_successful")
    completed_sessions, completion_basis = _completed_sessions(cell, root)
    if completed_sessions is None:
        completed_sessions = completed_requests
        completion_basis = "request-based"
    gpu_hours = None
    compute_cost = None
    if duration_seconds is not None and gpus is not None:
        gpu_hours = duration_seconds * gpus / 3600
        compute_cost = gpu_hours * options.cost_per_gpu_hour
    input_tokens = _first_metric(
        cell.metrics,
        "estimated_input_tokens",
        "input_total",
        "input_tokens",
        "prompt_tokens_total",
    )
    output_tokens = _first_metric(
        cell.metrics,
        "estimated_output_tokens",
        "output_total",
        "output_tokens_expected",
        "generation_tokens_total",
    )
    cell.cost = {
        "schema_version": "inferguard-cost/v1",
        "currency": options.cost_currency,
        "duration_seconds": duration_seconds,
        "gpus": gpus,
        "gpu_hours": gpu_hours,
        "gpu_hour_cost": options.cost_per_gpu_hour,
        "compute_cost": compute_cost,
        "completed_sessions": completed_sessions,
        "completed_requests": completed_requests,
        "completion_basis": completion_basis,
        "cost_per_completed_session": _safe_div(compute_cost, completed_sessions),
        "cost_per_completed_request": _safe_div(compute_cost, completed_requests),
        "cost_per_million_input_tokens": _cost_per_million_tokens(compute_cost, input_tokens),
        "cost_per_million_output_tokens": _cost_per_million_tokens(compute_cost, output_tokens),
    }
    economics = _cost_utilization_economics(cell, root, options, compute_cost=compute_cost)
    if economics:
        cell.cost["cost_economics"] = economics
        for finding in _idle_underutilization_findings(cell, economics):
            cell.findings.append(finding)


def _apply_throughput_per_gpu(cell: _CellBuilder, options: AnalyzeOptions) -> None:
    gpus = _derive_gpus(cell, options.gpus)
    if gpus is None or gpus <= 0:
        return
    cell.metrics["num_gpus"] = gpus
    for out_key, in_key in (
        ("tput_per_gpu", "total_tput_tps"),
        ("output_tput_per_gpu", "output_tput_tps"),
        ("input_tput_per_gpu", "input_tput_tps"),
    ):
        value = _to_float(cell.metrics.get(in_key))
        if value is not None:
            cell.metrics[out_key] = value / gpus


UTILIZATION_BUCKETS = (
    ("0-25%", 0.0, 0.25),
    ("25-50%", 0.25, 0.50),
    ("50-75%", 0.50, 0.75),
    ("75-100%", 0.75, 1.01),
)
TARGET_UTILIZATION = 0.90


def _cost_utilization_economics(
    cell: _CellBuilder,
    root: Path,
    options: AnalyzeOptions,
    *,
    compute_cost: float | None,
) -> dict[str, Any] | None:
    if compute_cost is None:
        return None
    path = (
        root / cell.artifacts["inferguard_bench_metrics_jsonl"]
        if isinstance(cell.artifacts.get("inferguard_bench_metrics_jsonl"), str)
        else None
    )
    metric_rows = _read_jsonl_dicts(path) if path is not None and path.exists() else []
    successes = [row for row in metric_rows if _truthy(row.get("success"))]
    total_tokens = sum(_row_tokens(row) for row in successes)
    if not successes or total_tokens <= 0:
        return None
    observed_utilization = _observed_utilization(cell, successes)
    idle_fraction = _observed_idle_fraction(cell, observed_utilization)
    penalty = (
        (TARGET_UTILIZATION / observed_utilization)
        if observed_utilization and observed_utilization > 0
        else None
    )
    curve = _utilization_curve(successes, compute_cost)
    customer_rows = _customer_idle_penalties(
        successes, compute_cost, observed_utilization, idle_fraction, penalty, options.cost_currency
    )
    return {
        "schema_version": "inferguard-cost-economics/v1",
        "currency": options.cost_currency,
        "target_utilization": TARGET_UTILIZATION,
        "observed_utilization": observed_utilization,
        "idle_fraction": idle_fraction,
        "idle_amortization_penalty": penalty,
        "cost_per_token_by_utilization": curve,
        "customer_idle_amortization": customer_rows,
    }


def _utilization_curve(rows: list[dict[str, Any]], compute_cost: float) -> list[dict[str, Any]]:
    buckets: dict[str, dict[str, Any]] = {
        label: {
            "bucket": label,
            "min_utilization": low,
            "max_utilization": min(high, 1.0),
            "completed_sessions": 0,
            "tokens": 0,
        }
        for label, low, high in UTILIZATION_BUCKETS
    }
    total_tokens = sum(_row_tokens(row) for row in rows) or 1
    for row in rows:
        utilization = _row_utilization(row)
        label = _utilization_bucket_label(utilization)
        bucket = buckets[label]
        bucket["completed_sessions"] += 1
        bucket["tokens"] += _row_tokens(row)
    out = []
    for bucket in buckets.values():
        tokens = bucket["tokens"]
        token_share = tokens / total_tokens if total_tokens else 0.0
        bucket_cost = compute_cost * token_share
        out.append(
            {
                **bucket,
                "compute_cost": bucket_cost,
                "cost_per_token": _safe_div(bucket_cost, tokens),
            }
        )
    return out


def _customer_idle_penalties(
    rows: list[dict[str, Any]],
    compute_cost: float,
    observed_utilization: float | None,
    idle_fraction: float | None,
    penalty: float | None,
    currency: str,
) -> list[dict[str, Any]]:
    total_tokens = sum(_row_tokens(row) for row in rows) or 1
    grouped: dict[str, dict[str, Any]] = {}
    for row in rows:
        metadata = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
        customer = str(row.get("customer_id") or metadata.get("customer_id") or "unknown")
        item = grouped.setdefault(
            customer,
            {
                "customer_id": customer,
                "completed_sessions": 0,
                "tokens": 0,
                "currency": currency,
                "observed_utilization": observed_utilization,
                "idle_fraction": idle_fraction,
                "idle_amortization_penalty": penalty,
                "recommendation": _idle_recommendation(customer, penalty),
            },
        )
        item["completed_sessions"] += 1
        item["tokens"] += _row_tokens(row)
    out = []
    for item in grouped.values():
        customer_cost = compute_cost * (item["tokens"] / total_tokens)
        item["compute_cost"] = customer_cost
        item["cost_per_token"] = _safe_div(customer_cost, item["tokens"])
        out.append(item)
    return sorted(out, key=lambda row: str(row.get("customer_id")))


def _idle_underutilization_findings(
    cell: _CellBuilder, economics: dict[str, Any]
) -> list[dict[str, Any]]:
    utilization = _to_float(economics.get("observed_utilization"))
    idle_fraction = _to_float(economics.get("idle_fraction"))
    penalty = _to_float(economics.get("idle_amortization_penalty"))
    if utilization is None or idle_fraction is None or penalty is None:
        return []
    if utilization >= 0.50 or idle_fraction <= 0.60 or penalty <= 1.50:
        return []
    findings = []
    rows = (
        economics.get("customer_idle_amortization")
        if isinstance(economics.get("customer_idle_amortization"), list)
        else []
    )
    target_rows = rows or [
        {"customer_id": "unknown", "recommendation": _idle_recommendation("unknown", penalty)}
    ]
    for row in target_rows:
        customer = row.get("customer_id") or "unknown"
        findings.append(
            _finding(
                "cost_idle_underutilization_high",
                "warning",
                f"Customer {customer} is paying ~{penalty:.2f}x the target cost-per-token because of idle GPU time.",
                cell.cell_id,
                {
                    "customer_id": customer,
                    "observed_utilization": utilization,
                    "idle_fraction": idle_fraction,
                    "idle_amortization_penalty": penalty,
                    "cost_per_token": row.get("cost_per_token"),
                    "recommendation": row.get("recommendation"),
                },
            )
        )
    return findings


def _observed_utilization(cell: _CellBuilder, rows: list[dict[str, Any]]) -> float | None:
    idle_mix = (
        cell.metrics.get("idle_active_mix")
        if isinstance(cell.metrics.get("idle_active_mix"), dict)
        else {}
    )
    explicit = _to_float(idle_mix.get("observed_utilization"))
    if explicit is not None:
        return max(0.0, min(1.0, explicit))
    values = [_row_utilization(row) for row in rows]
    values = [value for value in values if value is not None]
    return mean(values) if values else None


def _observed_idle_fraction(cell: _CellBuilder, observed_utilization: float | None) -> float | None:
    idle_mix = (
        cell.metrics.get("idle_active_mix")
        if isinstance(cell.metrics.get("idle_active_mix"), dict)
        else {}
    )
    explicit = _to_float(idle_mix.get("idle_fraction"))
    if explicit is not None:
        return max(0.0, min(1.0, explicit))
    return (1.0 - observed_utilization) if observed_utilization is not None else None


def _row_utilization(row: dict[str, Any]) -> float | None:
    metadata = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
    idle_mix = (
        metadata.get("idle_active_mix") if isinstance(metadata.get("idle_active_mix"), dict) else {}
    )
    value = _first_value(
        row.get("gpu_utilization"),
        row.get("gpu_utilization_pct"),
        metadata.get("gpu_utilization"),
        metadata.get("gpu_utilization_pct"),
        idle_mix.get("estimated_gpu_utilization"),
    )
    utilization = _to_float(value)
    if utilization is None:
        return None
    if utilization > 1.0:
        utilization /= 100.0
    return max(0.0, min(1.0, utilization))


def _utilization_bucket_label(utilization: float | None) -> str:
    value = 0.0 if utilization is None else utilization
    for label, low, high in UTILIZATION_BUCKETS:
        if low <= value < high:
            return label
    return "75-100%"


def _row_tokens(row: dict[str, Any]) -> int:
    return max(
        0,
        int(_to_float(row.get("input_tokens")) or 0)
        + int(_to_float(row.get("output_tokens")) or 0),
    )


def _idle_recommendation(customer: str, penalty: float | None) -> str:
    if penalty is None or penalty <= 1.5:
        return "Monitor utilization before changing placement."
    return f"Consolidate Customer {customer} to fewer GPUs or co-tenant with a compatible workload."


def _run_cost_summary(cells: list[dict[str, Any]]) -> dict[str, Any] | None:
    costs = [c.get("cost") for c in cells if c.get("cost")]
    if not costs:
        return None
    compute_costs = [c.get("compute_cost") for c in costs if c.get("compute_cost") is not None]
    completed_sessions = sum(c.get("completed_sessions") or 0 for c in costs)
    completed_requests = sum(c.get("completed_requests") or 0 for c in costs)
    compute_cost = sum(compute_costs) if compute_costs else None
    currency = next((c.get("currency") for c in costs if c.get("currency")), "USD")
    return {
        "schema_version": "inferguard-cost/v1",
        "currency": currency,
        "compute_cost": compute_cost,
        "completed_sessions": completed_sessions,
        "completed_requests": completed_requests,
        "cost_per_completed_session": _safe_div(compute_cost, completed_sessions),
        "cost_per_completed_request": _safe_div(compute_cost, completed_requests),
    }


def _derive_gpus(cell: _CellBuilder, explicit_gpus: int | None) -> int | None:
    topology = cell.identity.get("topology") or {}
    if _truthy(topology.get("is_multinode")):
        prefill_workers = _to_float(topology.get("prefill_num_workers")) or 0
        prefill_tp = _to_float(topology.get("prefill_tp")) or 0
        decode_workers = _to_float(topology.get("decode_num_workers")) or 0
        decode_tp = _to_float(topology.get("decode_tp")) or 0
        total = prefill_workers * prefill_tp + decode_workers * decode_tp
        if total > 0:
            return int(total)
    if explicit_gpus is not None:
        return explicit_gpus
    for key in ("num_gpu", "num_gpus", "gpus"):
        value = _to_float(topology.get(key) or cell.identity.get(key) or cell.metrics.get(key))
        if value is not None and value > 0:
            return int(value)
    prefill = _to_float(topology.get("num_prefill_gpu"))
    decode = _to_float(topology.get("num_decode_gpu"))
    if prefill is not None or decode is not None:
        total = (prefill or 0) + (decode or 0)
        return int(total) if total > 0 else None
    if _truthy(topology.get("is_multinode")):
        prefill_workers = _to_float(topology.get("prefill_num_workers")) or 0
        prefill_tp = _to_float(topology.get("prefill_tp")) or 0
        decode_workers = _to_float(topology.get("decode_num_workers")) or 0
        decode_tp = _to_float(topology.get("decode_tp")) or 0
        total = prefill_workers * prefill_tp + decode_workers * decode_tp
        return int(total) if total > 0 else None
    return None


def _cell_duration_seconds(cell: _CellBuilder) -> float | None:
    for key in ("duration_seconds", "runtime_seconds"):
        value = _to_float(cell.metrics.get(key))
        if value is not None and value >= 0:
            return value
    return None


def _completed_sessions(cell: _CellBuilder, root: Path) -> tuple[int | None, str]:
    artifact = cell.artifacts.get("inferguard_bench_metrics_jsonl")
    if not isinstance(artifact, str):
        return None, "request-based"
    path = root / artifact
    if not path.exists():
        return None, "request-based"
    latest_by_session: dict[str, tuple[int, bool]] = {}
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return None, "request-based"
    for line in lines:
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        session_id = record.get("session_id")
        if not session_id:
            continue
        turn_index = _to_float(record.get("turn_index"))
        turn = int(turn_index) if turn_index is not None else 0
        success = _truthy(record.get("success"))
        current = latest_by_session.get(str(session_id))
        if current is None or turn >= current[0]:
            latest_by_session[str(session_id)] = (turn, success)
    if not latest_by_session:
        return None, "request-based"
    return sum(1 for _, success in latest_by_session.values() if success), "session-based"


def _first_metric(metrics: dict[str, Any], *keys: str) -> float | None:
    for key in keys:
        value = _to_float(metrics.get(key))
        if value is not None:
            return value
    return None


def _safe_div(numerator: float | None, denominator: Any) -> float | None:
    denom = _to_float(denominator)
    if numerator is None or denom is None or denom == 0:
        return None
    return numerator / denom


def _cost_per_million_tokens(compute_cost: float | None, tokens: float | None) -> float | None:
    if compute_cost is None or tokens is None or tokens == 0:
        return None
    return compute_cost / (tokens / 1_000_000)


def _cross_run(cells: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "cell_ids": [c["cell_id"] for c in cells],
        "max_output_tput_tps": max(
            (c["metrics"].get("output_tput_tps") or 0 for c in cells), default=0
        ),
    }


def _cell_for_path(cells: dict[str, _CellBuilder], path: Path, root: Path) -> _CellBuilder | None:
    parent = Path(_rel(path.parent, root))
    for cell in cells.values():
        for artifact in cell.artifacts.values():
            artifact_paths = artifact if isinstance(artifact, list) else [artifact]
            for artifact_path in artifact_paths:
                if isinstance(artifact_path, str) and Path(artifact_path).parent == parent:
                    return cell
    return None


def _cell(cells: dict[str, _CellBuilder], cell_id: str, source_format: str) -> _CellBuilder:
    if cell_id not in cells:
        cells[cell_id] = _CellBuilder(cell_id, source_format)
    elif cells[cell_id].source_format != source_format:
        cells[cell_id].source_format = "mixed"
    return cells[cell_id]


def _cell_id(path: Path, root: Path, data: dict[str, Any]) -> str:
    for key in ("cell_id", "recipe_name", "name"):
        if data.get(key):
            return str(data[key])
    return _path_cell_id(path, root)


def _path_cell_id(path: Path, root: Path) -> str:
    parent = path.parent
    if parent == root:
        return path.stem
    return parent.relative_to(root).as_posix()


def _rel(path: Path, root: Path) -> str:
    return path.resolve().relative_to(root).as_posix()


def _manifest(
    manifest: list[dict[str, Any]],
    path: Path,
    root: Path,
    kind: str,
    cell_id: str | None,
    required: bool,
) -> None:
    manifest.append(
        {
            "path": _rel(path, root),
            "kind": kind,
            "cell_id": cell_id,
            "required": required,
            "present": True,
        }
    )


def _load_json(
    path: Path, parse_findings: list[dict[str, Any]], root: Path
) -> dict[str, Any] | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        parse_findings.append(_parse_finding(path, root, f"could not parse JSON: {exc}"))
        return None
    return data if isinstance(data, dict) else {}


def _read_csv(
    path: Path, parse_findings: list[dict[str, Any]], root: Path
) -> list[dict[str, str]] | None:
    try:
        with path.open(newline="", encoding="utf-8") as handle:
            return list(csv.DictReader(handle))
    except OSError as exc:
        parse_findings.append(_parse_finding(path, root, f"could not parse CSV: {exc}"))
        return None


def _set_completion(cell: _CellBuilder, total: Any, successful: Any) -> None:
    total_num = _to_float(total)
    success_num = _to_float(successful)
    if total_num is None and success_num is None:
        return
    if total_num is None:
        total_num = success_num
    if success_num is None:
        success_num = total_num
    rate = None if not total_num else success_num / total_num
    status = "complete" if rate == 1 else "partial" if rate and rate > 0 else "failed"
    cell.completion.update(
        {
            "status": status,
            "num_requests_total": int(total_num) if total_num is not None else None,
            "num_requests_successful": int(success_num) if success_num is not None else None,
            "success_rate": rate,
        }
    )


def _series(metrics: dict[str, Any], name: str, values: list[float | None]) -> None:
    clean = [v for v in values if v is not None]
    if not clean:
        return
    metrics[f"mean_{name}"] = mean(clean)
    metrics[f"median_{name}"] = median(clean)
    metrics[f"p50_{name}"] = metrics[f"median_{name}"]
    metrics[f"p90_{name}"] = _percentile(clean, 90)
    metrics[f"p95_{name}"] = _percentile(clean, 95)
    metrics[f"p99_{name}"] = _percentile(clean, 99)
    metrics[f"p99.9_{name}"] = _percentile(clean, 99.9)
    metrics[f"std_{name}"] = pstdev(clean) if len(clean) > 1 else 0.0


def _legacy_percentile_block(metrics: dict[str, Any], name: str, block: dict[str, Any]) -> None:
    for stat, out_stat in (("p50", "median"), ("p50", "p50"), ("p95", "p95"), ("p99", "p99")):
        if stat in block:
            metrics[f"{out_stat}_{name}"] = block[stat]


def _percentile(values: list[float], pct: float) -> float:
    ordered = sorted(values)
    k = (len(ordered) - 1) * (pct / 100)
    f = int(k)
    c = f + 1
    if c >= len(ordered):
        return ordered[f]
    return ordered[f] + (k - f) * (ordered[c] - ordered[f])


def _safe_inverse(value: float | None) -> float | None:
    if value is None or value <= 0:
        return None
    return 1.0 / value


def _apply_intvty_from_tpot(metrics: dict[str, Any]) -> None:
    for stat in ("mean", "median", "p90", "p95", "p99", "p99.9"):
        value = _to_float(metrics.get(f"{stat}_tpot"))
        inverse = _safe_inverse(value)
        if inverse is not None:
            metrics[f"{stat}_intvty"] = inverse
    if "std_intvty" not in metrics:
        metrics["std_intvty"] = None


def _compute_qps_stats(complete_times: list[float | None]) -> dict[str, float]:
    times = sorted(v for v in complete_times if v is not None)
    if len(times) < 2:
        return {}
    start, end = times[0], times[-1]
    duration = end - start
    if duration <= 0:
        return {}
    qps_values = []
    t = start
    while t + 1.0 <= end:
        qps_values.append(sum(1 for ct in times if t <= ct < t + 1.0))
        t += 1.0
    if not qps_values:
        qps_values = [len(times) / duration]
    out: dict[str, Any] = {}
    _series(out, "qps", qps_values)
    return {k: v for k, v in out.items() if k != "p50_qps"}


def _read_jsonl_dicts(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return rows
    for line in lines:
        if not line.strip():
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(item, dict):
            rows.append(item)
    return rows


def _native_tpot(row: dict[str, Any]) -> float | None:
    explicit = _to_float(row.get("itl") or row.get("tpot"))
    if explicit is not None:
        return explicit
    output_tokens = _to_float(row.get("output_tokens"))
    latency = _to_float(row.get("latency_seconds"))
    if output_tokens is None or output_tokens <= 0 or latency is None:
        return None
    return latency / output_tokens


def _apply_topology_identity(cell: _CellBuilder, topology: dict[str, Any]) -> None:
    identity_map = {
        "hw": "hardware",
        "runner_type": "hardware",
        "model_prefix": "infmax_model_prefix",
        "framework": "framework",
        "precision": "precision",
        "image": "image",
        "is_multinode": "is_multinode",
    }
    for source, target in identity_map.items():
        if topology.get(source) not in (None, ""):
            cell.identity[target] = topology[source]


def _duration(starts: list[float | None], ends: list[float | None]) -> float | None:
    clean_starts = [v for v in starts if v is not None]
    clean_ends = [v for v in ends if v is not None]
    if not clean_starts or not clean_ends:
        return None
    return max(clean_ends) - min(clean_starts)


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "y", "success", "succeeded"}


def _to_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _number_or_raw(value: Any) -> Any:
    numeric = _to_float(value)
    return numeric if numeric is not None else value


def _first(data: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in data:
            return data[key]
    return None


def _first_value(*values: Any) -> Any:
    for value in values:
        if value not in (None, ""):
            return value
    return None


def _finding(
    code: str, severity: str, message: str, cell_id: str | None, evidence: dict[str, Any]
) -> dict[str, Any]:
    return {
        "code": code,
        "severity": severity,
        "message": message,
        "cell_id": cell_id,
        "evidence": evidence,
    }


def _parse_finding(path: Path, root: Path, message: str) -> dict[str, Any]:
    return _finding(
        "missing_required_artifact", "critical", message, None, {"path": _rel(path, root)}
    )


def _md(value: Any) -> str:
    if value is None:
        return "-"
    if isinstance(value, float):
        return f"{value:.4g}"
    return str(value)

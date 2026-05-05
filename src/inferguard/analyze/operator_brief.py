"""Operator brief emitter for ``inferguard analyze`` reports."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from inferguard.io import atomic_write_json

SCHEMA_VERSION = "inferguard-operator-brief/v1"
SUCCESS_THRESHOLD = 0.95
TTFT_CLIFF_MULTIPLIER = 2.0
OOM_GPU_CACHE_USAGE_THRESHOLD = 0.95


def emit_operator_brief(report: dict[str, Any], output_dir: Path) -> list[Path]:
    """Write machine-readable and Markdown operator brief artifacts."""
    output_dir.mkdir(parents=True, exist_ok=True)
    brief = build_operator_brief(report)
    json_path = output_dir / "operator_brief.json"
    md_path = output_dir / "operator_brief.md"
    atomic_write_json(json_path, brief)
    md_path.write_text(render_operator_brief_markdown(brief), encoding="utf-8")
    return [json_path, md_path]


def build_operator_brief(report: dict[str, Any]) -> dict[str, Any]:
    input_root = Path(str(report.get("input_root") or "."))
    cells = list(report.get("cells") or [])
    workload_groups = _group_by_workload(cells)
    best_stable = [
        _best_stable_config(workload, group) for workload, group in sorted(workload_groups.items())
    ]
    best_stable = [item for item in best_stable if item is not None]
    ttft_cliffs = [
        _ttft_cliff(workload, group) for workload, group in sorted(workload_groups.items())
    ]
    failure_cliffs = [
        _failure_cliff(workload, group) for workload, group in sorted(workload_groups.items())
    ]
    oom_cliffs = [_oom_cliff(cell, input_root) for cell in cells]
    recommended = _recommended_engine_config(best_stable)
    findings = _operator_findings(report)
    cost_summary = _cost_summary(report)
    cost_comparison = _cost_comparison(cells)
    cost_economics = _cost_economics(cells)
    kv_by_customer = _kv_by_customer(cells, input_root)
    customer_workload_cost = _customer_workload_cost(cells, input_root)
    hardware_health = _hardware_health(findings)
    tokenizer_drift = _tokenizer_drift(findings)
    retry_storm = _retry_storm(findings)
    cold_start = _cold_start_decomposition(findings, cells)
    crash_recovery = _crash_recovery(findings, cells)
    quality_regression = _quality_regression(findings, cells)
    blue_green = _blue_green_comparison(findings)
    output_structure = _output_structure_regression(findings, cells)
    lmcache_comparison = _lmcache_comparison(cells, input_root)
    measured_vs_inferred = _measured_vs_inferred_claims(cells, input_root, lmcache_comparison)
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "source_report": str(input_root / "inferguard_report" / "report.json"),
        "input_root": str(input_root),
        "summary": {
            "total_cells": len(cells),
            "workload_classes": sorted(workload_groups),
            "recommended_engine_config": recommended,
            "cost": cost_summary,
        },
        "cost_comparison": cost_comparison,
        "cost_economics": cost_economics,
        "kv_by_customer": kv_by_customer,
        "customer_workload_cost": customer_workload_cost,
        "hardware_health": hardware_health,
        "tokenizer_drift": tokenizer_drift,
        "retry_storm": retry_storm,
        "cold_start_decomposition": cold_start,
        "crash_recovery": crash_recovery,
        "quality_regression": quality_regression,
        "blue_green_comparison": blue_green,
        "output_structure": output_structure,
        "lmcache_comparison": lmcache_comparison,
        "measured_vs_inferred": measured_vs_inferred,
        "best_stable_config": best_stable,
        "cliff_detection": {
            "ttft_p99": ttft_cliffs,
            "failure": failure_cliffs,
            "oom": oom_cliffs,
        },
        "recommended_engine_config": recommended,
        "operator_findings": findings,
        "repro_commands": _repro_commands(cells, input_root),
        "raw_artifact_paths": _raw_artifact_paths(report, input_root),
    }


def render_operator_brief_markdown(brief: dict[str, Any]) -> str:
    lines = [
        "# InferGuard Operator Brief",
        "",
        f"- Schema: `{brief['schema_version']}`",
        f"- Input root: `{brief['input_root']}`",
        f"- Recommended engine config: {brief['recommended_engine_config']}",
        "",
        "## Best stable config",
    ]
    best = brief.get("best_stable_config") or []
    if best:
        for item in best:
            lines.append(
                "- {workload}: `{cell}` at conc={conc}, p99 TTFT={ttft}, success={success}, cost/session={cost}".format(
                    workload=item.get("workload_class"),
                    cell=item.get("cell_id"),
                    conc=_dash(item.get("concurrency")),
                    ttft=_fmt(item.get("p99_ttft_seconds")),
                    success=_fmt(item.get("success_rate")),
                    cost=_fmt(item.get("cost_per_task")),
                )
            )
    else:
        lines.append("- No stable config observed at success rate >=95% and p99 TTFT <2x baseline.")
    cost = (brief.get("summary") or {}).get("cost") or {}
    if cost:
        currency = cost.get("currency") or "USD"
        lines.extend(
            [
                "",
                "## Cost model",
                f"- GPU-hour price: {currency} {_fmt(cost.get('gpu_hour_cost'))}",
                f"- GPU count: {_dash(cost.get('gpus'))}",
                f"- Total compute cost: {currency} {_fmt(cost.get('compute_cost'))}",
                f"- Cost per completed session: {currency} {_fmt(cost.get('cost_per_completed_session'))}",
                f"- Cost per completed request: {currency} {_fmt(cost.get('cost_per_completed_request'))}",
            ]
        )
    comparison_rows = brief.get("cost_comparison") or []
    if comparison_rows:
        lines.extend(
            [
                "",
                "### Cache-mode cost comparison",
                "| Workload | Engine | Cache mode | GPU-hour price | GPUs | Completed sessions | Cost/session | Cell |",
                "|---|---|---|---:|---:|---:|---:|---|",
            ]
        )
        for row in comparison_rows:
            currency = row.get("currency") or "USD"
            lines.append(
                "| {workload} | {engine} | {cache} | {currency} {gpu_hour} | {gpus} | {sessions} | {currency} {cost} | `{cell}` |".format(
                    workload=_dash(row.get("workload_class")),
                    engine=_dash(row.get("engine")),
                    cache=_dash(row.get("cache_mode")),
                    currency=currency,
                    gpu_hour=_fmt(row.get("gpu_hour_cost")),
                    gpus=_dash(row.get("gpus")),
                    sessions=_dash(row.get("completed_sessions")),
                    cost=_fmt(row.get("cost_per_completed_session")),
                    cell=_dash(row.get("cell_id")),
                )
            )
    economics = brief.get("cost_economics") or {}
    if economics:
        lines.extend(["", "## Cost economics"])
        curve_rows = economics.get("cost_per_token_by_utilization") or []
        if curve_rows:
            lines.extend(
                [
                    "| Utilization bucket | Completed sessions | Tokens | Compute cost | Cost/token |",
                    "|---|---:|---:|---:|---:|",
                ]
            )
            for row in curve_rows:
                currency = row.get("currency") or economics.get("currency") or "USD"
                lines.append(
                    "| {bucket} | {sessions} | {tokens} | {currency} {cost} | {currency} {cpt} |".format(
                        bucket=_dash(row.get("bucket")),
                        sessions=_dash(row.get("completed_sessions")),
                        tokens=_dash(row.get("tokens")),
                        currency=currency,
                        cost=_fmt(row.get("compute_cost")),
                        cpt=_fmt(row.get("cost_per_token")),
                    )
                )
        customer_rows = economics.get("customer_idle_amortization") or []
        if customer_rows:
            lines.extend(
                [
                    "",
                    "### Idle amortization by customer",
                    "| Customer | Observed util | Idle fraction | Idle penalty | Cost/token | Recommendation |",
                    "|---|---:|---:|---:|---:|---|",
                ]
            )
            for row in customer_rows:
                currency = row.get("currency") or economics.get("currency") or "USD"
                lines.append(
                    "| {customer} | {util} | {idle} | {penalty}× | {currency} {cpt} | {rec} |".format(
                        customer=_dash(row.get("customer_id")),
                        util=_fmt(row.get("observed_utilization")),
                        idle=_fmt(row.get("idle_fraction")),
                        penalty=_fmt(row.get("idle_amortization_penalty")),
                        currency=currency,
                        cpt=_fmt(row.get("cost_per_token")),
                        rec=_dash(row.get("recommendation")),
                    )
                )
    kv_rows = brief.get("kv_by_customer") or []
    if kv_rows:
        lines.extend(
            [
                "",
                "### KV by customer",
                "| Customer | HBM bytes | RAM bytes | SSD bytes | Evictions | Eviction rate | Source cell |",
                "|---|---:|---:|---:|---:|---:|---|",
            ]
        )
        for row in kv_rows[:5]:
            lines.append(
                "| {customer} | {hbm} | {ram} | {ssd} | {evictions} | {rate} | `{cell}` |".format(
                    customer=_dash(row.get("customer_id")),
                    hbm=_dash(row.get("hbm_bytes")),
                    ram=_dash(row.get("ram_bytes")),
                    ssd=_dash(row.get("ssd_bytes")),
                    evictions=_dash(row.get("evictions")),
                    rate=_fmt(row.get("eviction_rate")),
                    cell=_dash(row.get("cell_id")),
                )
            )
    customer_cost = brief.get("customer_workload_cost") or []
    if customer_cost:
        lines.extend(
            [
                "",
                "### Cost by customer × workload",
                "| Customer | Workload | Completed sessions | Cost/session | Input tokens | Output tokens | Cell |",
                "|---|---|---:|---:|---:|---:|---|",
            ]
        )
        for row in customer_cost:
            currency = row.get("currency") or "USD"
            lines.append(
                "| {customer} | {workload} | {sessions} | {currency} {cost} | {input} | {output} | `{cell}` |".format(
                    customer=_dash(row.get("customer_id")),
                    workload=_dash(row.get("workload_class")),
                    sessions=_dash(row.get("completed_sessions")),
                    currency=currency,
                    cost=_fmt(row.get("cost_per_completed_session")),
                    input=_dash(row.get("input_tokens")),
                    output=_dash(row.get("output_tokens")),
                    cell=_dash(row.get("cell_id")),
                )
            )
    lmcache = brief.get("lmcache_comparison") or {}
    lines.extend(["", "## LMCache comparison"])
    rows = lmcache.get("rows") or []
    if rows:
        lines.extend(
            [
                "| Cell | Workload | Engine | Cache mode | Hit rate | Hits | Misses | Evictions | Tier HBM | Tier CPU | Tier disk | Tier remote | Offload bytes | p95 retrieve ms | Modes | Claim status |",
                "|---|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|---|",
            ]
        )
        for row in rows:
            modes = ", ".join(str(item) for item in row.get("detected_modes") or []) or "-"
            lines.append(
                "| `{cell}` | {workload} | {engine} | {cache} | {hit_rate} | {hits} | {misses} | {evictions} | {hbm} | {cpu} | {disk} | {remote} | {offload} | {p95} | {modes} | {claim} |".format(
                    cell=_dash(row.get("cell_id")),
                    workload=_dash(row.get("workload_class")),
                    engine=_dash(row.get("engine")),
                    cache=_dash(row.get("cache_mode")),
                    hit_rate=_fmt(row.get("lmcache_hit_rate")),
                    hits=_dash(row.get("lmcache_hit_count")),
                    misses=_dash(row.get("lmcache_miss_count")),
                    evictions=_dash(row.get("lmcache_eviction_count")),
                    hbm=_dash(row.get("lmcache_tier_hbm_bytes")),
                    cpu=_dash(row.get("lmcache_tier_cpu_bytes")),
                    disk=_dash(row.get("lmcache_tier_disk_bytes")),
                    remote=_dash(row.get("lmcache_tier_remote_bytes")),
                    offload=_dash(row.get("lmcache_offload_bytes_total")),
                    p95=_fmt(row.get("lmcache_retrieve_latency_ms_p95")),
                    modes=modes,
                    claim=_dash(row.get("claim_status")),
                )
            )
    else:
        lines.append(
            "- No live LMCache metric rows observed; any cache-pressure conclusions remain `inferred_without_engine_metrics`."
        )
    if lmcache.get("ab_comparisons"):
        lines.extend(
            [
                "",
                "### LMCache A/B cells",
                "| Workload | Engine | Baseline cell | LMCache cell | Baseline p99 TTFT | LMCache p99 TTFT | Δ p99 TTFT | Status |",
                "|---|---|---|---|---:|---:|---:|---|",
            ]
        )
        for row in lmcache.get("ab_comparisons") or []:
            lines.append(
                "| {workload} | {engine} | `{baseline}` | `{lmcache}` | {base_p99} | {lm_p99} | {delta} | {status} |".format(
                    workload=_dash(row.get("workload_class")),
                    engine=_dash(row.get("engine")),
                    baseline=_dash(row.get("baseline_cell_id")),
                    lmcache=_dash(row.get("lmcache_cell_id")),
                    base_p99=_fmt(row.get("baseline_p99_ttft_seconds")),
                    lm_p99=_fmt(row.get("lmcache_p99_ttft_seconds")),
                    delta=_fmt(row.get("delta_p99_ttft_seconds")),
                    status=_dash(row.get("claim_status")),
                )
            )
    measured_rows = brief.get("measured_vs_inferred") or []
    lines.extend(["", "## Measured vs inferred"])
    lines.extend(["| Claim | Status | Evidence |", "|---|---|---|"])
    for row in measured_rows:
        lines.append(
            "| {claim} | `{status}` | {evidence} |".format(
                claim=_dash(row.get("claim")),
                status=_dash(row.get("status")),
                evidence=_dash(row.get("evidence")),
            )
        )
    quality_rows = brief.get("quality_regression") or []
    structure_rows = brief.get("output_structure") or []
    lines.extend(["", "## Quality regression"])
    if quality_rows:
        lines.extend(
            [
                "| Cell | Baseline accuracy | Canary accuracy | Δ accuracy | Samples | p-value |",
                "|---|---:|---:|---:|---:|---:|",
            ]
        )
        for row in quality_rows:
            lines.append(
                "| `{cell}` | {baseline} | {canary} | {delta} | {samples} | {p_value} |".format(
                    cell=_dash(row.get("cell_id")),
                    baseline=_fmt(row.get("baseline_accuracy")),
                    canary=_fmt(row.get("canary_accuracy")),
                    delta=_fmt(row.get("accuracy_delta")),
                    samples=_dash(row.get("eval_sample_count")),
                    p_value=_fmt(row.get("p_value")),
                )
            )
    else:
        lines.append("- No canary quality regression finding observed.")
    if structure_rows:
        lines.extend(
            [
                "",
                "### Output structure / tool parser",
                "| Cell | Schema | Baseline compliance | Candidate compliance | Divergent paths |",
                "|---|---|---:|---:|---|",
            ]
        )
        for row in structure_rows:
            paths = ", ".join(str(item) for item in row.get("divergent_field_paths") or [])
            lines.append(
                "| `{cell}` | `{schema}` | {baseline} | {candidate} | {paths} |".format(
                    cell=_dash(row.get("cell_id")),
                    schema=_dash(row.get("schema_id")),
                    baseline=_fmt(row.get("baseline_compliance_rate")),
                    candidate=_fmt(row.get("candidate_compliance_rate")),
                    paths=paths or "-",
                )
            )
    blue_green = brief.get("blue_green_comparison") or []
    lines.extend(["", "## Blue/green comparison"])
    if blue_green:
        lines.extend(
            [
                "| Workload | Metric | Blue stack | Green stack | Blue p99 | Green p99 | Regression | p-value |",
                "|---|---|---|---|---:|---:|---:|---:|",
            ]
        )
        for row in blue_green:
            lines.append(
                "| {workload} | {metric} | `{blue}` | `{green}` | {baseline} | {candidate} | {factor}× | {p_value} |".format(
                    workload=_dash(row.get("workload_class")),
                    metric=_dash(row.get("metric")),
                    blue=_dash(row.get("stack_a_id")),
                    green=_dash(row.get("stack_b_id")),
                    baseline=_fmt(row.get("baseline_p99")),
                    candidate=_fmt(row.get("candidate_p99")),
                    factor=_fmt(row.get("regression_factor")),
                    p_value=_fmt(row.get("p_value")),
                )
            )
    else:
        lines.append("- No blue/green p99 regression finding observed.")
    lines.extend(["", "## Cliff detection", "### TTFT p99 cliff"])
    for item in brief.get("cliff_detection", {}).get("ttft_p99", []):
        if item.get("status") == "observed":
            lines.append(
                f"- {item['workload_class']}: first cliff at conc={item['concurrency']} "
                f"({_fmt(item.get('p99_ttft_seconds'))}s vs baseline {_fmt(item.get('baseline_p99_ttft_seconds'))}s)."
            )
        else:
            lines.append(f"- {item['workload_class']}: {item.get('message')}")
    lines.append("### Failure cliff")
    for item in brief.get("cliff_detection", {}).get("failure", []):
        if item.get("status") == "observed":
            lines.append(
                f"- {item['workload_class']}: first success-rate drop below 95% at conc={item['concurrency']}."
            )
        else:
            lines.append(f"- {item['workload_class']}: {item.get('message')}")
    lines.append("### OOM cliff")
    for item in brief.get("cliff_detection", {}).get("oom", []):
        if item.get("status") == "observed":
            lines.append(
                f"- {item['cell_id']}: {item.get('trigger')} at sample {item.get('sequence')} (`{item.get('path')}`)."
            )
        else:
            lines.append(f"- {item['cell_id']}: {item.get('message')}")
    hardware = brief.get("hardware_health") or []
    lines.extend(["", "## Hardware health"])
    if hardware:
        lines.extend(
            [
                "| GPU index | GPU UUID | Divergence metric | Value | Severity | Cell |",
                "|---:|---|---|---:|---|---|",
            ]
        )
        for row in hardware:
            lines.append(
                "| {index} | `{uuid}` | {metric} | {value} | {severity} | `{cell}` |".format(
                    index=_dash(row.get("gpu_index")),
                    uuid=_dash(row.get("gpu_uuid")),
                    metric=_dash(row.get("divergence_metric")),
                    value=_fmt(row.get("divergence_value")),
                    severity=_dash(row.get("severity")),
                    cell=_dash(row.get("cell_id")),
                )
            )
    else:
        lines.append("- No partial GPU degradation finding observed.")
    tokenizer_rows = brief.get("tokenizer_drift") or []
    if tokenizer_rows:
        lines.extend(
            [
                "",
                "### Tokenizer/config drift",
                "| Client tokenizer | Server tokenizer | Divergence | Sample length | Severity | Cell |",
                "|---|---|---:|---:|---|---|",
            ]
        )
        for row in tokenizer_rows:
            lines.append(
                "| `{client}` | `{server}` | {divergence} | {length} | {severity} | `{cell}` |".format(
                    client=_dash(row.get("client_tokenizer")),
                    server=_dash(row.get("server_tokenizer")),
                    divergence=_fmt(row.get("divergence_pct")),
                    length=_dash(row.get("sample_text_length")),
                    severity=_dash(row.get("severity")),
                    cell=_dash(row.get("cell_id")),
                )
            )
    retry_rows = brief.get("retry_storm") or []
    lines.extend(["", "## Retry storm"])
    if retry_rows:
        for row in retry_rows:
            lines.append(
                "- Engine survives {multiplier}× burst for {window}s before queue depth max={queue}; recovery={recovery}s; preemptions={preemptions}.".format(
                    multiplier=_fmt(row.get("burst_multiplier")),
                    window=_fmt(row.get("burst_window_seconds")),
                    queue=_dash(row.get("queue_depth_max")),
                    recovery=_fmt(row.get("recovery_seconds")),
                    preemptions=_dash(row.get("preemption_count")),
                )
            )
    else:
        lines.append("- No retry-storm run observed.")
    cold_rows = brief.get("cold_start_decomposition") or []
    lines.extend(["", "## Cold-start decomposition"])
    if cold_rows:
        lines.extend(
            [
                "| Cell | Model load | CUDA graph capture | First-60s p99 TTFT | Steady p99 TTFT |",
                "|---|---:|---:|---:|---:|",
            ]
        )
        for row in cold_rows:
            lines.append(
                "| `{cell}` | {model_load} | {cudagraph} | {first} | {steady} |".format(
                    cell=_dash(row.get("cell_id")),
                    model_load=_fmt(row.get("model_load_seconds")),
                    cudagraph=_fmt(row.get("cudagraph_capture_seconds")),
                    first=_fmt(row.get("first_60s_p99_ttft_seconds")),
                    steady=_fmt(row.get("steady_state_p99_ttft_seconds")),
                )
            )
    else:
        lines.append("- No cold-start decomposition observed.")
    crash_rows = brief.get("crash_recovery") or []
    lines.extend(["", "## Crash recovery"])
    if crash_rows:
        lines.extend(
            [
                "| Cell | Recovery seconds | In-flight losses | Error signature | Retry successes |",
                "|---|---:|---:|---|---:|",
            ]
        )
        for row in crash_rows:
            lines.append(
                "| `{cell}` | {recovery} | {losses} | `{signature}` | {retries} |".format(
                    cell=_dash(row.get("cell_id")),
                    recovery=_fmt(row.get("recovery_time_seconds")),
                    losses=_dash(row.get("in_flight_request_loss_count")),
                    signature=_dash(row.get("customer_error_signature")),
                    retries=_dash(row.get("successful_retry_count_post_recovery")),
                )
            )
    else:
        lines.append("- No crash-recovery run observed.")
    lines.extend(["", "## Operator findings"])
    findings = brief.get("operator_findings") or []
    if findings:
        for finding in findings:
            lines.append(
                "- **{severity}** `{code}`: {message}".format(
                    severity=finding.get("severity", "info"),
                    code=finding.get("code", "unknown"),
                    message=finding.get("message", ""),
                )
            )
    else:
        lines.append("- No operator findings emitted.")
    lines.extend(["", "## Repro commands"])
    commands = brief.get("repro_commands") or []
    if commands:
        for command in commands:
            lines.append(f"- `{command}`")
    else:
        lines.append("- No exact native bench command could be reconstructed from artifacts.")
    lines.extend(["", "## Raw artifact paths"])
    for path in brief.get("raw_artifact_paths") or []:
        lines.append(f"- `{path}`")
    return "\n".join(lines) + "\n"


_LMCACHE_KEYS = (
    "lmcache_enabled",
    "lmcache_hit_count",
    "lmcache_miss_count",
    "lmcache_hit_rate",
    "lmcache_eviction_count",
    "lmcache_save_count",
    "lmcache_retrieve_count",
    "lmcache_tier_hbm_bytes",
    "lmcache_tier_cpu_bytes",
    "lmcache_tier_disk_bytes",
    "lmcache_tier_local_disk_bytes",
    "lmcache_tier_remote_bytes",
    "lmcache_offload_bytes_total",
    "lmcache_retrieve_latency_ms_p50",
    "lmcache_retrieve_latency_ms_p95",
    "lmcache_retrieve_latency_ms_p99",
    "lmcache_nixl_transfer_bytes",
    "lmcache_nixl_transfer_latency_ms",
    "lmcache_cacheblend_enabled",
    "lmcache_cachegen_enabled",
    "lmcache_mp_mode_enabled",
    "lmcache_connector_type",
    "lmcache_cache_salt_enabled",
    "raw_metrics_extra",
)


def _lmcache_comparison(cells: list[dict[str, Any]], root: Path) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for cell in cells:
        lmcache_metrics = _lmcache_metrics_for_cell(cell, root)
        cache_mode = _cache_mode(cell)
        topology = cell.get("topology") or {}
        is_lmcache_cell = (
            bool(lmcache_metrics)
            or "lmcache" in cache_mode.lower()
            or bool(topology.get("lmcache_enabled"))
        )
        if not is_lmcache_cell:
            continue
        row = {
            "cell_id": cell.get("cell_id"),
            "workload_class": _cell_workload(cell),
            "engine": _first(cell.get("framework"), topology.get("framework"), "unknown"),
            "cache_mode": cache_mode,
            "p99_ttft_seconds": _num((cell.get("metrics") or {}).get("p99_ttft")),
            "success_rate": _num((cell.get("completion") or {}).get("success_rate")),
            "slurm_job_id": topology.get("slurm_job_id") or topology.get("SLURM_JOB_ID"),
            "slurm_nodelist": topology.get("slurm_nodelist") or topology.get("SLURM_NODELIST"),
            "nccl_rdma_smoke": topology.get("nccl_rdma_smoke") or topology.get("rdma_smoke"),
            "cost_per_completed_session": (cell.get("cost") or {}).get(
                "cost_per_completed_session"
            ),
            "cost_per_token": _cell_cost_per_token(cell),
            "detected_modes": _lmcache_detected_modes(lmcache_metrics),
            "claim_status": "measured"
            if _has_live_lmcache_metrics(lmcache_metrics)
            else "inferred",
            "claim_caveat": None
            if _has_live_lmcache_metrics(lmcache_metrics)
            else "inferred_without_engine_metrics",
            **lmcache_metrics,
        }
        if row.get("lmcache_tier_disk_bytes") is None:
            row["lmcache_tier_disk_bytes"] = row.get("lmcache_tier_local_disk_bytes")
        rows.append(row)
    return {
        "schema_version": "inferguard-lmcache-comparison/v1",
        "rows": sorted(rows, key=lambda row: str(row.get("cell_id") or "")),
        "ab_comparisons": _lmcache_ab_comparisons(cells, rows),
    }


def _lmcache_metrics_for_cell(cell: dict[str, Any], root: Path) -> dict[str, Any]:
    metrics = cell.get("metrics") if isinstance(cell.get("metrics"), dict) else {}
    out = _extract_lmcache_dict(metrics)
    nested = metrics.get("lmcache") if isinstance(metrics.get("lmcache"), dict) else {}
    out.update(
        {key: value for key, value in _extract_lmcache_dict(nested).items() if value is not None}
    )
    path = _artifact_path(cell, root, "inferguard_bench_metrics_timeline_jsonl")
    if path is not None:
        for record in _read_jsonl(path):
            snapshot = (
                record.get("disagg_snapshot")
                if isinstance(record.get("disagg_snapshot"), dict)
                else record
            )
            if isinstance(snapshot, dict):
                out.update(
                    {
                        key: value
                        for key, value in _extract_lmcache_dict(snapshot).items()
                        if value is not None
                    }
                )
    return out


def _extract_lmcache_dict(data: dict[str, Any]) -> dict[str, Any]:
    return {key: data.get(key) for key in _LMCACHE_KEYS if key in data}


def _has_live_lmcache_metrics(metrics: dict[str, Any]) -> bool:
    for key, value in metrics.items():
        if key == "raw_metrics_extra":
            continue
        if value is not None:
            return True
    return False


def _lmcache_detected_modes(metrics: dict[str, Any]) -> list[str]:
    modes: list[str] = []
    for key, label in (
        ("lmcache_cacheblend_enabled", "CacheBlend"),
        ("lmcache_cachegen_enabled", "CacheGen"),
        ("lmcache_mp_mode_enabled", "MP mode"),
        ("lmcache_cache_salt_enabled", "cache_salt"),
    ):
        if metrics.get(key) is True:
            modes.append(label)
    connector = metrics.get("lmcache_connector_type")
    if connector:
        modes.append(f"connector={connector}")
    return modes


def _lmcache_ab_comparisons(
    cells: list[dict[str, Any]], lmcache_rows: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    baseline_cells: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for cell in cells:
        cache_mode = _cache_mode(cell).lower()
        if "lmcache" in cache_mode:
            continue
        key = (
            str(_cell_workload(cell)),
            str(
                _first(
                    cell.get("framework"), (cell.get("topology") or {}).get("framework"), "unknown"
                )
            ),
        )
        baseline_cells.setdefault(key, []).append(cell)
    comparisons: list[dict[str, Any]] = []
    for row in lmcache_rows:
        key = (str(row.get("workload_class")), str(row.get("engine")))
        candidates = baseline_cells.get(key) or []
        if not candidates:
            continue
        baseline = min(
            candidates,
            key=lambda cell: (
                _num((cell.get("metrics") or {}).get("p99_ttft")) is None,
                _num((cell.get("metrics") or {}).get("p99_ttft")) or 0,
            ),
        )
        baseline_p99 = _num((baseline.get("metrics") or {}).get("p99_ttft"))
        lmcache_p99 = _num(row.get("p99_ttft_seconds"))
        comparisons.append(
            {
                "workload_class": row.get("workload_class"),
                "engine": row.get("engine"),
                "baseline_cell_id": baseline.get("cell_id"),
                "lmcache_cell_id": row.get("cell_id"),
                "baseline_p99_ttft_seconds": baseline_p99,
                "lmcache_p99_ttft_seconds": lmcache_p99,
                "delta_p99_ttft_seconds": (lmcache_p99 - baseline_p99)
                if baseline_p99 is not None and lmcache_p99 is not None
                else None,
                "claim_status": "measured"
                if row.get("claim_status") == "measured"
                and baseline_p99 is not None
                and lmcache_p99 is not None
                else "inferred",
                "claim_caveat": None
                if row.get("claim_status") == "measured"
                and baseline_p99 is not None
                and lmcache_p99 is not None
                else "inferred_without_engine_metrics",
            }
        )
    return comparisons


def _measured_vs_inferred_claims(
    cells: list[dict[str, Any]], root: Path, lmcache: dict[str, Any]
) -> list[dict[str, Any]]:
    rows = lmcache.get("rows") or []
    ab = lmcache.get("ab_comparisons") or []
    has_live = any(row.get("claim_status") == "measured" for row in rows)
    eviction_measured = any(_num(row.get("lmcache_eviction_count")) is not None for row in rows)
    tier_measured = any(
        any(
            row.get(key) is not None
            for key in (
                "lmcache_tier_hbm_bytes",
                "lmcache_tier_cpu_bytes",
                "lmcache_tier_disk_bytes",
                "lmcache_tier_remote_bytes",
            )
        )
        for row in rows
    )
    salt_measured = any(row.get("lmcache_cache_salt_enabled") is True for row in rows)
    mode_measured = any(row.get("detected_modes") for row in rows)
    artifact_paths = _raw_artifact_paths({"artifact_manifest": []}, root)
    artifact_evidence = (
        "report artifacts and raw paths present"
        if artifact_paths
        else "artifact completeness not assessed"
    )
    return [
        {
            "claim": "LMCache improved TTFT",
            "status": "measured" if ab and has_live else ("inferred" if ab else "not_proven"),
            "claim_caveat": None if has_live or not ab else "inferred_without_engine_metrics",
            "evidence": "A/B p99 TTFT cells plus live LMCache metrics"
            if ab and has_live
            else "requires matching baseline/LMCache cells and live LMCache metrics",
        },
        {
            "claim": "eviction occurred",
            "status": "measured" if eviction_measured else "inferred",
            "claim_caveat": None if eviction_measured else "inferred_without_engine_metrics",
            "evidence": "lmcache_eviction_count present"
            if eviction_measured
            else "no lmcache_eviction_count metric present",
        },
        {
            "claim": "tier residency observed",
            "status": "measured" if tier_measured else "inferred",
            "claim_caveat": None if tier_measured else "inferred_without_engine_metrics",
            "evidence": "LMCache tier byte metrics present"
            if tier_measured
            else "no LMCache tier byte metrics present",
        },
        {
            "claim": "cross-tenant isolation",
            "status": "measured" if salt_measured else "not_proven",
            "evidence": "cache_salt metric exposed"
            if salt_measured
            else "requires cache_salt engine evidence; workload shape alone is not proof",
        },
        {
            "claim": "CacheBlend/CacheGen/MP mode detected",
            "status": "measured" if mode_measured else "not_proven",
            "evidence": "mode/connector metrics exposed"
            if mode_measured
            else "no mode metrics exposed",
        },
        {
            "claim": "artifact completeness",
            "status": "measured" if cells else "not_proven",
            "evidence": artifact_evidence,
        },
    ]


def _cell_workload(cell: dict[str, Any]) -> Any:
    metrics = cell.get("metrics") or {}
    return _first(
        metrics.get("workload_class"),
        cell.get("scenario_type"),
        metrics.get("kvcast_mode"),
        cell.get("source_format"),
        "unknown",
    )


def _cell_cost_per_token(cell: dict[str, Any]) -> float | None:
    cost = cell.get("cost") or {}
    compute = _num(cost.get("compute_cost"))
    metrics = cell.get("metrics") or {}
    tokens = (_num(metrics.get("input_tokens")) or 0.0) + (
        _num(metrics.get("output_tokens_actual")) or 0.0
    )
    if compute is None or tokens <= 0:
        return None
    return compute / tokens


def _operator_findings(report: dict[str, Any]) -> list[dict[str, Any]]:
    supported = {
        "hma_offload_incompatible",
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
    return [
        {
            "code": finding.get("code"),
            "severity": finding.get("severity", "info"),
            "message": finding.get("message", ""),
            "cell_id": finding.get("cell_id"),
            "evidence": finding.get("evidence") or {},
        }
        for finding in report.get("findings", [])
        if finding.get("code") in supported
    ]


def _hardware_health(findings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for finding in findings:
        if finding.get("code") != "gpu_partial_degradation":
            continue
        evidence = finding.get("evidence") if isinstance(finding.get("evidence"), dict) else {}
        rows.append(
            {
                "cell_id": finding.get("cell_id"),
                "severity": finding.get("severity", "warning"),
                "gpu_index": evidence.get("gpu_index"),
                "gpu_uuid": evidence.get("gpu_uuid"),
                "divergence_metric": evidence.get("divergence_metric"),
                "divergence_value": evidence.get("divergence_value"),
                "evidence": evidence,
            }
        )
    return rows


def _tokenizer_drift(findings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for finding in findings:
        if finding.get("code") != "tokenizer_mismatch_silent_drift":
            continue
        evidence = finding.get("evidence") if isinstance(finding.get("evidence"), dict) else {}
        rows.append(
            {
                "cell_id": finding.get("cell_id"),
                "severity": finding.get("severity", "critical"),
                "client_tokenizer": evidence.get("client_tokenizer"),
                "server_tokenizer": evidence.get("server_tokenizer"),
                "divergence_pct": evidence.get("divergence_pct"),
                "sample_text_length": evidence.get("sample_text_length"),
                "evidence": evidence,
            }
        )
    return rows


def _quality_regression(
    findings: list[dict[str, Any]], cells: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for finding in findings:
        if finding.get("code") != "canary_quality_regression":
            continue
        evidence = finding.get("evidence") if isinstance(finding.get("evidence"), dict) else {}
        cell_id = str(finding.get("cell_id"))
        rows.append(
            {
                "cell_id": finding.get("cell_id"),
                "severity": finding.get("severity", "critical"),
                **_quality_fields(evidence),
            }
        )
        seen.add(cell_id)
    for cell in cells:
        cell_id = str(cell.get("cell_id"))
        if cell_id in seen:
            continue
        quality = (cell.get("metrics") or {}).get("canary_quality") or {}
        if isinstance(quality, dict) and quality:
            rows.append(
                {"cell_id": cell.get("cell_id"), "severity": None, **_quality_fields(quality)}
            )
    return rows


def _quality_fields(data: dict[str, Any]) -> dict[str, Any]:
    return {
        "baseline_accuracy": data.get("baseline_accuracy"),
        "canary_accuracy": data.get("canary_accuracy"),
        "accuracy_delta": data.get("accuracy_delta"),
        "eval_sample_count": data.get("eval_sample_count"),
        "p_value": data.get("p_value"),
    }


def _blue_green_comparison(findings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for finding in findings:
        if finding.get("code") != "blue_green_p99_regression":
            continue
        evidence = finding.get("evidence") if isinstance(finding.get("evidence"), dict) else {}
        rows.append(
            {
                "cell_id": finding.get("cell_id"),
                "severity": finding.get("severity", "critical"),
                "stack_a_id": evidence.get("stack_a_id"),
                "stack_b_id": evidence.get("stack_b_id"),
                "workload_class": evidence.get("workload_class"),
                "metric": evidence.get("metric"),
                "baseline_p99": evidence.get("baseline_p99"),
                "candidate_p99": evidence.get("candidate_p99"),
                "regression_factor": evidence.get("regression_factor"),
                "p_value": evidence.get("p_value"),
            }
        )
    return rows


def _output_structure_regression(
    findings: list[dict[str, Any]], cells: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for finding in findings:
        if finding.get("code") != "prompt_template_tool_parser_regression":
            continue
        evidence = finding.get("evidence") if isinstance(finding.get("evidence"), dict) else {}
        cell_id = str(finding.get("cell_id"))
        rows.append(
            {
                "cell_id": finding.get("cell_id"),
                "severity": finding.get("severity", "critical"),
                **_structure_fields(evidence),
            }
        )
        seen.add(cell_id)
    for cell in cells:
        cell_id = str(cell.get("cell_id"))
        if cell_id in seen:
            continue
        structure = (cell.get("metrics") or {}).get("tool_call_schema_eval") or {}
        if isinstance(structure, dict) and structure:
            rows.append(
                {"cell_id": cell.get("cell_id"), "severity": None, **_structure_fields(structure)}
            )
    return rows


def _structure_fields(data: dict[str, Any]) -> dict[str, Any]:
    return {
        "baseline_compliance_rate": data.get("baseline_compliance_rate"),
        "candidate_compliance_rate": data.get("candidate_compliance_rate"),
        "schema_id": data.get("schema_id"),
        "divergent_field_paths": data.get("divergent_field_paths") or [],
    }


def _retry_storm(findings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for finding in findings:
        if finding.get("code") != "retry_storm_engine_overload":
            continue
        evidence = finding.get("evidence") if isinstance(finding.get("evidence"), dict) else {}
        rows.append(
            {
                "cell_id": finding.get("cell_id"),
                "severity": finding.get("severity", "warning"),
                "burst_peak_qps": evidence.get("burst_peak_qps"),
                "burst_multiplier": evidence.get("burst_multiplier"),
                "burst_window_seconds": evidence.get("burst_window_seconds"),
                "queue_depth_max": evidence.get("queue_depth_max"),
                "recovery_seconds": evidence.get("recovery_seconds"),
                "preemption_count": evidence.get("preemption_count"),
                "burst_success_rate": evidence.get("burst_success_rate"),
            }
        )
    return rows


def _cold_start_decomposition(
    findings: list[dict[str, Any]], cells: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for finding in findings:
        if finding.get("code") != "cold_start_ramp_extended":
            continue
        evidence = finding.get("evidence") if isinstance(finding.get("evidence"), dict) else {}
        cell_id = str(finding.get("cell_id"))
        rows.append({"cell_id": finding.get("cell_id"), **_cold_fields(evidence)})
        seen.add(cell_id)
    for cell in cells:
        cell_id = str(cell.get("cell_id"))
        if cell_id in seen:
            continue
        cold = (cell.get("metrics") or {}).get("cold_start") or {}
        if isinstance(cold, dict) and cold:
            rows.append({"cell_id": cell.get("cell_id"), **_cold_fields(cold)})
    return rows


def _cold_fields(data: dict[str, Any]) -> dict[str, Any]:
    return {
        "model_load_seconds": data.get("model_load_seconds"),
        "cudagraph_capture_seconds": _first(
            data.get("cudagraph_capture_seconds"),
            data.get("cuda_graph_capture_seconds"),
        ),
        "first_60s_p99_ttft_seconds": data.get("first_60s_p99_ttft_seconds"),
        "steady_state_p99_ttft_seconds": data.get("steady_state_p99_ttft_seconds"),
        "first_successful_request_seconds": data.get("first_successful_request_seconds"),
    }


def _crash_recovery(
    findings: list[dict[str, Any]], cells: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for finding in findings:
        if finding.get("code") != "engine_crash_recovery_slow":
            continue
        evidence = finding.get("evidence") if isinstance(finding.get("evidence"), dict) else {}
        cell_id = str(finding.get("cell_id"))
        rows.append({"cell_id": finding.get("cell_id"), **_crash_fields(evidence)})
        seen.add(cell_id)
    for cell in cells:
        cell_id = str(cell.get("cell_id"))
        if cell_id in seen:
            continue
        chaos = (cell.get("metrics") or {}).get("chaos_recovery") or {}
        if isinstance(chaos, dict) and chaos:
            rows.append({"cell_id": cell.get("cell_id"), **_crash_fields(chaos)})
    return rows


def _crash_fields(data: dict[str, Any]) -> dict[str, Any]:
    return {
        "recovery_time_seconds": data.get("recovery_time_seconds"),
        "time_from_crash_to_first_ready_seconds": data.get(
            "time_from_crash_to_first_ready_seconds"
        ),
        "in_flight_request_loss_count": data.get("in_flight_request_loss_count"),
        "customer_error_signature": data.get("customer_error_signature"),
        "successful_retry_count_post_recovery": data.get("successful_retry_count_post_recovery"),
    }


def _group_by_workload(cells: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    groups: dict[str, list[dict[str, Any]]] = {}
    for cell in cells:
        metrics = cell.get("metrics") or {}
        workload = _first(
            metrics.get("workload_class"),
            cell.get("scenario_type"),
            metrics.get("kvcast_mode"),
            cell.get("source_format"),
            "unknown",
        )
        groups.setdefault(str(workload), []).append(cell)
    return groups


def _cost_summary(report: dict[str, Any]) -> dict[str, Any]:
    run_cost = ((report.get("run_summary") or {}).get("cost") or {}).copy()
    cells = list(report.get("cells") or [])
    cell_costs = [cell.get("cost") or {} for cell in cells if cell.get("cost")]
    if cell_costs:
        gpu_hour_costs = {
            cost.get("gpu_hour_cost")
            for cost in cell_costs
            if cost.get("gpu_hour_cost") is not None
        }
        gpu_counts = {cost.get("gpus") for cost in cell_costs if cost.get("gpus") is not None}
        if len(gpu_hour_costs) == 1:
            run_cost["gpu_hour_cost"] = next(iter(gpu_hour_costs))
        if len(gpu_counts) == 1:
            run_cost["gpus"] = next(iter(gpu_counts))
    return run_cost


def _cost_comparison(cells: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for cell in cells:
        cost = cell.get("cost") or {}
        if not cost:
            continue
        topology = cell.get("topology") or {}
        metrics = cell.get("metrics") or {}
        workload = _first(
            metrics.get("workload_class"),
            cell.get("scenario_type"),
            metrics.get("kvcast_mode"),
            cell.get("source_format"),
            "unknown",
        )
        rows.append(
            {
                "workload_class": workload,
                "engine": _first(cell.get("framework"), topology.get("framework"), "unknown"),
                "cache_mode": _cache_mode(cell),
                "cell_id": cell.get("cell_id"),
                "currency": cost.get("currency") or "USD",
                "gpu_hour_cost": cost.get("gpu_hour_cost"),
                "gpus": cost.get("gpus"),
                "completed_sessions": cost.get("completed_sessions"),
                "completed_requests": cost.get("completed_requests"),
                "compute_cost": cost.get("compute_cost"),
                "cost_per_completed_session": cost.get("cost_per_completed_session"),
                "cost_per_completed_request": cost.get("cost_per_completed_request"),
                "completion_basis": cost.get("completion_basis"),
            }
        )
    return sorted(
        rows,
        key=lambda row: (
            str(row.get("workload_class") or ""),
            str(row.get("engine") or ""),
            str(row.get("cache_mode") or ""),
            str(row.get("cell_id") or ""),
        ),
    )


def _cost_economics(cells: list[dict[str, Any]]) -> dict[str, Any]:
    curve: dict[str, dict[str, Any]] = {}
    customer_rows: list[dict[str, Any]] = []
    currency = "USD"
    observed_utilizations = []
    idle_penalties = []
    for cell in cells:
        economics = (cell.get("cost") or {}).get("cost_economics") or {}
        if not isinstance(economics, dict):
            continue
        currency = economics.get("currency") or currency
        observed = _num(economics.get("observed_utilization"))
        penalty = _num(economics.get("idle_amortization_penalty"))
        if observed is not None:
            observed_utilizations.append(observed)
        if penalty is not None:
            idle_penalties.append(penalty)
        for row in economics.get("cost_per_token_by_utilization") or []:
            if not isinstance(row, dict):
                continue
            bucket = str(row.get("bucket") or "unknown")
            item = curve.setdefault(
                bucket,
                {
                    "bucket": bucket,
                    "completed_sessions": 0.0,
                    "tokens": 0.0,
                    "compute_cost": 0.0,
                    "currency": currency,
                },
            )
            item["completed_sessions"] += _num(row.get("completed_sessions")) or 0.0
            item["tokens"] += _num(row.get("tokens")) or 0.0
            item["compute_cost"] += _num(row.get("compute_cost")) or 0.0
        for row in economics.get("customer_idle_amortization") or []:
            if isinstance(row, dict):
                customer_rows.append({**row, "cell_id": cell.get("cell_id")})
    for row in curve.values():
        row["cost_per_token"] = row["compute_cost"] / row["tokens"] if row["tokens"] else None
    if not curve and not customer_rows:
        return {}
    return {
        "schema_version": "inferguard-cost-economics/v1",
        "currency": currency,
        "observed_utilization": sum(observed_utilizations) / len(observed_utilizations)
        if observed_utilizations
        else None,
        "idle_amortization_penalty": max(idle_penalties) if idle_penalties else None,
        "cost_per_token_by_utilization": sorted(
            curve.values(), key=lambda row: str(row.get("bucket"))
        ),
        "customer_idle_amortization": sorted(
            customer_rows, key=lambda row: (str(row.get("customer_id")), str(row.get("cell_id")))
        ),
    }


def _kv_by_customer(cells: list[dict[str, Any]], root: Path) -> list[dict[str, Any]]:
    rows: dict[str, dict[str, Any]] = {}
    for cell in cells:
        cell_id = cell.get("cell_id")
        customer_breakdown = (cell.get("metrics") or {}).get("customer_breakdown")
        if isinstance(customer_breakdown, dict):
            for customer, values in customer_breakdown.items():
                if not isinstance(values, dict):
                    continue
                item = rows.setdefault(
                    str(customer),
                    {
                        "customer_id": str(customer),
                        "hbm_bytes": 0.0,
                        "ram_bytes": 0.0,
                        "ssd_bytes": 0.0,
                        "evictions": 0.0,
                        "requests": 0.0,
                        "cell_id": cell_id,
                    },
                )
                item["hbm_bytes"] += _num(values.get("estimated_kv_holding_bytes")) or 0.0
                item["evictions"] += _num(values.get("evictions")) or 0.0
                item["requests"] += _num(values.get("total")) or 0.0
        path = _artifact_path(cell, root, "inferguard_bench_metrics_timeline_jsonl")
        if path is not None:
            for record in _read_jsonl(path):
                snapshot = record.get("customer_kv_snapshot")
                if not isinstance(snapshot, dict):
                    continue
                for customer, values in snapshot.items():
                    if not isinstance(values, dict):
                        continue
                    item = rows.setdefault(
                        str(customer),
                        {
                            "customer_id": str(customer),
                            "hbm_bytes": 0.0,
                            "ram_bytes": 0.0,
                            "ssd_bytes": 0.0,
                            "evictions": 0.0,
                            "requests": 0.0,
                            "cell_id": cell_id,
                        },
                    )
                    item["hbm_bytes"] = max(item["hbm_bytes"], _num(values.get("hbm_bytes")) or 0.0)
                    item["ram_bytes"] = max(item["ram_bytes"], _num(values.get("ram_bytes")) or 0.0)
                    item["ssd_bytes"] = max(item["ssd_bytes"], _num(values.get("ssd_bytes")) or 0.0)
    out = []
    for item in rows.values():
        requests = item.pop("requests", 0.0)
        item["eviction_rate"] = (item.get("evictions") or 0.0) / requests if requests else 0.0
        out.append(item)
    return sorted(out, key=lambda row: row.get("hbm_bytes") or 0, reverse=True)[:5]


def _customer_workload_cost(cells: list[dict[str, Any]], root: Path) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for cell in cells:
        cost = cell.get("cost") or {}
        compute_cost = _num(cost.get("compute_cost"))
        if compute_cost is None:
            continue
        path = _artifact_path(cell, root, "inferguard_bench_metrics_jsonl")
        metric_rows = _read_jsonl(path) if path is not None else []
        groups: dict[tuple[str, str], dict[str, Any]] = {}
        successful = [
            row
            for row in metric_rows
            if row.get("success") is True or str(row.get("success")).lower() == "true"
        ]
        total_success = len(successful) or 1
        for row in successful:
            metadata = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
            customer = str(row.get("customer_id") or metadata.get("customer_id") or "unknown")
            workload = str(row.get("workload_class") or "unknown")
            group = groups.setdefault(
                (customer, workload),
                {
                    "customer_id": customer,
                    "workload_class": workload,
                    "completed_sessions": 0,
                    "input_tokens": 0,
                    "output_tokens": 0,
                    "cell_id": cell.get("cell_id"),
                    "currency": cost.get("currency") or "USD",
                },
            )
            group["completed_sessions"] += 1
            group["input_tokens"] += int(_num(row.get("input_tokens")) or 0)
            group["output_tokens"] += int(_num(row.get("output_tokens")) or 0)
        for group in groups.values():
            share = group["completed_sessions"] / total_success
            group["compute_cost"] = compute_cost * share
            group["cost_per_completed_session"] = (
                group["compute_cost"] / group["completed_sessions"]
                if group["completed_sessions"]
                else None
            )
            out.append(group)
    return sorted(
        out, key=lambda row: (str(row.get("customer_id")), str(row.get("workload_class")))
    )


def _artifact_path(cell: dict[str, Any], root: Path, key: str) -> Path | None:
    artifact = (cell.get("artifacts") or {}).get(key)
    if not isinstance(artifact, str):
        return None
    path = root / artifact
    return path if path.exists() else None


def _read_jsonl(path: Path | None) -> list[dict[str, Any]]:
    if path is None:
        return []
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


def _cache_mode(cell: dict[str, Any]) -> str:
    topology = cell.get("topology") or {}
    for key in ("cache_mode", "offloading", "kv_offloading_backend"):
        value = topology.get(key)
        if value not in (None, ""):
            return str(value)
    cell_id = str(cell.get("cell_id") or "").lower()
    for marker in (
        "lmcache-ramssd",
        "lmcache_ramssd",
        "lmcache-ram",
        "lmcache_ram",
        "hicache",
        "native",
    ):
        if marker in cell_id:
            return marker.replace("_", "-")
    return "unknown"


def _best_stable_config(workload: str, cells: list[dict[str, Any]]) -> dict[str, Any] | None:
    baseline = _baseline_p99_ttft(cells)
    stable: list[dict[str, Any]] = []
    for cell in cells:
        success_rate = _num((cell.get("completion") or {}).get("success_rate"))
        p99_ttft = _num((cell.get("metrics") or {}).get("p99_ttft"))
        if success_rate is None or p99_ttft is None or success_rate < SUCCESS_THRESHOLD:
            continue
        if baseline is not None and p99_ttft >= baseline * TTFT_CLIFF_MULTIPLIER:
            continue
        stable.append(cell)
    if not stable:
        return None
    best = min(
        stable,
        key=lambda cell: (
            _cost_per_task(cell) is None,
            _cost_per_task(cell) or 0,
            -(_concurrency(cell) or 0),
        ),
    )
    return {
        "workload_class": workload,
        "cell_id": best.get("cell_id"),
        "concurrency": _concurrency(best),
        "success_rate": _num((best.get("completion") or {}).get("success_rate")),
        "p99_ttft_seconds": _num((best.get("metrics") or {}).get("p99_ttft")),
        "baseline_p99_ttft_seconds": baseline,
        "cost_per_task": _cost_per_task(best),
        "hardware": best.get("hardware"),
        "framework": best.get("framework"),
        "model": best.get("model"),
        "precision": best.get("precision"),
        "topology": best.get("topology") or {},
    }


def _ttft_cliff(workload: str, cells: list[dict[str, Any]]) -> dict[str, Any]:
    baseline = _baseline_p99_ttft(cells)
    if baseline is None:
        return {
            "workload_class": workload,
            "status": "not_observed",
            "message": "No conc=1 p99 TTFT baseline available.",
        }
    for cell in _sorted_by_concurrency(cells):
        conc = _concurrency(cell)
        p99 = _num((cell.get("metrics") or {}).get("p99_ttft"))
        if (
            conc is not None
            and conc > 1
            and p99 is not None
            and p99 > baseline * TTFT_CLIFF_MULTIPLIER
        ):
            return {
                "workload_class": workload,
                "status": "observed",
                "cell_id": cell.get("cell_id"),
                "concurrency": conc,
                "baseline_p99_ttft_seconds": baseline,
                "p99_ttft_seconds": p99,
                "threshold_seconds": baseline * TTFT_CLIFF_MULTIPLIER,
            }
    return {
        "workload_class": workload,
        "status": "not_observed",
        "baseline_p99_ttft_seconds": baseline,
        "message": "No p99 TTFT >2x baseline observed.",
    }


def _failure_cliff(workload: str, cells: list[dict[str, Any]]) -> dict[str, Any]:
    for cell in _sorted_by_concurrency(cells):
        success_rate = _num((cell.get("completion") or {}).get("success_rate"))
        if success_rate is not None and success_rate < SUCCESS_THRESHOLD:
            return {
                "workload_class": workload,
                "status": "observed",
                "cell_id": cell.get("cell_id"),
                "concurrency": _concurrency(cell),
                "success_rate": success_rate,
            }
    return {
        "workload_class": workload,
        "status": "not_observed",
        "message": "No success-rate drop below 95% observed.",
    }


def _oom_cliff(cell: dict[str, Any], root: Path) -> dict[str, Any]:
    path = _metrics_timeline_path(cell, root)
    if path is None:
        return {
            "cell_id": cell.get("cell_id"),
            "status": "not_observed",
            "message": "metrics_timeline.jsonl not present.",
        }
    previous_preemptions: float | None = None
    for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        snapshot = (
            record.get("disagg_snapshot")
            if isinstance(record.get("disagg_snapshot"), dict)
            else record
        )
        usage = (
            _num(snapshot.get("gpu_cache_usage", snapshot.get("kv_cache_usage")))
            if isinstance(snapshot, dict)
            else None
        )
        preemptions = (
            _num(snapshot.get("preemptions_total")) if isinstance(snapshot, dict) else None
        )
        if usage is not None and usage > OOM_GPU_CACHE_USAGE_THRESHOLD:
            return _oom_observed(
                cell, path, root, record, line_no, "gpu_cache_usage>0.95", usage, preemptions
            )
        if preemptions is not None and (
            preemptions > 0 if previous_preemptions is None else preemptions > previous_preemptions
        ):
            return _oom_observed(
                cell, path, root, record, line_no, "preemptions_begin", usage, preemptions
            )
        if preemptions is not None:
            previous_preemptions = preemptions
    return {
        "cell_id": cell.get("cell_id"),
        "status": "not_observed",
        "path": _rel(path, root),
        "message": "No GPU cache usage >0.95 or preemptions observed.",
    }


def _oom_observed(
    cell: dict[str, Any],
    path: Path,
    root: Path,
    record: dict[str, Any],
    line_no: int,
    trigger: str,
    usage: float | None,
    preemptions: float | None,
) -> dict[str, Any]:
    return {
        "cell_id": cell.get("cell_id"),
        "status": "observed",
        "trigger": trigger,
        "path": _rel(path, root),
        "line": line_no,
        "sequence": record.get("sequence"),
        "observed_at": record.get("observed_at"),
        "gpu_cache_usage": usage,
        "preemptions_total": preemptions,
    }


def _recommended_engine_config(best_stable: list[dict[str, Any]]) -> str:
    if not best_stable:
        return "No stable engine config observed. Re-run missing/failed cells before recommending a config."
    best = min(
        best_stable,
        key=lambda item: (
            item.get("cost_per_task") is None,
            item.get("cost_per_task") or 0,
            -(item.get("concurrency") or 0),
        ),
    )
    parts = [
        _first(best.get("hardware"), "unknown-hardware"),
        _first(best.get("framework"), "unknown-engine"),
        _first(best.get("precision"), None),
        _first(best.get("model"), None),
        f"conc={best.get('concurrency')}",
    ]
    topology = best.get("topology") or {}
    offloading = _first(topology.get("offloading"), topology.get("kv_offloading"), None)
    if offloading:
        parts.append(f"offload={offloading}")
    return " ".join(str(part) for part in parts if part not in (None, ""))


def _repro_commands(cells: list[dict[str, Any]], root: Path) -> list[str]:
    commands: list[str] = []
    for cell in cells:
        config_path = _artifact_path(cell, root, "inferguard_bench_config_json")
        if config_path is None or not config_path.exists():
            continue
        try:
            config = json.loads(config_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        command = config.get("command")
        if not isinstance(command, str):
            continue
        if command not in {"replay", "kvcast", "kv-stress"}:
            continue
        args = ["inferguard", "bench", str(command)]
        for key, flag in (
            ("endpoint", "--endpoint"),
            ("model", "--model"),
            ("trace_dir", "--trace-dir"),
            ("context_lengths", "--context-lengths"),
            ("concurrency_levels", "--concurrency"),
            ("kvcast_mode", "--mode"),
            ("output_tokens", "--output-tokens"),
            ("requests_per_level", "--requests-per-level"),
            ("duration_seconds", "--duration-seconds"),
            ("warmup_seconds", "--warmup-seconds"),
            ("metrics_url", "--metrics-url"),
            ("metrics_interval_seconds", "--metrics-interval"),
            ("output_dir", "--output-dir"),
        ):
            value = config.get(key)
            if value in (None, "", []):
                continue
            args.extend([flag, _shell_value(value)])
        if config.get("redact_prompts"):
            args.append("--redact-prompts")
        commands.append(" ".join(args))
    return sorted(set(commands))


def _raw_artifact_paths(report: dict[str, Any], root: Path) -> list[str]:
    paths = [str(root / "inferguard_report" / "report.json")]
    manifest = report.get("artifact_manifest") or []
    for artifact in manifest:
        if not artifact.get("present", True):
            continue
        raw = artifact.get("path")
        if isinstance(raw, str):
            paths.append(str(root / raw))
    for path in sorted(root.rglob("metrics_timeline.jsonl")):
        paths.append(str(path))
    plots_dir = root / "inferguard_report" / "plots"
    if plots_dir.exists():
        paths.extend(str(path) for path in sorted(plots_dir.glob("*.svg")))
    return sorted(set(paths))


def _metrics_timeline_path(cell: dict[str, Any], root: Path) -> Path | None:
    for artifact in (cell.get("artifacts") or {}).values():
        paths = artifact if isinstance(artifact, list) else [artifact]
        for raw in paths:
            if not isinstance(raw, str):
                continue
            candidate = root / raw
            timeline = candidate.parent / "metrics_timeline.jsonl"
            if timeline.exists():
                return timeline
    return None


def _artifact_path(cell: dict[str, Any], root: Path, key: str) -> Path | None:
    raw = (cell.get("artifacts") or {}).get(key)
    if isinstance(raw, str):
        return root / raw
    return None


def _baseline_p99_ttft(cells: list[dict[str, Any]]) -> float | None:
    baseline_cells = [cell for cell in cells if _concurrency(cell) == 1]
    values = [_num((cell.get("metrics") or {}).get("p99_ttft")) for cell in baseline_cells]
    values = [value for value in values if value is not None]
    return min(values) if values else None


def _sorted_by_concurrency(cells: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        cells,
        key=lambda cell: (
            _concurrency(cell) is None,
            _concurrency(cell) or 0,
            str(cell.get("cell_id")),
        ),
    )


def _concurrency(cell: dict[str, Any]) -> int | None:
    value = _num(cell.get("concurrency"))
    if value is not None:
        return int(value)
    levels = (cell.get("topology") or {}).get("concurrency_levels")
    if isinstance(levels, list) and len(levels) == 1:
        value = _num(levels[0])
        return int(value) if value is not None else None
    return None


def _cost_per_task(cell: dict[str, Any]) -> float | None:
    cost = cell.get("cost") or {}
    for key in ("cost_per_completed_session", "cost_per_completed_request"):
        value = _num(cost.get(key))
        if value is not None:
            return value
    return None


def _shell_value(value: Any) -> str:
    if isinstance(value, list):
        return ",".join(str(item) for item in value)
    return str(value)


def _rel(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return str(path)


def _num(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _first(*values: Any) -> Any:
    for value in values:
        if value not in (None, "", []):
            return value
    return None


def _fmt(value: Any) -> str:
    number = _num(value)
    if number is None:
        return "-"
    return f"{number:.4g}"


def _dash(value: Any) -> str:
    return "-" if value is None else str(value)

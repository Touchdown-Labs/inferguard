"""Markdown renderer for PRD §4.11 cost reports."""

from __future__ import annotations

from typing import Any

from .types import CostReport


def render_cost_markdown(report: CostReport) -> str:
    data = report.to_dict()
    envelope = data.get("safe_concurrency_envelope") or {}
    lines = [
        "# InferGuard cost report",
        "",
        f"- [measured] Schema: `{data['schema_version']}`",
        f"- [{data['claim_status']}] Claim status: `{data['claim_status']}`",
        f"- [measured] Cost input: `{data['cost_input']['source_path']}`",
        "",
        "## Unit economics",
        "",
        _line(data, "cost_per_million_prompt_tokens_usd", "Cost per million prompt tokens"),
        _line(data, "cost_per_million_completion_tokens_usd", "Cost per million generated tokens"),
        _line(data, "cost_per_useful_task_usd", "Cost per useful task"),
        _line(data, "gpu_hour_normalized_throughput", "Useful tasks per GPU-hour"),
        "",
        "## Failed-request waste",
        "",
        _line(data, "failed_request_waste_percent", "Failed-request waste percent"),
        _line(data, "failed_request_waste_dollars", "Failed-request waste dollars"),
        "",
        "## Safe concurrency envelope",
        "",
        f"- [{envelope.get('claim_status', 'not_proven')}] Safe concurrency: {_fmt(envelope.get('safe_concurrency'))}",
        f"- [measured] TTFT SLO ms: {_fmt(envelope.get('slo_ttft_ms'))}",
        f"- [measured] E2E SLO ms: {_fmt(envelope.get('slo_e2e_ms'))}",
        f"- [measured] Success-rate SLO: {_fmt(envelope.get('slo_success_rate'))}",
    ]
    levels = envelope.get("evaluated_levels") or []
    if levels:
        lines.extend(
            [
                "",
                "| Concurrency | p99 TTFT ms | p99 E2E ms | Success rate | Meets SLO |",
                "|---:|---:|---:|---:|---|",
            ]
        )
        for level in levels:
            lines.append(
                "| {conc} | {ttft} | {e2e} | {success} | {meets} |".format(
                    conc=_fmt(level.get("concurrency")),
                    ttft=_fmt(level.get("p99_ttft_ms")),
                    e2e=_fmt(level.get("p99_e2e_ms")),
                    success=_fmt(level.get("success_rate")),
                    meets=str(bool(level.get("meets_slo"))).lower(),
                )
            )
    return "\n".join(lines).rstrip() + "\n"


def _line(data: dict[str, Any], key: str, label: str) -> str:
    status = (data.get("claim_status_by_field") or {}).get(key) or data.get("claim_status")
    return f"- [{status}] {label}: {_fmt(data.get(key))}"


def _fmt(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, float):
        return f"{value:.6g}"
    return str(value)


__all__ = ["render_cost_markdown"]

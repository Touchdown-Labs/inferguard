"""Markdown renderer for PRD §4.5 bottleneck diagnosis."""

from __future__ import annotations

import json

from inferguard.diagnose_bottleneck.types import BottleneckDiagnosis, Evidence


def render_diagnosis_markdown(diagnosis: BottleneckDiagnosis) -> str:
    """Render an operator-readable diagnosis report."""

    metric_values = json.dumps(diagnosis.metric_values, sort_keys=True)
    evidence_paths = ", ".join(f"`{path}`" for path in diagnosis.evidence_paths) or "-"
    lines = [
        "# InferGuard bottleneck diagnosis",
        "",
        (
            f"- Verdict: `{diagnosis.verdict}` | claim_status=`{diagnosis.claim_status}` | "
            f"evidence_paths={evidence_paths} | metric_values=`{metric_values}`"
        ),
        f"- Confidence: {diagnosis.confidence:.3f}",
        f"- Rule fired: `{diagnosis.rule_fired}`",
        f"- Recommended next probe: `{diagnosis.recommended_next_probe}`",
        "",
        "## Reasoning",
        "",
        diagnosis.reasoning,
        "",
        "## Primary evidence",
        "",
    ]
    lines.extend(_render_evidence(diagnosis.primary_evidence))
    lines.extend(["", "## Secondary evidence", ""])
    if diagnosis.secondary_evidence:
        lines.extend(_render_evidence(diagnosis.secondary_evidence))
    else:
        lines.append("- None")
    lines.extend(["", "## Supporting request rows", ""])
    if diagnosis.supporting_request_rows:
        lines.extend(f"- `{request_id}`" for request_id in diagnosis.supporting_request_rows)
    else:
        lines.append("- None")
    lines.extend(["", "## Downgrades", ""])
    if diagnosis.downgrades:
        for downgrade in diagnosis.downgrades:
            lines.append(
                f"- `{downgrade.claim_id}`: `{downgrade.from_label}` -> "
                f"`{downgrade.to}` ({downgrade.reason})"
            )
    else:
        lines.append("- None")
    lines.append("")
    return "\n".join(lines)


def render_bottleneck_diagnosis_markdown(diagnosis: BottleneckDiagnosis) -> str:
    """Compatibility alias for the PRD implementation-map function name."""

    return render_diagnosis_markdown(diagnosis)


def _render_evidence(items: list[Evidence]) -> list[str]:
    rows: list[str] = []
    for item in items:
        payload = item.to_dict()
        value = payload.get("value_p95", payload.get("value"))
        rows.append(
            f"- `{payload['metric']}` = `{value}` from `{payload['source']}` "
            f"(claim_status=`{payload['claim_status']}`)"
        )
    return rows or ["- None"]


__all__ = ["render_bottleneck_diagnosis_markdown", "render_diagnosis_markdown"]

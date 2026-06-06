"""Operator-readable rendering for NVFP4 qualification results."""

from __future__ import annotations

from .types import NVFp4Qualification, NVFp4Verdict

_VERDICT_LABEL = {
    NVFp4Verdict.QUALIFIED.value: "QUALIFIED",
    NVFp4Verdict.NOT_QUALIFIED.value: "NOT QUALIFIED",
    NVFp4Verdict.NEEDS_REVIEW.value: "NEEDS REVIEW",
}


def render_qualification_markdown(q: NVFp4Qualification) -> str:
    """Render a qualification card as markdown."""
    lines: list[str] = []
    lines.append(f"# NVFP4 {q.check}: {_VERDICT_LABEL.get(str(q.verdict), str(q.verdict))}")
    lines.append("")
    lines.append(f"- Model: `{q.model or 'n/a'}`")
    lines.append(f"- Endpoint: `{q.endpoint or 'n/a'}`")
    lines.append(f"- Confidence: {q.confidence:.2f}")
    lines.append(f"- Claim status: {q.claim_status}")
    lines.append("")
    if q.results:
        lines.append("| Check | Result | Value | Threshold | Claim |")
        lines.append("|---|---|---|---|---|")
        for r in q.results:
            status = "PASS" if r.passed else "FAIL"
            lines.append(
                f"| {r.name} | {status} | {r.value} {r.unit} | {r.threshold} | {r.claim_status} |"
            )
        lines.append("")
    if q.reasoning:
        lines.append(f"**Reasoning:** {q.reasoning}")
        lines.append("")
    if q.recommended_next:
        lines.append(f"**Next:** {q.recommended_next}")
        lines.append("")
    return "\n".join(lines)


def render_qualification_console(q: NVFp4Qualification) -> str:
    """Compact multi-line console summary."""
    label = _VERDICT_LABEL.get(str(q.verdict), str(q.verdict))
    out = [f"NVFP4 {q.check}: {label} (confidence {q.confidence:.2f}, claim {q.claim_status})"]
    for r in q.results:
        mark = "PASS" if r.passed else "FAIL"
        out.append(f"  [{mark}] {r.name}: {r.value} {r.unit} (threshold {r.threshold})")
        if r.detail:
            out.append(f"         {r.detail}")
    if q.reasoning:
        out.append(f"  -> {q.reasoning}")
    if q.recommended_next:
        out.append(f"  next: {q.recommended_next}")
    return "\n".join(out)

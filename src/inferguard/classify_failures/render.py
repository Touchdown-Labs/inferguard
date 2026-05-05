"""Markdown rendering for failure classification reports."""

from __future__ import annotations

from inferguard.classify_failures.types import FailureClassification

NEXT_ACTIONS = {
    "oom_hbm_exhaustion": "Lower max model length or concurrency, reduce gpu-memory-utilization, or move to a higher-HBM SKU.",
    "cuda_error": "Collect CUDA driver/runtime versions, inspect DCGM XID/ECC evidence, and rerun with CUDA_LAUNCH_BLOCKING=1 for a narrow repro.",
    "nccl_error": "Run NCCL all_reduce_perf with NCCL_DEBUG=INFO and verify shared memory, topology, and multi-node interface selection.",
    "rdma_inactive": "Check ibstat/ibv_devinfo output for State: Active, then reseat or route around the inactive IB/RDMA link.",
    "model_config_mismatch": "Recheck model_config_summary.json, tokenizer/config revisions, tensor parallel settings, and model loader format.",
    "tokenizer_or_parser_failure": "Pin tokenizer/chat-template/tool-parser/reasoning-parser settings and run a one-request canary before load testing.",
    "container_image_incompatibility": "Rebuild or swap the container image so CUDA, GLIBC/GLIBCXX, PyTorch, and NCCL shared libraries match the host.",
    "endpoint_healthcheck_failure": "Inspect launch/healthcheck.json and launch logs, then verify the endpoint host, port, readiness, and route.",
    "client_timeout": "Increase client timeout only after checking queue depth, TTFT, and server health; cap request fanout during retry storms.",
    "server_crash": "Preserve core/stack traces, capture the exact engine command, and bisect model, CUDA graph, and kernel settings.",
    "slurm_allocation_failure": "Fix the Slurm account/partition/node/GPU request before rerunning engine or workload tests.",
    "not_enough_evidence": "Preserve the raw log tail and add the missing launch, healthcheck, request, preflight, or metrics artifact.",
}


def render_failure_classification_markdown(report: FailureClassification) -> str:
    """Render an operator-readable failure triage report."""

    lines = [
        "# InferGuard Failure Classification",
        "",
        f"- Schema: `{report.schema_version}`",
        f"- Job: `{report.job_id}`",
        f"- Top class: `{report.top_class}`",
        f"- Claim status: `{report.claim_status}`",
        f"- Failure count: {len(report.failures)}",
        "",
    ]
    if not report.failures:
        lines.extend(["## Ranked failures", "", "No failure evidence found.", ""])
        return "\n".join(lines)

    lines.extend(["## Ranked failures", ""])
    for failure in report.failures:
        paths = failure.to_dict()["evidence_paths"]
        lines.extend(
            [
                f"### {failure.rank}. `{failure.failure_class}`",
                "",
                f"- Confidence: {failure.confidence:.3f}",
                f"- Claim status: `{failure.claim_status}`",
                f"- Regex/source id: `{failure.regex_id}`",
                f"- Suggested next action: {NEXT_ACTIONS[failure.failure_class]}",
                "- Evidence paths:",
            ]
        )
        for path in paths:
            lines.append(f"  - `{path}`")
        if failure.evidence_excerpt:
            lines.extend(["- Evidence excerpt:", "", f"  `{failure.evidence_excerpt}`"])
        lines.append("")
    return "\n".join(lines)


__all__ = ["NEXT_ACTIONS", "render_failure_classification_markdown"]

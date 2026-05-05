"""Rule-based router MVP built on existing InferGuard artifacts."""

from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from inferguard.analyze import AnalyzeOptions, analyze_results
from inferguard.router.verdict import BottleneckClass, ExecutionPath, FindingRef, RouterVerdict
from inferguard.workload.fingerprint import WorkloadFingerprint


class RouterClassifyError(RuntimeError):
    """Raised when a router verdict cannot be produced."""


def classify_run_dir(
    run_dir: Path,
    *,
    workload_fingerprint_path: Path | None = None,
    slo: dict[str, float] | None = None,
    hardware_fleet: list[str] | None = None,
) -> RouterVerdict:
    report = _load_or_analyze(run_dir)
    fingerprint = _load_fingerprint(workload_fingerprint_path) if workload_fingerprint_path else None
    evidence = _finding_refs(report)
    bottleneck = _choose_bottleneck(report, fingerprint, slo or {})
    paths = _execution_paths(bottleneck, fingerprint, hardware_fleet or [])
    return RouterVerdict(
        bottleneck_class=bottleneck,
        execution_paths=paths,
        evidence=evidence,
        claim_label=_claim_label(report),
    )


def render_verdict_markdown(verdict: RouterVerdict) -> str:
    data = verdict.as_dict()
    lines = [
        "# InferGuard Router Verdict",
        "",
        f"- Schema: `{data['schema_version']}`",
        f"- Bottleneck: `{data['bottleneck_class']}`",
        f"- Claim label: `{data['claim_label']}`",
        "",
        "## Recommended Paths",
        "",
        "| Rank | Target | Confidence | Partner | Rationale |",
        "|---:|---|---:|---|---|",
    ]
    for index, path in enumerate(data["execution_paths"], start=1):
        lines.append(
            f"| {index} | `{path['target']}` | {path['confidence']:.2f} | "
            f"{path.get('referral_partner') or '-'} | {path['rationale']} |"
        )
    lines.extend(["", "## Claim Boundary", "", data["claim_boundary"], ""])
    return "\n".join(lines)


def _load_or_analyze(run_dir: Path) -> dict[str, Any]:
    candidates = [run_dir / "report.json", run_dir / "inferguard_report" / "report.json"]
    for path in candidates:
        if path.exists():
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data
    try:
        with TemporaryDirectory(prefix="inferguard-router-analyze-") as tmp:
            return analyze_results(run_dir, AnalyzeOptions(output_dir=Path(tmp), output_format="json"))
    except Exception as exc:  # noqa: BLE001 - CLI surfaces this as a route failure
        raise RouterClassifyError(f"could not load or analyze run_dir: {exc}") from exc


def _load_fingerprint(path: Path) -> WorkloadFingerprint:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return WorkloadFingerprint.model_validate(data)
    except Exception as exc:  # noqa: BLE001
        raise RouterClassifyError(f"could not load workload fingerprint {path}: {exc}") from exc


def _finding_refs(report: dict[str, Any]) -> list[FindingRef]:
    refs: list[FindingRef] = []
    for finding in report.get("findings") or []:
        if isinstance(finding, dict):
            refs.append(
                FindingRef(
                    source="inferguard-analyze",
                    code=str(finding.get("code") or "unknown"),
                    severity=str(finding.get("severity") or "info"),
                    message=str(finding.get("message") or ""),
                    cell_id=str(finding.get("cell_id")) if finding.get("cell_id") is not None else None,
                )
            )
    return refs


def _choose_bottleneck(
    report: dict[str, Any],
    fingerprint: WorkloadFingerprint | None,
    slo: dict[str, float],
) -> BottleneckClass:
    codes = {str(f.get("code")) for f in report.get("findings") or [] if isinstance(f, dict)}
    if "canary_quality_regression" in codes or "prompt_template_tool_parser_regression" in codes:
        return BottleneckClass.QUALITY_BOUND
    if {"retry_storm_engine_overload", "multi_tenant_noisy_neighbor"} & codes:
        return BottleneckClass.QUEUE_BOUND
    if {"kv_transfer_stall", "kv_footprint_imbalance", "prefix_eviction_cross_customer"} & codes:
        return BottleneckClass.KV_BOUND
    if "gpu_partial_degradation" in codes:
        return BottleneckClass.HOST_BOUND
    if _p99_ttft_ms(report) > slo.get("p95_ttft_ms", 1500) * 1.5:
        return BottleneckClass.PREFILL_BOUND
    if fingerprint is not None:
        input_p95 = fingerprint.input_token_distribution.p95 or 0
        if input_p95 >= 32768 or fingerprint.cacheability_score >= 0.55:
            return BottleneckClass.KV_BOUND
        if (fingerprint.prefill_decode_ratio or 0) >= 0.72:
            return BottleneckClass.PREFILL_BOUND
        if fingerprint.retry_rate > slo.get("error_rate_max", 0.01):
            return BottleneckClass.QUEUE_BOUND
    return BottleneckClass.DECODE_BOUND


def _execution_paths(
    bottleneck: BottleneckClass,
    fingerprint: WorkloadFingerprint | None,
    hardware_fleet: list[str],
) -> list[ExecutionPath]:
    private = fingerprint is not None and fingerprint.privacy_class in {"private", "regulated"}
    has_gb200 = any(hw.lower() == "gb200" for hw in hardware_fleet)
    if bottleneck == BottleneckClass.KV_BOUND:
        return [
            ExecutionPath(
                target="self_hosted_vllm",
                confidence=0.78,
                referral_partner="tensormesh",
                rationale="KV pressure or cacheability dominates; validate baseline vLLM before LMCache/TensorMesh cells.",
            ),
            ExecutionPath(
                target="self_hosted_sglang",
                confidence=0.64,
                referral_partner="radixark",
                rationale="Prefix-heavy agentic sessions may benefit from SGLang/RadixAttention if live metrics confirm reuse.",
            ),
        ]
    if bottleneck == BottleneckClass.PREFILL_BOUND:
        target = "self_hosted_dynamo" if has_gb200 else "self_hosted_vllm"
        return [
            ExecutionPath(
                target=target,
                confidence=0.72,
                referral_partner="gmi" if has_gb200 else "inferact",
                rationale="Prefill-bound workload should validate disaggregated prefill/decode or Blackwell topology.",
            )
        ]
    if bottleneck == BottleneckClass.QUALITY_BOUND:
        return [
            ExecutionPath(
                target="openai_api",
                confidence=0.68,
                referral_partner=None,
                rationale="Quality regression is the binding constraint; keep frontier API baseline until canary gate passes.",
            )
        ]
    if private:
        return [
            ExecutionPath(
                target="local_mlx",
                confidence=0.66,
                referral_partner="modular",
                rationale="Privacy class pushes toward local or self-hosted execution before hosted APIs.",
            )
        ]
    return [
        ExecutionPath(
            target="hosted_open_api",
            confidence=0.60,
            referral_partner="nebius",
            rationale="No stronger engine-specific bottleneck was proven; hosted open API is the conservative first comparison.",
        ),
        ExecutionPath(
            target="self_hosted_vllm",
            confidence=0.52,
            referral_partner="inferact",
            rationale="Run self-hosted baseline only if volume, privacy, or cost floor justifies operational ownership.",
        ),
    ]


def _p99_ttft_ms(report: dict[str, Any]) -> float:
    values: list[float] = []
    for cell in report.get("cells") or []:
        if not isinstance(cell, dict):
            continue
        metrics = cell.get("metrics") if isinstance(cell.get("metrics"), dict) else {}
        value = metrics.get("p99_ttft") or metrics.get("p99_ttft_seconds")
        try:
            values.append(float(value) * 1000)
        except (TypeError, ValueError):
            continue
    return max(values, default=0.0)


def _claim_label(report: dict[str, Any]) -> str:
    cells = report.get("cells") or []
    if any(isinstance(cell, dict) and cell.get("source_format") == "agentx-trace-replay" for cell in cells):
        return "measured_local"
    if cells:
        return "measured_local"
    return "inferred_without_engine_metrics"

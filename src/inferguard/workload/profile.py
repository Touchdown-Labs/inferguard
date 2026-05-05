"""Pre-flight workload fingerprinting."""

from __future__ import annotations

from collections import Counter, defaultdict
from pathlib import Path
from statistics import mean

from inferguard.workload.fingerprint import CostEstimate, Distribution, WorkloadFingerprint
from inferguard.workload.ingest import WorkloadSample, read_openai_jsonl_dir


class WorkloadAnalyzeError(RuntimeError):
    """Raised when workload analysis cannot produce a fingerprint."""


def analyze_workload_dir(
    log_dir: Path,
    *,
    source_format: str = "openai-jsonl",
    privacy_class: str = "public",
    latency_sensitivity: str = "loose",
) -> WorkloadFingerprint:
    if source_format != "openai-jsonl":
        raise WorkloadAnalyzeError(f"unsupported workload format: {source_format}")
    samples = read_openai_jsonl_dir(log_dir)
    if not samples:
        raise WorkloadAnalyzeError(f"no JSONL workload samples found under {log_dir}")
    return fingerprint_samples(
        samples,
        source_format=source_format,
        privacy_class=privacy_class,
        latency_sensitivity=latency_sensitivity,
    )


def fingerprint_samples(
    samples: list[WorkloadSample],
    *,
    source_format: str,
    privacy_class: str,
    latency_sensitivity: str,
) -> WorkloadFingerprint:
    input_tokens = [sample.input_tokens for sample in samples]
    output_tokens = [sample.output_tokens for sample in samples]
    by_session: dict[str, int] = defaultdict(int)
    prefix_counts: Counter[str] = Counter()
    workload_classes: Counter[str] = Counter()
    for sample in samples:
        by_session[sample.session_id] += 1
        if sample.prefix_key:
            prefix_counts[sample.prefix_key] += 1
        workload_classes[sample.workload_class] += 1
    repeated_prefix_samples = sum(count for count in prefix_counts.values() if count > 1)
    prefix_reuse_score = repeated_prefix_samples / len(samples) if samples else 0.0
    total_input = sum(input_tokens)
    total_output = sum(output_tokens)
    token_total = total_input + total_output
    prefill_decode_ratio = (total_input / token_total) if token_total else None
    tool_counts = [sample.tool_call_count for sample in samples]
    retry_rate = sum(1 for sample in samples if sample.retry_count > 0) / len(samples)
    rag_chunk_volume = sum(sample.rag_chunk_count for sample in samples)
    burstiness = _burstiness(samples)
    cacheability_score = min(
        1.0,
        (prefix_reuse_score * 0.65)
        + ((sum(by_session.values()) - len(by_session)) / len(samples) * 0.20)
        + (min(1.0, rag_chunk_volume / max(1, len(samples) * 4)) * 0.15),
    )
    return WorkloadFingerprint(
        sample_count=len(samples),
        source_format=source_format,
        input_token_distribution=_distribution(input_tokens),
        output_token_distribution=_distribution(output_tokens),
        session_length_distribution=_distribution(list(by_session.values())),
        prefix_reuse_score=round(prefix_reuse_score, 6),
        prefill_decode_ratio=round(prefill_decode_ratio, 6) if prefill_decode_ratio is not None else None,
        tool_call_fanout_distribution=_distribution(tool_counts),
        retry_rate=round(retry_rate, 6),
        rag_chunk_volume=rag_chunk_volume,
        burstiness_factor=round(burstiness, 6) if burstiness is not None else None,
        p95_latency_sensitivity=_validated_latency_sensitivity(latency_sensitivity),
        cacheability_score=round(cacheability_score, 6),
        privacy_class=_validated_privacy_class(privacy_class),
        workload_classes=dict(sorted(workload_classes.items())),
        cost_per_task_estimate=CostEstimate(
            input_tokens=total_input,
            output_tokens=total_output,
            notes=["No provider pricing was supplied; baseline_cost_usd is intentionally null."],
        ),
    )


def render_fingerprint_markdown(fingerprint: WorkloadFingerprint) -> str:
    data = fingerprint.as_dict()
    return "\n".join(
        [
            "# InferGuard Workload Fingerprint",
            "",
            f"- Schema: `{data['schema_version']}`",
            f"- Samples: {data['sample_count']}",
            f"- Privacy class: `{data['privacy_class']}`",
            f"- P95 input tokens: {_fmt(data['input_token_distribution']['p95'])}",
            f"- Prefix reuse score: {_fmt(data['prefix_reuse_score'])}",
            f"- Cacheability score: {_fmt(data['cacheability_score'])}",
            f"- Retry rate: {_fmt(data['retry_rate'])}",
            "",
            "## Claim Boundary",
            "",
            data["claim_boundary"],
            "",
        ]
    )


def _distribution(values: list[int]) -> Distribution:
    if not values:
        return Distribution()
    sorted_values = sorted(values)
    return Distribution(
        p50=_percentile(sorted_values, 50),
        p95=_percentile(sorted_values, 95),
        p99=_percentile(sorted_values, 99),
        max=float(sorted_values[-1]),
    )


def _percentile(sorted_values: list[int], percentile: int) -> float:
    if not sorted_values:
        return 0.0
    if len(sorted_values) == 1:
        return float(sorted_values[0])
    rank = (percentile / 100) * (len(sorted_values) - 1)
    lower = int(rank)
    upper = min(lower + 1, len(sorted_values) - 1)
    weight = rank - lower
    return float(sorted_values[lower] * (1 - weight) + sorted_values[upper] * weight)


def _burstiness(samples: list[WorkloadSample]) -> float | None:
    timestamps = sorted(sample.timestamp for sample in samples if sample.timestamp is not None)
    if len(timestamps) < 3:
        return None
    gaps = [max(0.0, b - a) for a, b in zip(timestamps, timestamps[1:], strict=False)]
    avg = mean(gaps)
    if avg <= 0:
        return None
    variance = mean((gap - avg) ** 2 for gap in gaps)
    return variance / avg


def _validated_latency_sensitivity(raw: str) -> str:
    if raw not in {"tight", "loose", "batch"}:
        raise WorkloadAnalyzeError("--latency-sensitivity must be one of tight|loose|batch")
    return raw


def _validated_privacy_class(raw: str) -> str:
    if raw not in {"public", "private", "regulated"}:
        raise WorkloadAnalyzeError("--privacy-class must be one of public|private|regulated")
    return raw


def _fmt(value: object) -> str:
    if value is None:
        return "-"
    if isinstance(value, float):
        return f"{value:.4g}"
    return str(value)

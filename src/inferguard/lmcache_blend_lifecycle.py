"""CacheBlend L0 GPU lifecycle metric and evidence normalization."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from inferguard.lmcache_cacheblend_boundary import read_cacheblend_boundary_evidence_jsonl
from inferguard.metrics_core import parse_labeled_prometheus_text

_DURATION_SUM = {
    "lmcache_blend_l0_gpu_operation_duration_seconds_sum",
    "lmcache_blend.l0_gpu_operation_duration_seconds_sum",
}
_DURATION_COUNT = {
    "lmcache_blend_l0_gpu_operation_duration_seconds_count",
    "lmcache_blend.l0_gpu_operation_duration_seconds_count",
}
_TRANSFER_CHUNKS = {
    "lmcache_blend_l0_gpu_transfer_chunks_total",
    "lmcache_blend.l0_gpu_transfer_chunks",
}
_TRANSFER_TOKENS = {
    "lmcache_blend_l0_gpu_transfer_tokens_total",
    "lmcache_blend.l0_gpu_transfer_tokens",
}

OperationKey = tuple[str, str]


@dataclass(frozen=True)
class CacheBlendLifecycleSummary:
    """Normalized CacheBlend L0 GPU lifecycle metrics and boundary evidence."""

    present: bool
    avg_duration_seconds_by_operation: dict[OperationKey, float]
    transfer_chunks_by_operation: dict[OperationKey, float]
    transfer_tokens_by_operation: dict[OperationKey, float]
    boundary_evidence: dict[str, Any] | None

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable representation."""
        return {
            "present": self.present,
            "avg_duration_seconds_by_operation": _stringify_keyed_dict(
                self.avg_duration_seconds_by_operation
            ),
            "transfer_chunks_by_operation": _stringify_keyed_dict(
                self.transfer_chunks_by_operation
            ),
            "transfer_tokens_by_operation": _stringify_keyed_dict(
                self.transfer_tokens_by_operation
            ),
            "boundary_evidence": self.boundary_evidence,
        }


def analyze_cacheblend_lifecycle(
    metrics_text: str,
    *,
    boundary_evidence_path: Path | None = None,
) -> CacheBlendLifecycleSummary:
    """Parse CacheBlend L0 GPU lifecycle metrics and optional boundary JSONL."""
    duration_sum: dict[OperationKey, float] = {}
    duration_count: dict[OperationKey, float] = {}
    transfer_chunks: dict[OperationKey, float] = {}
    transfer_tokens: dict[OperationKey, float] = {}

    present = False
    for sample in parse_labeled_prometheus_text(metrics_text):
        key = _operation_key(sample.labels)
        if sample.name in _DURATION_SUM:
            present = True
            duration_sum[key] = duration_sum.get(key, 0.0) + sample.value
        elif sample.name in _DURATION_COUNT:
            present = True
            duration_count[key] = duration_count.get(key, 0.0) + sample.value
        elif sample.name in _TRANSFER_CHUNKS:
            present = True
            transfer_chunks[key] = transfer_chunks.get(key, 0.0) + sample.value
        elif sample.name in _TRANSFER_TOKENS:
            present = True
            transfer_tokens[key] = transfer_tokens.get(key, 0.0) + sample.value

    boundary_evidence = read_cacheblend_boundary_evidence_jsonl(boundary_evidence_path)
    if boundary_evidence is not None and boundary_evidence.get("claim_status") == "measured":
        present = True

    return CacheBlendLifecycleSummary(
        present=present,
        avg_duration_seconds_by_operation={
            key: total / duration_count[key]
            for key, total in duration_sum.items()
            if duration_count.get(key, 0) > 0
        },
        transfer_chunks_by_operation=transfer_chunks,
        transfer_tokens_by_operation=transfer_tokens,
        boundary_evidence=boundary_evidence,
    )


def _operation_key(labels: dict[str, str]) -> OperationKey:
    return (labels.get("operation", "unknown"), labels.get("direction", "unknown"))


def _stringify_keyed_dict(values: dict[OperationKey, float]) -> dict[str, float]:
    return {f"{operation}:{direction}": value for (operation, direction), value in values.items()}


__all__ = ["CacheBlendLifecycleSummary", "analyze_cacheblend_lifecycle"]

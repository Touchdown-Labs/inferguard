"""Replay-backed validation helpers for InferGuard."""

from __future__ import annotations

import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class ReplayValidationResult:
    incident_id: str
    phase: str
    timestamp: float
    completed_sessions: int
    total_sessions: int
    output_throughput_tps: float
    mean_ttft_ms: float
    p99_ttft_ms: float
    mean_tpot_ms: float
    cache_usage_avg: float
    cache_usage_peak: float
    kv_offload_observed: bool
    raw_benchmark: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return {
            "incident_id": self.incident_id,
            "phase": self.phase,
            "timestamp": self.timestamp,
            "completed_sessions": self.completed_sessions,
            "total_sessions": self.total_sessions,
            "output_throughput_tps": self.output_throughput_tps,
            "mean_ttft_ms": self.mean_ttft_ms,
            "p99_ttft_ms": self.p99_ttft_ms,
            "mean_tpot_ms": self.mean_tpot_ms,
            "cache_usage_avg": self.cache_usage_avg,
            "cache_usage_peak": self.cache_usage_peak,
            "kv_offload_observed": self.kv_offload_observed,
            "raw_benchmark": self.raw_benchmark,
        }


@dataclass(frozen=True)
class ReplayValidationComparison:
    incident_id: str
    baseline: ReplayValidationResult
    post: ReplayValidationResult
    throughput_delta_pct: float
    ttft_delta_pct: float
    cache_usage_delta: float
    verdict: str
    improvements: list[str]
    regressions: list[str]

    def as_dict(self) -> dict[str, Any]:
        return {
            "incident_id": self.incident_id,
            "baseline": self.baseline.as_dict(),
            "post": self.post.as_dict(),
            "throughput_delta_pct": self.throughput_delta_pct,
            "ttft_delta_pct": self.ttft_delta_pct,
            "cache_usage_delta": self.cache_usage_delta,
            "verdict": self.verdict,
            "improvements": list(self.improvements),
            "regressions": list(self.regressions),
        }


class ReplayValidator:
    def __init__(
        self,
        export_file: str,
        target_endpoint: str,
        model_id: str,
        *,
        max_concurrency: int = 4,
        max_sessions: int | None = None,
        runtime_stack_id: str | None = None,
        skip_tokenizer: bool = True,
    ):
        self.export_file = export_file
        self.target_endpoint = target_endpoint.rstrip("/")
        self.model_id = model_id
        self.max_concurrency = max_concurrency
        self.max_sessions = max_sessions
        self.runtime_stack_id = runtime_stack_id or None
        self.skip_tokenizer = skip_tokenizer

    def _load_harness(self) -> Any:
        repo_root = Path(__file__).resolve().parents[2]
        demo_dir = repo_root / "demo"
        if str(demo_dir) not in sys.path:
            sys.path.insert(0, str(demo_dir))
        try:
            import replay_harness  # type: ignore
        except Exception as exc:  # pragma: no cover - import environment path
            raise RuntimeError(
                "Replay validation requires InferGuard demo extras. Install with "
                "pip install -e '.[demo]' before using replay validation."
            ) from exc
        return replay_harness

    async def run_replay(self, incident_id: str, phase: str) -> ReplayValidationResult:
        harness = self._load_harness()
        counter = harness.build_text_token_counter(None if self.skip_tokenizer else self.model_id)
        sessions, selection_metadata = harness.load_replay_sessions(
            export_file=self.export_file,
            count_text_tokens=counter,
            runtime_stack_ids={self.runtime_stack_id} if self.runtime_stack_id else None,
            max_sessions=self.max_sessions,
            allow_mixed_selection=True,
        )
        benchmark = await harness.run_export_replay_benchmark(
            sessions=sessions,
            selection_metadata=selection_metadata,
            model_id=self.model_id,
            model_name=self.model_id or None,
            chat_api_url=f"{self.target_endpoint}/v1/chat/completions",
            completion_api_url=f"{self.target_endpoint}/v1/completions",
            count_text_tokens=counter,
            max_concurrency=self.max_concurrency,
            selected_percentiles=[50.0, 90.0, 99.0],
            disable_tqdm=True,
            num_warmup_sessions=0,
        )
        aggregate = benchmark.get("aggregate_metrics", {})
        server_metrics = benchmark.get("server_metrics_summary", {})
        cache_avg = _as_float(
            server_metrics.get("cache_usage_avg"),
            fallback=_as_float(server_metrics.get("gpu_cache_usage_avg")),
        )
        cache_peak = _as_float(
            server_metrics.get("gpu_cache_usage_peak"),
            fallback=_as_float(server_metrics.get("cache_usage_peak"), fallback=cache_avg),
        )
        return ReplayValidationResult(
            incident_id=incident_id,
            phase=phase,
            timestamp=time.time(),
            completed_sessions=int(aggregate.get("completed_sessions") or len(sessions)),
            total_sessions=int(aggregate.get("total_sessions") or len(sessions)),
            output_throughput_tps=_first_float(
                aggregate,
                "output_throughput_tps",
                "output_throughput_tokens_per_sec",
                "output_tokens_per_second",
            ),
            mean_ttft_ms=_first_float(aggregate, "mean_ttft_ms", "ttft_mean_ms"),
            p99_ttft_ms=_first_float(aggregate, "p99_ttft_ms", "ttft_p99_ms"),
            mean_tpot_ms=_first_float(aggregate, "mean_tpot_ms", "tpot_mean_ms"),
            cache_usage_avg=cache_avg,
            cache_usage_peak=cache_peak,
            kv_offload_observed=bool(server_metrics.get("kv_offload_observed", False)),
            raw_benchmark=benchmark,
        )

    @staticmethod
    def compare(
        baseline: ReplayValidationResult,
        post: ReplayValidationResult,
    ) -> ReplayValidationComparison:
        throughput_delta_pct = _pct_delta(
            baseline.output_throughput_tps,
            post.output_throughput_tps,
        )
        ttft_delta_pct = _pct_delta(baseline.mean_ttft_ms, post.mean_ttft_ms)
        cache_usage_delta = post.cache_usage_avg - baseline.cache_usage_avg

        improvements: list[str] = []
        regressions: list[str] = []
        if throughput_delta_pct >= 5.0:
            improvements.append("throughput_improved")
        elif throughput_delta_pct <= -5.0:
            regressions.append("throughput_regressed")

        if ttft_delta_pct <= -10.0:
            improvements.append("ttft_improved")
        elif ttft_delta_pct >= 10.0:
            regressions.append("ttft_regressed")

        if cache_usage_delta <= -0.05:
            improvements.append("kv_improved")
        elif cache_usage_delta >= 0.05:
            regressions.append("kv_regressed")

        if improvements and not regressions:
            verdict = "improved"
        elif regressions and not improvements:
            verdict = "regressed"
        else:
            verdict = "inconclusive"

        return ReplayValidationComparison(
            incident_id=post.incident_id,
            baseline=baseline,
            post=post,
            throughput_delta_pct=throughput_delta_pct,
            ttft_delta_pct=ttft_delta_pct,
            cache_usage_delta=cache_usage_delta,
            verdict=verdict,
            improvements=improvements,
            regressions=regressions,
        )


def _as_float(value: Any, fallback: float = 0.0) -> float:
    try:
        if value is None:
            return fallback
        return float(value)
    except (TypeError, ValueError):
        return fallback


def _first_float(mapping: dict[str, Any], *keys: str) -> float:
    for key in keys:
        if key in mapping:
            return _as_float(mapping.get(key))
    return 0.0


def _pct_delta(baseline: float, post: float) -> float:
    if abs(baseline) < 1e-6:
        return 0.0 if abs(post) < 1e-6 else 100.0
    return ((post - baseline) / baseline) * 100.0

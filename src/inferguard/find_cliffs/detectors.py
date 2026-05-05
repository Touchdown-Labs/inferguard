"""Capacity cliff detectors for completed NeoCloud/GMI sweeps."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from inferguard.analyze.compare import _cliff_concurrency as _existing_cliff_concurrency
from inferguard.analyze.operator_brief import (
    _failure_cliff as _existing_failure_cliff,
)
from inferguard.analyze.operator_brief import (
    _ttft_cliff as _existing_ttft_cliff,
)

from .types import CAPACITY_CLIFF_NAMES, Cliff

MIN_SWEEP_POINTS = 4
KV_SATURATION_THRESHOLD = 0.95
THROUGHPUT_PLATEAU_DELTA = 0.05
THROUGHPUT_FUTURE_INCREASE = 0.10
E2E_JUMP_FACTOR = 2.0
DECODE_COLLAPSE_FACTOR = 2.0


@dataclass(frozen=True)
class SweepCell:
    """One completed or partially completed job cell in a sweep."""

    job_id: str
    job_dir: Path
    rel_dir: str
    operator_profile: dict[str, Any] = field(default_factory=dict)
    request_summary: dict[str, Any] = field(default_factory=dict)
    metrics_summary: dict[str, Any] = field(default_factory=dict)
    failure_classification: dict[str, Any] = field(default_factory=dict)
    bottleneck_diagnosis: dict[str, Any] = field(default_factory=dict)
    paths: dict[str, str] = field(default_factory=dict)

    @property
    def complete(self) -> bool:
        return bool(self.request_summary) and bool(self.metrics_summary)

    @property
    def concurrency(self) -> int | None:
        return _int_first(
            self.request_summary.get("concurrency"),
            self.operator_profile.get("concurrency"),
            self.operator_profile.get("target_concurrency"),
            self.operator_profile.get("max_concurrency"),
        )

    @property
    def context_length(self) -> int | None:
        return _int_first(
            self.request_summary.get("context_length"),
            self.request_summary.get("context_length_tokens"),
            self.operator_profile.get("context_length"),
            self.operator_profile.get("context_length_tokens"),
            self.operator_profile.get("prompt_tokens"),
            self.operator_profile.get("max_model_len"),
        )

    @property
    def success_rate(self) -> float | None:
        direct = _num(self.request_summary.get("success_rate"))
        if direct is not None:
            return direct
        total = _num(self.request_summary.get("request_count"))
        success = _num(self.request_summary.get("success_count"))
        if total is None or success is None or total <= 0:
            return None
        return success / total

    @property
    def p99_ttft_ms(self) -> float | None:
        return _percentile(self.request_summary.get("ttft_ms"), "p99")

    @property
    def p99_e2e_ms(self) -> float | None:
        return _percentile(self.request_summary.get("e2e_latency_ms"), "p99")

    @property
    def p99_tpot_ms(self) -> float | None:
        return _percentile(self.request_summary.get("tpot_ms"), "p99")

    @property
    def throughput_tokens_per_sec(self) -> float | None:
        direct = _num(self.request_summary.get("tokens_per_sec_aggregate"))
        if direct is not None:
            return direct
        return _percentile(self.request_summary.get("decode_tokens_per_sec"), "p50")

    @property
    def kv_usage_p95(self) -> float | None:
        kv_cache = _dict(self.metrics_summary.get("kv_cache"))
        for key in ("usage_fraction", "kv_cache_usage_perc", "cache_usage_fraction", "cache_usage_perc"):
            value = _percentile(kv_cache.get(key), "p95")
            if value is not None:
                return value
        return _percentile(self.metrics_summary.get("kv_cache_usage_perc"), "p95")

    @property
    def queue_waiting(self) -> float | None:
        queue = _dict(self.metrics_summary.get("queue"))
        return _percentile(queue.get("requests_waiting"), "p95") or _percentile(
            queue.get("num_requests_waiting"),
            "p95",
        )

    @property
    def queue_running(self) -> float | None:
        queue = _dict(self.metrics_summary.get("queue"))
        return _percentile(queue.get("requests_running"), "p95") or _percentile(
            queue.get("num_requests_running"),
            "p95",
        )

    @property
    def decode_parallelism(self) -> float | None:
        return _num(
            self.operator_profile.get("decode_parallelism")
            or self.operator_profile.get("decode_parallelism_size")
            or self.operator_profile.get("data_parallel_size")
        )

    def is_successful(self, success_rate_floor: float) -> bool:
        rate = self.success_rate
        return rate is not None and rate >= success_rate_floor and not self.is_oom

    @property
    def is_oom(self) -> bool:
        top_class = str(self.failure_classification.get("top_class") or "").lower()
        if top_class == "oom_hbm_exhaustion":
            return True
        for failure in self.failure_classification.get("failures") or []:
            if isinstance(failure, dict) and str(failure.get("class") or "").lower() == "oom_hbm_exhaustion":
                return True
        return False

    @property
    def is_queue_bound(self) -> bool:
        verdict = str(self.bottleneck_diagnosis.get("verdict") or "").lower()
        top_class = str(self.failure_classification.get("top_class") or "").lower()
        return verdict == "queue_bound" or top_class == "queue_bound"

    @property
    def is_decode_bound(self) -> bool:
        return str(self.bottleneck_diagnosis.get("verdict") or "").lower() == "decode_bound"


def detect_all_cliffs(
    cells: list[SweepCell],
    *,
    names: tuple[str, ...] = CAPACITY_CLIFF_NAMES,
    ttft_p99_floor_ms: float = 1000.0,
    success_rate_floor: float = 0.95,
) -> tuple[Cliff, ...]:
    detectors: dict[str, Callable[..., Cliff]] = {
        "max_context_before_oom": detect_max_context_before_oom,
        "max_concurrency_before_p99_cliff": detect_max_concurrency_before_p99_cliff,
        "throughput_plateau": detect_throughput_plateau,
        "kv_saturation_point": detect_kv_saturation_point,
        "queue_explosion_point": detect_queue_explosion_point,
        "decode_collapse_point": detect_decode_collapse_point,
    }
    return tuple(
        detectors[name](
            cells,
            ttft_p99_floor_ms=ttft_p99_floor_ms,
            success_rate_floor=success_rate_floor,
        )
        for name in names
    )


def detect_max_concurrency_before_p99_cliff(
    cells: list[SweepCell],
    *,
    ttft_p99_floor_ms: float,
    success_rate_floor: float,
) -> Cliff:
    name = "max_concurrency_before_p99_cliff"
    ordered = _by_concurrency(_complete(cells))
    curve = _curve(ordered, "concurrency", lambda cell: cell.p99_ttft_ms, "request_profile.ttft_ms.p99")
    if len(ordered) < MIN_SWEEP_POINTS:
        return _not_proven(name, ordered, curve, "add at least four completed concurrency cells")

    _legacy_capacity_checks(ordered)
    for prev, curr in zip(ordered, ordered[1:], strict=False):
        if curr.is_oom and prev.is_successful(success_rate_floor):
            return _measured(
                name,
                prev.concurrency,
                [prev, curr],
                curve,
                (
                    f"OOM cliff: {curr.job_id} at concurrency={curr.concurrency} reported "
                    "oom_hbm_exhaustion; previous completed cell succeeded."
                ),
                (
                    f"narrow the sweep between c={prev.concurrency} and c={curr.concurrency} "
                    "to localize the OOM threshold"
                ),
                confidence=0.92,
            )
        if (
            prev.p99_ttft_ms is not None
            and curr.p99_ttft_ms is not None
            and prev.p99_ttft_ms <= ttft_p99_floor_ms
            and curr.p99_ttft_ms > ttft_p99_floor_ms
        ):
            return _measured(
                name,
                prev.concurrency,
                [prev, curr],
                curve,
                (
                    f"p99 TTFT crossed the {ttft_p99_floor_ms:g} ms floor between "
                    f"c={prev.concurrency} ({prev.p99_ttft_ms:g} ms) and "
                    f"c={curr.concurrency} ({curr.p99_ttft_ms:g} ms)."
                ),
                (
                    f"narrow the sweep between c={prev.concurrency} and c={curr.concurrency} "
                    "to localize the p99 TTFT cliff"
                ),
                confidence=0.9,
            )
    return Cliff(
        name=name,
        value=None,
        claim_status="not_proven",
        evidence_paths=_evidence_paths(ordered),
        evidence_jobs=_evidence_jobs(ordered),
        supporting_curve=tuple(curve),
        reasoning=f"no p99 TTFT crossing above {ttft_p99_floor_ms:g} ms and no OOM transition observed",
        confidence=0.35,
        recommended_next_run=_extend_concurrency_run(ordered),
    )


def detect_max_context_before_oom(
    cells: list[SweepCell],
    *,
    ttft_p99_floor_ms: float,
    success_rate_floor: float,
) -> Cliff:
    del ttft_p99_floor_ms
    name = "max_context_before_oom"
    ordered = _by_context(_complete(cells))
    curve = _curve(ordered, "context_length", lambda cell: 1.0 if cell.is_oom else 0.0, "oom_observed")
    distinct_contexts = {cell.context_length for cell in ordered if cell.context_length is not None}
    if len(ordered) < MIN_SWEEP_POINTS or len(distinct_contexts) < MIN_SWEEP_POINTS:
        return _not_proven(name, ordered, curve, "add at least four completed context-length cells")
    for prev, curr in zip(ordered, ordered[1:], strict=False):
        if curr.is_oom and prev.is_successful(success_rate_floor):
            return _measured(
                name,
                prev.context_length,
                [prev, curr],
                curve,
                (
                    f"context OOM cliff: {curr.job_id} at context={curr.context_length} "
                    "reported oom_hbm_exhaustion; previous context completed successfully."
                ),
                (
                    f"narrow the sweep between context={prev.context_length} and "
                    f"context={curr.context_length} to localize the HBM OOM threshold"
                ),
                confidence=0.92,
            )
    return Cliff(
        name=name,
        value=None,
        claim_status="not_proven",
        evidence_paths=_evidence_paths(ordered),
        evidence_jobs=_evidence_jobs(ordered),
        supporting_curve=tuple(curve),
        reasoning="no adjacent context-length transition from success to oom_hbm_exhaustion was observed",
        confidence=0.35,
        recommended_next_run=_extend_context_run(ordered),
    )


def detect_throughput_plateau(
    cells: list[SweepCell],
    *,
    ttft_p99_floor_ms: float,
    success_rate_floor: float,
) -> Cliff:
    del ttft_p99_floor_ms, success_rate_floor
    name = "throughput_plateau"
    ordered = _by_concurrency(_complete(cells))
    curve = _curve(
        ordered,
        "concurrency",
        lambda cell: cell.throughput_tokens_per_sec,
        "request_profile.tokens_per_sec_aggregate",
    )
    with_throughput = [cell for cell in ordered if cell.throughput_tokens_per_sec is not None]
    if len(with_throughput) < MIN_SWEEP_POINTS:
        return _not_proven(name, with_throughput, curve, "add at least four throughput-bearing cells")
    for idx in range(0, len(with_throughput) - 2):
        trio = with_throughput[idx : idx + 3]
        values = [cell.throughput_tokens_per_sec for cell in trio]
        if not all(value is not None and value > 0 for value in values):
            continue
        deltas = [
            abs(float(values[pos + 1]) - float(values[pos])) / float(values[pos])
            for pos in range(0, 2)
        ]
        plateau_mean = sum(float(value) for value in values) / len(values)
        future = with_throughput[idx + 3 :]
        no_future_gain = all(
            (float(cell.throughput_tokens_per_sec or 0.0) - plateau_mean) / plateau_mean
            < THROUGHPUT_FUTURE_INCREASE
            for cell in future
        )
        if all(delta < THROUGHPUT_PLATEAU_DELTA for delta in deltas) and no_future_gain:
            return _measured(
                name,
                round(plateau_mean, 3),
                trio + future,
                curve,
                (
                    "three consecutive concurrency points changed by <5% throughput and "
                    "no later point improved by >=10%"
                ),
                (
                    f"run one focused point between c={trio[0].concurrency} and "
                    f"c={trio[-1].concurrency} to confirm the plateau knee"
                ),
                confidence=0.86,
            )
    peak = max((cell.throughput_tokens_per_sec or 0.0) for cell in with_throughput)
    return Cliff(
        name=name,
        value=round(peak, 3),
        claim_status="inferred",
        evidence_paths=_evidence_paths(with_throughput),
        evidence_jobs=_evidence_jobs(with_throughput),
        supporting_curve=tuple(curve),
        reasoning="no three-point <5% plateau observed; value is the best observed throughput, not a fixed cliff",
        confidence=0.45,
        recommended_next_run="extend concurrency above the current peak and add intermediate cells near the flattening region",
    )


def detect_kv_saturation_point(
    cells: list[SweepCell],
    *,
    ttft_p99_floor_ms: float,
    success_rate_floor: float,
) -> Cliff:
    del ttft_p99_floor_ms, success_rate_floor
    name = "kv_saturation_point"
    ordered = _by_concurrency(_complete(cells))
    curve = _curve(ordered, "concurrency", lambda cell: cell.kv_usage_p95, "metrics_summary.kv_cache.usage_fraction.p95")
    if len(ordered) < MIN_SWEEP_POINTS:
        return _not_proven(name, ordered, curve, "add at least four completed KV-cache cells")
    for idx, curr in enumerate(ordered):
        usage = curr.kv_usage_p95
        if usage is None or usage < KV_SATURATION_THRESHOLD:
            continue
        prev_jump = (
            idx > 0
            and ordered[idx - 1].p99_e2e_ms is not None
            and curr.p99_e2e_ms is not None
            and curr.p99_e2e_ms > ordered[idx - 1].p99_e2e_ms * E2E_JUMP_FACTOR
        )
        next_jump = (
            idx + 1 < len(ordered)
            and curr.p99_e2e_ms is not None
            and ordered[idx + 1].p99_e2e_ms is not None
            and ordered[idx + 1].p99_e2e_ms > curr.p99_e2e_ms * E2E_JUMP_FACTOR
        )
        if prev_jump or next_jump:
            evidence_cells = [cell for cell in ordered[max(idx - 1, 0) : min(idx + 2, len(ordered))]]
            return _measured(
                name,
                curr.concurrency,
                evidence_cells,
                curve,
                (
                    f"KV usage p95={usage:.3f} at c={curr.concurrency} with >2x adjacent "
                    "E2E p99 latency jump."
                ),
                (
                    f"narrow the sweep around c={curr.concurrency} and add KV timeline samples "
                    "to confirm the saturation boundary"
                ),
                confidence=0.88,
            )
    return Cliff(
        name=name,
        value=None,
        claim_status="not_proven",
        evidence_paths=_evidence_paths(ordered),
        evidence_jobs=_evidence_jobs(ordered),
        supporting_curve=tuple(curve),
        reasoning="no cell reached kv_cache.usage_fraction.p95 >= 0.95 with an adjacent >2x E2E p99 jump",
        confidence=0.35,
        recommended_next_run="increase context length or concurrency until KV usage p95 approaches 0.95, then add adjacent cells",
    )


def detect_queue_explosion_point(
    cells: list[SweepCell],
    *,
    ttft_p99_floor_ms: float,
    success_rate_floor: float,
) -> Cliff:
    del ttft_p99_floor_ms, success_rate_floor
    name = "queue_explosion_point"
    ordered = _by_concurrency(_complete(cells))
    curve = _curve(ordered, "concurrency", lambda cell: cell.queue_waiting, "metrics_summary.queue.requests_waiting")
    if len(ordered) < MIN_SWEEP_POINTS:
        return _not_proven(name, ordered, curve, "add at least four completed queue-metric cells")
    for prev, curr in zip(ordered, ordered[1:], strict=False):
        if curr.is_queue_bound:
            return _measured(
                name,
                curr.concurrency,
                [prev, curr],
                curve,
                f"{curr.job_id} emitted queue_bound diagnosis at concurrency={curr.concurrency}.",
                (
                    f"narrow the sweep between c={prev.concurrency} and c={curr.concurrency} "
                    "and collect queue wait histograms"
                ),
                confidence=0.86,
            )
        prev_wait = prev.queue_waiting or 0.0
        curr_wait = curr.queue_waiting or 0.0
        prev_e2e = prev.p99_e2e_ms
        curr_e2e = curr.p99_e2e_ms
        if curr_wait >= max(4.0, prev_wait * 2.0 + 1.0) and (
            prev_e2e is None or curr_e2e is None or curr_e2e > prev_e2e * E2E_JUMP_FACTOR
        ):
            return _measured(
                name,
                curr.concurrency,
                [prev, curr],
                curve,
                (
                    f"queue waiting rose from {prev_wait:g} to {curr_wait:g} at "
                    f"concurrency={curr.concurrency}."
                ),
                (
                    f"narrow the sweep between c={prev.concurrency} and c={curr.concurrency} "
                    "and test a queue budget or admission-control run"
                ),
                confidence=0.82,
            )
    return Cliff(
        name=name,
        value=None,
        claim_status="not_proven",
        evidence_paths=_evidence_paths(ordered),
        evidence_jobs=_evidence_jobs(ordered),
        supporting_curve=tuple(curve),
        reasoning="no queue_bound diagnosis or queue-waiting explosion was observed",
        confidence=0.35,
        recommended_next_run="extend concurrency and preserve queue metrics for each cell",
    )


def detect_decode_collapse_point(
    cells: list[SweepCell],
    *,
    ttft_p99_floor_ms: float,
    success_rate_floor: float,
) -> Cliff:
    del ttft_p99_floor_ms, success_rate_floor
    name = "decode_collapse_point"
    ordered = _decode_order(_complete(cells))
    curve_x = "decode_parallelism" if all(cell.decode_parallelism is not None for cell in ordered) else "concurrency"
    curve = _curve(ordered, curve_x, lambda cell: cell.p99_tpot_ms, "request_profile.tpot_ms.p99")
    with_tpot = [cell for cell in ordered if cell.p99_tpot_ms is not None]
    if len(with_tpot) < MIN_SWEEP_POINTS:
        return _not_proven(name, with_tpot, curve, "add at least four completed TPOT cells")
    values = [float(cell.p99_tpot_ms or 0.0) for cell in with_tpot]
    monotonic = all(values[idx + 1] > values[idx] for idx in range(0, len(values) - 1))
    if monotonic and values[-1] >= values[0] * DECODE_COLLAPSE_FACTOR:
        threshold = values[0] * DECODE_COLLAPSE_FACTOR
        collapse = next((cell for cell in with_tpot if float(cell.p99_tpot_ms or 0.0) >= threshold), with_tpot[-1])
        return _measured(
            name,
            collapse.concurrency,
            with_tpot,
            curve,
            "TPOT increased monotonically across the decode sweep, indicating decode collapse.",
            (
                f"narrow the sweep around c={collapse.concurrency} and test lower decode "
                "batching or more decode parallelism"
            ),
            confidence=0.84,
        )
    return Cliff(
        name=name,
        value=None,
        claim_status="not_proven",
        evidence_paths=_evidence_paths(with_tpot),
        evidence_jobs=_evidence_jobs(with_tpot),
        supporting_curve=tuple(curve),
        reasoning="TPOT did not increase monotonically enough to prove decode collapse",
        confidence=0.35,
        recommended_next_run="add adjacent TPOT-bearing cells while varying concurrency or decode parallelism",
    )


def summary_from_cliffs(cliffs: tuple[Cliff, ...]) -> dict[str, Any]:
    by_name = {cliff.name: cliff for cliff in cliffs}
    return {
        "max_concurrency": _value(by_name.get("max_concurrency_before_p99_cliff")),
        "max_context": _value(by_name.get("max_context_before_oom")),
        "throughput_plateau_tokens_per_sec": _value(by_name.get("throughput_plateau")),
        "kv_saturation_concurrency": _value(by_name.get("kv_saturation_point")),
        "decode_collapse_concurrency": _value(by_name.get("decode_collapse_point")),
        "queue_explosion_concurrency": _value(by_name.get("queue_explosion_point")),
        "cliffs_found": sum(1 for cliff in cliffs if cliff.claim_status == "measured"),
    }


def _legacy_capacity_checks(cells: list[SweepCell]) -> dict[str, Any]:
    rows = []
    operator_cells = []
    for cell in cells:
        if cell.concurrency is None:
            continue
        rows.append(
            {
                "concurrency": cell.concurrency,
                "success": cell.success_rate is not None and cell.success_rate >= 0.95,
                "ttft_seconds": None if cell.p99_ttft_ms is None else cell.p99_ttft_ms / 1000.0,
            }
        )
        operator_cells.append(
            {
                "cell_id": cell.job_id,
                "config": {"concurrency": cell.concurrency},
                "completion": {"success_rate": cell.success_rate},
                "metrics": {"p99_ttft": None if cell.p99_ttft_ms is None else cell.p99_ttft_ms / 1000.0},
            }
        )
    return {
        "compare_cliff_concurrency": _existing_cliff_concurrency(rows),
        "operator_ttft_cliff": _existing_ttft_cliff("capacity", operator_cells),
        "operator_failure_cliff": _existing_failure_cliff("capacity", operator_cells),
    }


def _complete(cells: list[SweepCell]) -> list[SweepCell]:
    return [cell for cell in cells if cell.complete]


def _by_concurrency(cells: list[SweepCell]) -> list[SweepCell]:
    return sorted(
        [cell for cell in cells if cell.concurrency is not None],
        key=lambda cell: (int(cell.concurrency or 0), cell.context_length or 0, cell.job_id),
    )


def _by_context(cells: list[SweepCell]) -> list[SweepCell]:
    return sorted(
        [cell for cell in cells if cell.context_length is not None],
        key=lambda cell: (int(cell.context_length or 0), cell.concurrency or 0, cell.job_id),
    )


def _decode_order(cells: list[SweepCell]) -> list[SweepCell]:
    with_tpot = [cell for cell in cells if cell.p99_tpot_ms is not None]
    if with_tpot and all(cell.decode_parallelism is not None for cell in with_tpot):
        return sorted(with_tpot, key=lambda cell: (-(cell.decode_parallelism or 0.0), cell.job_id))
    return _by_concurrency(with_tpot)


def _curve(
    cells: list[SweepCell],
    x_axis: str,
    y_getter: Callable[[SweepCell], float | int | None],
    metric: str,
) -> list[dict[str, Any]]:
    points: list[dict[str, Any]] = []
    for cell in cells:
        x_value = cell.context_length if x_axis == "context_length" else cell.concurrency
        if x_axis == "decode_parallelism":
            x_value = cell.decode_parallelism
        y_value = y_getter(cell)
        if x_value is None or y_value is None:
            continue
        points.append({"x": x_value, "y": y_value, "metric": metric, "job_id": cell.job_id})
    return points


def _measured(
    name: str,
    value: int | float | None,
    evidence_cells: list[SweepCell],
    curve: list[dict[str, Any]],
    reasoning: str,
    recommended_next_run: str,
    *,
    confidence: float,
) -> Cliff:
    return Cliff(
        name=name,
        value=value,
        claim_status="measured",
        evidence_paths=_evidence_paths(evidence_cells),
        evidence_jobs=_evidence_jobs(evidence_cells),
        supporting_curve=tuple(curve),
        reasoning=reasoning,
        confidence=confidence,
        recommended_next_run=recommended_next_run,
    )


def _not_proven(
    name: str,
    cells: list[SweepCell],
    curve: list[dict[str, Any]],
    reason: str,
) -> Cliff:
    return Cliff(
        name=name,
        value=None,
        claim_status="not_proven",
        evidence_paths=_evidence_paths(cells),
        evidence_jobs=_evidence_jobs(cells),
        supporting_curve=tuple(curve),
        reasoning=f"not_enough_evidence: {reason}",
        confidence=0.0,
        recommended_next_run="complete at least four adjacent sweep cells before fixing this cliff",
    )


def _evidence_paths(cells: list[SweepCell]) -> tuple[str, ...]:
    paths: list[str] = []
    for cell in cells:
        for key in ("request_summary", "metrics_summary", "failure_classification", "bottleneck_diagnosis", "operator_profile"):
            path = cell.paths.get(key)
            if path:
                paths.append(path)
    return tuple(_unique(paths))


def _evidence_jobs(cells: list[SweepCell]) -> tuple[str, ...]:
    return tuple(_unique([cell.job_id for cell in cells if cell.job_id]))


def _unique(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        out.append(item)
    return out


def _extend_concurrency_run(cells: list[SweepCell]) -> str:
    max_conc = max((cell.concurrency or 0 for cell in cells), default=0)
    if max_conc <= 0:
        return "run a four-point concurrency sweep with request and metrics summaries"
    return f"extend concurrency above c={max_conc} and keep adjacent cells near the first p99 or failure transition"


def _extend_context_run(cells: list[SweepCell]) -> str:
    max_context = max((cell.context_length or 0 for cell in cells), default=0)
    if max_context <= 0:
        return "run a four-point context-length sweep with request and metrics summaries"
    return f"extend context length above {max_context} tokens and keep adjacent cells near the first OOM transition"


def _value(cliff: Cliff | None) -> int | float | None:
    if cliff is None or cliff.claim_status != "measured":
        return None
    return cliff.value


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _percentile(value: Any, preferred: str) -> float | None:
    if isinstance(value, dict):
        for key in (preferred, "p95", "p50", "value", "max"):
            result = _num(value.get(key))
            if result is not None:
                return result
        return None
    return _num(value)


def _int_first(*values: Any) -> int | None:
    for value in values:
        number = _num(value)
        if number is not None:
            return int(number)
    return None


def _num(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


__all__ = [
    "MIN_SWEEP_POINTS",
    "SweepCell",
    "detect_all_cliffs",
    "detect_decode_collapse_point",
    "detect_kv_saturation_point",
    "detect_max_concurrency_before_p99_cliff",
    "detect_max_context_before_oom",
    "detect_queue_explosion_point",
    "detect_throughput_plateau",
    "summary_from_cliffs",
]

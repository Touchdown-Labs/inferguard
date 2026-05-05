"""Correlate vLLM aggregate metrics with per-GPU DCGM exporter samples."""

from __future__ import annotations

import argparse
import json
import logging
import math
import time
from collections import defaultdict
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from statistics import median
from typing import Any

import httpx
from prometheus_client.parser import text_string_to_metric_families

SCHEMA_VERSION = "dcgm-correlated/v1"
DEFAULT_VLLM_METRICS_URL = "http://localhost:8000/metrics"
DEFAULT_DCGM_METRICS_URL = "http://localhost:9400/metrics"
DEFAULT_DURATION_SECONDS = 600
DEFAULT_INTERVAL_SECONDS = 5
OUTPUT_FILENAME = "dcgm-correlated-v1.jsonl"
PARTIAL_DEGRADATION_MIN_CONSECUTIVE_SNAPSHOTS = 2
PARTIAL_DEGRADATION_SM_ACTIVITY_RATIO = 0.70
PARTIAL_DEGRADATION_TEMP_DELTA_C = 15.0

LOGGER = logging.getLogger(__name__)

DCGM_METRIC_FIELDS = {
    "DCGM_FI_DEV_SM_CLOCK": "dcgm_sm_clock",
    "DCGM_FI_DEV_MEM_CLOCK": "dcgm_mem_clock",
    "DCGM_FI_DEV_GPU_TEMP": "dcgm_gpu_temp",
    "DCGM_FI_DEV_MEMORY_TEMP": "dcgm_mem_temp",
    "DCGM_FI_DEV_MEM_TEMP": "dcgm_mem_temp",
    "DCGM_FI_DEV_POWER_USAGE": "dcgm_power_usage",
    "DCGM_FI_DEV_TOTAL_ENERGY_CONSUMPTION": "dcgm_total_energy_consumption",
    "DCGM_FI_DEV_GPU_UTIL": "dcgm_gpu_util",
    "DCGM_FI_DEV_MEM_COPY_UTIL": "dcgm_mem_copy_util",
    "DCGM_FI_DEV_FB_FREE": "dcgm_fb_free",
    "DCGM_FI_DEV_FB_USED": "dcgm_fb_used",
    "DCGM_FI_DEV_XID_ERRORS": "dcgm_xid_errors",
    "DCGM_FI_DEV_ECC_SBE_VOL_TOTAL": "dcgm_ecc_sbe_volatile_total",
    "DCGM_FI_DEV_ECC_DBE_VOL_TOTAL": "dcgm_ecc_dbe_volatile_total",
    "DCGM_FI_DEV_ECC_SBE_AGG_TOTAL": "dcgm_ecc_sbe_aggregate_total",
    "DCGM_FI_DEV_ECC_DBE_AGG_TOTAL": "dcgm_ecc_dbe_aggregate_total",
    "DCGM_FI_DEV_NVLINK_BANDWIDTH_TOTAL": "dcgm_nvlink_bandwidth_total",
}
DCGM_FIELDS = tuple(DCGM_METRIC_FIELDS.values())
VLLM_FIELDS = (
    "vllm_num_requests_running",
    "vllm_num_requests_waiting",
    "vllm_kv_cache_usage_perc",
    "vllm_num_preemptions_total",
    "vllm_e2e_request_latency_seconds_p99",
)

VLLM_DIRECT_FIELDS = {
    "vllm_num_requests_running": "vllm_num_requests_running",
    "vllm_num_requests_waiting": "vllm_num_requests_waiting",
    "vllm_kv_cache_usage_perc": "vllm_kv_cache_usage_perc",
    "vllm_num_preemptions_total": "vllm_num_preemptions_total",
}
VLLM_SUM_FIELDS = {
    "vllm_num_requests_running",
    "vllm_num_requests_waiting",
    "vllm_num_preemptions_total",
}
VLLM_MAX_FIELDS = {
    "vllm_kv_cache_usage_perc",
    "vllm_e2e_request_latency_seconds_p99",
}


@dataclass(frozen=True)
class PrometheusSample:
    """A normalized Prometheus exposition sample."""

    name: str
    labels: Mapping[str, str]
    value: float


class DcgmCorrelator:
    """Pull vLLM and DCGM Prometheus endpoints and emit aligned JSONL rows.

    vLLM's public metrics are aggregate per engine today; DCGM's exporter rows
    are per GPU and include both ``gpu`` index and ``UUID`` labels. The
    correlator therefore aligns both scrapes to the same fixed-width time
    window, keys DCGM rows by ``(timestamp_window, gpu_uuid)``, and broadcasts
    the vLLM aggregate fields onto every GPU row for that window.
    """

    def __init__(
        self,
        *,
        vllm_metrics_url: str = DEFAULT_VLLM_METRICS_URL,
        dcgm_metrics_url: str = DEFAULT_DCGM_METRICS_URL,
        output_dir: Path | str,
        duration_seconds: int | float = DEFAULT_DURATION_SECONDS,
        interval_seconds: int | float = DEFAULT_INTERVAL_SECONDS,
        http_client: httpx.Client | None = None,
        timeout_seconds: float = 5.0,
        time_fn: Callable[[], float] | None = None,
        sleep_fn: Callable[[float], None] | None = None,
        logger: logging.Logger | None = None,
    ) -> None:
        if interval_seconds <= 0:
            raise ValueError("interval_seconds must be positive")
        if duration_seconds < 0:
            raise ValueError("duration_seconds must be non-negative")
        self.vllm_metrics_url = vllm_metrics_url
        self.dcgm_metrics_url = dcgm_metrics_url
        self.output_dir = Path(output_dir)
        self.duration_seconds = float(duration_seconds)
        self.interval_seconds = float(interval_seconds)
        self.timeout_seconds = timeout_seconds
        self._client = http_client
        self._owns_client = http_client is None
        self._time_fn = time_fn or time.time
        self._sleep_fn = sleep_fn or time.sleep
        self.logger = logger or LOGGER

    @property
    def output_path(self) -> Path:
        return self.output_dir / OUTPUT_FILENAME

    def run(self) -> Path:
        """Sample for the configured duration and write ``dcgm-correlated/v1`` JSONL."""

        self.output_dir.mkdir(parents=True, exist_ok=True)
        sample_count = max(1, math.ceil(self.duration_seconds / self.interval_seconds))
        client = self._client or httpx.Client(timeout=self.timeout_seconds)
        self._client = client
        try:
            with self.output_path.open("w", encoding="utf-8") as handle:
                for index in range(sample_count):
                    started = self._time_fn()
                    for row in self.collect_once(observed_at=started):
                        handle.write(json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n")
                    if index < sample_count - 1:
                        elapsed = max(0.0, self._time_fn() - started)
                        self._sleep_fn(max(0.0, self.interval_seconds - elapsed))
        finally:
            if self._owns_client:
                client.close()
                self._client = None
        return self.output_path

    def collect_once(self, *, observed_at: float | None = None) -> list[dict[str, Any]]:
        """Collect one aligned scrape from both endpoints and return output rows."""

        timestamp = self._align_timestamp(observed_at if observed_at is not None else self._time_fn())
        timestamp_iso = _isoformat(timestamp)
        dcgm_samples = parse_prometheus_text(self._fetch_text(self.dcgm_metrics_url, source="DCGM"))
        vllm_samples = parse_prometheus_text(self._fetch_text(self.vllm_metrics_url, source="vLLM"))
        dcgm_rows = parse_dcgm_samples(dcgm_samples)
        vllm_fields = parse_vllm_samples(vllm_samples)

        if vllm_samples:
            self.logger.warning("vLLM metrics are aggregate per-engine; correlation joins on time only")
        else:
            self.logger.warning("empty vLLM scrape; emitting rows with null vLLM fields")
        if not dcgm_rows:
            self.logger.warning("empty DCGM scrape; emitting null dcgm-correlated/v1 row")

        if not dcgm_rows:
            return [_build_row(timestamp_iso, int(self.interval_seconds), None, vllm_fields)]
        return [
            _build_row(timestamp_iso, int(self.interval_seconds), dcgm_row, vllm_fields)
            for dcgm_row in dcgm_rows
        ]

    def _fetch_text(self, url: str, *, source: str) -> str:
        client = self._client or httpx.Client(timeout=self.timeout_seconds)
        close_client = self._client is None
        try:
            response = client.get(url, timeout=self.timeout_seconds)
            response.raise_for_status()
        except Exception as exc:  # pragma: no cover - exception type depends on transport
            self.logger.warning("empty %s scrape from %s: %s", source, url, exc)
            return ""
        finally:
            if close_client:
                client.close()
        text = response.text
        if not text.strip():
            self.logger.warning("empty %s scrape from %s", source, url)
            return ""
        return text

    def _align_timestamp(self, timestamp: float) -> float:
        return align_timestamp(timestamp, self.interval_seconds)


class DcgmCorrelatorError(ValueError):
    """Raised for invalid dcgm-correlated/v1 inputs."""


def align_timestamp(timestamp: float, window_seconds: int | float = DEFAULT_INTERVAL_SECONDS) -> float:
    """Round a UNIX timestamp down to the nearest scrape window boundary."""

    if window_seconds <= 0:
        raise DcgmCorrelatorError("window_seconds must be positive")
    return math.floor(timestamp / window_seconds) * window_seconds


def parse_prometheus_text(text: str) -> list[PrometheusSample]:
    """Parse Prometheus exposition text into finite numeric samples.

    The prometheus-client parser handles both colon names (``vllm:*``) and
    underscore names (``vllm_*``). Invalid samples are skipped so a partially
    malformed scrape still produces a null-tolerant correlation row.
    """

    if not text.strip():
        return []
    samples: list[PrometheusSample] = []
    try:
        families = text_string_to_metric_families(text)
        for family in families:
            for sample in family.samples:
                value = float(sample.value)
                if math.isfinite(value):
                    samples.append(
                        PrometheusSample(
                            name=str(sample.name),
                            labels={str(key): str(value) for key, value in sample.labels.items()},
                            value=value,
                        )
                    )
    except (OSError, ValueError):
        LOGGER.warning("failed to parse Prometheus text; treating scrape as empty", exc_info=True)
        return []
    return samples


def parse_dcgm_samples(samples: Iterable[PrometheusSample]) -> list[dict[str, Any]]:
    """Return one normalized DCGM row per GPU UUID."""

    rows: dict[tuple[str, int | None], dict[str, Any]] = {}
    for sample in samples:
        field = DCGM_METRIC_FIELDS.get(sample.name)
        if field is None:
            continue
        gpu_uuid = _gpu_uuid(sample.labels)
        gpu_index = _gpu_index(sample.labels.get("gpu"))
        if gpu_uuid is None:
            if gpu_index is None:
                continue
            gpu_uuid = f"gpu-index-{gpu_index}"
        key = (gpu_uuid, gpu_index)
        row = rows.setdefault(
            key,
            {
                "gpu_uuid": gpu_uuid,
                "gpu_index": gpu_index,
                **{name: None for name in DCGM_FIELDS},
            },
        )
        if field == "dcgm_nvlink_bandwidth_total":
            row[field] = float(row[field] or 0.0) + sample.value
        else:
            row[field] = sample.value
    return sorted(rows.values(), key=lambda row: (row["gpu_index"] is None, row["gpu_index"] or 0, row["gpu_uuid"]))


def parse_vllm_samples(samples: Iterable[PrometheusSample]) -> dict[str, float | None]:
    """Return aggregate vLLM fields for broadcast onto every DCGM row."""

    fields: dict[str, float | None] = {name: None for name in VLLM_FIELDS}
    histogram_buckets: dict[tuple[tuple[str, str], ...], dict[float, float]] = defaultdict(dict)
    for sample in samples:
        normalized = _normalize_metric_name(sample.name)
        direct_field = VLLM_DIRECT_FIELDS.get(normalized)
        if direct_field is not None:
            _aggregate_vllm_field(fields, direct_field, sample.value)
            continue
        if normalized == "vllm_e2e_request_latency_seconds":
            quantile = sample.labels.get("quantile")
            if quantile in {None, "0.99", ".99", "99", "p99", "P99"}:
                _aggregate_vllm_field(fields, "vllm_e2e_request_latency_seconds_p99", sample.value)
            continue
        if normalized == "vllm_e2e_request_latency_seconds_bucket":
            le = _parse_bucket_bound(sample.labels.get("le"))
            if le is None:
                continue
            labels_key = tuple(sorted((key, value) for key, value in sample.labels.items() if key != "le"))
            histogram_buckets[labels_key][le] = sample.value

    if fields["vllm_e2e_request_latency_seconds_p99"] is None:
        for buckets in histogram_buckets.values():
            p99 = _histogram_quantile(0.99, buckets)
            if p99 is not None:
                _aggregate_vllm_field(fields, "vllm_e2e_request_latency_seconds_p99", p99)
    return fields


def detect_partial_gpu_degradation(
    rows: Iterable[Mapping[str, Any]],
    *,
    min_consecutive_snapshots: int = PARTIAL_DEGRADATION_MIN_CONSECUTIVE_SNAPSHOTS,
    sm_activity_ratio: float = PARTIAL_DEGRADATION_SM_ACTIVITY_RATIO,
    temp_delta_c: float = PARTIAL_DEGRADATION_TEMP_DELTA_C,
) -> list[dict[str, Any]]:
    """Detect S-09 partial GPU degradation from ``dcgm-correlated/v1`` rows.

    A GPU is flagged when either:
    - its SM activity proxy (DCGM GPU util) is below ``sm_activity_ratio`` of
      the cluster median for ``min_consecutive_snapshots`` aligned windows;
    - its temperature is materially above the cluster median for the same
      window count; or
    - any ECC/XID error counter is non-zero.
    """

    if min_consecutive_snapshots <= 0:
        raise DcgmCorrelatorError("min_consecutive_snapshots must be positive")
    snapshots: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for row in rows:
        if row.get("gpu_uuid") is None and row.get("gpu_index") is None:
            continue
        snapshots[str(row.get("timestamp") or row.get("observed_at") or "__single_snapshot__")].append(row)

    findings: list[dict[str, Any]] = []
    consecutive: dict[tuple[str, str], int] = {}
    emitted: set[tuple[str, str]] = set()
    for timestamp in sorted(snapshots):
        gpu_rows = snapshots[timestamp]
        util_values = [_number(row.get("dcgm_gpu_util")) for row in gpu_rows]
        util_values = [value for value in util_values if value is not None]
        temp_values = [_number(row.get("dcgm_gpu_temp")) for row in gpu_rows]
        temp_values = [value for value in temp_values if value is not None]
        median_util = median(util_values) if len(util_values) >= 2 else None
        median_temp = median(temp_values) if len(temp_values) >= 2 else None
        active_keys: set[tuple[str, str]] = set()

        for row in gpu_rows:
            gpu_key = _degradation_gpu_key(row)
            ecc_errors = _ecc_error_count(row)
            if ecc_errors and (gpu_key, "ecc_error_count") not in emitted:
                findings.append(
                    _degradation_finding(
                        row,
                        divergence_metric="ecc_error_count",
                        divergence_value=ecc_errors,
                        timestamp=timestamp,
                        consecutive_snapshots=1,
                    )
                )
                emitted.add((gpu_key, "ecc_error_count"))

            util = _number(row.get("dcgm_gpu_util"))
            if median_util is not None and median_util > 0 and util is not None:
                ratio = util / median_util
                if ratio < sm_activity_ratio:
                    key = (gpu_key, "sm_activity_ratio_to_cluster_median")
                    active_keys.add(key)
                    consecutive[key] = consecutive.get(key, 0) + 1
                    if consecutive[key] >= min_consecutive_snapshots and key not in emitted:
                        findings.append(
                            _degradation_finding(
                                row,
                                divergence_metric="sm_activity_ratio_to_cluster_median",
                                divergence_value=ratio,
                                timestamp=timestamp,
                                consecutive_snapshots=consecutive[key],
                                cluster_median=median_util,
                                observed_value=util,
                            )
                        )
                        emitted.add(key)

            temp = _number(row.get("dcgm_gpu_temp"))
            if median_temp is not None and temp is not None:
                delta = temp - median_temp
                if delta > temp_delta_c:
                    key = (gpu_key, "gpu_temp_delta_c_from_cluster_median")
                    active_keys.add(key)
                    consecutive[key] = consecutive.get(key, 0) + 1
                    if consecutive[key] >= min_consecutive_snapshots and key not in emitted:
                        findings.append(
                            _degradation_finding(
                                row,
                                divergence_metric="gpu_temp_delta_c_from_cluster_median",
                                divergence_value=delta,
                                timestamp=timestamp,
                                consecutive_snapshots=consecutive[key],
                                cluster_median=median_temp,
                                observed_value=temp,
                            )
                        )
                        emitted.add(key)

        for key in list(consecutive):
            if key not in active_keys and key[1] != "ecc_error_count":
                consecutive[key] = 0
    return findings


def _degradation_finding(
    row: Mapping[str, Any],
    *,
    divergence_metric: str,
    divergence_value: float,
    timestamp: str,
    consecutive_snapshots: int,
    cluster_median: float | None = None,
    observed_value: float | None = None,
) -> dict[str, Any]:
    metadata = {
        "gpu_index": row.get("gpu_index"),
        "gpu_uuid": row.get("gpu_uuid"),
        "divergence_metric": divergence_metric,
        "divergence_value": divergence_value,
    }
    return {
        **metadata,
        "timestamp": timestamp,
        "consecutive_snapshots": consecutive_snapshots,
        "cluster_median": cluster_median,
        "observed_value": observed_value,
    }


def _degradation_gpu_key(row: Mapping[str, Any]) -> str:
    return str(row.get("gpu_uuid") or f"gpu-index-{row.get('gpu_index')}")


def _ecc_error_count(row: Mapping[str, Any]) -> float:
    total = 0.0
    for key in (
        "dcgm_xid_errors",
        "dcgm_ecc_sbe_volatile_total",
        "dcgm_ecc_dbe_volatile_total",
        "dcgm_ecc_sbe_aggregate_total",
        "dcgm_ecc_dbe_aggregate_total",
    ):
        value = _number(row.get(key))
        if value is not None and value > 0:
            total += value
    return total


def _number(value: Any) -> float | None:
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _aggregate_vllm_field(fields: dict[str, float | None], field: str, value: float) -> None:
    current = fields[field]
    if field in VLLM_SUM_FIELDS:
        fields[field] = value if current is None else current + value
    elif field in VLLM_MAX_FIELDS:
        fields[field] = value if current is None else max(current, value)
    else:
        fields[field] = value


def _histogram_quantile(quantile: float, buckets: Mapping[float, float]) -> float | None:
    if not buckets:
        return None
    finite_buckets = sorted((bound, count) for bound, count in buckets.items() if math.isfinite(bound))
    total = buckets.get(math.inf)
    if total is None and finite_buckets:
        total = finite_buckets[-1][1]
    if total is None or total <= 0:
        return None
    rank = quantile * total
    for bound, count in finite_buckets:
        if count >= rank:
            return bound
    return finite_buckets[-1][0] if finite_buckets else None


def _parse_bucket_bound(raw: str | None) -> float | None:
    if raw is None:
        return None
    if raw in {"+Inf", "Inf", "inf", "+inf"}:
        return math.inf
    try:
        value = float(raw)
    except ValueError:
        return None
    return value if math.isfinite(value) else None


def _normalize_metric_name(name: str) -> str:
    return name.replace(":", "_")


def _gpu_uuid(labels: Mapping[str, str]) -> str | None:
    for key in ("UUID", "uuid", "gpu_uuid", "GPU_UUID"):
        value = labels.get(key)
        if value:
            return value
    return None


def _gpu_index(raw: str | None) -> int | None:
    if raw is None or raw == "":
        return None
    try:
        return int(raw)
    except ValueError:
        return None


def _build_row(
    timestamp_iso: str,
    window_seconds: int,
    dcgm_row: Mapping[str, Any] | None,
    vllm_fields: Mapping[str, float | None],
) -> dict[str, Any]:
    row: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "timestamp": timestamp_iso,
        "timestamp_window_seconds": window_seconds,
        "gpu_uuid": None,
        "gpu_index": None,
        **{name: None for name in DCGM_FIELDS},
        **{name: vllm_fields.get(name) for name in VLLM_FIELDS},
    }
    if dcgm_row is not None:
        row["gpu_uuid"] = dcgm_row.get("gpu_uuid")
        row["gpu_index"] = dcgm_row.get("gpu_index")
        for field in DCGM_FIELDS:
            row[field] = dcgm_row.get(field)
    return row


def _isoformat(timestamp: float) -> str:
    return datetime.fromtimestamp(timestamp, tz=UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Emit dcgm-correlated/v1 JSONL from vLLM and DCGM metrics.")
    parser.add_argument("--vllm-metrics-url", default=DEFAULT_VLLM_METRICS_URL)
    parser.add_argument("--dcgm-metrics-url", default=DEFAULT_DCGM_METRICS_URL)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--duration-seconds", type=float, default=DEFAULT_DURATION_SECONDS)
    parser.add_argument("--interval-seconds", type=float, default=DEFAULT_INTERVAL_SECONDS)
    parser.add_argument("--log-level", default="INFO")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    logging.basicConfig(level=getattr(logging, str(args.log_level).upper(), logging.INFO), format="%(levelname)s %(message)s")
    correlator = DcgmCorrelator(
        vllm_metrics_url=args.vllm_metrics_url,
        dcgm_metrics_url=args.dcgm_metrics_url,
        output_dir=args.output_dir,
        duration_seconds=args.duration_seconds,
        interval_seconds=args.interval_seconds,
    )
    output_path = correlator.run()
    print(output_path)
    return 0


if __name__ == "__main__":  # pragma: no cover - exercised by bash script/operator use
    raise SystemExit(main())


__all__ = [
    "DEFAULT_DCGM_METRICS_URL",
    "DEFAULT_DURATION_SECONDS",
    "DEFAULT_INTERVAL_SECONDS",
    "DEFAULT_VLLM_METRICS_URL",
    "OUTPUT_FILENAME",
    "SCHEMA_VERSION",
    "DcgmCorrelator",
    "DcgmCorrelatorError",
    "PrometheusSample",
    "align_timestamp",
    "detect_partial_gpu_degradation",
    "parse_dcgm_samples",
    "parse_prometheus_text",
    "parse_vllm_samples",
]

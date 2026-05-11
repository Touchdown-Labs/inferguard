"""Async runner for PRD §4.3 ``collect-metrics``."""

from __future__ import annotations

import asyncio
import json
import math
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

from inferguard.disagg.adapters import scrape
from inferguard.disagg.types import EngineName
from inferguard.io import (
    atomic_write_json,
    register_jsonl_stream,
    register_partial_results,
    unregister_jsonl_stream,
    unregister_partial_results,
)

from .normalize import build_metrics_summary, normalize_dcgm_sample, normalize_engine_sample
from .types import (
    ENGINE_GROUPS,
    RAW_PROM_SAMPLES_SCHEMA_VERSION,
    CollectMetricsOptions,
    EngineMetricsSample,
    GpuMetricsSample,
    MetricsSummary,
)

ENGINE_TIMELINE_FILENAME = "engine_metrics_timeline.jsonl"
GPU_TIMELINE_FILENAME = "gpu_metrics_timeline.jsonl"
METRICS_SUMMARY_FILENAME = "metrics_summary.json"
RAW_SAMPLES_FILENAME = "raw_samples.jsonl"
LMCACHE_COMPAT_REPORT_FILENAME = "lmcache_compat_report.json"
SUPPORTED_ENGINES = {"vllm", "sglang", "lmcache", "dynamo-sglang"}


class CollectMetricsError(ValueError):
    """Raised when collect-metrics options are invalid."""


@dataclass(frozen=True)
class ScrapeResult:
    """HTTP scrape result for raw Prometheus text."""

    url: str
    text: str
    http_status: int | None = None
    scrape_error: str = ""

    @property
    def ok(self) -> bool:
        return not self.scrape_error


def collect_metrics(
    options: CollectMetricsOptions,
    *,
    emit: Any | None = print,
) -> MetricsSummary:
    """Run the async collector and write the three PRD §4.3 artifacts."""

    return asyncio.run(run_collect_metrics(options, emit=emit))


async def run_collect_metrics(
    options: CollectMetricsOptions,
    *,
    emit: Any | None = print,
) -> MetricsSummary:
    """Scrape engine and DCGM metrics over the configured wall-clock window."""

    _validate_options(options)
    output_dir = Path(options.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    engine_path = output_dir / ENGINE_TIMELINE_FILENAME
    gpu_path = output_dir / GPU_TIMELINE_FILENAME
    summary_path = output_dir / METRICS_SUMMARY_FILENAME
    raw_path = output_dir / RAW_SAMPLES_FILENAME
    compat_path = output_dir / LMCACHE_COMPAT_REPORT_FILENAME
    partial_path = output_dir / "partial_results.json"
    labels = options.labels()

    sample_count_target = max(1, math.ceil(options.duration_seconds / options.interval_seconds))
    dcgm_every = max(1, math.ceil(options.dcgm_interval_seconds / options.interval_seconds))
    engine_rows: list[dict[str, Any]] = []
    gpu_rows: list[dict[str, Any]] = []
    last_engine_text = ""
    last_lmcache_text = ""

    raw_handle = raw_path.open("w", encoding="utf-8") if options.keep_raw_samples else None
    if raw_handle is not None:
        register_jsonl_stream(raw_handle)
    register_partial_results(
        partial_path,
        lambda: _partial_results_payload(
            options,
            engine_rows=engine_rows,
            gpu_rows=gpu_rows,
            engine_path=engine_path,
            gpu_path=gpu_path,
            summary_path=summary_path,
            raw_path=raw_path if options.keep_raw_samples else None,
        ),
    )
    try:
        async with httpx.AsyncClient(timeout=options.timeout_seconds) as client:
            with (
                engine_path.open("w", encoding="utf-8") as engine_handle,
                gpu_path.open("w", encoding="utf-8") as gpu_handle,
            ):
                register_jsonl_stream(engine_handle)
                register_jsonl_stream(gpu_handle)
                try:
                    for sequence in range(sample_count_target):
                        started = asyncio.get_running_loop().time()
                        observed_at = _utc_now_iso()
                        engine_result, lmcache_result, snapshot = await _scrape_engine_bundle(
                            client,
                            options,
                        )
                        last_engine_text = engine_result.text
                        if lmcache_result is not None:
                            last_lmcache_text = lmcache_result.text
                        if raw_handle is not None:
                            _write_raw_row(
                                raw_handle, sequence, observed_at, "engine", engine_result, labels
                            )
                            if lmcache_result is not None:
                                _write_raw_row(
                                    raw_handle,
                                    sequence,
                                    observed_at,
                                    "lmcache",
                                    lmcache_result,
                                    labels,
                                )

                        combined_engine_text = engine_result.text
                        if lmcache_result is not None and lmcache_result.text:
                            combined_engine_text = f"{combined_engine_text}\n{lmcache_result.text}"
                        normalized = normalize_engine_sample(
                            options.engine,
                            combined_engine_text,
                            snapshot=snapshot,
                        )
                        scrape_error = engine_result.scrape_error or getattr(
                            snapshot, "scrape_error", ""
                        )
                        for group in ENGINE_GROUPS:
                            group_data = normalized["groups"][group]
                            sample = EngineMetricsSample(
                                sequence=sequence,
                                observed_at=observed_at,
                                engine=options.engine,
                                group=group,
                                model_name=str(normalized.get("model_name") or ""),
                                metrics={
                                    key: value
                                    for key, value in normalized["observed_metrics"].items()
                                    if key in group_data.get("source_metrics", [])
                                },
                                source_metrics=list(group_data.get("source_metrics", [])),
                                normalized={
                                    key: value
                                    for key, value in group_data.items()
                                    if key
                                    not in {
                                        "claim_status",
                                        "claim_status_per_field",
                                        "source_metrics",
                                    }
                                },
                                claim_status=str(group_data.get("claim_status") or "not_proven"),
                                claim_status_per_field=dict(
                                    group_data.get("claim_status_per_field") or {}
                                ),
                                labels=labels,
                                scrape_error=scrape_error,
                            )
                            row = sample.as_dict()
                            engine_rows.append(row)
                            _write_jsonl(engine_handle, row)

                        if options.dcgm_metrics_url and sequence % dcgm_every == 0:
                            dcgm_result = await _fetch_text(client, options.dcgm_metrics_url)
                            if raw_handle is not None:
                                _write_raw_row(
                                    raw_handle, sequence, observed_at, "dcgm", dcgm_result, labels
                                )
                            dcgm_rows = normalize_dcgm_sample(
                                dcgm_result.text,
                                observed_at=observed_at,
                                sequence=sequence,
                                timestamp_window_seconds=int(options.dcgm_interval_seconds),
                                labels=labels,
                                scrape_error=dcgm_result.scrape_error,
                            )
                            for raw_gpu_row in dcgm_rows:
                                sample = GpuMetricsSample(**raw_gpu_row)
                                row = sample.as_dict()
                                gpu_rows.append(row)
                                _write_jsonl(gpu_handle, row)

                        if sequence < sample_count_target - 1:
                            elapsed = asyncio.get_running_loop().time() - started
                            await asyncio.sleep(max(0.0, options.interval_seconds - elapsed))
                finally:
                    unregister_jsonl_stream(engine_handle)
                    unregister_jsonl_stream(gpu_handle)
    finally:
        unregister_partial_results(partial_path)
        if raw_handle is not None:
            unregister_jsonl_stream(raw_handle)
            raw_handle.close()

    summary_data = build_metrics_summary(
        engine=options.engine,
        duration_seconds=options.duration_seconds,
        engine_rows=engine_rows,
        gpu_rows=gpu_rows,
        sample_count=sample_count_target,
        dcgm_sample_count=len(gpu_rows),
        generated_at=_utc_now_iso(),
        labels=labels,
    )
    summary = MetricsSummary(**summary_data)
    atomic_write_json(summary_path, summary.as_dict())
    if options.lmcache_metrics_url:
        from inferguard.compat import build_compat_report, write_compat_report

        write_compat_report(
            build_compat_report(
                engine_text=last_engine_text,
                lmcache_text=last_lmcache_text,
                engine_source=options.engine_metrics_url,
                lmcache_source=options.lmcache_metrics_url,
            ),
            compat_path,
        )
    if emit is not None:
        emit(_stdout_summary(options.engine, summary.as_dict()))
    return summary


async def _scrape_engine_bundle(
    client: httpx.AsyncClient,
    options: CollectMetricsOptions,
) -> tuple[ScrapeResult, ScrapeResult | None, Any]:
    adapter_engine = _adapter_engine(options.engine)
    tasks: list[Any] = [
        _fetch_text(client, options.engine_metrics_url),
        scrape(options.engine_metrics_url, "prefill", adapter_engine, client),
    ]
    if options.lmcache_metrics_url:
        tasks.append(_fetch_text(client, options.lmcache_metrics_url))
    results = await asyncio.gather(*tasks)
    engine_result = results[0]
    snapshot = results[1]
    lmcache_result = results[2] if len(results) > 2 else None
    return engine_result, lmcache_result, snapshot


async def _fetch_text(client: httpx.AsyncClient, url: str) -> ScrapeResult:
    try:
        response = await client.get(url, timeout=client.timeout)
    except Exception as exc:
        return ScrapeResult(url=url, text="", scrape_error=_classify_exc(exc))
    if response.status_code >= 400:
        return ScrapeResult(
            url=url,
            text="",
            http_status=response.status_code,
            scrape_error=f"http_{response.status_code}",
        )
    text = response.text
    if not text.strip():
        return ScrapeResult(url=url, text="", http_status=response.status_code, scrape_error="")
    return ScrapeResult(url=url, text=text, http_status=response.status_code)


def _partial_results_payload(
    options: CollectMetricsOptions,
    *,
    engine_rows: list[dict[str, Any]],
    gpu_rows: list[dict[str, Any]],
    engine_path: Path,
    gpu_path: Path,
    summary_path: Path,
    raw_path: Path | None,
) -> dict[str, Any]:
    artifacts = {
        "engine_metrics_timeline": str(engine_path),
        "gpu_metrics_timeline": str(gpu_path),
        "metrics_summary": str(summary_path),
    }
    if raw_path is not None:
        artifacts["raw_samples"] = str(raw_path)
    if options.lmcache_metrics_url:
        artifacts["lmcache_compat_report"] = str(summary_path.parent / LMCACHE_COMPAT_REPORT_FILENAME)
    return {
        "command": "collect-metrics",
        "status": "interrupted",
        "claim_status": "inferred",
        "claim_reason": "interrupted_partial_results",
        "engine": options.engine,
        "sample_count": len({row.get("sequence") for row in engine_rows}),
        "engine_row_count": len(engine_rows),
        "gpu_row_count": len(gpu_rows),
        "artifacts": artifacts,
    }


def _write_raw_row(
    handle: Any,
    sequence: int,
    observed_at: str,
    source: str,
    result: ScrapeResult,
    labels: dict[str, str],
) -> None:
    row = {
        "schema_version": RAW_PROM_SAMPLES_SCHEMA_VERSION,
        "sequence": sequence,
        "observed_at": observed_at,
        "source": source,
        "url": result.url,
        "http_status": result.http_status,
        "scrape_error": result.scrape_error,
        "raw_text": result.text,
        "labels": dict(sorted(labels.items())),
    }
    _write_jsonl(handle, row)


def _write_jsonl(handle: Any, row: MappingLike) -> None:
    handle.write(json.dumps(dict(row), sort_keys=True, separators=(",", ":")) + "\n")
    handle.flush()


def _stdout_summary(engine: str, summary: dict[str, Any]) -> str:
    kv_cache = summary.get("kv_cache") or {}
    gpu_util = summary.get("gpu_util") or {}
    hbm = summary.get("hbm") or {}
    gpu_util_p95 = ((gpu_util.get("DCGM_FI_DEV_GPU_UTIL") or {}).get("p95")) or 0.0
    hbm_used_p95 = ((hbm.get("DCGM_FI_DEV_FB_USED") or {}).get("p95")) or 0.0
    kv_cache_max = _number(kv_cache.get("usage_fraction")) or 0.0
    return (
        "inferguard collect-metrics: "
        f"engine={engine} "
        f"samples={summary.get('sample_count', 0)} "
        f"dcgm_samples={summary.get('dcgm_sample_count', 0)} "
        f"duration={summary.get('duration_seconds', 0):g} "
        f"kv_cache_max={kv_cache_max:g} "
        f"gpu_util_p95={float(gpu_util_p95):g} "
        f"hbm_used_p95_mib={int(round(float(hbm_used_p95)))}"
    )


def _adapter_engine(engine: str) -> EngineName:
    if engine == "dynamo-sglang":
        return "dynamo"
    if engine in {"vllm", "sglang", "lmcache"}:
        return engine  # type: ignore[return-value]
    return "unknown"


def _validate_options(options: CollectMetricsOptions) -> None:
    if options.engine not in SUPPORTED_ENGINES:
        raise CollectMetricsError("--engine must be one of vllm|sglang|lmcache|dynamo-sglang")
    if not options.engine_metrics_url:
        raise CollectMetricsError("--engine-metrics-url is required")
    if options.duration_seconds <= 0:
        raise CollectMetricsError("--duration-seconds must be positive")
    if options.interval_seconds <= 0:
        raise CollectMetricsError("--interval-seconds must be positive")
    if options.dcgm_interval_seconds <= 0:
        raise CollectMetricsError("--dcgm-interval-seconds must be positive")
    if options.timeout_seconds <= 0:
        raise CollectMetricsError("timeout_seconds must be positive")


def _classify_exc(exc: Exception) -> str:
    name = type(exc).__name__
    if "Timeout" in name:
        return "timeout"
    if "Connect" in name or "Network" in name:
        return "connect_error"
    if "DNS" in name or "GetAddr" in name:
        return "dns_error"
    return name.lower()


def _number(value: Any) -> float | None:
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


MappingLike = dict[str, Any]

__all__ = [
    "ENGINE_TIMELINE_FILENAME",
    "GPU_TIMELINE_FILENAME",
    "LMCACHE_COMPAT_REPORT_FILENAME",
    "METRICS_SUMMARY_FILENAME",
    "RAW_SAMPLES_FILENAME",
    "SUPPORTED_ENGINES",
    "CollectMetricsError",
    "CollectMetricsOptions",
    "collect_metrics",
    "run_collect_metrics",
]

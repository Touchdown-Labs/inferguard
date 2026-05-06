"""Per-engine Prometheus adapters.

Each adapter is a pure function of ``(prometheus_text) -> DisaggSnapshot``.
The public ``scrape()`` helper does the HTTP dance and dispatches to the
correct adapter based on ``engine`` (auto-detected or user-forced).

vLLM and SGLang are the primary shipped adapters. v0.5 adds provisional
LMCache, Dynamo KVBM, and CPU/GPU offload metrics; inferred metric names are
called out inline and should be validated against live endpoints before GA.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import TYPE_CHECKING

# Keep this historical module importable while allowing focused submodules such
# as ``inferguard.disagg.adapters.lmcache``.
__path__ = [str(Path(__file__).with_suffix(""))]

from inferguard.config import HTTP_TIMEOUT_SECONDS, USER_AGENT
from inferguard.disagg.adapters.lmcache import parse_lmcache_snapshot
from inferguard.disagg.engines import detect_engine
from inferguard.disagg.types import (
    DisaggSnapshot,
    EndpointId,
    EngineName,
    Role,
)
from inferguard.metrics_core import (
    LabeledSample,
    histogram_avg,
    parse_labeled_prometheus_text,
    parse_prometheus_text,
)

if TYPE_CHECKING:
    import httpx


# --- field maps -------------------------------------------------------------
#
# ``normalized_field -> prometheus_metric_name``. Adapters copy values from
# the parsed dict using these maps, skipping anything not present. Adding a
# new engine is a single-row addition here plus a detection rule in
# ``engines.py``.

VLLM_FIELD_MAP: dict[str, str] = {
    "kv_cache_usage": "vllm:gpu_cache_usage_perc",
    "requests_running": "vllm:num_requests_running",
    "requests_waiting": "vllm:num_requests_waiting",
    "requests_swapped": "vllm:num_requests_swapped",
    "preemptions_total": "vllm:num_preemptions_total",
    "kv_transfer_sent_bytes_total": "vllm:kv_transfer_sent_bytes_total",
    "kv_transfer_recv_bytes_total": "vllm:kv_transfer_recv_bytes_total",
    "kv_transfer_errors_total": "vllm:kv_transfer_errors_total",
    # vLLM v0.12 KV-offload connector names are inferred from the public
    # connector design and should be validated against a live v0.12+ endpoint.
    "vllm_offload_dma_bytes_per_sec": "vllm:kv_offload_dma_bytes_per_second",
    "vllm_offload_async_queue_depth": "vllm:kv_offload_async_queue_depth",
    "vllm_offload_eviction_count": "vllm:kv_offload_eviction_count_total",
    "prefix_cache_hits": "vllm:prefix_cache_hits_total",
    "prefix_cache_queries": "vllm:prefix_cache_queries_total",
    "cpu_prefix_cache_hits": "vllm:cpu_prefix_cache_hits_total",
    "cpu_prefix_cache_queries": "vllm:cpu_prefix_cache_queries_total",
    "external_prefix_cache_hits": "vllm:external_prefix_cache_hits_total",
    "external_prefix_cache_queries": "vllm:external_prefix_cache_queries_total",
    "prompt_tokens_cached_total": "vllm:prompt_tokens_cached_total",
    "kv_offload_bytes_gpu_to_cpu": "vllm:kv_offload_bytes_gpu_to_cpu",
    "kv_offload_bytes_cpu_to_gpu": "vllm:kv_offload_bytes_cpu_to_gpu",
    "kv_offload_time_gpu_to_cpu": "vllm:kv_offload_time_gpu_to_cpu",
    "kv_offload_time_cpu_to_gpu": "vllm:kv_offload_time_cpu_to_gpu",
    "cpu_kv_cache_usage_pct": "vllm:cpu_kv_cache_usage_pct",
    "simple_cpu_offload_total_blocks": "vllm:simple_cpu_offload_total_blocks",
    "simple_cpu_offload_free_blocks": "vllm:simple_cpu_offload_free_blocks",
    "simple_cpu_offload_used_blocks": "vllm:simple_cpu_offload_used_blocks",
    "simple_cpu_offload_usage_perc": "vllm:simple_cpu_offload_usage_perc",
    "simple_cpu_offload_pending_loads": "vllm:simple_cpu_offload_pending_loads",
    "simple_cpu_offload_pending_stores": "vllm:simple_cpu_offload_pending_stores",
}
_VLLM_TTFT_PREFIX = "vllm:time_to_first_token_seconds"
_VLLM_TPOT_PREFIX = "vllm:time_per_output_token_seconds"

SGLANG_FIELD_MAP: dict[str, str] = {
    "kv_cache_usage": "sglang:token_usage",
    "requests_running": "sglang:num_running_reqs",
    "requests_waiting": "sglang:num_queue_reqs",
    "preemptions_total": "sglang:num_preemptions_total",
    "kv_transfer_sent_bytes_total": "sglang:kv_transfer_sent_bytes_total",
    "kv_transfer_recv_bytes_total": "sglang:kv_transfer_recv_bytes_total",
    "kv_transfer_errors_total": "sglang:kv_transfer_errors_total",
    # SGLang HiCache names are inferred from public HiCache tier semantics;
    # validate against a live SGLang endpoint before promoting beyond v0.5.
    "sglang_hicache_l1_hit_count": "sglang:hicache_l1_hit_count_total",
    "sglang_hicache_l2_hit_count": "sglang:hicache_l2_hit_count_total",
    "sglang_hicache_l3_hit_count": "sglang:hicache_l3_hit_count_total",
    "sglang_hicache_lookup_count": "sglang:hicache_lookup_count_total",
    "sglang_hicache_l2_bytes": "sglang:hicache_l2_bytes",
    "sglang_hicache_l3_bytes": "sglang:hicache_l3_bytes",
}
_SGLANG_TTFT_PREFIX = "sglang:time_to_first_token_seconds"
_SGLANG_TPOT_PREFIX = "sglang:time_per_output_token_seconds"

# LMCache metric names are provisional aliases from the v0.5 plan; live
# LMCache v0.4.x endpoints may expose retrieve/lookup/local_cpu names instead.
LMCACHE_FIELD_MAP: dict[str, str] = {
    "lmcache_hit_rate": "lmcache:hit_rate",
    "lmcache_eviction_count": "lmcache:eviction_count",
    "lmcache_tier_cpu_bytes": 'lmcache:tier_usage{tier="cpu"}',
    "lmcache_tier_local_disk_bytes": 'lmcache:tier_usage{tier="local_disk"}',
    "lmcache_tier_remote_bytes": 'lmcache:tier_usage{tier="remote"}',
    "lmcache_remote_bytes_sent": "lmcache:remote_bytes_sent_total",
    "lmcache_remote_bytes_received": "lmcache:remote_bytes_received_total",
    "lmcache_queue_depth": "lmcache:queue_depth",
}

# Populated for Dynamo KVBM, validation pending. Names are inferred from
# Dynamo KVBM tier semantics and need live-endpoint validation.
DYNAMO_FIELD_MAP: dict[str, str] = {
    "dynamo_block_l1_count": 'dynamo:kvbm_blocks{tier="l1_gpu"}',
    "dynamo_block_l2_count": 'dynamo:kvbm_blocks{tier="l2_cpu"}',
    "dynamo_block_l3_count": 'dynamo:kvbm_blocks{tier="l3_storage"}',
    "dynamo_kvbm_evictions": "dynamo:kvbm_evictions_total",
    "dynamo_kvbm_promotions": "dynamo:kvbm_promotions_total",
}
_DYNAMO_RESIDENCY_PREFIX = "dynamo:kvbm_block_residency_seconds"

# TODO(Packet B): populate once upstream llm-d metrics are validated.  # noqa: scan-no-stubs deliberate-empty-map-pending-llm-d-stability
LLMD_FIELD_MAP: dict[str, str] = {}

# Label keys we scan on ``kv_transfer_*`` families to discover the connector
# (NIXL, Mooncake, LMCache, native, etc.). First non-empty match wins.
CONNECTOR_LABEL_CANDIDATES: tuple[str, ...] = (
    "kv_transfer_backend",
    "connector",
    "transfer_impl",
    "backend",
)

_INT_FIELDS = {
    "requests_running",
    "requests_waiting",
    "requests_swapped",
    "preemptions_total",
    "kv_transfer_sent_bytes_total",
    "kv_transfer_recv_bytes_total",
    "kv_transfer_errors_total",
    "vllm_offload_async_queue_depth",
    "vllm_offload_eviction_count",
    "prefix_cache_hits",
    "prefix_cache_queries",
    "cpu_prefix_cache_hits",
    "cpu_prefix_cache_queries",
    "external_prefix_cache_hits",
    "external_prefix_cache_queries",
    "prompt_tokens_cached_total",
    "prompt_tokens_local_compute",
    "prompt_tokens_local_cache_hit",
    "prompt_tokens_external_kv_transfer",
    "simple_cpu_offload_total_blocks",
    "simple_cpu_offload_free_blocks",
    "simple_cpu_offload_used_blocks",
    "simple_cpu_offload_pending_loads",
    "simple_cpu_offload_pending_stores",
    "lmcache_eviction_count",
    "lmcache_tier_cpu_bytes",
    "lmcache_tier_local_disk_bytes",
    "lmcache_tier_remote_bytes",
    "lmcache_remote_bytes_sent",
    "lmcache_remote_bytes_received",
    "lmcache_queue_depth",
    "dynamo_block_l1_count",
    "dynamo_block_l2_count",
    "dynamo_block_l3_count",
    "dynamo_kvbm_evictions",
    "dynamo_kvbm_promotions",
    "sglang_hicache_l1_hit_count",
    "sglang_hicache_l2_hit_count",
    "sglang_hicache_l3_hit_count",
    "sglang_hicache_lookup_count",
    "sglang_hicache_l2_bytes",
    "sglang_hicache_l3_bytes",
    "prefill_queue_depth",
    "decode_queue_depth",
}


# --- public API -------------------------------------------------------------


async def scrape(
    url: str,
    role: Role,
    engine: EngineName | None,
    client: httpx.AsyncClient,
) -> DisaggSnapshot:
    """Fetch a metrics endpoint and return a normalized snapshot.

    Historically the CLI help said endpoint base URL while runbooks often pass
    the explicit `/metrics` URL. Accept both forms so operator paste commands do
    not accidentally request `/metrics/metrics`.
    """
    stripped_url = url.rstrip("/")
    scrape_url = stripped_url if stripped_url.endswith("/metrics") else f"{stripped_url}/metrics"
    try:
        response = await client.get(
            scrape_url,
            timeout=HTTP_TIMEOUT_SECONDS,
            headers={"User-Agent": USER_AGENT},
        )
    except Exception as exc:
        return _unreachable_snapshot(url, role, reason=_classify_exc(exc))

    if response.status_code >= 400:
        return _unreachable_snapshot(
            url, role, reason=f"http_{response.status_code}", engine=engine or "unknown"
        )

    text = response.text
    resolved_engine: EngineName = engine or detect_engine(text)

    if resolved_engine == "vllm":
        return _parse_vllm(text, url, role)
    if resolved_engine == "sglang":
        return _parse_sglang(text, url, role)
    if resolved_engine == "dynamo":
        return _parse_dynamo(text, url, role)
    if resolved_engine == "lmcache":
        return _parse_lmcache(text, url, role)
    if resolved_engine == "llm-d":
        return _parse_with_map(
            text, url, role, engine="llm-d", field_map=LLMD_FIELD_MAP
        )
    # Unknown / unidentified: still return what we can so the caller sees
    # endpoint is reachable; detect.py will emit ``engine_unidentified``.
    return DisaggSnapshot(
        endpoint=EndpointId(url=url, role=role, engine="unknown"),
        scraped_at=time.time(),
        scrape_error="no_metrics_recognized" if text.strip() else "empty_body",
    )


# --- per-engine parsers -----------------------------------------------------


def _parse_vllm(text: str, url: str, role: Role) -> DisaggSnapshot:
    metrics = parse_prometheus_text(text)
    if not any(k.startswith("vllm:") for k in metrics):
        return DisaggSnapshot(
            endpoint=EndpointId(url=url, role=role, engine="vllm"),
            scraped_at=time.time(),
            scrape_error="no_metrics_recognized",
        )
    labeled = parse_labeled_prometheus_text(text)
    connector = _detect_connector(labeled, prefix="vllm:kv_transfer")
    base = _extract_base_fields(metrics, VLLM_FIELD_MAP)
    base.update(_extract_vllm_labeled_fields(labeled))
    base["ttft_avg_seconds"] = histogram_avg(metrics, _VLLM_TTFT_PREFIX)
    base["tpot_avg_seconds"] = histogram_avg(metrics, _VLLM_TPOT_PREFIX)
    return DisaggSnapshot(
        endpoint=EndpointId(url=url, role=role, engine="vllm", connector=connector),
        scraped_at=time.time(),
        **base,
    )


def _extract_vllm_labeled_fields(samples: list[LabeledSample]) -> dict[str, float | int | None]:
    fields = {
        "kv_offload_bytes_gpu_to_cpu": _labeled_metric(
            samples, "vllm:kv_offload_total_bytes", {"transfer_type": "GPU_to_CPU"}
        ),
        "kv_offload_bytes_cpu_to_gpu": _labeled_metric(
            samples, "vllm:kv_offload_total_bytes", {"transfer_type": "CPU_to_GPU"}
        ),
        "kv_offload_time_gpu_to_cpu": _labeled_metric(
            samples, "vllm:kv_offload_total_time", {"transfer_type": "GPU_to_CPU"}
        ),
        "kv_offload_time_cpu_to_gpu": _labeled_metric(
            samples, "vllm:kv_offload_total_time", {"transfer_type": "CPU_to_GPU"}
        ),
        "prompt_tokens_local_compute": _as_int(
            _labeled_metric(
                samples, "vllm:prompt_tokens_by_source_total", {"source": "local_compute"}
            )
        ),
        "prompt_tokens_local_cache_hit": _as_int(
            _labeled_metric(
                samples, "vllm:prompt_tokens_by_source_total", {"source": "local_cache_hit"}
            )
        ),
        "prompt_tokens_external_kv_transfer": _as_int(
            _labeled_metric(
                samples,
                "vllm:prompt_tokens_by_source_total",
                {"source": "external_kv_transfer"},
            )
        ),
    }
    return {key: value for key, value in fields.items() if value is not None}


def _parse_sglang(text: str, url: str, role: Role) -> DisaggSnapshot:
    metrics = parse_prometheus_text(text)
    if not any(k.startswith("sglang:") for k in metrics):
        return DisaggSnapshot(
            endpoint=EndpointId(url=url, role=role, engine="sglang"),
            scraped_at=time.time(),
            scrape_error="no_metrics_recognized",
        )
    labeled = parse_labeled_prometheus_text(text)
    connector = _detect_connector(labeled, prefix="sglang:kv_transfer")
    base = _extract_base_fields(metrics, SGLANG_FIELD_MAP)
    base["ttft_avg_seconds"] = histogram_avg(metrics, _SGLANG_TTFT_PREFIX)
    base["tpot_avg_seconds"] = histogram_avg(metrics, _SGLANG_TPOT_PREFIX)
    return DisaggSnapshot(
        endpoint=EndpointId(url=url, role=role, engine="sglang", connector=connector),
        scraped_at=time.time(),
        **base,
    )


def _parse_lmcache(text: str, url: str, role: Role) -> DisaggSnapshot:
    return parse_lmcache_snapshot(text, url, role)


def _parse_dynamo(text: str, url: str, role: Role) -> DisaggSnapshot:
    metrics = parse_prometheus_text(text)
    snap = _parse_with_map(
        text,
        url,
        role,
        engine="dynamo",
        field_map=DYNAMO_FIELD_MAP,
        required_prefix="dynamo:",
    )
    if snap.scrape_error:
        return snap
    base = snap.as_dict()
    base.pop("endpoint")
    base.pop("scraped_at")
    base["dynamo_block_residency_seconds"] = histogram_avg(
        metrics, _DYNAMO_RESIDENCY_PREFIX
    )
    return DisaggSnapshot(
        endpoint=snap.endpoint,
        scraped_at=snap.scraped_at,
        **base,
    )


def _parse_with_map(
    text: str,
    url: str,
    role: Role,
    *,
    engine: EngineName,
    field_map: dict[str, str],
    required_prefix: str | None = None,
) -> DisaggSnapshot:
    """Minimal generic parser for engines whose field maps may be empty."""
    if not field_map:
        # Extension point not yet filled — surface a useful error but still
        # return a snapshot so callers can reason about it.
        return DisaggSnapshot(
            endpoint=EndpointId(url=url, role=role, engine=engine),
            scraped_at=time.time(),
            scrape_error="adapter_not_implemented",
        )
    metrics = parse_prometheus_text(text)
    if required_prefix is not None and not any(k.startswith(required_prefix) for k in metrics):
        return DisaggSnapshot(
            endpoint=EndpointId(url=url, role=role, engine=engine),
            scraped_at=time.time(),
            scrape_error="no_metrics_recognized",
        )
    labeled = parse_labeled_prometheus_text(text)
    base = _extract_base_fields(metrics, field_map, labeled)
    return DisaggSnapshot(
        endpoint=EndpointId(url=url, role=role, engine=engine),
        scraped_at=time.time(),
        **base,
    )


# --- helpers ----------------------------------------------------------------


def _extract_base_fields(
    metrics: dict[str, float],
    field_map: dict[str, str],
    samples: list[LabeledSample] | None = None,
) -> dict[str, float | int | None]:
    """Copy mapped fields from parsed metrics; coerce int fields."""
    out: dict[str, float | int | None] = {}
    for normalized, source in field_map.items():
        value = _lookup_metric(metrics, source, samples or [])
        if value is None:
            out[normalized] = None
            continue
        if normalized in _INT_FIELDS:
            out[normalized] = int(value)
        else:
            out[normalized] = float(value)
    return out


def _lookup_metric(
    metrics: dict[str, float], source: str, samples: list[LabeledSample]
) -> float | None:
    """Return an unlabeled metric or exact-label selector value."""
    if "{" not in source:
        return metrics.get(source)
    name, selector = source.split("{", 1)
    expected = _parse_selector(selector.rstrip("}"))
    for sample in samples:
        if sample.name == name and all(
            sample.labels.get(key) == value for key, value in expected.items()
        ):
            return sample.value
    return None


def _labeled_metric(
    samples: list[LabeledSample], name: str, labels: dict[str, str]
) -> float | None:
    values = [
        sample.value
        for sample in samples
        if sample.name == name and all(sample.labels.get(key) == value for key, value in labels.items())
    ]
    return sum(values) if values else None


def _as_int(value: float | None) -> int | None:
    return int(value) if value is not None else None


def _parse_selector(raw: str) -> dict[str, str]:
    selector: dict[str, str] = {}
    for part in raw.split(","):
        key, _, value = part.partition("=")
        if key and value:
            selector[key.strip()] = value.strip().strip('"')
    return selector


def _detect_connector(samples: list[LabeledSample], *, prefix: str) -> str:
    """Scan ``kv_transfer_*`` samples for a connector label value."""
    for sample in samples:
        if not sample.name.startswith(prefix):
            continue
        for key in CONNECTOR_LABEL_CANDIDATES:
            value = sample.labels.get(key, "")
            if value:
                return value.lower()
    return ""


def _unreachable_snapshot(
    url: str, role: Role, *, reason: str, engine: EngineName = "unknown"
) -> DisaggSnapshot:
    return DisaggSnapshot(
        endpoint=EndpointId(url=url, role=role, engine=engine),
        scraped_at=time.time(),
        scrape_error=f"unreachable: {reason}" if not reason.startswith("http_") else reason,
    )


def _classify_exc(exc: Exception) -> str:
    name = type(exc).__name__
    # Compact network-error taxonomy without importing httpx at module-top.
    if "Timeout" in name:
        return "timeout"
    if "Connect" in name or "Network" in name:
        return "connect_error"
    if "DNS" in name or "GetAddr" in name:
        return "dns_error"
    return name.lower()


__all__ = [
    "scrape",
    "VLLM_FIELD_MAP",
    "SGLANG_FIELD_MAP",
    "LMCACHE_FIELD_MAP",
    "DYNAMO_FIELD_MAP",
    "LLMD_FIELD_MAP",
    "CONNECTOR_LABEL_CANDIDATES",
]

"""LMCache/TensorMesh Prometheus adapter."""

from __future__ import annotations

import time

from inferguard.disagg.metrics_schema import parse_lmcache_prometheus
from inferguard.disagg.types import DisaggSnapshot, EndpointId, Role


def parse_lmcache_snapshot(text: str, url: str, role: Role) -> DisaggSnapshot:
    """Return a DisaggSnapshot with normalized LMCache fields.

    This adapter normalizes observed Prometheus samples only. It does not infer
    real LMCache compatibility, eviction proof, fragmentation proof, CacheBlend
    proof, or TensorMesh production-stack support from workload shape.
    """
    metrics = parse_lmcache_prometheus(text)
    data = metrics.as_dict()
    recognized = any(value is not None for key, value in data.items() if key != "raw_metrics_extra")
    if not recognized and not data.get("raw_metrics_extra"):
        return DisaggSnapshot(
            endpoint=EndpointId(url=url, role=role, engine="lmcache"),
            scraped_at=time.time(),
            scrape_error="no_metrics_recognized",
        )
    # Backward-compatible aliases used by the first v0.5 adapter/tests.
    data["lmcache_tier_local_disk_bytes"] = data.get("lmcache_tier_disk_bytes")
    data["lmcache_remote_bytes_sent"] = data.get("lmcache_offload_bytes_total")
    return DisaggSnapshot(
        endpoint=EndpointId(
            url=url,
            role=role,
            engine="lmcache",
            connector=str(data.get("lmcache_connector_type") or ""),
        ),
        scraped_at=time.time(),
        **data,
    )


__all__ = ["parse_lmcache_snapshot", "parse_lmcache_prometheus"]

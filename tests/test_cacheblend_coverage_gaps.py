# SPDX-License-Identifier: Apache-2.0
"""TDD tests for CacheBlend metric coverage gaps.

These tests validate:
1. Phantom alias removal: lmcache_blend.retrieve_successes is NOT recognized
2. normalize.py includes lmcache_blend.* metrics in LMCACHE_LOCKED_METRICS
3. compat.py covers serde metrics for CacheBlend
4. All upstream LMCache CB metrics have corresponding coverage
"""

from __future__ import annotations

from inferguard.collect_metrics.normalize import LMCACHE_LOCKED_METRICS
from inferguard.compat import LMCACHE_COMPAT_REGISTRY
from inferguard.lmcache_blend_metrics import (
    _COUNTER_ALIASES,
    analyze_cacheblend_metrics,
)


# ── 1. Phantom alias removal ──────────────────────────────────────────────


def test_retrieve_successes_alias_removed_from_counter_aliases():
    """The phantom alias `retrieve_successes` MUST NOT be in _COUNTER_ALIASES
    because LMCache never emits `lmcache_blend.retrieve_successes`."""
    assert "retrieve_successes" not in _COUNTER_ALIASES


def test_retrieve_successes_not_parsed_from_prometheus_text():
    """Even if a scrape contains `lmcache_blend_retrieve_successes_total`,
    it must NOT appear in counters since LMCache never emits it."""
    text = "lmcache_blend_retrieve_successes_total 5\n"
    summary = analyze_cacheblend_metrics(text)
    assert "retrieve_successes" not in summary.counters
    assert summary.present is False


def test_retrieve_successes_dotted_alias_not_parsed():
    """Dotted OTel alias `lmcache_blend.retrieve_successes` must also be ignored."""
    text = "lmcache_blend.retrieve_successes 5\n"
    summary = analyze_cacheblend_metrics(text)
    assert "retrieve_successes" not in summary.counters
    assert summary.present is False


# ── 2. normalize.py LMCACHE_LOCKED_METRICS includes lmcache_blend counters ─


def test_normalize_includes_blend_lookup_requests():
    assert "lmcache_blend_lookup_requests_total" in LMCACHE_LOCKED_METRICS


def test_normalize_includes_blend_lookup_hit_tokens():
    assert "lmcache_blend_lookup_hit_tokens_total" in LMCACHE_LOCKED_METRICS


def test_normalize_includes_blend_lookup_requested_tokens():
    assert "lmcache_blend_lookup_requested_tokens_total" in LMCACHE_LOCKED_METRICS


def test_normalize_includes_blend_lookup_fingerprint_hits():
    assert "lmcache_blend_lookup_fingerprint_hits_total" in LMCACHE_LOCKED_METRICS


def test_normalize_includes_blend_lookup_storage_hits():
    assert "lmcache_blend_lookup_storage_hits_total" in LMCACHE_LOCKED_METRICS


def test_normalize_includes_blend_lookup_stale_chunks():
    assert "lmcache_blend_lookup_stale_chunks_total" in LMCACHE_LOCKED_METRICS


def test_normalize_includes_blend_lookup_no_gpu_context_errors():
    assert "lmcache_blend_lookup_no_gpu_context_errors_total" in LMCACHE_LOCKED_METRICS


def test_normalize_includes_blend_retrieve_requests():
    assert "lmcache_blend_retrieve_requests_total" in LMCACHE_LOCKED_METRICS


def test_normalize_includes_blend_retrieve_chunks():
    assert "lmcache_blend_retrieve_chunks_total" in LMCACHE_LOCKED_METRICS


def test_normalize_includes_blend_retrieve_failures():
    assert "lmcache_blend_retrieve_failures_total" in LMCACHE_LOCKED_METRICS


def test_normalize_includes_blend_store_pre_computed_requests():
    assert "lmcache_blend_store_pre_computed_requests_total" in LMCACHE_LOCKED_METRICS


def test_normalize_includes_blend_store_pre_computed_chunks():
    assert "lmcache_blend_store_pre_computed_chunks_total" in LMCACHE_LOCKED_METRICS


def test_normalize_includes_blend_store_pre_computed_failures():
    assert "lmcache_blend_store_pre_computed_failures_total" in LMCACHE_LOCKED_METRICS


def test_normalize_includes_blend_store_final_requests():
    assert "lmcache_blend_store_final_requests_total" in LMCACHE_LOCKED_METRICS


def test_normalize_includes_blend_store_final_chunks():
    assert "lmcache_blend_store_final_chunks_total" in LMCACHE_LOCKED_METRICS


def test_normalize_includes_blend_store_final_failures():
    assert "lmcache_blend_store_final_failures_total" in LMCACHE_LOCKED_METRICS


def test_normalize_includes_blend_fingerprints_registered():
    assert "lmcache_blend_fingerprints_registered_total" in LMCACHE_LOCKED_METRICS


def test_normalize_includes_blend_chunks_evicted():
    assert "lmcache_blend_chunks_evicted_total" in LMCACHE_LOCKED_METRICS


def test_normalize_includes_blend_l0_gpu_operation_duration():
    assert "lmcache_blend_l0_gpu_operation_duration_seconds" in LMCACHE_LOCKED_METRICS


def test_normalize_includes_blend_l0_gpu_transfer_chunks():
    assert "lmcache_blend_l0_gpu_transfer_chunks_total" in LMCACHE_LOCKED_METRICS


def test_normalize_includes_blend_l0_gpu_transfer_tokens():
    assert "lmcache_blend_l0_gpu_transfer_tokens_total" in LMCACHE_LOCKED_METRICS


def test_normalize_includes_blend_serde_encode_duration():
    assert "lmcache_blend_serde_encode_duration_seconds" in LMCACHE_LOCKED_METRICS


def test_normalize_includes_blend_serde_decode_duration():
    assert "lmcache_blend_serde_decode_duration_seconds" in LMCACHE_LOCKED_METRICS


def test_normalize_includes_blend_serde_bytes_in():
    assert "lmcache_blend_serde_bytes_in_total" in LMCACHE_LOCKED_METRICS


def test_normalize_includes_blend_serde_bytes_out():
    assert "lmcache_blend_serde_bytes_out_total" in LMCACHE_LOCKED_METRICS


def test_normalize_includes_blend_serde_failures():
    assert "lmcache_blend_serde_failures_total" in LMCACHE_LOCKED_METRICS


# ── 3. compat.py serde coverage ───────────────────────────────────────────


def test_compat_registry_includes_blend_serde_family():
    """The compat registry must have a serde family for lmcache_cacheblend."""
    serde_families = [
        spec
        for spec in LMCACHE_COMPAT_REGISTRY
        if spec.surface == "lmcache_cacheblend" and "serde" in spec.family
    ]
    assert len(serde_families) > 0, "No serde MetricFamilySpec found for lmcache_cacheblend surface"
    serde = serde_families[0]
    # Must cover encode, decode, bytes, and failures
    pattern_str = " ".join(serde.patterns)
    assert "serde_encode_duration" in pattern_str
    assert "serde_decode_duration" in pattern_str
    assert "serde_bytes_in" in pattern_str
    assert "serde_bytes_out" in pattern_str
    assert "serde_failures" in pattern_str


# ── 4. Comprehensive upstream metric validation ───────────────────────────

# The canonical list of LMCache CB metrics (from LMCache source of truth)
UPSTREAM_CB_METRICS: list[str] = [
    "lmcache_blend.lookup_requests",
    "lmcache_blend.lookup_requested_tokens",
    "lmcache_blend.lookup_hit_tokens",
    "lmcache_blend.lookup_fingerprint_hits",
    "lmcache_blend.lookup_storage_hits",
    "lmcache_blend.lookup_stale_chunks",
    "lmcache_blend.lookup_no_gpu_context_errors",
    "lmcache_blend.retrieve_requests",
    "lmcache_blend.retrieve_chunks",
    "lmcache_blend.retrieve_failures",
    "lmcache_blend.store_pre_computed_requests",
    "lmcache_blend.store_pre_computed_chunks",
    "lmcache_blend.store_pre_computed_failures",
    "lmcache_blend.store_final_requests",
    "lmcache_blend.store_final_chunks",
    "lmcache_blend.store_final_failures",
    "lmcache_blend.fingerprints_registered",
    "lmcache_blend.chunks_evicted",
    "lmcache_blend.l0_gpu_operation_duration_seconds_sum",
    "lmcache_blend.l0_gpu_operation_duration_seconds_count",
    "lmcache_blend.l0_gpu_transfer_chunks",
    "lmcache_blend.l0_gpu_transfer_tokens",
    "lmcache_blend.serde_encode_duration_seconds_sum",
    "lmcache_blend.serde_encode_duration_seconds_count",
    "lmcache_blend.serde_decode_duration_seconds_sum",
    "lmcache_blend.serde_decode_duration_seconds_count",
    "lmcache_blend.serde_bytes_in",
    "lmcache_blend.serde_bytes_out",
    "lmcache_blend.serde_failures",
]


def test_all_upstream_cb_metrics_have_counter_or_alias_coverage():
    """Every upstream CB metric must have a corresponding alias in at least one
    of the three analyzer modules (metrics, lifecycle, serde)."""
    from inferguard.lmcache_blend_metrics import _COUNTER_ALIASES as metrics_aliases
    from inferguard.lmcache_blend_lifecycle import (
        _DURATION_SUM,
        _DURATION_COUNT,
        _TRANSFER_CHUNKS,
        _TRANSFER_TOKENS,
    )
    from inferguard.lmcache_blend_serde import (
        _ENCODE_SUM,
        _ENCODE_COUNT,
        _DECODE_SUM,
        _DECODE_COUNT,
        _BYTES_IN,
        _BYTES_OUT,
        _FAILURES,
    )

    all_recognized = set()
    # From metrics
    for aliases in metrics_aliases.values():
        all_recognized.update(aliases)
    # From lifecycle
    all_recognized.update(_DURATION_SUM)
    all_recognized.update(_DURATION_COUNT)
    all_recognized.update(_TRANSFER_CHUNKS)
    all_recognized.update(_TRANSFER_TOKENS)
    # From serde
    all_recognized.update(_ENCODE_SUM)
    all_recognized.update(_ENCODE_COUNT)
    all_recognized.update(_DECODE_SUM)
    all_recognized.update(_DECODE_COUNT)
    all_recognized.update(_BYTES_IN)
    all_recognized.update(_BYTES_OUT)
    all_recognized.update(_FAILURES)

    for metric in UPSTREAM_CB_METRICS:
        assert (
            metric in all_recognized
        ), f"Upstream CB metric {metric!r} has no alias in any CB analyzer"


def test_compat_registry_covers_all_cb_metric_families():
    """Every upstream CB metric must match at least one pattern in the compat registry."""
    surface_specs = [
        spec for spec in LMCACHE_COMPAT_REGISTRY if spec.surface == "lmcache_cacheblend"
    ]
    assert len(surface_specs) > 0, "No lmcache_cacheblend specs in compat registry"

    import fnmatch

    # Build the underscore + _total variants that prometheus would emit
    for metric in UPSTREAM_CB_METRICS:
        # Convert dotted form to underscore form (the form prometheus emits)
        underscore = metric.replace(".", "_")
        # Check if any pattern matches
        matched = False
        for spec in surface_specs:
            for pattern in spec.patterns:
                if fnmatch.fnmatch(underscore, pattern) or fnmatch.fnmatch(
                    underscore + "_total", pattern
                ):
                    matched = True
                    break
            if matched:
                break
        assert matched, (
            f"Upstream CB metric {metric!r} (underscore: {underscore!r}) "
            f"not matched by any compat pattern"
        )

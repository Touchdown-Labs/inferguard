from __future__ import annotations

from inferguard.lmcache_blend_metrics import analyze_cacheblend_metrics


CACHEBLEND_PROM = """
lmcache_blend_lookup_requests_total 4
lmcache_blend_lookup_hit_tokens_total 75
lmcache_blend_lookup_requested_tokens_total 100
lmcache_blend_lookup_fingerprint_hits_total 10
lmcache_blend_lookup_storage_hits_total 8
lmcache_blend_lookup_stale_chunks_total 2
lmcache_blend_fingerprint_registered_total 20
lmcache_blend_fingerprint_evicted_total 5
lmcache_blend_retrieve_requests_total 3
lmcache_blend_retrieve_successes_total 2
lmcache_blend_retrieve_failures_total 1
lmcache_blend_store_pre_computed_total 7
lmcache_blend_store_final_total 6
lmcache_blend_chunks_evicted_total 4
"""


def test_analyze_cacheblend_metrics_detects_present_surface():
    summary = analyze_cacheblend_metrics(CACHEBLEND_PROM)

    assert summary.present is True
    assert summary.counters["lookup_requests"] == 4
    assert summary.counters["retrieve_failures"] == 1


def test_analyze_cacheblend_metrics_computes_blend_hit_rate():
    summary = analyze_cacheblend_metrics(CACHEBLEND_PROM)

    assert summary.blend_hit_rate == 0.75


def test_analyze_cacheblend_metrics_computes_stale_ratio():
    summary = analyze_cacheblend_metrics(CACHEBLEND_PROM)

    assert summary.stale_ratio == 0.2


def test_analyze_cacheblend_metrics_computes_fingerprint_efficiency():
    summary = analyze_cacheblend_metrics(CACHEBLEND_PROM)

    assert summary.fingerprint_efficiency == 0.8


def test_analyze_cacheblend_metrics_computes_eviction_rate():
    summary = analyze_cacheblend_metrics(CACHEBLEND_PROM)

    assert summary.eviction_rate == 0.25


def test_analyze_cacheblend_metrics_handles_missing_denominator():
    summary = analyze_cacheblend_metrics("lmcache_blend_lookup_hit_tokens_total 5\n")

    assert summary.present is True
    assert summary.blend_hit_rate is None
    assert summary.stale_ratio is None


def test_analyze_cacheblend_metrics_accepts_dotted_otel_names():
    summary = analyze_cacheblend_metrics(
        "lmcache_blend.lookup_hit_tokens 3\nlmcache_blend.lookup_requested_tokens 6\n"
    )

    assert summary.counters["lookup_hit_tokens"] == 3
    assert summary.blend_hit_rate == 0.5


def test_analyze_cacheblend_metrics_empty_text_is_not_present():
    summary = analyze_cacheblend_metrics("# HELP unrelated x\nunrelated_total 1\n")

    assert summary.present is False
    assert summary.counters == {}

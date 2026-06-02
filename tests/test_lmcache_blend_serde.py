from __future__ import annotations

from inferguard.lmcache_blend_serde import analyze_cacheblend_serde_metrics


SERDE_PROM = """
lmcache_blend_serde_encode_duration_seconds_sum{serde_type="fp8"} 0.06
lmcache_blend_serde_encode_duration_seconds_count{serde_type="fp8"} 3
lmcache_blend_serde_decode_duration_seconds_sum{serde_type="fp8"} 0.12
lmcache_blend_serde_decode_duration_seconds_count{serde_type="fp8"} 4
lmcache_blend_serde_bytes_in_total{serde_type="fp8"} 1000
lmcache_blend_serde_bytes_out_total{serde_type="fp8"} 250
lmcache_blend_serde_failures_total{serde_type="fp8",direction="encode"} 2
lmcache_blend_serde_failures_total{serde_type="fp8",direction="decode"} 1
lmcache_blend_serde_bytes_in_total{serde_type="naive"} 100
lmcache_blend_serde_bytes_out_total{serde_type="naive"} 100
"""


def test_analyze_cacheblend_serde_detects_present_surface():
    summary = analyze_cacheblend_serde_metrics(SERDE_PROM)

    assert summary.present is True
    assert summary.bytes_in_by_serde["fp8"] == 1000
    assert summary.bytes_out_by_serde["fp8"] == 250


def test_analyze_cacheblend_serde_computes_compression_ratio():
    summary = analyze_cacheblend_serde_metrics(SERDE_PROM)

    assert summary.compression_ratio_by_serde["fp8"] == 0.25
    assert summary.compression_ratio_by_serde["naive"] == 1.0


def test_analyze_cacheblend_serde_records_failures_by_direction():
    summary = analyze_cacheblend_serde_metrics(SERDE_PROM)

    assert summary.failures_by_serde_direction[("fp8", "encode")] == 2
    assert summary.failures_by_serde_direction[("fp8", "decode")] == 1
    assert summary.total_failures == 3


def test_analyze_cacheblend_serde_computes_histogram_averages():
    summary = analyze_cacheblend_serde_metrics(SERDE_PROM)

    assert summary.encode_avg_seconds_by_serde["fp8"] == 0.02
    assert summary.decode_avg_seconds_by_serde["fp8"] == 0.03


def test_analyze_cacheblend_serde_handles_zero_bytes_in():
    summary = analyze_cacheblend_serde_metrics(
        'lmcache_blend_serde_bytes_in_total{serde_type="fp8"} 0\n'
        'lmcache_blend_serde_bytes_out_total{serde_type="fp8"} 10\n'
    )

    assert summary.present is True
    assert summary.compression_ratio_by_serde["fp8"] is None


def test_analyze_cacheblend_serde_empty_text_is_not_present():
    summary = analyze_cacheblend_serde_metrics("unrelated_total 1\n")

    assert summary.present is False
    assert summary.total_failures == 0

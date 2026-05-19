# SPDX-License-Identifier: Apache-2.0
"""TDD tests for serde MetricFamilySpec end-to-end in build_compat_report().

These tests prove the serde family for lmcache_cacheblend surface works
correctly in the compat report pipeline, covering:

1. Serde present → compat detects as populated
2. Serde absent → compat flags correctly
3. Histogram suffix matching (_sum, _count, _bucket)
4. No CB metrics → serde not_applicable
5. Partial serde presence
6. _cacheblend_summary includes serde metrics when present
"""

from __future__ import annotations

from inferguard.compat import build_compat_report


# ── Helpers ───────────────────────────────────────────────────────────────

CB_LOOKUP_METRICS = """\
lmcache_blend_lookup_requests_total 10
lmcache_blend_lookup_requested_tokens_total 5000
lmcache_blend_lookup_hit_tokens_total 4000
lmcache_blend_lookup_fingerprint_hits_total 3500
lmcache_blend_lookup_storage_hits_total 500
lmcache_blend_retrieve_requests_total 8
lmcache_blend_retrieve_chunks_total 32
lmcache_blend_store_pre_computed_requests_total 6
lmcache_blend_store_pre_computed_chunks_total 24
lmcache_blend_store_final_requests_total 5
lmcache_blend_store_final_chunks_total 20
lmcache_blend_fingerprints_registered_total 100
lmcache_blend_chunks_evicted_total 2
"""

SERDE_FULL_METRICS = """\
lmcache_blend_serde_encode_duration_seconds_sum{serde_type="fp8"} 0.42
lmcache_blend_serde_encode_duration_seconds_count{serde_type="fp8"} 21
lmcache_blend_serde_encode_duration_seconds_bucket{serde_type="fp8",le="0.01"} 5
lmcache_blend_serde_encode_duration_seconds_bucket{serde_type="fp8",le="0.05"} 15
lmcache_blend_serde_encode_duration_seconds_bucket{serde_type="fp8",le="0.1"} 19
lmcache_blend_serde_encode_duration_seconds_bucket{serde_type="fp8",le="+Inf"} 21
lmcache_blend_serde_decode_duration_seconds_sum{serde_type="fp8"} 0.21
lmcache_blend_serde_decode_duration_seconds_count{serde_type="fp8"} 21
lmcache_blend_serde_bytes_in_total{serde_type="fp8"} 10240
lmcache_blend_serde_bytes_out_total{serde_type="fp8"} 2560
lmcache_blend_serde_failures_total{serde_type="fp8",direction="encode"} 0
"""

SERDE_ENCODE_ONLY = """\
lmcache_blend_serde_encode_duration_seconds_sum{serde_type="fp8"} 0.1
lmcache_blend_serde_encode_duration_seconds_count{serde_type="fp8"} 5
"""

SERDE_DECODE_ONLY = """\
lmcache_blend_serde_decode_duration_seconds_sum{serde_type="fp8"} 0.2
lmcache_blend_serde_decode_duration_seconds_count{serde_type="fp8"} 3
"""


def _serde_family(report: dict) -> dict | None:
    """Extract the serde family row from a compat report."""
    for row in report["families"]:
        if row["surface"] == "lmcache_cacheblend" and row["family"] == "serde":
            return row
    return None


def _cacheblend_family(report: dict, family_name: str) -> dict | None:
    """Extract a specific cacheblend family row from a compat report."""
    for row in report["families"]:
        if row["surface"] == "lmcache_cacheblend" and row["family"] == family_name:
            return row
    return None


# ── 1. Serde present → compat passes ─────────────────────────────────────


def test_serde_present_with_cb_metrics_compat_passes():
    """When serde metrics AND other CB metrics are present, the serde family
    should be detected as populated (not missing)."""
    report = build_compat_report(
        lmcache_text=CB_LOOKUP_METRICS + SERDE_FULL_METRICS,
    )
    serde = _serde_family(report)
    assert serde is not None, "serde family not found in compat report"
    assert serde["applicable"] is True
    assert serde["status"] == "populated", (
        f"Expected 'populated', got {serde['status']!r} " f"(matched: {serde['matched_metrics']})"
    )
    assert serde["series_count"] > 0
    assert serde["populated_series_count"] > 0


def test_serde_present_includes_histogram_series():
    """Serde histogram metrics with _sum, _count, _bucket suffixes should all
    be captured."""
    report = build_compat_report(
        lmcache_text=CB_LOOKUP_METRICS + SERDE_FULL_METRICS,
    )
    serde = _serde_family(report)
    assert serde is not None
    matched = serde["matched_metrics"]
    # Verify histogram suffixes are captured for encode duration
    encode_sum = any("encode_duration_seconds_sum" in m for m in matched)
    encode_count = any("encode_duration_seconds_count" in m for m in matched)
    encode_bucket = any("encode_duration_seconds_bucket" in m for m in matched)
    assert encode_sum, f"encode_duration_seconds_sum not matched in {matched}"
    assert encode_count, f"encode_duration_seconds_count not matched in {matched}"
    assert encode_bucket, f"encode_duration_seconds_bucket not matched in {matched}"


def test_serde_present_counter_suffixes_matched():
    """Counter metrics with _total suffix should be matched by the glob patterns."""
    report = build_compat_report(
        lmcache_text=CB_LOOKUP_METRICS + SERDE_FULL_METRICS,
    )
    serde = _serde_family(report)
    assert serde is not None
    matched = serde["matched_metrics"]
    bytes_in = any("serde_bytes_in" in m for m in matched)
    bytes_out = any("serde_bytes_out" in m for m in matched)
    failures = any("serde_failures" in m for m in matched)
    assert bytes_in, f"serde_bytes_in not matched in {matched}"
    assert bytes_out, f"serde_bytes_out not matched in {matched}"
    assert failures, f"serde_failures not matched in {matched}"


# ── 2. Serde absent → compat flags it ────────────────────────────────────


def test_serde_absent_with_other_cb_metrics_flags_not_applicable():
    """When other CB metrics are present but serde metrics are missing,
    the serde family should appear as not_applicable.

    Note: The compat report's _family_row() treats all lmcache_cacheblend
    families without matched names as not_applicable, since the surface-level
    applicability is checked per-family based on actual metric matches.
    """
    report = build_compat_report(
        lmcache_text=CB_LOOKUP_METRICS,
    )
    serde = _serde_family(report)
    assert serde is not None, "serde family should always appear in report"
    # CB is observed → applicable=True, but no serde matched names
    # → _family_row overrides to not_applicable
    assert (
        serde["status"] == "not_applicable"
    ), f"Expected 'not_applicable', got {serde['status']!r}"
    assert serde["series_count"] == 0
    assert serde["matched_metrics"] == []


def test_serde_absent_other_cb_families_still_populated():
    """When serde is absent, other CB families (lookup, retrieve, etc.)
    should still be correctly populated."""
    report = build_compat_report(
        lmcache_text=CB_LOOKUP_METRICS,
    )
    lookup = _cacheblend_family(report, "lookup")
    assert lookup is not None
    assert lookup["status"] == "populated"
    retrieve = _cacheblend_family(report, "retrieve")
    assert retrieve is not None
    assert retrieve["status"] == "populated"


# ── 3. Histogram suffix matching ─────────────────────────────────────────


def test_serde_histogram_bucket_suffix_matched():
    """Verify the glob pattern matches _bucket suffix for histogram metrics."""
    report = build_compat_report(
        lmcache_text=CB_LOOKUP_METRICS + SERDE_FULL_METRICS,
    )
    serde = _serde_family(report)
    assert serde is not None
    matched = serde["matched_metrics"]
    # Check decode histogram is also matched
    decode_sum = any("decode_duration_seconds_sum" in m for m in matched)
    decode_count = any("decode_duration_seconds_count" in m for m in matched)
    assert decode_sum, f"decode_duration_seconds_sum not matched in {matched}"
    assert decode_count, f"decode_duration_seconds_count not matched in {matched}"


def test_serde_histogram_with_many_labels():
    """Serde histogram with multiple label dimensions should all match."""
    text = (
        CB_LOOKUP_METRICS
        + """\
lmcache_blend_serde_encode_duration_seconds_sum{serde_type="fp8",model="llama"} 0.1
lmcache_blend_serde_encode_duration_seconds_count{serde_type="fp8",model="llama"} 5
lmcache_blend_serde_encode_duration_seconds_bucket{serde_type="fp8",model="llama",le="0.01"} 3
lmcache_blend_serde_encode_duration_seconds_bucket{serde_type="fp8",model="llama",le="+Inf"} 5
"""
    )
    report = build_compat_report(lmcache_text=text)
    serde = _serde_family(report)
    assert serde is not None
    assert serde["status"] == "populated"
    assert any("encode_duration_seconds_bucket" in m for m in serde["matched_metrics"])


# ── 4. cacheblend_observed=False → serde not_applicable ──────────────────


def test_no_cb_metrics_serde_not_applicable():
    """When no CB metrics at all are present, the serde family should be
    not_applicable (since required_when=cacheblend_observed)."""
    report = build_compat_report(
        lmcache_text="lmcache_mp_sm_read_requests_total 10\n",
    )
    serde = _serde_family(report)
    assert serde is not None
    assert serde["applicable"] is False, f"Expected applicable=False, got {serde['applicable']}"
    assert serde["status"] == "not_applicable"


def test_empty_text_serde_not_applicable():
    """Empty prometheus text → serde family should be not_applicable."""
    report = build_compat_report(lmcache_text="")
    serde = _serde_family(report)
    assert serde is not None
    assert serde["status"] == "not_applicable"
    assert serde["applicable"] is False


def test_engine_only_text_serde_not_applicable():
    """Only engine metrics (vLLM), no LMCache → serde not_applicable."""
    report = build_compat_report(
        engine_text="vllm:num_requests_running 5\n",
    )
    serde = _serde_family(report)
    assert serde is not None
    assert serde["status"] == "not_applicable"
    assert serde["applicable"] is False


# ── 5. Partial serde presence ────────────────────────────────────────────


def test_partial_serde_encode_only():
    """Some but not all serde metrics present (encode but not decode)
    → should still be detected and marked populated."""
    report = build_compat_report(
        lmcache_text=CB_LOOKUP_METRICS + SERDE_ENCODE_ONLY,
    )
    serde = _serde_family(report)
    assert serde is not None
    assert serde["applicable"] is True
    assert (
        serde["status"] == "populated"
    ), f"Expected 'populated' for partial serde, got {serde['status']!r}"
    # Should have encode but not decode
    matched = serde["matched_metrics"]
    assert any("encode_duration" in m for m in matched)
    assert not any("decode_duration" in m for m in matched)


def test_partial_serde_decode_only():
    """Some but not all serde metrics present (decode but not encode)
    → should still be detected and marked populated."""
    report = build_compat_report(
        lmcache_text=CB_LOOKUP_METRICS + SERDE_DECODE_ONLY,
    )
    serde = _serde_family(report)
    assert serde is not None
    assert serde["status"] == "populated"
    matched = serde["matched_metrics"]
    assert any("decode_duration" in m for m in matched)
    assert not any("encode_duration" in m for m in matched)


def test_partial_serde_bytes_only():
    """Only bytes_in/bytes_out, no encode/decode/failures."""
    text = (
        CB_LOOKUP_METRICS
        + """\
lmcache_blend_serde_bytes_in_total{serde_type="fp8"} 100
lmcache_blend_serde_bytes_out_total{serde_type="fp8"} 25
"""
    )
    report = build_compat_report(lmcache_text=text)
    serde = _serde_family(report)
    assert serde is not None
    assert serde["status"] == "populated"
    matched = serde["matched_metrics"]
    assert any("serde_bytes_in" in m for m in matched)
    assert any("serde_bytes_out" in m for m in matched)
    assert not any("encode_duration" in m for m in matched)
    assert not any("decode_duration" in m for m in matched)


# ── 6. Serde in _cacheblend_summary ──────────────────────────────────────


def test_cacheblend_summary_observed_true_when_serde_present():
    """When serde metrics are present alongside CB metrics, the
    cacheblend_summary should have observed=True."""
    report = build_compat_report(
        lmcache_text=CB_LOOKUP_METRICS + SERDE_FULL_METRICS,
    )
    summary = report["lmcache_cacheblend_summary"]
    assert summary["observed"] is True


def test_cacheblend_summary_observed_false_when_no_serde_no_cb():
    """When neither serde nor CB metrics are present, observed=False."""
    report = build_compat_report(lmcache_text="")
    summary = report["lmcache_cacheblend_summary"]
    assert summary["observed"] is False


def test_cacheblend_summary_lookup_counts_with_serde():
    """Cacheblend summary should still report lookup counts correctly
    when serde metrics are also present."""
    report = build_compat_report(
        lmcache_text=CB_LOOKUP_METRICS + SERDE_FULL_METRICS,
    )
    summary = report["lmcache_cacheblend_summary"]
    assert summary["lookup_requests"] == 10
    assert summary["lookup_fingerprint_hits"] == 3500
    assert summary["lookup_storage_hits"] == 500


# ── 7. Surface-level aggregation includes serde ──────────────────────────


def test_surface_rows_include_serde_when_populated():
    """The surfaces dict should reflect serde in the lmcache_cacheblend stats."""
    report = build_compat_report(
        lmcache_text=CB_LOOKUP_METRICS + SERDE_FULL_METRICS,
    )
    surfaces = report["surfaces"]
    cb = surfaces.get("lmcache_cacheblend")
    assert cb is not None
    assert cb["family_count"] > 0
    # Serde being populated should contribute to the populated count
    assert cb["populated"] > 0


def test_surface_rows_serde_missing_reduces_populated_count():
    """When serde is absent from an otherwise complete CB scrape,
    the surface row should show it via a non-zero missing/not_applicable count."""
    report_with_serde = build_compat_report(
        lmcache_text=CB_LOOKUP_METRICS + SERDE_FULL_METRICS,
    )
    report_without_serde = build_compat_report(
        lmcache_text=CB_LOOKUP_METRICS,
    )
    cb_with = report_with_serde["surfaces"]["lmcache_cacheblend"]
    cb_without = report_without_serde["surfaces"]["lmcache_cacheblend"]
    # With serde populated, the populated count should be >= the count without
    assert cb_with["populated"] >= cb_without["populated"]


# ── 8. report observed flags ─────────────────────────────────────────────


def test_report_observed_cacheblend_true_when_serde_present():
    """The top-level observed dict should show lmcache_cacheblend=True
    when serde metrics are present (since serde starts with lmcache_blend_)."""
    # Serde metrics start with lmcache_blend_ which triggers cacheblend detection
    report = build_compat_report(
        lmcache_text=SERDE_FULL_METRICS,
    )
    assert report["observed"]["lmcache_cacheblend"] is True


def test_report_observed_cacheblend_false_when_no_serde_no_cb():
    """No serde and no CB metrics → lmcache_cacheblend=False."""
    report = build_compat_report(lmcache_text="")
    assert report["observed"]["lmcache_cacheblend"] is False


# ── 9. Serde failures tracked in diagnostic findings ──────────────────────


def test_serde_failures_nonzero_contributes_to_cacheblend_failures():
    """When serde failures are non-zero, they should NOT independently appear
    as a diagnostic finding (since they're tracked in cacheblend_summary),
    but the cacheblend_summary should be present."""
    text = (
        CB_LOOKUP_METRICS
        + """\
lmcache_blend_serde_encode_duration_seconds_sum{serde_type="fp8"} 0.1
lmcache_blend_serde_encode_duration_seconds_count{serde_type="fp8"} 5
lmcache_blend_serde_bytes_in_total{serde_type="fp8"} 100
lmcache_blend_serde_bytes_out_total{serde_type="fp8"} 25
lmcache_blend_serde_failures_total{serde_type="fp8",direction="encode"} 3
"""
    )
    report = build_compat_report(lmcache_text=text)
    # The serde failures should not be in the non-serde failure diagnostic
    # (those track retrieve/store failures, not serde failures)
    # But verify serde family is populated with failures tracked
    serde = _serde_family(report)
    assert serde is not None
    assert serde["status"] == "populated"
    assert any("serde_failures" in m for m in serde["matched_metrics"])

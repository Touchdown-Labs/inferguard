from __future__ import annotations

import json

import pytest
from typer.testing import CliRunner

from inferguard.cli import app


def test_cacheblend_report_cli_outputs_metrics_serde_and_lifecycle(tmp_path):
    metrics = tmp_path / "metrics.prom"
    evidence = tmp_path / "evidence.jsonl"
    metrics.write_text(
        "\n".join(
            [
                "lmcache_blend_lookup_hit_tokens_total 5",
                "lmcache_blend_lookup_requested_tokens_total 10",
                'lmcache_blend_serde_bytes_in_total{serde_type="fp8"} 100',
                'lmcache_blend_serde_bytes_out_total{serde_type="fp8"} 25',
                'lmcache_blend_l0_gpu_transfer_chunks_total{operation="retrieve_pre_computed",direction="l1_to_gpu"} 3',
            ]
        ),
        encoding="utf-8",
    )
    evidence.write_text(
        json.dumps({"stage": "cb_retrieve_pre_computed_gpu_start", "event": "start"}) + "\n",
        encoding="utf-8",
    )

    result = CliRunner().invoke(
        app,
        [
            "cacheblend-report",
            "--metrics-file",
            str(metrics),
            "--boundary-evidence-file",
            str(evidence),
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["cacheblend_metrics"]["blend_hit_rate"] == 0.5
    assert payload["serde"]["compression_ratio_by_serde"]["fp8"] == 0.25
    assert payload["lifecycle"]["boundary_evidence"]["claim_status"] == "measured"


def test_cacheblend_report_cli_covers_current_lmcache_cb_metric_surface(tmp_path):
    metrics = tmp_path / "metrics.prom"
    metrics.write_text(
        "\n".join(
            [
                "lmcache_blend_lookup_requests_total 1",
                "lmcache_blend_lookup_requested_tokens_total 100",
                "lmcache_blend_lookup_hit_tokens_total 75",
                "lmcache_blend_lookup_fingerprint_hits_total 10",
                "lmcache_blend_lookup_storage_hits_total 8",
                "lmcache_blend_lookup_stale_chunks_total 2",
                "lmcache_blend_lookup_no_gpu_context_errors_total 1",
                "lmcache_blend_retrieve_requests_total 3",
                "lmcache_blend_retrieve_chunks_total 12",
                "lmcache_blend_retrieve_failures_total 1",
                "lmcache_blend_store_pre_computed_requests_total 4",
                "lmcache_blend_store_pre_computed_chunks_total 16",
                "lmcache_blend_store_pre_computed_failures_total 1",
                "lmcache_blend_store_final_requests_total 5",
                "lmcache_blend_store_final_chunks_total 20",
                "lmcache_blend_store_final_failures_total 1",
                "lmcache_blend_fingerprints_registered_total 25",
                "lmcache_blend_chunks_evicted_total 5",
                'lmcache_blend_l0_gpu_operation_duration_seconds_sum{operation="retrieve_pre_computed",direction="l1_to_gpu"} 0.6',
                'lmcache_blend_l0_gpu_operation_duration_seconds_count{operation="retrieve_pre_computed",direction="l1_to_gpu"} 3',
                'lmcache_blend_l0_gpu_transfer_chunks_total{operation="retrieve_pre_computed",direction="l1_to_gpu"} 12',
                'lmcache_blend_l0_gpu_transfer_tokens_total{operation="retrieve_pre_computed",direction="l1_to_gpu"} 3072',
                'lmcache_blend_serde_encode_duration_seconds_sum{serde_type="fp8"} 0.4',
                'lmcache_blend_serde_encode_duration_seconds_count{serde_type="fp8"} 2',
                'lmcache_blend_serde_decode_duration_seconds_sum{serde_type="fp8"} 0.2',
                'lmcache_blend_serde_decode_duration_seconds_count{serde_type="fp8"} 2',
                'lmcache_blend_serde_bytes_in_total{serde_type="fp8"} 400',
                'lmcache_blend_serde_bytes_out_total{serde_type="fp8"} 100',
                'lmcache_blend_serde_failures_total{serde_type="fp8",direction="encode"} 1',
            ]
        ),
        encoding="utf-8",
    )

    result = CliRunner().invoke(
        app,
        ["cacheblend-report", "--metrics-file", str(metrics)],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    counters = payload["cacheblend_metrics"]["counters"]
    for key in (
        "lookup_requests",
        "lookup_requested_tokens",
        "lookup_hit_tokens",
        "lookup_fingerprint_hits",
        "lookup_storage_hits",
        "lookup_stale_chunks",
        "lookup_no_gpu_context_errors",
        "retrieve_requests",
        "retrieve_chunks",
        "retrieve_failures",
        "store_pre_computed_requests",
        "store_pre_computed_chunks",
        "store_pre_computed_failures",
        "store_final_requests",
        "store_final_chunks",
        "store_final_failures",
        "fingerprints_registered",
        "chunks_evicted",
    ):
        assert counters[key] > 0
    assert payload["cacheblend_metrics"]["blend_hit_rate"] == 0.75
    assert payload["cacheblend_metrics"]["stale_ratio"] == 0.2
    assert payload["cacheblend_metrics"]["fingerprint_efficiency"] == 0.8
    assert payload["cacheblend_metrics"]["eviction_rate"] == 0.2
    assert payload["lifecycle"]["avg_duration_seconds_by_operation"][
        "retrieve_pre_computed:l1_to_gpu"
    ] == pytest.approx(0.2)
    assert payload["lifecycle"]["transfer_chunks_by_operation"][
        "retrieve_pre_computed:l1_to_gpu"
    ] == 12
    assert payload["lifecycle"]["transfer_tokens_by_operation"][
        "retrieve_pre_computed:l1_to_gpu"
    ] == 3072
    assert payload["serde"]["compression_ratio_by_serde"]["fp8"] == 0.25
    assert payload["serde"]["total_failures"] == 1
    assert payload["serde"]["failures_by_serde_direction"]["fp8:encode"] == 1

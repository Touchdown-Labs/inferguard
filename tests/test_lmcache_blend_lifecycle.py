from __future__ import annotations

import json

import pytest

from inferguard.lmcache_blend_lifecycle import analyze_cacheblend_lifecycle


LIFECYCLE_PROM = """
lmcache_blend_l0_gpu_operation_duration_seconds_sum{operation="retrieve_pre_computed",direction="l1_to_gpu"} 0.30
lmcache_blend_l0_gpu_operation_duration_seconds_count{operation="retrieve_pre_computed",direction="l1_to_gpu"} 3
lmcache_blend_l0_gpu_transfer_chunks_total{operation="retrieve_pre_computed",direction="l1_to_gpu"} 9
lmcache_blend_l0_gpu_transfer_tokens_total{operation="retrieve_pre_computed",direction="l1_to_gpu"} 144
"""


def test_analyze_cacheblend_lifecycle_detects_l0_gpu_metrics():
    summary = analyze_cacheblend_lifecycle(LIFECYCLE_PROM)

    assert summary.present is True
    assert summary.transfer_chunks_by_operation[("retrieve_pre_computed", "l1_to_gpu")] == 9
    assert summary.transfer_tokens_by_operation[("retrieve_pre_computed", "l1_to_gpu")] == 144


def test_analyze_cacheblend_lifecycle_computes_avg_duration():
    summary = analyze_cacheblend_lifecycle(LIFECYCLE_PROM)

    assert summary.avg_duration_seconds_by_operation[
        ("retrieve_pre_computed", "l1_to_gpu")
    ] == pytest.approx(0.1)


def test_analyze_cacheblend_lifecycle_reads_boundary_evidence(tmp_path):
    evidence = tmp_path / "cb-boundary.jsonl"
    evidence.write_text(
        json.dumps(
            {
                "stage": "cb_retrieve_pre_computed_gpu_start",
                "event": "start",
                "request_id": "req-1",
                "num_chunks": 2,
                "token_ids": [1, 2, 3],
            }
        )
        + "\n",
        encoding="utf-8",
    )

    summary = analyze_cacheblend_lifecycle("", boundary_evidence_path=evidence)

    assert summary.present is True
    assert summary.boundary_evidence is not None
    assert summary.boundary_evidence["claim_status"] == "measured"
    assert "token_ids" not in json.dumps(summary.boundary_evidence)


def test_analyze_cacheblend_lifecycle_empty_inputs_not_present():
    summary = analyze_cacheblend_lifecycle("")

    assert summary.present is False
    assert summary.boundary_evidence is None

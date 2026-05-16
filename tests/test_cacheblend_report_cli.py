from __future__ import annotations

import json

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

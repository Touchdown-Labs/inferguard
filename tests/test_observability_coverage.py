from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from inferguard.cli import app
from inferguard.observability_coverage import build_observability_coverage_report


def test_observability_coverage_marks_vllm_external_and_cpu_offload() -> None:
    report = build_observability_coverage_report(
        engine_text="""
vllm:time_to_first_token_seconds_sum 2
vllm:time_to_first_token_seconds_count 10
vllm:prompt_tokens_total 1000
vllm:generation_tokens_total 500
vllm:num_requests_running 2
vllm:num_requests_waiting 1
vllm:kv_cache_usage_perc 0.7
vllm:prefix_cache_queries_total 100
vllm:prefix_cache_hits_total 60
vllm:external_prefix_cache_queries_total 30
vllm:external_prefix_cache_hits_total 10
vllm:prompt_tokens_by_source_total{source="external_kv_transfer"} 200
vllm:kv_offload_total_bytes{transfer_type="GPU_to_CPU"} 4096
vllm:simple_cpu_offload_used_blocks 7
vllm:kv_transfer_sent_bytes_total 123
""",
        expected_engine="vllm",
        external_cache_configured=True,
        cpu_offload_configured=True,
        disaggregated_or_external_cache=True,
    )

    families = {(row["surface"], row["family"]): row for row in report["families"]}
    assert report["detected_engines"] == ["vllm"]
    assert families[("vllm", "external_prefix_cache")]["status"] == "populated"
    assert families[("vllm", "cpu_offload")]["status"] == "populated"
    assert families[("vllm", "kv_transfer")]["status"] == "populated"
    assert report["surfaces"]["sglang"]["status"] == "not_applicable"


def test_observability_coverage_marks_sglang_and_lmcache_mp() -> None:
    report = build_observability_coverage_report(
        engine_text="""
sglang:time_to_first_token_seconds_sum 1
sglang:time_to_first_token_seconds_count 5
sglang:prompt_tokens_total 100
sglang:generation_tokens_total 50
sglang:num_running_reqs 1
sglang:num_queue_reqs 0
sglang:cache_hit_rate 0.5
sglang:token_usage 0.7
""",
        lmcache_text="""
lmcache_mp_sm_read_requests_total 1
lmcache_mp_l1_read_keys_total 1
lmcache_mp_lookup_requested_tokens_total 100
lmcache_mp_lookup_hit_tokens_total 50
""",
        expected_engine="sglang",
        expect_lmcache_mode="mp",
    )

    assert report["detected_engines"] == ["sglang"]
    assert report["detected_lmcache_mode"] == "mp"
    assert report["surfaces"]["sglang"]["status"] in {"complete", "partial"}
    assert report["surfaces"]["lmcache_mp"]["status"] in {"complete", "partial"}
    assert report["surfaces"]["vllm"]["status"] == "not_applicable"


def test_observability_coverage_cli_writes_report(tmp_path: Path) -> None:
    metrics = tmp_path / "vllm.prom"
    metrics.write_text(
        """
vllm:prompt_tokens_total 100
vllm:generation_tokens_total 40
vllm:num_requests_running 1
vllm:kv_cache_usage_perc 0.5
vllm:prefix_cache_queries_total 10
vllm:prefix_cache_hits_total 8
""",
        encoding="utf-8",
    )
    output = tmp_path / "coverage.json"

    result = CliRunner().invoke(
        app,
        [
            "observability-coverage",
            "--engine-metrics-file",
            str(metrics),
            "--expected-engine",
            "vllm",
            "--output",
            str(output),
            "--json",
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["schema_version"] == "inferguard-observability-coverage/v1"
    assert payload["detected_engines"] == ["vllm"]
    assert output.exists()

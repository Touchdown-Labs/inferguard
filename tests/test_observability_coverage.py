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
    assert report["lmcache_compat"]["detected_architecture"]["label"] == "sglang_mp_lmcache_candidate"
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


def test_observability_coverage_includes_lmcache_non_prometheus_evidence() -> None:
    report = build_observability_coverage_report(
        lmcache_http_evidence={"booleans": {"is_healthy": True}, "endpoints": {"health": {}}},
        lmcache_log_evidence={"line_count": 2, "event_counts": {"store": 1}},
        lmcache_trace_evidence={"present": True, "claim_status": "measured", "record_count": 2},
        lmcache_otel_evidence={"present": True, "claim_status": "measured", "lmcache_span_count": 3},
        lmcache_trace_replay_evidence={"present": True, "claim_status": "measured", "row_count": 1},
        lmcache_lookup_hash_evidence={"present": True, "claim_status": "measured", "row_count": 1},
    )

    assert report["surfaces"]["lmcache_http"]["status"] == "complete"
    assert report["surfaces"]["lmcache_logs"]["status"] == "complete"
    assert report["surfaces"]["lmcache_trace_recording"]["status"] == "complete"
    assert report["surfaces"]["lmcache_otel"]["status"] == "complete"
    assert report["surfaces"]["lmcache_trace_replay"]["status"] == "complete"
    assert report["surfaces"]["lmcache_lookup_hash"]["status"] == "complete"


def test_lmcache_compat_cli_accepts_evidence_files(tmp_path: Path) -> None:
    http = tmp_path / "http.json"
    log = tmp_path / "log.json"
    trace = tmp_path / "trace.json"
    otel = tmp_path / "otel.json"
    trace_replay = tmp_path / "trace_replay.json"
    lookup_hash = tmp_path / "lookup_hash.json"
    http.write_text('{"booleans": {"is_healthy": true}, "endpoints": {"health": {}}}', encoding="utf-8")
    log.write_text('{"line_count": 1, "event_counts": {"store": 1}}', encoding="utf-8")
    trace.write_text('{"present": true, "claim_status": "measured"}', encoding="utf-8")
    otel.write_text('{"present": true, "claim_status": "measured"}', encoding="utf-8")
    trace_replay.write_text('{"present": true, "claim_status": "measured"}', encoding="utf-8")
    lookup_hash.write_text('{"present": true, "claim_status": "measured"}', encoding="utf-8")

    result = CliRunner().invoke(
        app,
        [
            "lmcache-compat",
            "--lmcache-http-evidence-file",
            str(http),
            "--lmcache-log-evidence-file",
            str(log),
            "--lmcache-trace-evidence-file",
            str(trace),
            "--lmcache-otel-evidence-file",
            str(otel),
            "--lmcache-trace-replay-evidence-file",
            str(trace_replay),
            "--lmcache-lookup-hash-evidence-file",
            str(lookup_hash),
            "--json",
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["surfaces"]["lmcache_http"]["status"] == "complete"
    assert payload["surfaces"]["lmcache_logs"]["status"] == "complete"
    assert payload["surfaces"]["lmcache_trace_replay"]["status"] == "complete"
    assert payload["surfaces"]["lmcache_lookup_hash"]["status"] == "complete"


def test_observability_coverage_cli_accepts_new_lmcache_evidence_files(tmp_path: Path) -> None:
    log = tmp_path / "log.json"
    trace_replay = tmp_path / "trace_replay.json"
    lookup_hash = tmp_path / "lookup_hash.json"
    log.write_text('{"line_count": 1, "event_counts": {"retrieve": 1}}', encoding="utf-8")
    trace_replay.write_text('{"present": true, "claim_status": "measured", "row_count": 1}', encoding="utf-8")
    lookup_hash.write_text('{"present": true, "claim_status": "measured", "row_count": 1}', encoding="utf-8")

    result = CliRunner().invoke(
        app,
        [
            "observability-coverage",
            "--lmcache-log-evidence-file",
            str(log),
            "--lmcache-trace-replay-evidence-file",
            str(trace_replay),
            "--lmcache-lookup-hash-evidence-file",
            str(lookup_hash),
            "--json",
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["surfaces"]["lmcache_logs"]["status"] == "complete"
    assert payload["surfaces"]["lmcache_trace_replay"]["status"] == "complete"
    assert payload["surfaces"]["lmcache_lookup_hash"]["status"] == "complete"


def test_lmcache_compat_reports_vllm_mp_architecture_and_findings() -> None:
    report = build_observability_coverage_report(
        engine_text="""
vllm:cache_config_info{kv_connector="LMCacheMPConnector",kv_role="kv_both"} 1
vllm:external_prefix_cache_queries_total 100
vllm:external_prefix_cache_hits_total 0
""",
        lmcache_text="""
lmcache_mp_sm_read_requests_total 10
lmcache_mp_sm_write_requests_total 10
lmcache_mp_l1_write_keys_total 10
lmcache_mp_l1_evicted_keys_total 4
lmcache_mp_lookup_requested_tokens_total{model_name="Qwen/Qwen3-8B",cache_salt=""} 1000
lmcache_mp_lookup_hit_tokens_total{model_name="Qwen/Qwen3-8B",cache_salt=""} 100
lmcache_mp_l2_prefetch_failure_total 1
""",
        expected_engine="vllm",
        expect_lmcache_mode="mp",
        external_cache_configured=True,
    )

    compat = report["lmcache_compat"]
    assert compat["detected_architecture"]["label"] == "vllm_mp_lmcache"
    assert compat["detected_architecture"]["claim_status"] == "measured"
    codes = {item["code"] for item in compat["diagnostic_findings"]}
    assert "lmcache_mp_low_hit_rate" in codes
    assert "lmcache_mp_empty_cache_salt" in codes
    assert "lmcache_mp_l1_eviction_pressure" in codes
    assert "lmcache_mp_l2_failures" in codes
    question_codes = {item["code"] for item in compat["upstream_questions"]}
    assert "lmcache_mp_empty_cache_salt" in question_codes


def test_lmcache_cacheblend_surface_and_findings_are_reported() -> None:
    report = build_observability_coverage_report(
        lmcache_text="""
lmcache_blend_lookup_requests_total 10
lmcache_blend_lookup_fingerprint_hits_total 4
lmcache_blend_lookup_storage_hits_total 3
lmcache_blend_lookup_stale_chunks_total 2
lmcache_blend_lookup_no_gpu_context_errors_total 1
lmcache_blend_retrieve_requests_total 7
lmcache_blend_retrieve_chunks_total 14
lmcache_blend_retrieve_failures_total 1
lmcache_blend_store_pre_computed_requests_total 6
lmcache_blend_store_pre_computed_chunks_total 13
lmcache_blend_store_pre_computed_failures_total 0
lmcache_blend_store_final_requests_total 5
lmcache_blend_store_final_chunks_total 12
lmcache_blend_store_final_failures_total 0
lmcache_blend_fingerprints_registered_total 8
lmcache_blend_chunks_evicted_total 2
""",
        expect_lmcache_mode="mp",
    )

    compat = report["lmcache_compat"]
    families = {(row["surface"], row["family"]): row for row in compat["families"]}
    assert compat["observed"]["lmcache_cacheblend"] is True
    assert compat["observed"]["lmcache_embedded"] is False
    assert compat["detected_architecture"]["label"] == "lmcache_mp_server"
    assert report["surfaces"]["lmcache_cacheblend"]["status"] == "complete"
    assert families[("lmcache_cacheblend", "lookup")]["status"] == "populated"
    assert families[("lmcache_cacheblend", "failure")]["status"] == "populated"
    assert families[("lmcache_cacheblend", "no_gpu_context")]["status"] == "populated"
    assert families[("lmcache_cacheblend", "stale")]["status"] == "populated"
    assert any(item["code"] == "lmcache_cacheblend_failures" for item in compat["diagnostic_findings"])
    assert not any(gap["surface"] == "lmcache_cacheblend" for gap in report["coverage_gaps"])


def test_lmcache_cacheblend_surface_is_optional_when_absent() -> None:
    report = build_observability_coverage_report(
        lmcache_text="""
lmcache_mp_sm_read_requests_total 1
lmcache_mp_l1_read_keys_total 1
""",
        expect_lmcache_mode="mp",
    )

    assert report["lmcache_compat"]["observed"]["lmcache_cacheblend"] is False
    assert report["surfaces"]["lmcache_cacheblend"]["status"] == "not_applicable"


def test_lmcache_embedded_source_alias_families_are_reported() -> None:
    report = build_observability_coverage_report(
        lmcache_text="""
lmcache:lmcache_is_healthy 1
lmcache:get_blocking_failed_count 1
lmcache:put_failed_count 2
lmcache:storage_events_ongoing_count 3
lmcache:storage_events_done_count 4
lmcache:storage_events_not_found_count 5
lmcache:chunk_statistics_chunks 6
""",
        expect_lmcache_mode="embedded",
    )

    families = {(row["surface"], row["family"]): row for row in report["lmcache_compat"]["families"]}
    assert report["detected_lmcache_mode"] == "embedded"
    assert families[("lmcache_embedded", "production_health")]["status"] == "populated"
    assert families[("lmcache_embedded", "production_failures")]["status"] == "populated"
    assert families[("lmcache_embedded", "production_storage_events")]["status"] == "populated"
    assert families[("lmcache_embedded", "chunk_stats")]["status"] == "populated"


def test_lmcache_compat_promotes_trace_and_otel_missing_evidence() -> None:
    report = build_observability_coverage_report(
        lmcache_text="""
lmcache_mp_sm_read_requests_total 10
lmcache_mp_l1_read_keys_total 5
""",
        expect_lmcache_mode="mp",
        lmcache_trace_evidence={"present": True, "claim_status": "not_proven"},
        lmcache_otel_evidence={"present": True, "claim_status": "not_proven"},
        mp_observability={
            "trace_recording_enabled": True,
            "tracing_enabled": True,
            "event_bus_queue_size": 10000,
        },
    )

    codes = {item["code"] for item in report["lmcache_compat"]["diagnostic_findings"]}
    assert "lmcache_mp_trace_enabled_but_no_trace_artifact" in codes
    assert "otel_tracing_enabled_but_no_spans" in codes

from __future__ import annotations

import json
from pathlib import Path

from inferguard.cli import app
from inferguard.observability_coverage import (
    build_observability_coverage_report,
    read_cacheblend_boundary_evidence_jsonl,
)
from typer.testing import CliRunner

LMCACHE_FIXTURES = Path(__file__).parent / "fixtures" / "lmcache_metrics"


def _lmcache_fixture(name: str) -> str:
    return (LMCACHE_FIXTURES / name).read_text(encoding="utf-8")


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
    offload = report["kv_cache_offload"]
    assert offload["vllm_native_cpu_offload"]["status"] == "populated"
    assert offload["vllm_native_cpu_offload"]["gpu_to_cpu_bytes"] == 4096
    assert offload["lmcache_mp_l0_l1_kv_transfer"]["status"] == "missing"
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


def test_lmcache_cacheblend_l0_gpu_lifecycle_is_fixture_backed_not_live_validated() -> None:
    report = build_observability_coverage_report(
        lmcache_text="""
lmcache_blend_l0_gpu_operation_duration_seconds_sum{operation="store_pre_computed",direction="gpu_to_gpu",instance_id="worker-0"} 1.2
lmcache_blend_l0_gpu_operation_duration_seconds_count{operation="store_pre_computed",direction="gpu_to_gpu",instance_id="worker-0"} 3
lmcache_blend_l0_gpu_transfer_chunks_total{operation="retrieve_pre_computed",direction="gpu_to_cpu",instance_id="worker-0"} 7
lmcache_blend_l0_gpu_transfer_tokens_total{operation="retrieve_pre_computed",direction="gpu_to_cpu",instance_id="worker-0"} 700
""",
        expect_lmcache_mode="mp",
    )

    families = {(row["surface"], row["family"]): row for row in report["lmcache_compat"]["families"]}
    row = families[("lmcache_cacheblend", "l0_gpu_lifecycle")]
    assert row["status"] == "populated"
    assert row["support_level"] == "fixture_backed"
    assert row["support_level"] != "live_validated"
    assert report["surfaces"]["lmcache_cacheblend"]["status"] == "complete"


def test_lmcache_cacheblend_boundary_jsonl_is_sanitized_and_reported() -> None:
    evidence = read_cacheblend_boundary_evidence_jsonl(
        Path(__file__).parent / "fixtures" / "lmcache_cacheblend_boundary_evidence.jsonl"
    )

    assert evidence["present"] is True
    assert evidence["claim_status"] == "measured"
    assert evidence["row_count"] == 6
    assert evidence["event_counts"] == {
        "store_pre_computed.submitted": 1,
        "store_pre_computed.start": 1,
        "retrieve_pre_computed.start": 1,
        "retrieve_pre_computed.end": 1,
        "store_final.submitted": 1,
        "store_final.end": 1,
    }
    assert evidence["stages"] == ["retrieve_pre_computed", "store_final", "store_pre_computed"]
    encoded = json.dumps(evidence)
    for forbidden in ["token_ids", "block_ids", "hashes", "object_keys", "tok-raw", "block-raw", "hash-raw", "s3://raw-key"]:
        assert forbidden not in encoded

    report = build_observability_coverage_report(lmcache_cacheblend_boundary_evidence=evidence)
    assert report["surfaces"]["lmcache_cacheblend_boundary"]["status"] == "complete"
    assert report["lmcache_compat"]["lmcache_cacheblend_boundary_evidence"] == evidence


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


def test_lmcache_production_metrics_reference_families_are_reported() -> None:
    report = build_observability_coverage_report(
        lmcache_text=_lmcache_fixture("production_full.prom"),
        expect_lmcache_mode="embedded",
    )

    families = {(row["surface"], row["family"]): row for row in report["lmcache_compat"]["families"]}
    expected_populated = {
        "production_requests",
        "production_tokens",
        "production_hit_rate",
        "production_latency_performance",
        "production_detailed_profiling",
        "production_cache_usage_lifecycle",
        "production_remote_backend_network",
        "production_local_cpu_backend",
        "production_memory_management",
        "production_p2p",
        "production_health_internal",
        "chunk_stats",
        "production_connector_metrics",
    }
    assert report["detected_lmcache_mode"] == "embedded"
    for family in expected_populated:
        assert families[("lmcache_embedded", family)]["status"] == "populated"


def test_vllm_embedded_dynamic_offload_fixture_is_classified() -> None:
    report = build_observability_coverage_report(
        engine_text=_lmcache_fixture("vllm_embedded_dynamic_offload.prom"),
        expected_engine="vllm",
        expect_lmcache_mode="embedded",
        cpu_offload_configured=True,
    )

    compat = report["lmcache_compat"]
    families = {(row["surface"], row["family"]): row for row in compat["families"]}
    architecture = compat["detected_architecture"]
    signals = architecture["signals"]
    assert report["detected_engines"] == ["vllm"]
    assert report["detected_lmcache_mode"] == "embedded"
    assert architecture["label"] == "vllm_embedded_lmcache"
    assert architecture["claim_status"] == "measured"
    assert signals["vllm_embedded_connector_label"] is True
    assert signals["vllm_lmcache_offload_backend_label"] is True
    assert "LMCacheConnectorV1Dynamic" in architecture["connector_labels"]
    assert "lmcache" in architecture["offload_backend_labels"]
    assert families[("lmcache_embedded", "production_requests")]["status"] == "populated"
    assert families[("lmcache_embedded", "production_tokens")]["status"] == "populated"
    assert report["surfaces"]["vllm_simple_cpu_offload"]["status"] == "complete"


def test_observability_coverage_summarizes_lmcache_mp_kv_cpu_gpu_transfer() -> None:
    report = build_observability_coverage_report(
        lmcache_text="""
lmcache_mp_sm_read_requests_total 1
lmcache_mp_l1_read_keys_total 1
lmcache_mp_l0_l1_store_throughput_gbs_sum 12
lmcache_mp_l0_l1_store_throughput_gbs_count 3
lmcache_mp_l0_l1_load_throughput_gbs_sum 6
lmcache_mp_l0_l1_load_throughput_gbs_count 2
""",
        expect_lmcache_mode="mp",
    )

    transfer = report["kv_cache_offload"]["lmcache_mp_l0_l1_kv_transfer"]
    assert transfer["status"] == "populated"
    assert transfer["gpu_to_cpu_store_throughput_gbs"] == 4
    assert transfer["cpu_to_gpu_load_throughput_gbs"] == 3


def test_vllm_stale_connector_fixture_emits_user_finding() -> None:
    report = build_observability_coverage_report(
        engine_text=_lmcache_fixture("vllm_stale_connector.prom"),
        expected_engine="vllm",
        expect_lmcache_mode="embedded",
    )

    compat = report["lmcache_compat"]
    codes = {item["code"] for item in compat["diagnostic_findings"]}
    assert compat["detected_architecture"]["label"] == "vllm_embedded_lmcache"
    assert compat["detected_architecture"]["signals"]["stale_lmcache_connector_label"] is True
    assert "lmcache_stale_connector" in codes


def test_vllm_lmcache_offload_flag_without_metrics_is_inferred_only() -> None:
    report = build_observability_coverage_report(
        engine_text=_lmcache_fixture("vllm_lmcache_offload_flag_only.prom"),
        expected_engine="vllm",
    )

    compat = report["lmcache_compat"]
    architecture = compat["detected_architecture"]
    codes = {item["code"] for item in compat["diagnostic_findings"]}
    assert report["detected_lmcache_mode"] == "unknown"
    assert architecture["label"] == "vllm_embedded_lmcache"
    assert architecture["claim_status"] == "inferred"
    assert architecture["signals"]["vllm_lmcache_offload_backend_label"] is True
    assert architecture["signals"]["lmcache_embedded_metrics"] is False
    assert "vllm_lmcache_offload_flag_without_metrics" in codes


def test_sglang_embedded_lmcache_fixture_is_distinct_from_hicache() -> None:
    report = build_observability_coverage_report(
        engine_text=_lmcache_fixture("sglang_lmcache_embedded.prom"),
        expected_engine="sglang",
        expect_lmcache_mode="embedded",
    )

    compat = report["lmcache_compat"]
    architecture = compat["detected_architecture"]
    signals = architecture["signals"]
    codes = {item["code"] for item in compat["diagnostic_findings"]}
    assert report["detected_engines"] == ["sglang"]
    assert report["detected_lmcache_mode"] == "embedded"
    assert architecture["label"] == "sglang_embedded_lmcache"
    assert architecture["claim_status"] == "measured"
    assert signals["sglang_enable_lmcache_label"] is True
    assert signals["sglang_lmcache_connector_label"] is True
    assert signals["sglang_lmcradix_cache_label"] is True
    assert signals["sglang_hicache_metrics"] is True
    assert "LMCacheLayerwiseConnector" in architecture["connector_labels"]
    assert "LMCRadixCache" in architecture["cache_labels"]
    assert "sglang_lmcache_with_hicache_metrics" in codes
    assert "sglang_hicache_not_lmcache" not in codes


def test_sglang_hicache_only_fixture_does_not_claim_lmcache() -> None:
    report = build_observability_coverage_report(
        engine_text=_lmcache_fixture("sglang_hicache_only.prom"),
        expected_engine="sglang",
    )

    compat = report["lmcache_compat"]
    architecture = compat["detected_architecture"]
    codes = {item["code"] for item in compat["diagnostic_findings"]}
    assert report["detected_engines"] == ["sglang"]
    assert report["detected_lmcache_mode"] == "unknown"
    assert architecture["label"] == "unknown"
    assert architecture["signals"]["sglang_hicache_metrics"] is True
    assert architecture["signals"]["sglang_lmcache_connector_label"] is False
    assert architecture["signals"]["sglang_enable_lmcache_label"] is False
    assert "sglang_hicache_not_lmcache" in codes


def test_lmcache_mp_l0_lifecycle_populated_when_block_metrics_present() -> None:
    report = build_observability_coverage_report(
        lmcache_text="""
lmcache_mp_sm_read_requests_total 1
lmcache_mp_l1_read_keys_total 1
lmcache_mp_l1_write_keys_total 1
lmcache_mp_l1_chunk_lifetime_seconds_count 2
lmcache_mp_l0_block_lifetime_seconds_count 3
lmcache_mp_l0_block_idle_before_evict_seconds_count 3
lmcache_mp_l0_block_reuse_gap_seconds_count 3
lmcache_mp_l0_l1_store_throughput_gbs_count 2
lmcache_mp_l0_l1_load_throughput_gbs_count 2
""",
        expect_lmcache_mode="mp",
    )

    compat = report["lmcache_compat"]
    families = {(row["surface"], row["family"]): row for row in compat["families"]}
    assert families[("lmcache_mp", "l0_lifecycle")]["status"] == "populated"
    assert families[("lmcache_mp", "l0_l1_throughput")]["status"] == "populated"
    assert not any(
        gap["surface"] == "lmcache_mp" and gap["family"] == "l0_lifecycle"
        for gap in report["coverage_gaps"]
    )


def test_lmcache_mp_l0_lifecycle_missing_emits_gap_and_diagnostic() -> None:
    report = build_observability_coverage_report(
        lmcache_text="""
lmcache_mp_sm_read_requests_total 1
lmcache_mp_l1_read_keys_total 1
lmcache_mp_l1_write_keys_total 1
lmcache_mp_l1_chunk_lifetime_seconds_count 2
lmcache_mp_real_reuse_gap_seconds_count 2
lmcache_mp_l0_l1_store_throughput_gbs_count 2
lmcache_mp_l0_l1_load_throughput_gbs_count 2
""",
        expect_lmcache_mode="mp",
        mp_observability={"metrics_sample_rate": 1.0},
    )

    compat = report["lmcache_compat"]
    families = {(row["surface"], row["family"]): row for row in compat["families"]}
    assert families[("lmcache_mp", "l0_lifecycle")]["status"] == "missing"
    assert any(
        gap["surface"] == "lmcache_mp" and gap["family"] == "l0_lifecycle"
        for gap in report["coverage_gaps"]
    )
    diagnostic_codes = {item["code"] for item in compat["diagnostic_findings"]}
    upstream_codes = {item["code"] for item in compat["upstream_questions"]}
    assert "lmcache_mp_l0_lifecycle_missing" in diagnostic_codes
    assert "lmcache_mp_l0_lifecycle_missing" in upstream_codes


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


def test_lmcache_compat_promotes_parser_only_p2p_pd_log_findings() -> None:
    report = build_observability_coverage_report(
        lmcache_log_evidence={
            "line_count": 3,
            "event_counts": {
                "p2p_transfer_failure": 1,
                "pd_role_mismatch": 1,
                "nixl_request": 1,
            },
            "findings": [
                {
                    "code": "lmcache_log_p2p_transfer_failure",
                    "category": "p2p_transfer_failure",
                    "severity": "warning",
                    "message": "P2P transfer failed.",
                    "event_count": 1,
                    "evidence_status": "parser_only",
                },
                {
                    "code": "lmcache_log_pd_role_mismatch",
                    "category": "pd_role_mismatch",
                    "severity": "warning",
                    "message": "PD role mismatch.",
                    "event_count": 1,
                    "evidence_status": "parser_only",
                },
            ],
        },
    )

    findings = report["lmcache_compat"]["diagnostic_findings"]
    by_code = {item["code"]: item for item in findings}
    assert by_code["lmcache_log_p2p_transfer_failure"]["evidence_status"] == "parser_only"
    assert by_code["lmcache_log_pd_role_mismatch"]["evidence_status"] == "parser_only"
    assert report["surfaces"]["lmcache_logs"]["status"] == "complete"

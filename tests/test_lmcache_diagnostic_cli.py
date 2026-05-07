from __future__ import annotations

import json
import shutil
from pathlib import Path

from typer.testing import CliRunner

from inferguard.cli import app

FIXTURES = Path(__file__).parent / "fixtures"
PACKET_A_MISSING_PROM = FIXTURES / "lmcache_live" / "packet_a_missing_prometheus"


def test_packet_a_missing_prometheus_fixture_is_non_scoreable() -> None:
    manifest = json.loads((PACKET_A_MISSING_PROM / "fixture_manifest.json").read_text(encoding="utf-8"))

    assert manifest["row_id"] == "B1"
    assert manifest["packet_id"] == "a"
    assert manifest["score_points"] == 0
    assert manifest["acceptance_status"] == "rejected_missing_prometheus_families"
    assert manifest["redacted"] is True
    assert manifest["raw_prompts_removed"] is True
    assert manifest["raw_hashes_removed"] is True


def test_collect_lmcache_packet_a_failure_keeps_missing_prometheus_families_strict(
    tmp_path: Path,
) -> None:
    output_dir = tmp_path / "packet"

    result = CliRunner().invoke(
        app,
        [
            "collect-lmcache",
            "--output-dir",
            str(output_dir),
            "--engine-metrics-file",
            str(PACKET_A_MISSING_PROM / "vllm_metrics_loaded.prom"),
            "--lmcache-metrics-file",
            str(PACKET_A_MISSING_PROM / "lmcache_metrics_loaded.prom"),
            "--lmcache-health-file",
            str(PACKET_A_MISSING_PROM / "lmcache-health.json"),
            "--lmcache-status-file",
            str(PACKET_A_MISSING_PROM / "lmcache-status.json"),
            "--lmcache-log-file",
            str(PACKET_A_MISSING_PROM / "lmcache.log"),
            "--lmcache-lookup-hash-path",
            str(PACKET_A_MISSING_PROM / "lookup_hashes_000.jsonl"),
            "--expect-mode",
            "mp",
            "--json",
        ],
    )

    assert result.exit_code == 0, result.output
    manifest = json.loads(result.output)
    assert manifest["detected_mode"] == "mp"
    assert manifest["l2_configured"] is False
    compat = json.loads((output_dir / "lmcache_compat_report.json").read_text(encoding="utf-8"))
    missing_families = {
        item["family"]
        for item in compat["failure_reasons"]
        if item["code"] == "lmcache_mp_family_missing"
    }
    assert missing_families >= {"lookup_tokens", "l1_memory"}
    finding_by_code = {item["code"]: item for item in compat["diagnostic_findings"]}
    assert finding_by_code[
        "lmcache_mp_lookup_tokens_prometheus_missing_with_live_lookup_evidence"
    ]["evidence_status"] == "live_alternate_not_scoreable"
    assert finding_by_code[
        "lmcache_mp_l1_memory_prometheus_missing_with_http_memory_evidence"
    ]["evidence_status"] == "live_alternate_not_scoreable"


def test_lmcache_compat_cli_shows_b1_missing_prometheus_families() -> None:
    result = CliRunner().invoke(
        app,
        [
            "lmcache-compat",
            "--engine-metrics-file",
            str(PACKET_A_MISSING_PROM / "vllm_metrics_loaded.prom"),
            "--lmcache-metrics-file",
            str(PACKET_A_MISSING_PROM / "lmcache_metrics_loaded.prom"),
            "--lmcache-http-evidence-file",
            str(PACKET_A_MISSING_PROM / "lmcache_http_evidence.json"),
            "--lmcache-log-evidence-file",
            str(PACKET_A_MISSING_PROM / "lmcache_log_evidence.json"),
            "--lmcache-lookup-hash-evidence-file",
            str(PACKET_A_MISSING_PROM / "lmcache_lookup_hash_evidence.json"),
            "--expect-mode",
            "mp",
            "--fail-on",
            "missing-required",
            "--json",
        ],
    )

    assert result.exit_code == 1
    payload = json.loads(result.output)
    assert payload["detected_mode"] == "mp"
    assert payload["detected_architecture"]["label"] == "vllm_mp_lmcache"
    missing_families = {
        item["family"]
        for item in payload["failure_reasons"]
        if item["code"] == "lmcache_mp_family_missing"
    }
    assert missing_families >= {"lookup_tokens", "l1_memory"}
    question_codes = {item["code"] for item in payload["upstream_questions"]}
    assert question_codes >= {
        "lmcache_mp_lookup_counters_missing",
        "lmcache_mp_l1_memory_gauge_missing",
        "vllm_external_prefix_no_hits",
    }


def test_observability_coverage_cli_lists_b1_family_gaps() -> None:
    result = CliRunner().invoke(
        app,
        [
            "observability-coverage",
            "--engine-metrics-file",
            str(PACKET_A_MISSING_PROM / "vllm_metrics_loaded.prom"),
            "--lmcache-metrics-file",
            str(PACKET_A_MISSING_PROM / "lmcache_metrics_loaded.prom"),
            "--lmcache-http-evidence-file",
            str(PACKET_A_MISSING_PROM / "lmcache_http_evidence.json"),
            "--lmcache-log-evidence-file",
            str(PACKET_A_MISSING_PROM / "lmcache_log_evidence.json"),
            "--lmcache-lookup-hash-evidence-file",
            str(PACKET_A_MISSING_PROM / "lmcache_lookup_hash_evidence.json"),
            "--expected-engine",
            "vllm",
            "--expect-lmcache-mode",
            "mp",
            "--json",
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["detected_lmcache_mode"] == "mp"
    gaps = {(gap["surface"], gap["family"], gap["status"]) for gap in payload["coverage_gaps"]}
    assert ("lmcache_mp", "lookup_tokens", "missing") in gaps
    assert ("lmcache_mp", "l1_memory", "missing") in gaps
    assert ("lmcache_mp", "l2_counters", "missing") not in gaps


def test_diagnose_bottleneck_cli_surfaces_b1_missing_prometheus_family(tmp_path: Path) -> None:
    job_dir = tmp_path / "packet_a_missing_prometheus_job"
    shutil.copytree(FIXTURES / "job_dirs" / "not_enough_evidence", job_dir)
    compat_path = job_dir / "metrics" / "lmcache_compat_report.json"
    compat = CliRunner().invoke(
        app,
        [
            "lmcache-compat",
            "--engine-metrics-file",
            str(PACKET_A_MISSING_PROM / "vllm_metrics_loaded.prom"),
            "--lmcache-metrics-file",
            str(PACKET_A_MISSING_PROM / "lmcache_metrics_loaded.prom"),
            "--lmcache-http-evidence-file",
            str(PACKET_A_MISSING_PROM / "lmcache_http_evidence.json"),
            "--lmcache-log-evidence-file",
            str(PACKET_A_MISSING_PROM / "lmcache_log_evidence.json"),
            "--lmcache-lookup-hash-evidence-file",
            str(PACKET_A_MISSING_PROM / "lmcache_lookup_hash_evidence.json"),
            "--expect-mode",
            "mp",
            "--output",
            str(compat_path),
            "--json",
        ],
    )
    assert compat.exit_code == 0, compat.output

    output_dir = tmp_path / "diagnosis"
    diagnosis = CliRunner().invoke(
        app,
        [
            "diagnose-bottleneck",
            "--job-dir",
            str(job_dir),
            "--output-dir",
            str(output_dir),
            "--json-only",
        ],
    )

    assert diagnosis.exit_code == 0, diagnosis.output
    payload = json.loads((output_dir / "bottleneck_diagnosis.json").read_text(encoding="utf-8"))
    assert payload["verdict"] == "not_enough_evidence"
    assert payload["claim_status"] == "not_proven"
    assert payload["rule_fired"] == "lmcache_mp_family_missing"
    failure_families = {
        item["family"] for item in payload["metric_values"]["lmcache_compat.failure_reasons"]
    }
    assert failure_families >= {"lookup_tokens", "l1_memory"}
    assert "lookup_tokens" in payload["reasoning"]

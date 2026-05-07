import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from inferguard.diagnose_bottleneck import (
    BOTTLENECK_DIAGNOSIS_SCHEMA_VERSION,
    diagnose,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
RUNNER = REPO_ROOT / "scripts" / "run_neocloud_nvidia_profile.py"
FIXTURES = Path(__file__).resolve().parent / "fixtures" / "job_dirs"


def _diagnosis(name: str) -> dict:
    return diagnose(FIXTURES / name).to_dict()


def _write_lmcache_compat_report(
    root: Path,
    *,
    detected_mode: str = "mp",
    diagnostic_findings: list[dict] | None = None,
    failure_reasons: list[dict] | None = None,
    upstream_questions: list[dict] | None = None,
    detected_architecture: dict | None = None,
) -> None:
    compat = {
        "schema_version": "inferguard-observability-compat/v1",
        "detected_mode": detected_mode,
        "detected_architecture": detected_architecture
        or {"label": "vllm_mp_lmcache", "claim_status": "measured"},
        "diagnostic_findings": diagnostic_findings or [],
        "failure_reasons": failure_reasons or [],
        "upstream_questions": upstream_questions or [],
    }
    (root / "metrics" / "lmcache_compat_report.json").write_text(
        json.dumps(compat, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def test_prefill_bound_fixture() -> None:
    diagnosis = _diagnosis("prefill_bound")

    assert diagnosis["verdict"] == "prefill_bound"
    assert diagnosis["claim_status"] == "measured"


def test_decode_bound_fixture() -> None:
    diagnosis = _diagnosis("decode_bound")

    assert diagnosis["verdict"] == "decode_bound"


def test_queue_bound_fixture() -> None:
    diagnosis = _diagnosis("queue_bound")

    assert diagnosis["verdict"] == "queue_bound"


def test_kv_bound_fixture() -> None:
    diagnosis = _diagnosis("kv_bound")

    assert diagnosis["verdict"] == "kv_bound"


def test_network_bound_fixture() -> None:
    diagnosis = _diagnosis("network_bound")

    assert diagnosis["verdict"] == "network_bound"
    assert any("nccl" in path for path in diagnosis["evidence_paths"])


def test_network_bound_reads_locked_nccl_text_path(tmp_path: Path) -> None:
    root = tmp_path / "network_text"
    shutil.copytree(FIXTURES / "network_bound", root)
    shutil.rmtree(root / "nccl")
    preflight = root / "preflight"
    preflight.mkdir()
    (preflight / "nccl_all_reduce.txt").write_text(
        "# all_reduce_perf\nbusbw: 220\nexpected_busbw_gbps: 500\n",
        encoding="utf-8",
    )

    diagnosis = diagnose(root).to_dict()

    assert diagnosis["verdict"] == "network_bound"
    assert any("preflight/nccl_all_reduce.txt" in path for path in diagnosis["evidence_paths"])


def test_host_bound_fixture() -> None:
    diagnosis = _diagnosis("host_bound")

    assert diagnosis["verdict"] == "host_bound"


def test_missing_engine_metrics_no_verdict() -> None:
    diagnosis = _diagnosis("no_engine_metrics")

    assert diagnosis["verdict"] == "not_enough_evidence"
    assert diagnosis["claim_status"] == "not_proven"


def test_multi_node_no_nccl_no_network_verdict() -> None:
    diagnosis = _diagnosis("multi_node_no_nccl")

    assert diagnosis["verdict"] != "network_bound"
    assert diagnosis["verdict"] == "not_enough_evidence"
    assert diagnosis["claim_status"] == "not_proven"


def test_sglang_b200_fp8_no_prefill_verdict() -> None:
    diagnosis = _diagnosis("sglang_b200_fp8_high_ttft")

    assert diagnosis["verdict"] != "prefill_bound"
    assert any(
        downgrade["reason"].startswith("sglang_chunked_prefill_bug")
        for downgrade in diagnosis.get("downgrades", [])
    )


def test_failed_launch_overrides() -> None:
    diagnosis = _diagnosis("model_launch_bound")

    assert diagnosis["verdict"] == "model_launch_bound"


def test_external_validated_healthcheck_is_not_launch_bound(tmp_path: Path) -> None:
    root = tmp_path / "external_validated"
    shutil.copytree(FIXTURES / "prefill_bound", root)
    healthcheck_path = root / "launch" / "healthcheck.json"
    healthcheck = json.loads(healthcheck_path.read_text(encoding="utf-8"))
    healthcheck["status"] = "external_validated"
    healthcheck_path.write_text(
        json.dumps(healthcheck, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    diagnosis = diagnose(root).to_dict()

    assert diagnosis["verdict"] == "prefill_bound"


def test_not_enough_fixture() -> None:
    diagnosis = _diagnosis("not_enough_evidence")

    assert diagnosis["verdict"] == "not_enough_evidence"


def test_lmcache_compat_missing_signal_becomes_specific_diagnosis(tmp_path: Path) -> None:
    root = tmp_path / "lmcache_mp_missing_signal"
    shutil.copytree(FIXTURES / "not_enough_evidence", root)
    _write_lmcache_compat_report(
        root,
        upstream_questions=[
            {
                "code": "lmcache_mp_lookup_counters_missing",
                "owner_question": "Should lookup counters populate?",
            }
        ],
    )

    diagnosis = diagnose(root).to_dict()

    assert diagnosis["verdict"] == "not_enough_evidence"
    assert diagnosis["claim_status"] == "inferred"
    assert diagnosis["rule_fired"] == "lmcache_mp_lookup_counters_missing"


def test_lmcache_compat_surfaces_even_without_request_profile(tmp_path: Path) -> None:
    root = tmp_path / "lmcache_packet_without_request_profile"
    shutil.copytree(FIXTURES / "not_enough_evidence", root)
    shutil.rmtree(root / "request_profile")
    _write_lmcache_compat_report(
        root,
        diagnostic_findings=[
            {
                "code": "lmcache_mp_empty_cache_salt",
                "severity": "info",
                "message": "LMCache MP lookup metrics contain an empty cache_salt label.",
            }
        ],
    )

    diagnosis = diagnose(root).to_dict()

    assert diagnosis["verdict"] == "not_enough_evidence"
    assert diagnosis["claim_status"] == "inferred"
    assert diagnosis["rule_fired"] == "lmcache_mp_empty_cache_salt"
    assert diagnosis["metric_values"]["lmcache_compat.detected_architecture"]["label"] == (
        "vllm_mp_lmcache"
    )


def test_lmcache_compat_diagnostic_findings_become_specific_diagnosis(tmp_path: Path) -> None:
    root = tmp_path / "lmcache_mp_l2_failure"
    shutil.copytree(FIXTURES / "not_enough_evidence", root)
    _write_lmcache_compat_report(
        root,
        detected_architecture={"label": "vllm_mp_lmcache", "claim_status": "measured"},
        diagnostic_findings=[
            {
                "code": "lmcache_mp_low_hit_rate",
                "severity": "warning",
                "message": "LMCache MP token hit rate is below 30%.",
                "metrics": {"hit_rate": 0.1},
            },
            {
                "code": "lmcache_mp_l2_failures",
                "severity": "critical",
                "message": "LMCache MP reports failed L2 store or prefetch work.",
                "metrics": {"l2_failed_operations_or_keys": 1},
            },
        ],
    )

    diagnosis = diagnose(root).to_dict()

    assert diagnosis["verdict"] == "not_enough_evidence"
    assert diagnosis["claim_status"] == "measured"
    assert diagnosis["rule_fired"] == "lmcache_mp_l2_failures"
    assert diagnosis["metric_values"]["lmcache_compat.detected_architecture"]["label"] == "vllm_mp_lmcache"


def test_lmcache_compat_new_evidence_surfaces_become_diagnosis(tmp_path: Path) -> None:
    root = tmp_path / "lmcache_cacheblend_lookup_hash"
    shutil.copytree(FIXTURES / "not_enough_evidence", root)
    _write_lmcache_compat_report(
        root,
        diagnostic_findings=[
            {
                "code": "lmcache_lookup_hash_missing_rotation_config",
                "severity": "info",
                "message": "Lookup-hash JSONL is present without bounded rotation evidence.",
            },
            {
                "code": "lmcache_cacheblend_retrieve_failures",
                "severity": "warning",
                "message": "CacheBlend retrieve failures were reported.",
                "metrics": {"lmcache_blend_retrieve_failures_total": 2},
            },
        ],
    )

    diagnosis = diagnose(root).to_dict()

    assert diagnosis["rule_fired"] == "lmcache_cacheblend_retrieve_failures"
    assert diagnosis["claim_status"] == "measured"
    assert any("lmcache_compat_report.json" in path for path in diagnosis["evidence_paths"])


@pytest.mark.parametrize(
    ("code", "severity", "expected_claim"),
    [
        ("lmcache_prometheus_unreachable", "warning", "measured"),
        ("lmcache_mp_observability_disabled", "warning", "measured"),
        ("lmcache_logging_disabled", "warning", "measured"),
        ("otel_tracing_enabled_but_no_spans", "warning", "measured"),
        ("lmcache_mp_trace_enabled_but_no_trace_artifact", "warning", "measured"),
        ("lmcache_trace_file_parse_failure", "warning", "measured"),
        ("lmcache_trace_replay_failure", "warning", "measured"),
        ("lmcache_mp_l1_no_reads", "info", "inferred"),
        ("lmcache_mp_l1_no_writes", "info", "inferred"),
        ("lmcache_mp_l1_eviction_pressure", "warning", "measured"),
        ("lmcache_mp_l1_saturation", "warning", "measured"),
        ("lmcache_mp_l1_leak", "warning", "measured"),
        ("lmcache_mp_sampled_histogram_sparse", "info", "inferred"),
        ("lmcache_mp_real_reuse_missing", "info", "inferred"),
        ("lmcache_mp_real_reuse_low", "warning", "measured"),
        ("lmcache_mp_l0_lifecycle_missing", "info", "inferred"),
        ("lmcache_mp_l0_l1_throughput_missing", "info", "inferred"),
        ("lmcache_mp_l0_l1_throughput_low", "warning", "measured"),
        ("lmcache_mp_l2_not_configured", "info", "inferred"),
        ("lmcache_mp_l2_store_missing", "info", "inferred"),
        ("lmcache_mp_l2_prefetch_missing", "info", "inferred"),
        ("lmcache_mp_l2_load_missing", "info", "inferred"),
        ("lmcache_mp_l2_store_backlog", "warning", "measured"),
        ("lmcache_mp_l2_load_backlog", "warning", "measured"),
        ("lmcache_mp_l2_throughput_low", "warning", "measured"),
        ("lmcache_mp_l2_failures", "critical", "measured"),
        ("lmcache_mp_l2_prefetch_memory_crowding", "warning", "measured"),
        ("lmcache_lookup_zero_hit", "warning", "measured"),
        ("lmcache_lookup_low_hit", "warning", "measured"),
        ("vllm_l0_excluded_caveat", "info", "inferred"),
        ("lmcache_cache_salt_cross_hit", "critical", "measured"),
        ("lmcache_cache_salt_cardinality_risk", "warning", "measured"),
        ("lmcache_cache_salt_quota_risk", "warning", "measured"),
        ("lmcache_mp_eventbus_taildrop_unobservable", "warning", "measured"),
        ("lmcache_mp_eventbus_pressure", "warning", "measured"),
        ("lmcache_production_metrics_missing", "info", "inferred"),
        ("lmcache_production_health_unhealthy", "warning", "measured"),
        ("lmcache_remote_backend_unhealthy", "warning", "measured"),
        ("lmcache_chunk_stats_disabled", "info", "inferred"),
        ("lmcache_chunk_stats_low_reuse", "warning", "measured"),
        ("lmcache_connector_invalid_blocks", "critical", "measured"),
    ],
)
def test_lmcache_checklist_compat_findings_become_specific_diagnoses(
    tmp_path: Path, code: str, severity: str, expected_claim: str
) -> None:
    root = tmp_path / code
    shutil.copytree(FIXTURES / "not_enough_evidence", root)
    _write_lmcache_compat_report(
        root,
        diagnostic_findings=[
            {
                "code": code,
                "severity": severity,
                "message": f"Fixture-backed LMCache checklist finding: {code}.",
                "metrics": {"fixture": code},
            }
        ],
    )

    diagnosis = diagnose(root).to_dict()

    assert diagnosis["verdict"] == "not_enough_evidence"
    assert diagnosis["rule_fired"] == code
    assert diagnosis["claim_status"] == expected_claim
    assert diagnosis["metric_values"]["lmcache_compat.diagnostic_findings"][0]["code"] == code


def test_lmcache_compat_failure_reasons_override_findings(tmp_path: Path) -> None:
    root = tmp_path / "lmcache_prometheus_unreachable"
    shutil.copytree(FIXTURES / "not_enough_evidence", root)
    _write_lmcache_compat_report(
        root,
        failure_reasons=[
            {
                "code": "lmcache_prometheus_unreachable",
                "message": "LMCache Prometheus endpoint was configured but unreachable.",
            }
        ],
        diagnostic_findings=[
            {
                "code": "lmcache_mp_low_hit_rate",
                "severity": "warning",
                "message": "Low hit rate should not mask missing metrics access.",
            }
        ],
    )

    diagnosis = diagnose(root).to_dict()

    assert diagnosis["rule_fired"] == "lmcache_prometheus_unreachable"
    assert diagnosis["claim_status"] == "not_proven"
    assert diagnosis["metric_values"]["lmcache_compat.failure_reasons"][0]["code"] == (
        "lmcache_prometheus_unreachable"
    )


def test_lmcache_embedded_and_unknown_mode_findings_are_not_dropped(tmp_path: Path) -> None:
    for mode, code in (
        ("embedded", "lmcache_stale_connector"),
        ("unknown", "vllm_lmcache_offload_flag_without_metrics"),
    ):
        root = tmp_path / f"{mode}_{code}"
        shutil.copytree(FIXTURES / "not_enough_evidence", root)
        _write_lmcache_compat_report(
            root,
            detected_mode=mode,
            diagnostic_findings=[
                {
                    "code": code,
                    "severity": "warning",
                    "message": f"{mode} mode finding should be surfaced.",
                }
            ],
        )

        diagnosis = diagnose(root).to_dict()

        assert diagnosis["rule_fired"] == code
        assert diagnosis["claim_status"] == "measured"


def test_lmcache_log_evidence_becomes_specific_diagnosis(tmp_path: Path) -> None:
    root = tmp_path / "lmcache_log_pd"
    shutil.copytree(FIXTURES / "not_enough_evidence", root)
    (root / "metrics" / "lmcache_log_evidence.json").write_text(
        json.dumps(
            {
                "schema_version": "inferguard-lmcache-logs/v1",
                "event_counts": {"pd_sender": 1, "pd_receiver": 1, "p2p_peer": 0},
                "config": {"enable_pd": True, "stale_lmcache_connector_seen": False},
                "mode_candidates": ["disaggregated_prefill"],
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    diagnosis = diagnose(root).to_dict()

    assert diagnosis["rule_fired"] == "lmcache_log_pd_evidence_present"
    assert diagnosis["claim_status"] == "inferred"
    assert "disaggregated_prefill" in diagnosis["metric_values"]["lmcache_log.mode_candidates"]


def test_lmcache_log_parser_only_p2p_failure_becomes_specific_diagnosis(tmp_path: Path) -> None:
    root = tmp_path / "lmcache_log_p2p_failure"
    shutil.copytree(FIXTURES / "not_enough_evidence", root)
    (root / "metrics" / "lmcache_log_evidence.json").write_text(
        json.dumps(
            {
                "schema_version": "inferguard-lmcache-logs/v1",
                "event_counts": {"p2p_transfer_failure": 1, "pd_role_mismatch": 0},
                "config": {"stale_lmcache_connector_seen": False},
                "mode_candidates": ["p2p"],
                "findings": [
                    {
                        "code": "lmcache_log_p2p_transfer_failure",
                        "category": "p2p_transfer_failure",
                        "severity": "warning",
                        "message": "P2P transfer failed.",
                        "event_count": 1,
                        "evidence_status": "parser_only",
                    }
                ],
                "numeric_hints": {"p2p_transfer_speed": []},
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    diagnosis = diagnose(root).to_dict()

    assert diagnosis["rule_fired"] == "lmcache_log_p2p_transfer_failure"
    assert diagnosis["claim_status"] == "inferred"
    assert diagnosis["metric_values"]["lmcache_log.findings"][0]["evidence_status"] == "parser_only"


def test_schema_version_locked() -> None:
    diagnosis = _diagnosis("prefill_bound")

    assert diagnosis["schema_version"] == BOTTLENECK_DIAGNOSIS_SCHEMA_VERSION


def test_stdout_summary_format(tmp_path: Path) -> None:
    output_dir = tmp_path / "diagnosis"
    completed = subprocess.run(
        [
            sys.executable,
            str(RUNNER),
            "diagnose-bottleneck",
            "--job-dir",
            str(FIXTURES / "prefill_bound"),
            "--output-dir",
            str(output_dir),
        ],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    assert re.match(
        r"^inferguard diagnose-bottleneck: verdict=\w+ confidence=[\d.]+ evidence_paths=\d+ claim=\w+\n$",
        completed.stdout,
    )
    diagnosis = json.loads((output_dir / "bottleneck_diagnosis.json").read_text(encoding="utf-8"))
    assert diagnosis["verdict"] == "prefill_bound"


def test_evidence_attached() -> None:
    diagnosis = _diagnosis("prefill_bound")

    assert diagnosis["evidence_paths"]
    assert diagnosis["metric_values"]
    assert len(diagnosis["primary_evidence"]) >= 1
    for entry in diagnosis["primary_evidence"]:
        assert entry["metric"]
        assert entry["source"]
        assert "value" in entry or "value_p95" in entry

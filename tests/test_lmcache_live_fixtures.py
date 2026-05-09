from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pytest

from inferguard.disagg.adapters.lmcache import parse_lmcache_prometheus

LIVE_FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "lmcache_live"
PACKET_A_DIR = LIVE_FIXTURE_ROOT / "packet_a"

# Packet A launch/config proof uses compact command artifacts already emitted by
# scripts/lmcache_mp_modal_packet_lab.py at the run root. Accepted live fixtures
# must copy these files verbatim or as sanitized JSON lists with the same names.
PACKET_A_REQUIRED_FILES = (
    "fixture_manifest.json",
    "lmcache_command.json",
    "lmcache_env.json",
    "vllm_command.json",
    "vllm_metrics_loaded.prom",
    "lmcache_metrics_loaded.prom",
    "packet_manifest.json",
    "lmcache_compat_report.json",
    "observability_coverage.json",
    "bottleneck_diagnosis.json",
    "lmcache_http_evidence.json",
    "lmcache_log_evidence.json",
    "lmcache_trace_evidence.json",
    "lmcache_trace_replay_evidence.json",
)
PACKET_B_REQUIRED_FILES = (
    *PACKET_A_REQUIRED_FILES,
    "workload_manifest.json",
    "traffic_requests.jsonl",
    "packet-b-lifecycle-evidence.json",
    "agent_kv_offload_report.json",
)
PACKET_C_REQUIRED_FILES = (
    *PACKET_A_REQUIRED_FILES,
    "workload_manifest.json",
    "traffic_requests.jsonl",
    "lmcache_l2_config.json",
)
PACKET_B_REQUIRED_FAMILIES = (
    "lookup_reuse",
    "lookup_hits",
    "l1_lifecycle",
    "l0_lifecycle",
    "real_reuse",
    "l1_eviction",
    "l0_l1_throughput",
)

_SECRET_PATTERN = re.compile(
    r"(HF_TOKEN|OPENAI_API_KEY|ANTHROPIC_API_KEY|PASSWORD|SECRET|CREDENTIAL|AUTH_TOKEN)",
    re.IGNORECASE,
)
_RAW_PROMPT_PATTERN = re.compile(r'"prompt"\s*:|"messages"\s*:', re.IGNORECASE)
_RAW_HASH_PATTERN = re.compile(r"raw-secret-hash|raw_hash|raw-hash", re.IGNORECASE)


def test_landed_live_fixtures_are_sanitized_and_pass_acceptance_contract() -> None:
    """Validate accepted live fixtures if present without inventing a fake one.

    Workstream 1/B1 prep should land this executable gate before any Modal artifact is
    imported. With no fixture present, this test proves the gate is armed but does not
    move score. Once `tests/fixtures/lmcache_live/packet_a/fixture_manifest.json` is
    imported with `acceptance_status=accepted`, the same test enforces the B1 contract.
    """

    for fixture_dir in _accepted_live_fixture_dirs():
        if fixture_dir.name == "packet_a":
            _assert_packet_a_b1_acceptance(fixture_dir)
        elif fixture_dir.name == "packet_b":
            _assert_packet_b_c1_acceptance(fixture_dir)
        elif fixture_dir.name == "packet_c":
            _assert_packet_c_d1_acceptance(fixture_dir)
        else:
            raise AssertionError(f"unknown accepted LMCache live fixture: {fixture_dir}")


def test_packet_a_acceptance_contract_rejects_non_live_or_incomplete_fixture(tmp_path: Path) -> None:
    fixture_dir = tmp_path / "packet_a"
    fixture_dir.mkdir()
    _write_json(
        fixture_dir / "fixture_manifest.json",
        {
            "row_id": "B1",
            "packet_id": "a",
            "source": "synthetic_unit_test",
            "score_points": 10,
            "redacted": True,
            "raw_hashes_removed": True,
            "raw_prompts_removed": True,
            "acceptance_status": "accepted",
        },
    )

    with pytest.raises(AssertionError, match="live_modal_h100"):
        _assert_packet_a_manifest(_read_json(fixture_dir / "fixture_manifest.json"))

    manifest = _read_json(fixture_dir / "fixture_manifest.json")
    manifest["source"] = "live_modal_h100"
    _write_json(fixture_dir / "fixture_manifest.json", manifest)

    with pytest.raises(AssertionError, match="missing required B1 fixture artifact"):
        _assert_packet_a_b1_acceptance(fixture_dir)


def test_packet_b_acceptance_contract_rejects_incomplete_lifecycle_fixture(tmp_path: Path) -> None:
    fixture_dir = tmp_path / "packet_b"
    fixture_dir.mkdir()
    _write_json(
        fixture_dir / "fixture_manifest.json",
        {
            "row_id": "C1",
            "packet_id": "b",
            "benchmark_id": "LC1",
            "workload_profile": "long_context_agent_kv_offload",
            "raw_prompts_recorded": False,
            "source": "live_modal_h100",
            "score_points": 6,
            "redacted": True,
            "raw_hashes_removed": True,
            "raw_prompts_removed": True,
            "acceptance_status": "accepted",
        },
    )

    with pytest.raises(AssertionError, match="missing required C1 fixture artifact"):
        _assert_packet_b_c1_acceptance(fixture_dir)


def _accepted_live_fixture_dirs() -> list[Path]:
    if not LIVE_FIXTURE_ROOT.exists():
        return []
    dirs: list[Path] = []
    for manifest_path in sorted(LIVE_FIXTURE_ROOT.glob("*/fixture_manifest.json")):
        manifest = _read_json(manifest_path)
        if manifest.get("acceptance_status") == "accepted":
            dirs.append(manifest_path.parent)
    return dirs


def _assert_packet_a_b1_acceptance(fixture_dir: Path) -> None:
    manifest = _read_json(fixture_dir / "fixture_manifest.json")
    _assert_packet_a_manifest(manifest)
    _assert_required_files(fixture_dir, PACKET_A_REQUIRED_FILES)
    _assert_fixture_sanitized(fixture_dir)
    _assert_shared_mp_artifact_metric_acceptance(fixture_dir)


def _assert_shared_mp_artifact_metric_acceptance(fixture_dir: Path) -> None:
    packet_manifest = _read_json(fixture_dir / "packet_manifest.json")
    compat = _read_json(fixture_dir / "lmcache_compat_report.json")
    coverage = _read_json(fixture_dir / "observability_coverage.json")
    diagnosis = _read_json(fixture_dir / "bottleneck_diagnosis.json")
    trace = _read_json(fixture_dir / "lmcache_trace_evidence.json")
    trace_replay = _read_json(fixture_dir / "lmcache_trace_replay_evidence.json")
    lmcache_command = _read_json_list(fixture_dir / "lmcache_command.json")
    lmcache_env = _read_json(fixture_dir / "lmcache_env.json")
    vllm_command = _read_json_list(fixture_dir / "vllm_command.json")

    _assert_packet_a_launch_proof(
        lmcache_command=lmcache_command,
        lmcache_env=lmcache_env,
        vllm_command=vllm_command,
    )

    metrics = parse_lmcache_prometheus(
        (fixture_dir / "lmcache_metrics_loaded.prom").read_text(encoding="utf-8")
    )
    assert metrics.lmcache_mp_mode_enabled is True
    _assert_positive(metrics.lmcache_sm_read_requests, "lmcache_sm_read_requests")
    _assert_positive(metrics.lmcache_sm_write_requests, "lmcache_sm_write_requests")
    _assert_positive(metrics.lmcache_l1_read_keys, "lmcache_l1_read_keys")
    _assert_positive(metrics.lmcache_l1_write_keys, "lmcache_l1_write_keys")
    _assert_positive(metrics.lmcache_l1_memory_usage_bytes, "lmcache_l1_memory_usage_bytes")
    _assert_positive(metrics.lmcache_lookup_requested_tokens, "lmcache_lookup_requested_tokens")
    _assert_positive(metrics.lmcache_lookup_hit_tokens, "lmcache_lookup_hit_tokens")

    assert packet_manifest.get("detected_mode") == "mp"
    assert packet_manifest.get("l2_configured") is False
    assert compat.get("detected_mode") == "mp"
    assert compat.get("l2_configured") is False
    assert compat.get("detected_architecture", {}).get("label") == "vllm_mp_lmcache"
    assert compat.get("detected_architecture", {}).get("claim_status") in {"measured", "inferred"}
    assert coverage.get("detected_lmcache_mode") == "mp"
    assert coverage.get("config", {}).get("l2_configured") is False

    assert trace.get("claim_status") == "measured"
    _assert_positive(trace.get("record_count"), "lmcache_trace_evidence.record_count")
    assert trace_replay.get("claim_status") == "measured"

    finding_codes = {
        item.get("code")
        for item in diagnosis.get("findings", []) + diagnosis.get("diagnostic_findings", [])
        if isinstance(item, dict)
    }
    if diagnosis.get("rule_fired"):
        finding_codes.add(diagnosis["rule_fired"])
    metric_values = diagnosis.get("metric_values", {})
    has_lmcache_diagnosis = any(str(code).startswith("lmcache") for code in finding_codes)
    has_lmcache_arch_confirmation = (
        metric_values.get("lmcache_compat.detected_architecture", {}).get("label")
        == "vllm_mp_lmcache"
    )
    assert has_lmcache_diagnosis or has_lmcache_arch_confirmation, (
        "B1 diagnosis must include an LMCache-specific finding/rule or measured architecture confirmation"
    )


def _assert_packet_b_c1_acceptance(fixture_dir: Path) -> None:
    manifest = _read_json(fixture_dir / "fixture_manifest.json")
    _assert_packet_b_manifest(manifest)
    _assert_required_files(fixture_dir, PACKET_B_REQUIRED_FILES, row_id="C1")
    _assert_fixture_sanitized(fixture_dir)

    _assert_shared_mp_artifact_metric_acceptance(fixture_dir)
    workload = _read_json(fixture_dir / "workload_manifest.json")
    evidence = _read_json(fixture_dir / "packet-b-lifecycle-evidence.json")
    lmcache_command = _read_json_list(fixture_dir / "lmcache_command.json")
    compat = _read_json(fixture_dir / "lmcache_compat_report.json")

    assert workload.get("packet_id") == "b"
    assert workload.get("sdlc_row_id") == "C1"
    assert workload.get("benchmark_id") == "LC1"
    assert workload.get("workload") == "reuse_eviction"
    assert workload.get("workload_profile") == "long_context_agent_kv_offload"
    assert str(workload.get("trace_source", "")).startswith("traces/isb1-dsv4-agent")
    assert workload.get("metrics_sample_rate") == 1.0
    assert workload.get("raw_prompts_recorded") is False
    _assert_packet_b_traffic_rows_metadata_only(fixture_dir / "traffic_requests.jsonl")
    assert [phase.get("phase") for phase in workload.get("phases", [])] == [
        "warm",
        "pressure",
        "retest",
    ]
    assert _cmd_value(lmcache_command, "--metrics-sample-rate") == "1.0"
    assert _cmd_value(lmcache_command, "--l1-size-gb") == str(workload.get("l1_size_gb"))

    assert evidence.get("schema_version") == "inferguard-lmcache-mp-packet-b-lifecycle/v1"
    assert evidence.get("claim_status") == "measured"
    assert evidence.get("metrics_sample_rate") == 1.0
    assert evidence.get("missing_required_families") == []
    families = evidence.get("required_families")
    assert isinstance(families, dict)
    for family in PACKET_B_REQUIRED_FAMILIES:
        row = families.get(family)
        assert isinstance(row, dict), f"missing Packet B family row: {family}"
        assert row.get("status") == "populated", f"Packet B family not populated: {family}"
        assert row.get("matched_metrics"), f"Packet B family has no matched metric: {family}"

    family_rows = {
        (row.get("surface"), row.get("family")): row
        for row in compat.get("families", [])
        if isinstance(row, dict)
    }
    for family in ("l1_lifecycle", "l0_lifecycle", "real_reuse", "l0_l1_throughput"):
        row = family_rows.get(("lmcache_mp", family))
        assert row and row.get("status") == "populated", f"compat report missing Packet B {family}"


def _assert_packet_c_d1_acceptance(fixture_dir: Path) -> None:
    manifest = _read_json(fixture_dir / "fixture_manifest.json")
    _assert_packet_c_manifest(manifest)
    _assert_required_files(fixture_dir, PACKET_C_REQUIRED_FILES, row_id="D1")
    _assert_fixture_sanitized(fixture_dir)

    workload = _read_json(fixture_dir / "workload_manifest.json")
    l2_config = _read_json(fixture_dir / "lmcache_l2_config.json")
    lmcache_command = _read_json_list(fixture_dir / "lmcache_command.json")
    packet_manifest = _read_json(fixture_dir / "packet_manifest.json")
    compat = _read_json(fixture_dir / "lmcache_compat_report.json")
    coverage = _read_json(fixture_dir / "observability_coverage.json")
    trace = _read_json(fixture_dir / "lmcache_trace_evidence.json")
    trace_replay = _read_json(fixture_dir / "lmcache_trace_replay_evidence.json")

    assert workload.get("packet_id") == "c"
    assert workload.get("workload") == "l2_reuse"
    assert workload.get("raw_prompts_recorded") is False
    _assert_packet_b_traffic_rows_metadata_only(fixture_dir / "traffic_requests.jsonl")

    assert _cmd_value(lmcache_command, "--l2-store-policy") == "skip_l1"
    assert _cmd_value(lmcache_command, "--l2-prefetch-policy") == "default"
    adapter = json.loads(_cmd_value(lmcache_command, "--l2-adapter"))
    assert adapter == {"type": "mock", "max_size_gb": 80, "mock_bandwidth_gb": 4}
    assert l2_config.get("adapter") == adapter

    assert packet_manifest.get("detected_mode") == "mp"
    assert packet_manifest.get("l2_configured") is True
    assert compat.get("failure_reasons") == []
    assert compat.get("detected_mode") == "mp"
    assert compat.get("l2_configured") is True
    assert coverage.get("detected_lmcache_mode") == "mp"
    assert coverage.get("config", {}).get("l2_configured") is True

    family_rows = {
        (row.get("surface"), row.get("family")): row
        for row in compat.get("families", [])
        if isinstance(row, dict)
    }
    for family in ("l2_counters", "l2_throughput"):
        row = family_rows.get(("lmcache_mp", family))
        assert row and row.get("status") == "populated", f"compat report missing Packet C {family}"
        assert row.get("matched_metrics"), f"Packet C family has no matched metric: {family}"
    l2_summary = compat.get("lmcache_l2_summary", {})
    _assert_positive(l2_summary.get("store_tasks"), "lmcache_l2_summary.store_tasks")
    _assert_positive(l2_summary.get("store_completed"), "lmcache_l2_summary.store_completed")
    _assert_positive(l2_summary.get("load_completed"), "lmcache_l2_summary.load_completed")

    assert trace.get("claim_status") == "measured"
    _assert_positive(trace.get("record_count"), "lmcache_trace_evidence.record_count")
    assert trace_replay.get("claim_status") == "measured"


def _assert_packet_b_traffic_rows_metadata_only(path: Path) -> None:
    required = {
        "request_index",
        "phase",
        "prefix_group",
        "prompt_chars",
        "trace_id",
        "synthetic_redaction_status",
        "cache_salt",
    }
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert rows, "Packet B traffic request log must contain metadata rows"
    for row in rows:
        assert "prompt" not in row
        assert "messages" not in row
        assert "secret" not in {str(key).lower() for key in row}
        assert required.issubset(row), f"Packet B traffic row missing metadata keys: {row}"
        assert row.get("raw_prompt_recorded") is False


def _assert_packet_a_launch_proof(
    *,
    lmcache_command: list[Any],
    lmcache_env: dict[str, Any],
    vllm_command: list[Any],
) -> None:
    assert lmcache_command[:2] == ["lmcache", "server"]
    assert _cmd_value(lmcache_command, "--host") == "127.0.0.1"
    assert _cmd_value(lmcache_command, "--port") == "6555"
    assert _cmd_value(lmcache_command, "--http-port") == "8080"
    assert _cmd_value(lmcache_command, "--prometheus-port") == "9090"
    assert _cmd_value(lmcache_command, "--trace-level") == "storage"
    assert "--trace-output" in lmcache_command
    assert "--lookup-hash-log-dir" in lmcache_command
    assert _cmd_value(lmcache_command, "--eviction-policy") == "LRU"
    assert _cmd_value(lmcache_command, "--metrics-sample-rate") == "1.0"
    assert _cmd_value(lmcache_command, "--event-bus-queue-size") == "10000"
    assert "LMCACHE_CONFIG_FILE" not in lmcache_env, "Packet A must remain L1-only; no L2 config"

    assert vllm_command[:3] == ["vllm", "serve", "Qwen/Qwen3-8B"]
    kv_transfer_config = json.loads(_cmd_value(vllm_command, "--kv-transfer-config"))
    assert kv_transfer_config["kv_connector"] == "LMCacheMPConnector"
    assert kv_transfer_config["kv_role"] == "kv_both"
    assert kv_transfer_config["kv_load_failure_policy"] == "recompute"
    assert kv_transfer_config["kv_connector_extra_config"] == {
        "lmcache.mp.host": "tcp://127.0.0.1",
        "lmcache.mp.port": 6555,
        "lmcache.mp.mq_timeout": 10,
    }
    assert "--disable-hybrid-kv-cache-manager" in vllm_command


def _assert_packet_a_manifest(manifest: dict[str, Any]) -> None:
    assert manifest.get("row_id") == "B1"
    assert manifest.get("packet_id") == "a"
    assert manifest.get("source") == "live_modal_h100"
    assert manifest.get("score_points") == 10
    assert manifest.get("redacted") is True
    assert manifest.get("raw_hashes_removed") is True
    assert manifest.get("raw_prompts_removed") is True
    assert manifest.get("acceptance_status") == "accepted"


def _assert_packet_b_manifest(manifest: dict[str, Any]) -> None:
    assert manifest.get("row_id") == "C1"
    assert manifest.get("packet_id") == "b"
    assert manifest.get("benchmark_id") == "LC1"
    assert manifest.get("workload_profile") == "long_context_agent_kv_offload"
    assert manifest.get("raw_prompts_recorded", False) is False
    assert manifest.get("source") == "live_modal_h100"
    assert manifest.get("score_points") == 6
    assert manifest.get("redacted") is True
    assert manifest.get("raw_hashes_removed") is True
    assert manifest.get("raw_prompts_removed") is True
    assert manifest.get("acceptance_status") == "accepted"


def _assert_packet_c_manifest(manifest: dict[str, Any]) -> None:
    assert manifest.get("row_id") == "D1"
    assert manifest.get("packet_id") == "c"
    assert manifest.get("workload") == "l2_reuse"
    assert manifest.get("source") == "live_modal_h100"
    assert manifest.get("score_points") == 6
    assert manifest.get("redacted") is True
    assert manifest.get("raw_hashes_removed") is True
    assert manifest.get("raw_prompts_removed") is True
    assert manifest.get("acceptance_status") == "accepted"


def _assert_required_files(
    fixture_dir: Path, rel_paths: tuple[str, ...], *, row_id: str = "B1"
) -> None:
    for rel_path in rel_paths:
        path = fixture_dir / rel_path
        assert path.exists(), f"missing required {row_id} fixture artifact: {rel_path}"
        assert path.stat().st_size > 0, f"empty required {row_id} fixture artifact: {rel_path}"


def _assert_fixture_sanitized(fixture_dir: Path) -> None:
    for path in fixture_dir.rglob("*"):
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        assert not _SECRET_PATTERN.search(text), f"secret-like token found in {path}"
        assert not _RAW_PROMPT_PATTERN.search(text), f"raw prompt/message payload found in {path}"
        text_without_manifest_receipts = text.replace("raw_hashes_removed", "")
        assert not _RAW_HASH_PATTERN.search(
            text_without_manifest_receipts
        ), f"raw chunk hash marker found in {path}"


def _assert_positive(value: int | float | None, label: str) -> None:
    assert value is not None and value > 0, f"expected positive {label}, got {value!r}"


def _cmd_value(command: list[Any], flag: str) -> str:
    assert flag in command, f"missing command flag {flag}"
    index = command.index(flag)
    assert index + 1 < len(command), f"missing value for command flag {flag}"
    value = command[index + 1]
    assert isinstance(value, str), f"expected string value for {flag}, got {value!r}"
    return value


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(payload, dict), f"expected JSON object in {path}"
    return payload


def _read_json_list(path: Path) -> list[Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(payload, list), f"expected JSON list in {path}"
    return payload


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")

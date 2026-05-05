"""Tests for the public disagg data types and their JSON round-trip."""

import json

from inferguard.disagg.types import (
    SCHEMA_VERSION,
    DisaggFinding,
    DisaggSnapshot,
    DisaggStatus,
    EndpointId,
)


def _snap(role: str, *, url: str = "http://x") -> DisaggSnapshot:
    return DisaggSnapshot(
        endpoint=EndpointId(url=url, role=role, engine="vllm", connector="nixl"),
        scraped_at=1234567890.0,
        kv_cache_usage=0.45,
        requests_running=5,
    )


def test_endpoint_as_dict_round_trips() -> None:
    e = EndpointId(url="http://p", role="prefill", engine="vllm")
    data = e.as_dict()
    assert data["url"] == "http://p"
    assert data["role"] == "prefill"
    assert data["engine"] == "vllm"


def test_snapshot_as_dict_includes_defaults() -> None:
    snap = _snap("prefill")
    data = snap.as_dict()
    assert data["endpoint"]["role"] == "prefill"
    assert data["kv_cache_usage"] == 0.45
    assert data["requests_running"] == 5
    assert data["requests_waiting"] is None
    assert data["scrape_error"] == ""


def test_finding_as_dict_preserves_evidence() -> None:
    f = DisaggFinding(
        code="kv_transfer_errors_present",
        severity="warning",
        message="errors observed",
        evidence={"errors_by_role": {"prefill": 7}},
    )
    data = f.as_dict()
    assert data["code"] == "kv_transfer_errors_present"
    assert data["evidence"]["errors_by_role"] == {"prefill": 7}


def test_status_as_dict_is_json_serializable() -> None:
    status = DisaggStatus(
        prefill=_snap("prefill"),
        decode=_snap("decode"),
        transfer=None,
        findings=[
            DisaggFinding(code="engine_unidentified", severity="warning", message="x"),
        ],
    )
    blob = json.dumps(status.as_dict())
    parsed = json.loads(blob)
    assert parsed["schema_version"] == SCHEMA_VERSION
    assert parsed["transfer"] is None
    assert len(parsed["findings"]) == 1
    assert parsed["findings"][0]["code"] == "engine_unidentified"


def test_schema_version_is_v1() -> None:
    assert SCHEMA_VERSION == "disagg-status/v1"

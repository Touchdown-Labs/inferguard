"""Tests for the disagg detectors — one per rule code."""

from inferguard.disagg.detect import evaluate
from inferguard.disagg.types import (
    DisaggSnapshot,
    DisaggStatus,
    EndpointId,
)


def _snap(
    role: str,
    *,
    engine: str = "vllm",
    connector: str = "nixl",
    scrape_error: str = "",
    **fields,
) -> DisaggSnapshot:
    return DisaggSnapshot(
        endpoint=EndpointId(
            url=f"http://{role}",
            role=role,  # type: ignore[arg-type]
            engine=engine,  # type: ignore[arg-type]
            connector=connector,
        ),
        scraped_at=0.0,
        scrape_error=scrape_error,
        **fields,
    )


def _codes(status: DisaggStatus) -> list[str]:
    return [f.code for f in evaluate(status)]


def test_endpoint_unreachable_flags_both_sides() -> None:
    status = DisaggStatus(
        prefill=_snap("prefill", scrape_error="unreachable: timeout"),
        decode=_snap("decode", requests_running=5),
        transfer=None,
    )
    codes = _codes(status)
    assert "endpoint_unreachable" in codes


def test_engine_unidentified_when_unknown() -> None:
    status = DisaggStatus(
        prefill=_snap("prefill", engine="unknown"),
        decode=_snap("decode", engine="vllm", requests_running=5),
        transfer=None,
    )
    codes = _codes(status)
    assert "engine_unidentified" in codes


def test_connector_mismatch_between_prefill_and_decode() -> None:
    status = DisaggStatus(
        prefill=_snap("prefill", connector="nixl", requests_running=8),
        decode=_snap("decode", connector="mooncake", requests_running=8),
        transfer=None,
    )
    assert "connector_mismatch" in _codes(status)


def test_connector_match_produces_no_mismatch_finding() -> None:
    status = DisaggStatus(
        prefill=_snap("prefill", connector="nixl", requests_running=8),
        decode=_snap("decode", connector="nixl", requests_running=8),
        transfer=None,
    )
    assert "connector_mismatch" not in _codes(status)


def test_kv_transfer_errors_warning() -> None:
    status = DisaggStatus(
        prefill=_snap("prefill", requests_running=4, kv_transfer_errors_total=5),
        decode=_snap("decode", requests_running=4, kv_transfer_errors_total=0),
        transfer=None,
    )
    findings = evaluate(status)
    codes = [f.code for f in findings]
    assert "kv_transfer_errors_present" in codes


def test_kv_transfer_errors_critical_at_100_plus() -> None:
    status = DisaggStatus(
        prefill=_snap("prefill", requests_running=4, kv_transfer_errors_total=150),
        decode=_snap("decode", requests_running=4, kv_transfer_errors_total=0),
        transfer=None,
    )
    findings = evaluate(status)
    severity = {f.code: f.severity for f in findings}
    assert severity["kv_transfer_errors_present"] == "critical"


def test_kv_transfer_stall_detection() -> None:
    status = DisaggStatus(
        prefill=_snap(
            "prefill",
            requests_running=8,
            kv_transfer_sent_bytes_total=0,
            kv_transfer_recv_bytes_total=0,
        ),
        decode=_snap(
            "decode",
            requests_running=8,
            kv_transfer_sent_bytes_total=0,
            kv_transfer_recv_bytes_total=0,
        ),
        transfer=None,
    )
    assert "kv_transfer_stall" in _codes(status)


def test_kv_transfer_stall_not_flagged_without_running() -> None:
    status = DisaggStatus(
        prefill=_snap(
            "prefill",
            requests_running=0,
            kv_transfer_sent_bytes_total=0,
            kv_transfer_recv_bytes_total=0,
        ),
        decode=_snap(
            "decode",
            requests_running=0,
            kv_transfer_sent_bytes_total=0,
            kv_transfer_recv_bytes_total=0,
        ),
        transfer=None,
    )
    assert "kv_transfer_stall" not in _codes(status)


def test_prefill_decode_imbalance_decode_side() -> None:
    status = DisaggStatus(
        prefill=_snap("prefill", requests_running=2),
        decode=_snap("decode", requests_running=20),
        transfer=None,
    )
    # ratio = 2/20 = 0.1 < 0.5 → decode-side pressure
    codes = _codes(status)
    assert "prefill_decode_imbalance" in codes


def test_prefill_decode_imbalance_prefill_side() -> None:
    status = DisaggStatus(
        prefill=_snap("prefill", requests_running=30),
        decode=_snap("decode", requests_running=3),
        transfer=None,
    )
    # ratio = 30/3 = 10 > 2.0 → prefill-side pressure
    codes = _codes(status)
    assert "prefill_decode_imbalance" in codes


def test_healthy_status_has_no_findings() -> None:
    status = DisaggStatus(
        prefill=_snap(
            "prefill",
            requests_running=8,
            kv_transfer_sent_bytes_total=100_000,
            kv_transfer_recv_bytes_total=100_000,
            kv_transfer_errors_total=0,
        ),
        decode=_snap(
            "decode",
            requests_running=8,
            kv_transfer_sent_bytes_total=100_000,
            kv_transfer_recv_bytes_total=100_000,
            kv_transfer_errors_total=0,
        ),
        transfer=None,
    )
    assert evaluate(status) == []

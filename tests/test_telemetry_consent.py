from __future__ import annotations

import json
import os
import socket
import subprocess
import urllib.request
from pathlib import Path

import httpx
import pytest

from inferguard.harness.telemetry import (
    DEFAULT_DP_PARAMS,
    REDACTED_VALUE,
    TelemetryClient,
    TelemetryState,
    _sanitize_value,
    apply_dp_stub,
    sanitize_for_telemetry,
)


def rig() -> dict:
    return {
        "gpu_model": "H200",
        "gpu_count_bucket": "8",
        "engine": "vllm",
        "engine_version_major_minor": "0.20",
    }


def aggregates() -> dict:
    return {
        "ttft_p50_ms_bucketed": 420,
        "ttft_p99_ms_bucketed": 5500,
        "kv_pressure_p95_bucketed": 0.85,
        "prefix_cache_hit_rate_bucketed": 0.42,
        "tool_stall_pct_bucketed": 0.40,
        "node_counts": {"model_call": 12, "tool_call": 47},
        "concurrency_cliff_estimate": 32,
    }


def client(tmp_path: Path, env: dict[str, str] | None = None) -> TelemetryClient:
    return TelemetryClient(
        config_dir=tmp_path / "inferguard", env=env or {}, cluster_fingerprint="cluster-a"
    )


@pytest.mark.harness
def test_default_state_is_disabled(tmp_path: Path) -> None:
    assert client(tmp_path).status().state is TelemetryState.DISABLED


@pytest.mark.harness
def test_do_not_track_hard_disables(tmp_path: Path) -> None:
    c = client(tmp_path, {"DO_NOT_TRACK": "1"})
    c.enable_pending_consent()
    assert c.status().hard_disabled is True
    assert c.state is TelemetryState.DISABLED


@pytest.mark.harness
def test_env_disabled_hard_disables(tmp_path: Path) -> None:
    c = client(tmp_path, {"INFERGUARD_TELEMETRY": "disabled"})
    c.grant_consent("token")
    assert c.can_upload() is False


@pytest.mark.harness
def test_enable_moves_to_pending_consent(tmp_path: Path) -> None:
    status = client(tmp_path).enable_pending_consent()
    assert status.state is TelemetryState.ENABLED_PENDING_CONSENT


@pytest.mark.harness
def test_grant_consent_persists_token_and_state(tmp_path: Path) -> None:
    c = client(tmp_path)
    c.enable_pending_consent()
    status = c.grant_consent("token-123")
    assert status.state is TelemetryState.ENABLED_WITH_CONSENT
    assert c.load_consent_token() == "token-123"
    assert c.can_upload() is True


@pytest.mark.harness
def test_consent_token_uses_secrets_path_and_0600_mode(tmp_path: Path) -> None:
    c = client(tmp_path)
    c.grant_consent("token-123")

    assert c.consent_path == tmp_path / "inferguard" / "secrets" / "consent.token"
    assert c.consent_path.read_text(encoding="utf-8").strip() == "token-123"
    assert c.consent_path.stat().st_mode & 0o777 == 0o600


@pytest.mark.harness
def test_refuses_world_readable_consent_token(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    c = client(tmp_path)
    c.grant_consent("token-123")
    os.chmod(c.consent_path, 0o644)

    assert c.load_consent_token() is None
    assert c.can_upload() is False
    assert "insecure permissions" in caplog.text


@pytest.mark.harness
def test_disable_turns_off_upload_path(tmp_path: Path) -> None:
    c = client(tmp_path)
    c.grant_consent("token-123")
    c.disable()
    assert c.state is TelemetryState.DISABLED
    assert c.can_upload() is False


@pytest.mark.harness
def test_verify_payload_requires_consent(tmp_path: Path) -> None:
    with pytest.raises(PermissionError):
        client(tmp_path).verify_payload(
            payload_kind="bench-summary", rig_fingerprint=rig(), aggregates=aggregates()
        )


@pytest.mark.harness
def test_verify_payload_matches_locked_schema(tmp_path: Path) -> None:
    c = client(tmp_path)
    c.grant_consent("token-123")
    payload = c.verify_payload(
        payload_kind="bench-summary",
        rig_fingerprint=rig(),
        aggregates=aggregates(),
    )
    assert payload["schema_version"] == "inferguard-telemetry/v1"
    assert payload["dp_params"] == DEFAULT_DP_PARAMS
    assert len(payload["anonymized_deployment_id"]) == 16


@pytest.mark.harness
def test_write_pending_payload_writes_to_uploads_pending(tmp_path: Path) -> None:
    c = client(tmp_path)
    c.grant_consent("token-123")
    payload = c.verify_payload(
        payload_kind="metrics-rollup",
        rig_fingerprint=rig(),
        aggregates=aggregates(),
    )
    output = c.write_pending_payload(payload)
    assert output.parent.name == "uploads-pending"
    assert json.loads(output.read_text())["payload_kind"] == "metrics-rollup"
    assert output.stat().st_mode & 0o777 == 0o600
    assert c.log_tail(1)[0]["path"] == str(output)


@pytest.mark.harness
def test_queue_payload_refuses_without_enabled_consent(tmp_path: Path) -> None:
    with pytest.raises(PermissionError):
        client(tmp_path).queue_payload(
            payload_kind="bench-summary", rig_fingerprint=rig(), aggregates=aggregates()
        )


@pytest.mark.harness
def test_sanitize_drops_never_collected_keys() -> None:
    clean = sanitize_for_telemetry(
        {
            "messages": [{"role": "user", "content": "secret"}],
            "node_counts": {"model_call": 1},
            "nested": {"api_key": "secret", "safe": 1},
        }
    )
    assert "messages" not in clean
    assert clean["nested"] == {"safe": 1}


@pytest.mark.harness
def test_sanitizer_redacts_prompt_like_content() -> None:
    prompt = "Explain the customer incident in detail. " * 8

    assert _sanitize_value(prompt) == REDACTED_VALUE


@pytest.mark.harness
def test_sanitizer_allows_long_schema_metadata() -> None:
    value = "schema_version=" + ("agent-trace/v1," * 30)

    assert _sanitize_value(value) == value


@pytest.mark.harness
def test_sanitizer_redacts_emails() -> None:
    assert _sanitize_value("owner=sre@example.com") == REDACTED_VALUE


@pytest.mark.harness
def test_sanitizer_redacts_file_paths() -> None:
    assert _sanitize_value("profile stored at /home/inferguard/secrets/token.txt") == REDACTED_VALUE


@pytest.mark.harness
def test_sanitizer_redacts_ip_addresses() -> None:
    assert _sanitize_value("leader=10.42.0.8") == REDACTED_VALUE
    assert _sanitize_value("leader=[2001:db8::1]") == REDACTED_VALUE


@pytest.mark.harness
def test_sanitizer_redacts_base64_blobs() -> None:
    blob = "QWxhZGRpbjpvcGVuIHNlc2FtZQ==" * 2

    assert _sanitize_value(blob) == REDACTED_VALUE


@pytest.mark.harness
def test_sanitizer_redacts_hex_tokens() -> None:
    token = "0123456789abcdef0123456789abcdef01234567"

    assert _sanitize_value(f"token={token}") == REDACTED_VALUE


@pytest.mark.harness
def test_strict_sanitizer_redacts_strings_over_50_chars() -> None:
    assert _sanitize_value("x" * 51, strict=True) == REDACTED_VALUE


@pytest.mark.harness
def test_sanitize_for_telemetry_recurses_into_dicts_and_lists() -> None:
    clean = sanitize_for_telemetry({"labels": ["safe", "admin@example.com"]})

    assert clean == {"labels": ["safe", REDACTED_VALUE]}


@pytest.mark.harness
def test_dp_stub_preserves_bucketed_aggregates() -> None:
    assert apply_dp_stub({"ttft_p50_ms_bucketed": 420}) == {"ttft_p50_ms_bucketed": 420}


@pytest.mark.harness
def test_no_outbound_http_without_explicit_network_opt_in() -> None:
    with pytest.raises(AssertionError):
        httpx.get("https://api.touchdown.ai/v1/ingest", timeout=0.01)


@pytest.mark.harness
def test_env_enabled_without_token_is_pending(tmp_path: Path) -> None:
    assert (
        client(tmp_path, {"INFERGUARD_TELEMETRY": "enabled"}).state
        is TelemetryState.ENABLED_PENDING_CONSENT
    )


@pytest.mark.harness
async def test_outbound_aiohttp_call_is_blocked() -> None:
    aiohttp = pytest.importorskip("aiohttp")

    with pytest.raises(AssertionError):
        async with aiohttp.ClientSession() as session:
            await session.get("https://api.touchdown.ai/v1/ingest")


@pytest.mark.harness
def test_outbound_urllib_call_is_blocked() -> None:
    with pytest.raises(AssertionError):
        urllib.request.urlopen("https://api.touchdown.ai/v1/ingest", timeout=0.01)


@pytest.mark.harness
def test_outbound_non_loopback_socket_is_blocked() -> None:
    with pytest.raises(AssertionError):
        socket.create_connection(("8.8.8.8", 53), timeout=0.01)


@pytest.mark.harness
def test_subprocess_curl_call_is_blocked() -> None:
    with pytest.raises(AssertionError):
        subprocess.run(["curl", "https://api.touchdown.ai/v1/ingest"], check=False)


@pytest.mark.harness
def test_subprocess_curl_loopback_target_is_allowed() -> None:
    try:
        completed = subprocess.run(
            ["curl", "--version", "http://127.0.0.1"],
            check=False,
            capture_output=True,
            text=True,
            timeout=2,
        )
    except FileNotFoundError:
        pytest.skip("curl is not installed")

    assert completed.returncode == 0

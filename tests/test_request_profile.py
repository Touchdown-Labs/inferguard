import json
import math
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import pytest

from inferguard.bench.types import RequestMetric
from inferguard.request_profile import profile_endpoint
from inferguard.request_profile.runner import run_request_profile
from inferguard.request_profile.types import RequestProfileOptions
from tests.fixtures.mock_vllm_server import start_mock_servers

REPO_ROOT = Path(__file__).resolve().parents[3]
RUNNER = REPO_ROOT / "scripts" / "run_neocloud_nvidia_profile.py"
FIXTURES = Path(__file__).resolve().parent / "fixtures" / "request_profile"
CANARY = FIXTURES / "canary_short.jsonl"
LONG_CONTEXT = FIXTURES / "long_context_coding.jsonl"
EXPECTED = FIXTURES / "expected_outputs.json"


def _run_profile(tmp_path: Path, *, server_kwargs: dict | None = None, **kwargs):
    handle = start_mock_servers("b300", **(server_kwargs or {}))
    output_dir = tmp_path / "request_profile"
    try:
        summary = profile_endpoint(
            endpoint=handle.endpoint_url,
            model="mock-dsv4",
            input_jsonl=kwargs.pop("input_jsonl", CANARY),
            output_dir=output_dir,
            workload_label="canary_short",
            job_id="job-request-profile-test",
            **kwargs,
        )
        rows = _read_jsonl(output_dir / "requests_profile.jsonl")
        summary_json = json.loads(
            (output_dir / "requests_summary.json").read_text(encoding="utf-8")
        )
        return rows, summary_json, summary
    finally:
        handle.teardown()


def _read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def _parse_ts(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _in_flight_max(rows: list[dict]) -> int:
    events: list[tuple[datetime, int]] = []
    for row in rows:
        events.append((_parse_ts(row["send_ts"]), 1))
        events.append((_parse_ts(row["done_ts"]), -1))
    in_flight = 0
    highest = 0
    for _ts, delta in sorted(events, key=lambda item: (item[0], item[1])):
        in_flight += delta
        highest = max(highest, in_flight)
    return highest


def test_mock_vllm_basic_profile(tmp_path: Path) -> None:
    rows, summary, _ = _run_profile(
        tmp_path,
        concurrency=2,
        max_requests=4,
        stream=True,
        include_usage=True,
        continuous_usage_stats=True,
    )

    expected = json.loads(EXPECTED.read_text(encoding="utf-8"))
    assert len(rows) == summary["request_count"] == 4
    assert all(set(expected["required_row_keys"]).issubset(row) for row in rows)
    assert all(row["ttft_ms"] is not None for row in rows)
    assert all(row["e2e_latency_ms"] > 0 for row in rows)
    assert all("success" in row for row in rows)


def test_streaming_first_token_timestamp(tmp_path: Path) -> None:
    rows, _summary, _ = _run_profile(
        tmp_path,
        concurrency=1,
        max_requests=3,
        stream=True,
        include_usage=True,
    )

    for row in rows:
        send_ts = _parse_ts(row["send_ts"])
        first_token_ts = _parse_ts(row["first_token_ts"])
        done_ts = _parse_ts(row["done_ts"])
        assert send_ts <= first_token_ts <= done_ts
        derived_ms = (first_token_ts - send_ts).total_seconds() * 1000.0
        assert math.isclose(row["ttft_ms"], derived_ms, rel_tol=0.0, abs_tol=1.0)


def test_failure_rows_emitted(tmp_path: Path) -> None:
    rows, summary, _ = _run_profile(
        tmp_path,
        server_kwargs={"inject_failure_rate": 0.5},
        concurrency=2,
        max_requests=6,
        stream=True,
        include_usage=True,
    )

    failures = [row for row in rows if not row["success"]]
    assert len(rows) == 6
    assert len(failures) >= 1
    assert all(row["error_type"] is not None for row in failures)
    assert summary["failure_count"] == len(failures)


def test_summary_aggregates(tmp_path: Path) -> None:
    _rows, summary, _ = _run_profile(
        tmp_path,
        concurrency=2,
        max_requests=5,
        stream=True,
        include_usage=True,
    )

    assert summary["ttft_ms"]["p99"] >= summary["ttft_ms"]["p95"] >= summary["ttft_ms"]["p50"]
    assert summary["tpot_ms"]["p99"] >= summary["tpot_ms"]["p95"] >= summary["tpot_ms"]["p50"]
    assert summary["e2e_latency_ms"]["p99"] >= summary["e2e_latency_ms"]["p95"]
    assert summary["success_count"] + summary["failure_count"] == summary["request_count"]
    assert summary["success_rate"] == summary["success_count"] / summary["request_count"]


def test_tokenizer_fallback(tmp_path: Path) -> None:
    rows, summary, _ = _run_profile(
        tmp_path,
        server_kwargs={"suppress_usage": True},
        concurrency=1,
        max_requests=3,
        stream=True,
        include_usage=True,
    )

    assert all(row["prompt_tokens_source"] == "tokenizer" for row in rows)
    assert all(row["claim_status"] == "inferred" for row in rows)
    assert summary["claim_status"] == "inferred"


def test_closed_loop_concurrency_bound(tmp_path: Path) -> None:
    rows, _summary, _ = _run_profile(
        tmp_path,
        input_jsonl=LONG_CONTEXT,
        concurrency=4,
        max_requests=16,
        stream=True,
        include_usage=True,
    )

    assert _in_flight_max(rows) <= 4


def test_poisson_arrival_rate(tmp_path: Path) -> None:
    rows, _summary, _ = _run_profile(
        tmp_path,
        concurrency=20,
        max_requests=120,
        stream=False,
        arrival_mode="poisson",
        rate_rps=40.0,
        seed=1,
    )

    starts = sorted(_parse_ts(row["send_ts"]) for row in rows)
    measured_rps = (len(starts) - 1) / (starts[-1] - starts[0]).total_seconds()
    assert abs((measured_rps - 40.0) / 40.0) < 0.15
    assert all(row["streaming"] is False for row in rows)
    assert all(row["first_token_ts"] is None for row in rows)


def test_jsonl_streaming_survives_keyboard_interrupt(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    input_path = tmp_path / "requests.jsonl"
    input_path.write_text(
        "\n".join(
            [
                json.dumps({"request_id": "r0", "messages": [{"role": "user", "content": "hi"}]}),
                json.dumps({"request_id": "r1", "messages": [{"role": "user", "content": "hi"}]}),
                json.dumps({"request_id": "r2", "messages": [{"role": "user", "content": "hi"}]}),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    output_dir = tmp_path / "request_profile"

    async def interrupted_profile(options, specs, *, on_metric=None):
        assert on_metric is not None
        for sequence in range(2):
            on_metric(
                RequestMetric(
                    request_id=f"r{sequence}",
                    trace_id=f"t{sequence}",
                    session_id=f"s{sequence}",
                    turn_index=sequence,
                    workload_class="unit",
                    concurrency=options.concurrency,
                    success=True,
                    start_time=100.0 + sequence,
                    end_time=101.0 + sequence,
                    latency_seconds=1.0,
                    ttft_seconds=0.1,
                    input_tokens=8,
                    output_tokens=4,
                    input_tokens_source="api_usage",
                    output_tokens_source="api_usage",
                    tokens_per_second=4.0,
                    status_code=200,
                    metadata={
                        "sequence": sequence,
                        "cached_tokens": 0,
                        "content_token_offsets_seconds": [0.1, 0.2, 0.3],
                    },
                )
            )
        raise KeyboardInterrupt

    monkeypatch.setattr("inferguard.request_profile.runner._profile_requests", interrupted_profile)

    with pytest.raises(KeyboardInterrupt):
        run_request_profile(
            RequestProfileOptions(
                endpoint="http://127.0.0.1:9/v1/chat/completions",
                model="mock",
                input_jsonl=str(input_path),
                output_dir=str(output_dir),
                concurrency=2,
                stream=True,
                job_id="job-interrupted",
            )
        )

    rows = _read_jsonl(output_dir / "requests_profile.jsonl")
    assert [row["job_id"] for row in rows] == ["job-interrupted", "job-interrupted"]
    assert [row["success"] for row in rows] == [True, True]
    assert not (output_dir / "requests_summary.json").exists()


def test_schema_version_locked(tmp_path: Path) -> None:
    rows, _summary, _ = _run_profile(
        tmp_path,
        concurrency=1,
        max_requests=1,
        stream=True,
        include_usage=True,
    )

    assert rows[0]["schema_version"] == "inferguard-request-profile/v1"


def test_stdout_summary_format(tmp_path: Path) -> None:
    handle = start_mock_servers("b300")
    output_dir = tmp_path / "request_profile"
    try:
        completed = subprocess.run(
            [
                sys.executable,
                str(RUNNER),
                "request-profile",
                "--endpoint",
                handle.endpoint_url,
                "--model",
                "mock-dsv4",
                "--input-jsonl",
                str(CANARY),
                "--output-dir",
                str(output_dir),
                "--max-requests",
                "2",
                "--stream",
                "--include-usage",
                "--job-id",
                "job-request-profile-stdout",
            ],
            cwd=REPO_ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
    finally:
        handle.teardown()

    assert completed.returncode == 0, completed.stderr
    assert re.match(
        r"^inferguard request-profile: requests=\d+ success=\d+ failures=\d+ "
        r"ttft_p50=[\d.]+ ttft_p95=[\d.]+ tpot_p50=[\d.]+ "
        r"e2e_p99=[\d.]+ tokens_per_sec=[\d.]+\n$",
        completed.stdout,
    )


def test_mtp_bug_downgrade(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("INFERGUARD_SPECULATIVE_ALGORITHM", "eagle")
    rows, _summary, _ = _run_profile(
        tmp_path,
        server_kwargs={"simulate_mtp_bug": True},
        engine="sglang",
        concurrency=1,
        max_requests=3,
        stream=True,
        include_usage=True,
    )

    assert all(row["cached_tokens"] in (0, None) for row in rows)
    assert all(row["claim_status_per_field"]["cached_tokens"] == "inferred" for row in rows)

from __future__ import annotations

import json
import logging
from pathlib import Path

import httpx
import pytest

from inferguard.harness.dcgm_correlate import (
    OUTPUT_FILENAME,
    SCHEMA_VERSION,
    DcgmCorrelator,
    align_timestamp,
    parse_dcgm_samples,
    parse_prometheus_text,
    parse_vllm_samples,
)

DCGM_TEXT = """
# HELP DCGM_FI_DEV_GPU_UTIL GPU utilization.
# TYPE DCGM_FI_DEV_GPU_UTIL gauge
DCGM_FI_DEV_SM_CLOCK{gpu="0",UUID="GPU-aaaa"} 1410
DCGM_FI_DEV_MEM_CLOCK{gpu="0",UUID="GPU-aaaa"} 1593
DCGM_FI_DEV_GPU_TEMP{gpu="0",UUID="GPU-aaaa"} 61
DCGM_FI_DEV_MEMORY_TEMP{gpu="0",UUID="GPU-aaaa"} 68
DCGM_FI_DEV_POWER_USAGE{gpu="0",UUID="GPU-aaaa"} 455.5
DCGM_FI_DEV_TOTAL_ENERGY_CONSUMPTION{gpu="0",UUID="GPU-aaaa"} 9000
DCGM_FI_DEV_GPU_UTIL{gpu="0",UUID="GPU-aaaa"} 83
DCGM_FI_DEV_MEM_COPY_UTIL{gpu="0",UUID="GPU-aaaa"} 44
DCGM_FI_DEV_FB_FREE{gpu="0",UUID="GPU-aaaa"} 1024
DCGM_FI_DEV_FB_USED{gpu="0",UUID="GPU-aaaa"} 79360
DCGM_FI_DEV_XID_ERRORS{gpu="0",UUID="GPU-aaaa"} 0
DCGM_FI_DEV_NVLINK_BANDWIDTH_TOTAL{gpu="0",UUID="GPU-aaaa",link="0"} 12
DCGM_FI_DEV_NVLINK_BANDWIDTH_TOTAL{gpu="0",UUID="GPU-aaaa",link="1"} 8
DCGM_FI_DEV_GPU_UTIL{gpu="1",UUID="GPU-bbbb"} 72
DCGM_FI_DEV_FB_USED{gpu="1",UUID="GPU-bbbb"} 65536
"""

VLLM_TEXT = """
vllm:num_requests_running{model_name="deepseek"} 3
vllm:num_requests_waiting{model_name="deepseek"} 7
vllm:kv_cache_usage_perc{model_name="deepseek"} 0.82
vllm:num_preemptions_total{model_name="deepseek"} 2
vllm:e2e_request_latency_seconds{model_name="deepseek",quantile="0.99"} 4.2
"""


def make_client(*, vllm_text: str = VLLM_TEXT, dcgm_text: str = DCGM_TEXT) -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "vllm.test":
            return httpx.Response(200, text=vllm_text)
        if request.url.host == "dcgm.test":
            return httpx.Response(200, text=dcgm_text)
        return httpx.Response(404, text="missing")

    return httpx.Client(transport=httpx.MockTransport(handler))


def collect_once(tmp_path: Path, *, vllm_text: str = VLLM_TEXT, dcgm_text: str = DCGM_TEXT):
    client = make_client(vllm_text=vllm_text, dcgm_text=dcgm_text)
    correlator = DcgmCorrelator(
        vllm_metrics_url="http://vllm.test/metrics",
        dcgm_metrics_url="http://dcgm.test/metrics",
        output_dir=tmp_path,
        duration_seconds=5,
        interval_seconds=5,
        http_client=client,
    )
    try:
        return correlator.collect_once(observed_at=1730000002.7)
    finally:
        client.close()


@pytest.mark.harness
def test_align_timestamp_rounds_down_to_five_second_window() -> None:
    assert align_timestamp(1730000004.999, 5) == 1730000000
    assert align_timestamp(1730000005.000, 5) == 1730000005


@pytest.mark.harness
def test_parse_prometheus_text_handles_colon_names_and_labels() -> None:
    samples = parse_prometheus_text('vllm:num_requests_running{model_name="m"} 4\n')
    assert samples[0].name == "vllm:num_requests_running"
    assert samples[0].labels == {"model_name": "m"}
    assert samples[0].value == 4.0


@pytest.mark.harness
def test_parse_prometheus_text_skips_empty_scrapes() -> None:
    assert parse_prometheus_text("\n# only comments\n") == []


@pytest.mark.harness
def test_parse_dcgm_samples_builds_one_row_per_gpu_uuid() -> None:
    rows = parse_dcgm_samples(parse_prometheus_text(DCGM_TEXT))
    assert [row["gpu_uuid"] for row in rows] == ["GPU-aaaa", "GPU-bbbb"]
    assert rows[0]["gpu_index"] == 0
    assert rows[0]["dcgm_gpu_util"] == 83.0
    assert rows[1]["dcgm_fb_used"] == 65536.0


@pytest.mark.harness
def test_parse_dcgm_samples_sums_nvlink_bandwidth_links() -> None:
    row = parse_dcgm_samples(parse_prometheus_text(DCGM_TEXT))[0]
    assert row["dcgm_nvlink_bandwidth_total"] == 20.0


@pytest.mark.harness
def test_parse_vllm_samples_broadcast_fields_from_colon_metrics() -> None:
    fields = parse_vllm_samples(parse_prometheus_text(VLLM_TEXT))
    assert fields["vllm_num_requests_running"] == 3.0
    assert fields["vllm_num_requests_waiting"] == 7.0
    assert fields["vllm_kv_cache_usage_perc"] == 0.82
    assert fields["vllm_num_preemptions_total"] == 2.0
    assert fields["vllm_e2e_request_latency_seconds_p99"] == 4.2


@pytest.mark.harness
def test_parse_vllm_samples_estimates_p99_from_histogram_buckets() -> None:
    text = """
vllm:e2e_request_latency_seconds_bucket{le="1"} 1
vllm:e2e_request_latency_seconds_bucket{le="2"} 20
vllm:e2e_request_latency_seconds_bucket{le="5"} 100
vllm:e2e_request_latency_seconds_bucket{le="+Inf"} 100
"""
    fields = parse_vllm_samples(parse_prometheus_text(text))
    assert fields["vllm_e2e_request_latency_seconds_p99"] == 5.0


@pytest.mark.harness
def test_collect_once_broadcasts_vllm_aggregate_to_each_gpu_row(tmp_path: Path) -> None:
    rows = collect_once(tmp_path)
    assert len(rows) == 2
    assert {row["gpu_uuid"] for row in rows} == {"GPU-aaaa", "GPU-bbbb"}
    assert {row["vllm_num_requests_running"] for row in rows} == {3.0}
    assert rows[0]["timestamp"] == "2024-10-27T03:33:20Z"
    assert rows[0]["timestamp_window_seconds"] == 5
    assert rows[0]["schema_version"] == SCHEMA_VERSION


@pytest.mark.harness
def test_empty_dcgm_scrape_emits_null_gpu_row(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.WARNING)
    rows = collect_once(tmp_path, dcgm_text="")
    assert len(rows) == 1
    assert rows[0]["gpu_uuid"] is None
    assert rows[0]["dcgm_gpu_util"] is None
    assert rows[0]["vllm_num_requests_running"] == 3.0
    assert "empty DCGM scrape" in caplog.text


@pytest.mark.harness
def test_empty_vllm_scrape_keeps_dcgm_rows_with_null_vllm_fields(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.WARNING)
    rows = collect_once(tmp_path, vllm_text="")
    assert len(rows) == 2
    assert rows[0]["gpu_uuid"] == "GPU-aaaa"
    assert rows[0]["vllm_num_requests_running"] is None
    assert "empty vLLM scrape" in caplog.text


@pytest.mark.harness
def test_http_failure_does_not_crash_and_emits_null_row(tmp_path: Path) -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, text="unavailable")

    client = httpx.Client(transport=httpx.MockTransport(handler))
    correlator = DcgmCorrelator(
        vllm_metrics_url="http://vllm.test/metrics",
        dcgm_metrics_url="http://dcgm.test/metrics",
        output_dir=tmp_path,
        http_client=client,
    )
    try:
        rows = correlator.collect_once(observed_at=1730000002.7)
    finally:
        client.close()
    assert rows == [
        {
            "schema_version": SCHEMA_VERSION,
            "timestamp": "2024-10-27T03:33:20Z",
            "timestamp_window_seconds": 5,
            "gpu_uuid": None,
            "gpu_index": None,
            "dcgm_sm_clock": None,
            "dcgm_mem_clock": None,
            "dcgm_gpu_temp": None,
            "dcgm_mem_temp": None,
            "dcgm_power_usage": None,
            "dcgm_total_energy_consumption": None,
            "dcgm_gpu_util": None,
            "dcgm_mem_copy_util": None,
            "dcgm_fb_free": None,
            "dcgm_fb_used": None,
            "dcgm_xid_errors": None,
            "dcgm_ecc_sbe_volatile_total": None,
            "dcgm_ecc_dbe_volatile_total": None,
            "dcgm_ecc_sbe_aggregate_total": None,
            "dcgm_ecc_dbe_aggregate_total": None,
            "dcgm_nvlink_bandwidth_total": None,
            "vllm_num_requests_running": None,
            "vllm_num_requests_waiting": None,
            "vllm_kv_cache_usage_perc": None,
            "vllm_num_preemptions_total": None,
            "vllm_e2e_request_latency_seconds_p99": None,
        }
    ]


@pytest.mark.harness
def test_run_writes_dcgm_correlated_jsonl_for_each_sample(tmp_path: Path) -> None:
    client = make_client()
    times = iter([1730000002.7, 1730000002.8, 1730000007.1, 1730000007.2])
    sleeps: list[float] = []
    correlator = DcgmCorrelator(
        vllm_metrics_url="http://vllm.test/metrics",
        dcgm_metrics_url="http://dcgm.test/metrics",
        output_dir=tmp_path,
        duration_seconds=6,
        interval_seconds=5,
        http_client=client,
        time_fn=lambda: next(times),
        sleep_fn=sleeps.append,
    )
    try:
        path = correlator.run()
    finally:
        client.close()
    assert path == tmp_path / OUTPUT_FILENAME
    lines = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    assert len(lines) == 4
    assert {line["timestamp"] for line in lines} == {
        "2024-10-27T03:33:20Z",
        "2024-10-27T03:33:25Z",
    }
    assert sleeps and sleeps[0] > 0

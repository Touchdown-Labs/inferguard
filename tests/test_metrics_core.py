"""Tests for the pure Prometheus parser."""

from inferguard.metrics_core import (
    LabeledSample,
    histogram_avg,
    parse_labeled_prometheus_text,
    parse_prometheus_text,
)


def test_parse_basic_metric() -> None:
    text = "foo_metric 42.5\n"
    result = parse_prometheus_text(text)
    assert result == {"foo_metric": 42.5}


def test_parse_discards_labels() -> None:
    text = 'foo_metric{a="b",c="d"} 7.0\n'
    result = parse_prometheus_text(text)
    assert result == {"foo_metric": 7.0}


def test_parse_skips_comments_and_blanks() -> None:
    text = "# HELP foo bar\n# TYPE foo gauge\n\nfoo 1.0\n"
    result = parse_prometheus_text(text)
    assert result == {"foo": 1.0}


def test_parse_labeled_preserves_labels() -> None:
    text = 'vllm:kv_transfer_errors_total{connector="nixl",role="prefill"} 3\n'
    samples = parse_labeled_prometheus_text(text)
    assert len(samples) == 1
    s = samples[0]
    assert s.name == "vllm:kv_transfer_errors_total"
    assert s.value == 3.0
    assert s.labels == {"connector": "nixl", "role": "prefill"}


def test_parse_labeled_handles_escapes() -> None:
    text = 'foo{msg="hello\\"world"} 1\n'
    samples = parse_labeled_prometheus_text(text)
    assert samples[0].labels["msg"] == 'hello"world'


def test_parse_labeled_empty_label_block() -> None:
    text = "bar 2.0\n"
    samples = parse_labeled_prometheus_text(text)
    assert samples == [LabeledSample(name="bar", value=2.0, labels={})]


def test_histogram_avg() -> None:
    metrics = {
        "vllm:time_to_first_token_seconds_sum": 2.0,
        "vllm:time_to_first_token_seconds_count": 10,
    }
    assert histogram_avg(metrics, "vllm:time_to_first_token_seconds") == 0.2


def test_histogram_avg_zero_count_returns_none() -> None:
    metrics = {"foo_sum": 1.0, "foo_count": 0}
    assert histogram_avg(metrics, "foo") is None


def test_histogram_avg_missing_returns_none() -> None:
    assert histogram_avg({"foo_sum": 1.0}, "foo") is None


def test_parse_fixture_vllm() -> None:
    text = _read_fixture("vllm.txt")
    result = parse_prometheus_text(text)
    assert result["vllm:gpu_cache_usage_perc"] == 0.82
    assert int(result["vllm:num_requests_running"]) == 24
    # Histogram parts present for both TTFT and TPOT.
    assert histogram_avg(result, "vllm:time_to_first_token_seconds") is not None
    assert histogram_avg(result, "vllm:time_per_output_token_seconds") is not None


def test_parse_fixture_sglang() -> None:
    text = _read_fixture("sglang.txt")
    result = parse_prometheus_text(text)
    assert result["sglang:token_usage"] == 0.55
    assert int(result["sglang:num_running_reqs"]) == 12


def _read_fixture(name: str) -> str:
    from pathlib import Path

    return (Path(__file__).parent / "fixtures" / name).read_text()

import json
import subprocess

from typer.testing import CliRunner

from inferguard.analyze import AnalyzeOptions, analyze_results
from inferguard.bench.upstream import UpstreamBenchConfig, run_upstream
from inferguard.cli import app


def test_bench_upstream_help_surfaces_options() -> None:
    result = CliRunner().invoke(app, ["bench", "upstream", "--help"])

    assert result.exit_code == 0
    assert "vllm" in result.stdout
    assert "sglang" in result.stdout
    assert "--profile" in result.stdout
    assert "radix" in result.stdout


def test_vllm_upstream_mocked_subprocess_writes_artifacts(monkeypatch, tmp_path) -> None:
    captured = {}

    def fake_run(args, check, capture_output, text, timeout, env):
        captured["args"] = args
        captured["env"] = env
        payload = {
            "num_requests": 2,
            "successful_requests": 2,
            "request_throughput": 4.0,
            "output_throughput": 16.0,
            "total_input_tokens": 20,
            "total_output_tokens": 8,
            "mean_ttft_ms": 50.0,
            "p99_ttft_ms": 70.0,
            "mean_e2el_ms": 200.0,
            "p99_e2el_ms": 250.0,
        }
        return subprocess.CompletedProcess(args, 0, stdout=json.dumps(payload), stderr="")

    monkeypatch.setattr("inferguard.bench.upstream.subprocess.run", fake_run)
    out = tmp_path / "upstream"

    result = run_upstream(
        UpstreamBenchConfig(
            engine="vllm",
            profile="prefix-repetition",
            model="m",
            endpoint="http://localhost:8000",
            output_dir=out,
            num_prompts=2,
        )
    )

    assert captured["args"][:3] == ["vllm", "bench", "serve"]
    assert "prefix_repetition" in captured["args"]
    assert result["run"]["schema_version"] == "inferguard-bench-upstream/v1"
    assert result["summary"]["schema_version"] == "inferguard-bench-summary/v1"
    for name in [
        "run.json",
        "config.json",
        "requests.jsonl",
        "metrics.jsonl",
        "summary.json",
        "upstream.json",
        "upstream_stdout.txt",
        "upstream_stderr.txt",
    ]:
        assert (out / name).exists()

    report = analyze_results(tmp_path, AnalyzeOptions(output_dir=tmp_path / "report", output_format="json"))
    assert report["cells"][0]["source_format"] == "inferguard-bench-native"
    assert report["cells"][0]["metrics"]["p99_ttft"] == 0.07


def test_sglang_radix_toggle_sets_env(monkeypatch, tmp_path) -> None:
    captured = {}

    def fake_run(args, check, capture_output, text, timeout, env):
        captured["args"] = args
        captured["env"] = env
        payload = {"num_requests": 1, "successful_requests": 1, "mean_ttft_ms": 10.0}
        return subprocess.CompletedProcess(args, 0, stdout=json.dumps(payload), stderr="")

    monkeypatch.setattr("inferguard.bench.upstream.subprocess.run", fake_run)

    run_upstream(
        UpstreamBenchConfig(
            engine="sglang",
            profile="random",
            model="m",
            endpoint="http://127.0.0.1:30000",
            output_dir=tmp_path / "sglang",
            enable_radix_cache=False,
        )
    )

    assert captured["args"][:3] == ["python3", "-m", "sglang.bench_serving"]
    assert captured["env"]["SGLANG_ENABLE_RADIX_CACHE"] == "0"


def test_upstream_cli_invokes_mocked_wrapper(monkeypatch, tmp_path) -> None:
    def fake_run_upstream(config):
        return {
            "summary": {
                "request_counts": {"total": 1, "success": 1, "failed": 0},
                "schema_version": "inferguard-bench-summary/v1",
            }
        }

    monkeypatch.setattr("inferguard.cli.run_upstream", fake_run_upstream)
    result = CliRunner().invoke(
        app,
        [
            "bench",
            "upstream",
            "vllm",
            "--profile",
            "random",
            "--model",
            "m",
            "--output-dir",
            str(tmp_path / "out"),
        ],
    )

    assert result.exit_code == 0
    assert "Wrote InferGuard bench artifacts" in result.stdout

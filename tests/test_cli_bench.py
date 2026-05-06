from pathlib import Path

from typer.testing import CliRunner

from inferguard.cli import app

FIXTURES = Path(__file__).parent / "fixtures"


def test_bench_help_surfaces_commands() -> None:
    result = CliRunner().invoke(app, ["bench", "--help"])

    assert result.exit_code == 0
    assert "replay" in result.stdout
    assert "kv-stress" in result.stdout


def test_bench_replay_help() -> None:
    result = CliRunner().invoke(app, ["bench", "replay", "--help"])

    assert result.exit_code == 0
    assert "--trace-dir" in result.stdout
    assert "--concurrency" in result.stdout


def test_bench_kv_stress_help() -> None:
    result = CliRunner().invoke(app, ["bench", "kv-stress", "--help"])

    assert result.exit_code == 0
    assert "--context-lengths" in result.stdout
    assert "--output-tokens" in result.stdout


def test_bench_replay_missing_trace_dir_exits_cleanly(tmp_path) -> None:
    result = CliRunner().invoke(
        app,
        [
            "bench",
            "replay",
            "--endpoint",
            "http://local/v1/chat/completions",
            "--model",
            "m",
            "--trace-dir",
            str(tmp_path / "missing"),
            "--output-dir",
            str(tmp_path / "out"),
        ],
    )

    assert result.exit_code == 3
    assert "trace-dir does not exist" in result.stderr


def test_bench_replay_rejects_endpoint_query(tmp_path) -> None:
    trace_dir = tmp_path / "traces"
    trace_dir.mkdir()
    (trace_dir / "trace.jsonl").write_text(
        '{"trace_id":"t","session_id":"s","turn_index":0,"workload_class":"coding-long",'
        '"messages":[{"role":"user","content":"hi"}],"metadata":{}}\n',
        encoding="utf-8",
    )

    result = CliRunner().invoke(
        app,
        [
            "bench",
            "replay",
            "--endpoint",
            "http://local/v1/chat/completions?token=secret",
            "--model",
            "m",
            "--trace-dir",
            str(trace_dir),
            "--output-dir",
            str(tmp_path / "out"),
        ],
    )

    assert result.exit_code == 3
    assert "must not include userinfo" in result.stderr


def test_preflight_command_surfaces_hma_warning() -> None:
    result = CliRunner().invoke(
        app,
        [
            "preflight",
            "--model",
            "deepseek-ai/DeepSeek-V4-Pro",
            "--engine",
            "vllm",
            "--kv-offloading-backend",
            "native",
            "--no-disable-hybrid-kv-cache-manager",
            "--json",
        ],
    )

    assert result.exit_code == 1
    assert "inferguard-preflight/v1" in result.stdout
    assert "hma_offload_incompatible" in result.stdout


def test_lmcache_compat_cli_can_fail_on_missing_required() -> None:
    result = CliRunner().invoke(
        app,
        [
            "lmcache-compat",
            "--engine-metrics-file",
            str(FIXTURES / "lmcache_metrics/mp_modal_real_slice.prom"),
            "--lmcache-metrics-file",
            str(FIXTURES / "lmcache_metrics/mp_modal_real_slice.prom"),
            "--expect-mode",
            "mp",
            "--fail-on",
            "missing-required",
            "--json",
        ],
    )

    assert result.exit_code == 1
    assert '"detected_mode": "mp"' in result.stdout
    assert "lmcache_mp_lookup_counters_missing" in result.stdout

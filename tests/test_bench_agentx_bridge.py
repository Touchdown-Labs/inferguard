import json

from inferguard.bench.agentx_bridge import AgentXReplayConfig, run_agentx_replay
from inferguard.cli import app
from typer.testing import CliRunner


def _stderr(result):
    try:
        return result.stderr
    except ValueError:
        return result.output


def test_agentx_replay_help_surfaces_required_flags() -> None:
    result = CliRunner().invoke(app, ["bench", "agentx-replay", "--help"])

    assert result.exit_code == 0
    assert "--trace-source" in result.stdout
    assert "--allow-network-clone" in result.stdout


def test_agentx_replay_requires_tester_without_network_clone(tmp_path) -> None:
    result = CliRunner().invoke(
        app,
        [
            "bench",
            "agentx-replay",
            "--endpoint",
            "http://local:8000",
            "--model",
            "m",
            "--trace-source",
            "semianalysisai/cc-traces-0",
            "--output-dir",
            str(tmp_path / "out"),
        ],
    )

    assert result.exit_code == 3
    assert "Pass --tester-path" in _stderr(result)
    assert "--allow-network-clone" in _stderr(result)


def test_agentx_replay_smoke_with_fake_tester(tmp_path) -> None:
    tester = tmp_path / "kv-cache-tester" / "trace_replay_tester.py"
    tester.parent.mkdir()
    tester.write_text(
        """
import argparse
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument('--api-endpoint', required=True)
parser.add_argument('--trace-directory')
parser.add_argument('--hf-dataset')
parser.add_argument('--start-users', required=True)
parser.add_argument('--max-users', required=True)
parser.add_argument('--test-duration', required=True)
parser.add_argument('--output-dir', required=True)
parser.add_argument('--metrics-output-prefix', required=True)
parser.add_argument('--timing-strategy', required=True)
parser.add_argument('--recycle', action='store_true')
args = parser.parse_args()
assert args.start_users == args.max_users == '2'
assert args.timing_strategy == 'original'
assert args.recycle
out = Path(args.output_dir)
out.mkdir(parents=True, exist_ok=True)
(out / 'detailed_results.csv').write_text(
    'user_id,trace_id,request_idx,success,request_start_time,request_complete_time,ttft,ttlt,itl,input_tokens,output_tokens_actual,output_tokens_expected,cache_hit_blocks,cache_miss_blocks\\n'
    'u1,t1,0,True,1.0,3.0,0.4,2.0,0.1,100,20,24,3,2\\n',
    encoding='utf-8',
)
Path(args.metrics_output_prefix + '_server_metrics.csv').write_text(
    'prefix_cache_hits,prefix_cache_queries\\n1,2\\n', encoding='utf-8'
)
""",
        encoding="utf-8",
    )
    traces = tmp_path / "traces"
    traces.mkdir()
    out_dir = tmp_path / "out"

    result = run_agentx_replay(
        AgentXReplayConfig(
            endpoint="http://local:8000",
            model="m",
            trace_source=str(traces),
            concurrency=2,
            duration_seconds=60,
            output_dir=out_dir,
            tester_path=tester.parent,
        )
    )

    assert result["run"]["schema_version"] == "inferguard-bench-agentx/v1"
    assert result["summary"]["schema_version"] == "inferguard-bench-summary/v1"
    assert result["summary"]["request_counts"]["success"] == 1
    metric = json.loads((out_dir / "metrics.jsonl").read_text(encoding="utf-8"))
    assert metric["input_tokens_source"] == "server_authoritative"
    assert metric["metadata"]["cache_hit_blocks"] == 3
    assert (out_dir / "metrics_server_metrics.csv").exists()

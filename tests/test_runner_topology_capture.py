import asyncio
import json

from inferguard.bench.client import ChatResult
from inferguard.bench.runner import BenchConfig, run_replay


class FakeClient:
    def __init__(self, endpoint: str, *, model: str, timeout: float = 300.0) -> None:
        self.endpoint = endpoint
        self.model = model
        self.timeout = timeout

    async def stream_chat(self, http, *, messages, output_tokens, metadata=None):
        return ChatResult(
            success=True,
            start_time=1.0,
            end_time=1.25,
            latency_seconds=0.25,
            ttft_seconds=0.05,
            output_text="ok",
            input_tokens=12,
            output_tokens=2,
            input_tokens_source="estimated",
            output_tokens_source="estimated",
            status_code=200,
        )


async def _run_with_topology_env(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr("inferguard.bench.runner.OpenAIStreamingChatClient", FakeClient)
    for key, value in {
        "TP": "8",
        "EP_SIZE": "8",
        "DP_ATTENTION": "false",
        "OFFLOADING": "none",
        "SPEC_DECODING": "mtp",
        "HW": "h200",
        "MODEL_PREFIX": "deepseek",
        "FRAMEWORK": "vllm",
        "PRECISION": "FP8",
        "IMAGE": "vllm/image:tag",
        "IS_MULTINODE": "true",
        "PREFILL_NUM_WORKERS": "2",
        "PREFILL_TP": "4",
        "DECODE_NUM_WORKERS": "1",
        "DECODE_TP": "8",
    }.items():
        monkeypatch.setenv(key, value)
    trace_dir = tmp_path / "traces"
    trace_dir.mkdir()
    (trace_dir / "trace.jsonl").write_text(
        json.dumps(
            {
                "trace_id": "trace-1",
                "session_id": "session-1",
                "turn_index": 0,
                "workload_class": "coding-long",
                "messages": [{"role": "user", "content": "hello"}],
                "expected_input_tokens": 8,
                "expected_output_tokens": 4,
                "metadata": {},
            }
        )
        + "\n",
        encoding="utf-8",
    )

    await run_replay(
        BenchConfig(
            command="replay",
            endpoint="http://local/v1/chat/completions",
            model="test-model",
            trace_dir=trace_dir,
            concurrency_levels=[1],
            output_dir=tmp_path / "out",
            output_tokens=4,
        )
    )


def test_runner_captures_topology_env_vars(monkeypatch, tmp_path) -> None:
    asyncio.run(_run_with_topology_env(monkeypatch, tmp_path))

    config = json.loads((tmp_path / "out" / "config.json").read_text())
    assert config["schema_version"] == "inferguard-bench-config/v1"
    assert config["topology"]["tp"] == "8"
    assert config["topology"]["ep_size"] == "8"
    assert config["topology"]["hw"] == "h200"
    assert config["topology"]["prefill_num_workers"] == "2"
    assert config["topology"]["decode_tp"] == "8"

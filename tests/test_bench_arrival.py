import json

from inferguard.bench.runner import BenchConfig, _arrival_phase, poisson_arrival_offsets, run_replay


class FakeClient:
    def __init__(self, endpoint: str, *, model: str, timeout: float = 300.0) -> None:
        pass

    async def stream_chat(self, http, *, messages, output_tokens, metadata=None):
        from inferguard.bench.client import ChatResult

        return ChatResult(
            success=True,
            start_time=1.0,
            end_time=1.1,
            latency_seconds=0.1,
            ttft_seconds=0.01,
            output_text="ok",
            input_tokens=1,
            output_tokens=1,
            input_tokens_source="estimated",
            output_tokens_source="estimated",
        )


def test_poisson_seed_is_deterministic() -> None:
    first = poisson_arrival_offsets(8, rate_rps=12.0, seed=7)
    second = poisson_arrival_offsets(8, rate_rps=12.0, seed=7)
    third = poisson_arrival_offsets(8, rate_rps=12.0, seed=8)
    assert first == second
    assert first != third
    assert first == sorted(first)


def test_onoff_32_phase_toggle() -> None:
    assert _arrival_phase(0) == "on"
    assert _arrival_phase(31) == "on"
    assert _arrival_phase(32) == "off"
    assert _arrival_phase(63) == "off"
    assert _arrival_phase(64) == "on"


async def _closed_loop_default_keeps_v1_summary(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr("inferguard.bench.runner.OpenAIStreamingChatClient", FakeClient)
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
                "metadata": {},
            }
        )
        + "\n",
        encoding="utf-8",
    )
    result = await run_replay(
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
    assert result["summary"]["schema_version"] == "inferguard-bench-summary/v1"


def test_closed_loop_default_keeps_v1_summary(monkeypatch, tmp_path) -> None:
    import asyncio

    asyncio.run(_closed_loop_default_keeps_v1_summary(monkeypatch, tmp_path))

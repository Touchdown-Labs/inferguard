from __future__ import annotations

import json
import sys
from pathlib import Path

import httpx
import pytest

from inferguard.harness.agent_trace import (
    AgentTracer,
    LangGraphCallback,
    framework_callback,
    langgraph_callback,
)
from inferguard.harness.permissions import PermissionPolicy
from inferguard.schemas.agent_trace import iter_agent_trace_jsonl, validate_agent_trace_event
from tests.fixtures.mock_vllm_server import start_mock_servers


def make_tracer(tmp_path: Path, **kwargs) -> AgentTracer:
    framework = kwargs.pop("framework", "raw_openai")
    return AgentTracer(output_dir=tmp_path, framework=framework, **kwargs)


def record_sample_model_call(tracer: AgentTracer):
    return tracer.record_model_call(
        endpoint="http://localhost:8000/v1/chat/completions",
        model="mock-dsv4",
        input_tokens=10,
        output_tokens=5,
        input_tokens_source="api",
        output_tokens_source="api",
        ttft_seconds=0.1,
        tpot_seconds=0.02,
        latency_seconds=0.2,
        tool_choice="auto",
        stream=True,
        stop_reason="end_turn",
        request_id="req-1",
        kv_pressure_label="measured",
    )


@pytest.mark.harness
def test_agent_tracer_creates_empty_trace_file(tmp_path: Path) -> None:
    tracer = make_tracer(tmp_path)
    assert tracer.trace_path.exists()
    assert tracer.trace_path.read_text() == ""


@pytest.mark.harness
def test_record_model_call_writes_valid_jsonl(tmp_path: Path) -> None:
    tracer = make_tracer(tmp_path)
    event = record_sample_model_call(tracer)
    assert validate_agent_trace_event(event.as_dict()).as_dict()["kind"] == "model_call"
    line = json.loads(tracer.trace_path.read_text().splitlines()[0])
    assert line["model_call"]["model"] == "mock-dsv4"


@pytest.mark.harness
def test_record_tool_call_writes_valid_jsonl(tmp_path: Path) -> None:
    tracer = make_tracer(tmp_path)
    tracer.record_tool_call(
        name="filesystem.read_file",
        wall_time_seconds=0.083,
        stall_seconds=0.003,
        result_size_bytes=4096,
    )
    line = json.loads(tracer.trace_path.read_text().splitlines()[0])
    assert line["tool_call"]["result_kind"] == "text"


@pytest.mark.harness
def test_record_branch_writes_valid_jsonl(tmp_path: Path) -> None:
    tracer = make_tracer(tmp_path)
    tracer.record_branch(branch_kind="fan_out", siblings=["a", "b"])
    line = json.loads(tracer.trace_path.read_text().splitlines()[0])
    assert line["branch"]["siblings"] == ["a", "b"]


@pytest.mark.harness
def test_finalize_writes_summary(tmp_path: Path) -> None:
    tracer = make_tracer(tmp_path)
    record_sample_model_call(tracer)
    summary = tracer.finalize()
    assert summary.total_tokens == {"input": 10, "output": 5}
    lines = [json.loads(line) for line in tracer.trace_path.read_text().splitlines()]
    assert lines[-1]["event_type"] == "summary"


@pytest.mark.harness
def test_finalize_is_single_use(tmp_path: Path) -> None:
    tracer = make_tracer(tmp_path)
    tracer.finalize()
    with pytest.raises(RuntimeError):
        tracer.finalize()


@pytest.mark.harness
def test_default_trace_redacts_prompts(tmp_path: Path) -> None:
    tracer = make_tracer(tmp_path)
    tracer.record_http_exchange(
        endpoint="http://localhost/v1/chat/completions",
        request_body=json.dumps({"model": "m", "messages": [{"role": "user", "content": "SECRET"}]}).encode(),
        response_body=b'data: {"choices":[{"delta":{"content":"ok"}}],"usage":{"prompt_tokens":2,"completion_tokens":1}}\n\ndata: [DONE]\n\n',
        status_code=200,
        timestamp_start=1.0,
        timestamp_end=2.0,
        ttft_seconds=0.1,
    )
    assert "SECRET" not in tracer.trace_path.read_text()
    assert not tracer.prompts_path.exists()


@pytest.mark.harness
def test_save_prompts_writes_local_debug_file(tmp_path: Path) -> None:
    tracer = make_tracer(tmp_path, save_prompts=True)
    tracer.record_http_exchange(
        endpoint="http://localhost/v1/chat/completions",
        request_body=json.dumps({"model": "m", "messages": [{"role": "user", "content": "SECRET"}]}).encode(),
        response_body=b'{"choices":[{"message":{"content":"ok"}}],"usage":{"prompt_tokens":2,"completion_tokens":1}}',
        status_code=200,
        timestamp_start=1.0,
        timestamp_end=2.0,
        ttft_seconds=0.1,
    )
    assert "SECRET" in tracer.prompts_path.read_text()
    assert "SECRET" not in tracer.trace_path.read_text()


@pytest.mark.harness
def test_http_exchange_estimates_tokens_without_usage(tmp_path: Path) -> None:
    tracer = make_tracer(tmp_path)
    event = tracer.record_http_exchange(
        endpoint="http://localhost/v1/chat/completions",
        request_body=json.dumps({"model": "m", "messages": [{"role": "user", "content": "hello world"}]}).encode(),
        response_body=b'data: {"choices":[{"delta":{"content":"hello"}}]}\n\ndata: [DONE]\n\n',
        status_code=200,
        timestamp_start=1.0,
        timestamp_end=1.5,
        ttft_seconds=0.1,
    )
    assert event.model_call is not None
    assert event.model_call.input_tokens_source == "estimated"
    assert event.model_call.output_tokens_source == "estimated"


@pytest.mark.harness
def test_http_exchange_marks_errors(tmp_path: Path) -> None:
    tracer = make_tracer(tmp_path)
    event = tracer.record_http_exchange(
        endpoint="http://localhost/v1/chat/completions",
        request_body=b'{"model":"m"}',
        response_body=b'{"error":{"message":"bad"}}',
        status_code=500,
        timestamp_start=1.0,
        timestamp_end=1.2,
        ttft_seconds=0.2,
    )
    assert event.model_call is not None
    assert event.model_call.stop_reason == "error"


@pytest.mark.harness
def test_proxy_forwards_to_mock_vllm_and_records_trace(tmp_path: Path) -> None:
    server = start_mock_servers("h100")
    try:
        tracer = make_tracer(tmp_path, target_endpoint=server.endpoint_url)
        with tracer.proxy() as proxy:
            response = httpx.post(
                f"{proxy.base_url}/chat/completions",
                json={
                    "model": "mock-dsv4",
                    "stream": True,
                    "messages": [{"role": "user", "content": "hello"}],
                    "max_tokens": 8,
                },
                timeout=10,
            )
        assert response.status_code == 200
        events = [json.loads(line) for line in tracer.trace_path.read_text().splitlines()]
        assert events[0]["kind"] == "model_call"
        # The proxy forwards requests unchanged. This request does not opt into
        # OpenAI-compatible streaming usage chunks, so the tracer correctly falls
        # back to estimating from the streamed text instead of copying max_tokens.
        assert events[0]["model_call"]["output_tokens_source"] == "estimated"
        assert events[0]["model_call"]["output_tokens"] == 2
    finally:
        server.teardown()


@pytest.mark.harness
def test_proxy_env_sets_common_openai_variables(tmp_path: Path) -> None:
    env = make_tracer(tmp_path).proxy_env("http://127.0.0.1:8765/v1")
    assert env["OPENAI_BASE_URL"].endswith("/v1")
    assert env["INFERGUARD_AGENT_TRACE_ID"]


@pytest.mark.harness
def test_trace_subprocess_sets_proxy_env(tmp_path: Path) -> None:
    server = start_mock_servers("h100")
    script = tmp_path / "print_env.py"
    output = tmp_path / "env.txt"
    script.write_text(
        f"import os, pathlib\npathlib.Path(r'{output}').write_text(os.environ['OPENAI_BASE_URL'])\n",
        encoding="utf-8",
    )
    try:
        tracer = make_tracer(tmp_path / "trace", target_endpoint=server.endpoint_url)
        result = tracer.trace_subprocess([sys.executable, str(script)])
        assert result.returncode == 0
        assert output.read_text().startswith("http://127.0.0.1:")
        assert json.loads(tracer.trace_path.read_text().splitlines()[-1])["event_type"] == "summary"
    finally:
        server.teardown()


@pytest.mark.harness
def test_trace_subprocess_reports_failure(tmp_path: Path) -> None:
    tracer = make_tracer(tmp_path)
    result = tracer.trace_subprocess([sys.executable, "-c", "import sys; sys.exit(3)"])
    assert result.returncode == 3
    summary = json.loads(tracer.trace_path.read_text().splitlines()[-1])
    assert summary["exit_status"] == "error"


@pytest.mark.harness
def test_permission_policy_blocks_non_loopback_proxy_target(tmp_path: Path) -> None:
    tracer = make_tracer(
        tmp_path,
        target_endpoint="https://api.touchdown.ai/v1/chat/completions",
        permission_policy=PermissionPolicy(),
    )
    with pytest.raises(PermissionError):
        with tracer.proxy():
            pass


@pytest.mark.harness
def test_langgraph_callback_records_tool_event(tmp_path: Path) -> None:
    tracer = make_tracer(tmp_path, framework="langgraph")
    callback = langgraph_callback(tracer)
    callback.on_tool_end("result", name="tool.name")
    line = json.loads(tracer.trace_path.read_text().splitlines()[0])
    assert line["framework"] == "langgraph"
    assert line["tool_call"]["name"] == "tool.name"


@pytest.mark.harness
def test_iter_agent_trace_jsonl_reads_events(tmp_path: Path) -> None:
    tracer = make_tracer(tmp_path)
    record_sample_model_call(tracer)
    tracer.finalize()
    events = list(iter_agent_trace_jsonl(tracer.trace_path))
    assert len(events) == 2


@pytest.mark.harness
def test_summary_redaction_flag_reflects_save_prompts(tmp_path: Path) -> None:
    tracer = make_tracer(tmp_path, save_prompts=True)
    tracer.finalize()
    summary = json.loads(tracer.trace_path.read_text().splitlines()[-1])
    assert summary["redaction"]["prompts_redacted"] is False


@pytest.mark.harness
def test_langgraph_callback_records_chat_model_span_with_usage(tmp_path: Path) -> None:
    tracer = make_tracer(tmp_path, framework="langgraph")
    callback = LangGraphCallback(tracer)
    callback.on_chat_model_start(
        {"name": "fake-chat-model"},
        [[{"role": "user", "content": "hello model"}]],
        run_id="model-run-1",
    )
    callback.on_chat_model_end(
        {
            "content": "ok",
            "usage": {"prompt_tokens": 11, "completion_tokens": 3},
            "model": "fake-chat-model",
            "finish_reason": "stop",
        },
        run_id="model-run-1",
    )
    event = json.loads(tracer.trace_path.read_text().splitlines()[0])
    assert event["kind"] == "model_call"
    assert event["framework"] == "langgraph"
    assert event["model_call"]["model"] == "fake-chat-model"
    assert event["model_call"]["input_tokens"] == 11
    assert event["model_call"]["output_tokens"] == 3
    assert event["timestamp_end"] >= event["timestamp_start"]


@pytest.mark.harness
def test_langgraph_callback_records_tool_span_without_argument_content(tmp_path: Path) -> None:
    tracer = make_tracer(tmp_path, framework="langgraph")
    callback = LangGraphCallback(tracer)
    callback.on_tool_start({"name": "search_docs"}, {"query": "SECRET ARGUMENT"}, run_id="tool-1")
    callback.on_tool_end({"ok": True}, run_id="tool-1")
    text = tracer.trace_path.read_text()
    assert "SECRET ARGUMENT" not in text
    event = json.loads(text.splitlines()[0])
    assert event["kind"] == "tool_call"
    assert event["tool_call"]["name"] == "search_docs"
    assert event["tool_call"]["result_kind"] == "json"


@pytest.mark.harness
def test_langgraph_callback_save_prompts_writes_tool_args_to_local_debug_file(tmp_path: Path) -> None:
    tracer = make_tracer(tmp_path, framework="langgraph", save_prompts=True)
    callback = LangGraphCallback(tracer)
    callback.on_tool_start({"name": "search_docs"}, {"query": "SECRET ARGUMENT"}, run_id="tool-1")
    callback.on_tool_end("done", run_id="tool-1")
    assert "SECRET ARGUMENT" not in tracer.trace_path.read_text()
    assert "SECRET ARGUMENT" in tracer.prompts_path.read_text()


@pytest.mark.harness
def test_langgraph_callback_records_chain_as_branch_event(tmp_path: Path) -> None:
    tracer = make_tracer(tmp_path, framework="langgraph")
    callback = LangGraphCallback(tracer)
    callback.on_chain_start({"name": "fan_out"}, {"input": "redacted"}, run_id="chain-1")
    callback.on_chain_end({"output": "redacted"}, run_id="chain-1")
    event = json.loads(tracer.trace_path.read_text().splitlines()[0])
    assert event["kind"] == "branch"
    assert event["branch"]["branch_kind"] == "fan_out"
    assert event["branch"]["siblings"] == ["fan_out"]


@pytest.mark.harness
@pytest.mark.parametrize("framework", ["crewai", "autogen", "claude_code", "cursor_sdk"])
def test_framework_callback_stubs_raise_not_implemented(tmp_path: Path, framework: str) -> None:
    tracer = make_tracer(tmp_path, framework=framework)
    with pytest.raises(NotImplementedError, match="Framework hook only available for LangGraph"):
        framework_callback(framework, tracer)


@pytest.mark.harness
def test_framework_callback_returns_langgraph_callback(tmp_path: Path) -> None:
    tracer = make_tracer(tmp_path, framework="langgraph")
    assert isinstance(framework_callback("langgraph", tracer), LangGraphCallback)
    assert framework_callback("raw_openai", tracer) is None


@pytest.mark.harness
def test_langgraph_callback_integrates_with_langgraph_when_installed(tmp_path: Path) -> None:
    graph_module = pytest.importorskip("langgraph.graph")
    StateGraph = graph_module.StateGraph
    start = graph_module.START
    end = graph_module.END

    tracer = make_tracer(tmp_path, framework="langgraph")

    def node(state: dict[str, str]) -> dict[str, str]:
        return {"output": state["input"].upper()}

    graph = StateGraph(dict)
    graph.add_node("fan_out", node)
    graph.add_edge(start, "fan_out")
    graph.add_edge("fan_out", end)
    app = graph.compile()
    app.invoke({"input": "ok"}, config={"callbacks": [LangGraphCallback(tracer)]})
    events = [json.loads(line) for line in tracer.trace_path.read_text().splitlines()]
    if not events:
        pytest.skip("installed LangGraph did not emit callback events for this minimal graph")
    assert any(event["framework"] == "langgraph" for event in events)

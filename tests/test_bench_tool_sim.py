import asyncio
import json

import httpx

from inferguard.bench.client import OpenAIStreamingChatClient
from inferguard.bench.types import ToolCall


def _sse(content: str, *, done: bool = False) -> bytes:
    chunk = {"choices": [{"delta": {"content": content}}], "usage": {"prompt_tokens": 1, "completion_tokens": 1}}
    body = f"data: {json.dumps(chunk)}\n\n"
    if done:
        body += "data: [DONE]\n\n"
    return body.encode()


async def _run_tool_sim() -> None:
    calls = []

    async def handler(request: httpx.Request) -> httpx.Response:
        calls.append(json.loads(request.content.decode()))
        return httpx.Response(200, content=_sse("x", done=True))

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as http:
        client = OpenAIStreamingChatClient("http://test/v1/chat/completions", model="m")
        result = await client.stream_chat(
            http,
            messages=[{"role": "user", "content": "hi"}],
            output_tokens=2,
            tool_calls=[ToolCall("bash", 20, 1)],
            simulate_tools=True,
        )
    assert len(calls) == 2
    assert result.success is True
    assert result.tool_simulation_seconds >= 0.015
    assert result.engine_processing_seconds < result.latency_seconds


def test_tool_sim_sleep_accounting_and_resume() -> None:
    asyncio.run(_run_tool_sim())


async def _run_tool_sim_disabled() -> None:
    calls = []

    async def handler(request: httpx.Request) -> httpx.Response:
        calls.append(json.loads(request.content.decode()))
        return httpx.Response(200, content=_sse("x", done=True))

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as http:
        client = OpenAIStreamingChatClient("http://test/v1/chat/completions", model="m")
        result = await client.stream_chat(
            http,
            messages=[{"role": "user", "content": "hi"}],
            output_tokens=2,
            tool_calls=[ToolCall("bash", 20, 1)],
            simulate_tools=False,
        )
    assert len(calls) == 1
    assert result.tool_simulation_seconds == 0.0


def test_tool_sim_disabled_is_single_stream() -> None:
    asyncio.run(_run_tool_sim_disabled())

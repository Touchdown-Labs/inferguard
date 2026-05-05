import asyncio

import httpx

from inferguard.bench.client import OpenAIStreamingChatClient


async def _streaming_client_reads_sse_usage_and_ttft() -> None:
    body = (
        'data: {"choices":[{"delta":{"content":"hel"}}]}\n\n'
        'data: {"choices":[{"delta":{"content":"lo"}}]}\n\n'
        'data: {"choices":[],"usage":{"prompt_tokens":11,"completion_tokens":2}}\n\n'
        "data: [DONE]\n\n"
    )

    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/chat/completions"
        return httpx.Response(200, content=body.encode())

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        result = await OpenAIStreamingChatClient(
            "http://test/v1/chat/completions", model="m"
        ).stream_chat(
            http,
            messages=[{"role": "user", "content": "hello"}],
            output_tokens=4,
        )

    assert result.success is True
    assert result.output_text == "hello"
    assert result.ttft_seconds is not None
    assert result.input_tokens == 11
    assert result.output_tokens == 2
    assert result.input_tokens_source == "api_usage"
    assert result.output_tokens_source == "api_usage"


def test_streaming_client_reads_sse_usage_and_ttft() -> None:
    asyncio.run(_streaming_client_reads_sse_usage_and_ttft())


async def _streaming_client_estimates_tokens_without_usage() -> None:
    body = 'data: {"choices":[{"delta":{"content":"hello world"}}]}\n\ndata: [DONE]\n\n'

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=body.encode())

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        result = await OpenAIStreamingChatClient(
            "http://test/v1/chat/completions", model="m"
        ).stream_chat(
            http,
            messages=[{"role": "user", "content": "hello"}],
            output_tokens=4,
        )

    assert result.success is True
    assert result.input_tokens_source == "estimated"
    assert result.output_tokens_source == "estimated"
    assert result.input_tokens > 0
    assert result.output_tokens > 0


def test_streaming_client_estimates_tokens_without_usage() -> None:
    asyncio.run(_streaming_client_estimates_tokens_without_usage())


async def _streaming_client_ignores_role_only_chunk_for_ttft() -> None:
    body = (
        'data: {"choices":[{"delta":{"role":"assistant"}}]}\n\n'
        'data: {"choices":[{"delta":{"content":"real token"}}]}\n\n'
        "data: [DONE]\n\n"
    )

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=body.encode())

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        result = await OpenAIStreamingChatClient(
            "http://test/v1/chat/completions", model="m"
        ).stream_chat(
            http,
            messages=[{"role": "user", "content": "hello"}],
            output_tokens=4,
        )

    assert result.success is True
    assert result.done_seen is True
    assert result.valid_content_seen is True
    assert result.first_sse_seconds is not None
    assert result.first_content_token_seconds is not None
    assert result.ttft_seconds == result.first_content_token_seconds
    assert result.first_content_token_seconds >= result.first_sse_seconds


def test_streaming_client_ignores_role_only_chunk_for_ttft() -> None:
    asyncio.run(_streaming_client_ignores_role_only_chunk_for_ttft())


async def _streaming_client_fails_without_generated_content() -> None:
    body = 'data: {"choices":[{"delta":{"role":"assistant"}}]}\n\ndata: [DONE]\n\n'

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=body.encode())

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        result = await OpenAIStreamingChatClient(
            "http://test/v1/chat/completions", model="m"
        ).stream_chat(
            http,
            messages=[{"role": "user", "content": "hello"}],
            output_tokens=4,
        )

    assert result.success is False
    assert result.valid_content_seen is False
    assert result.ttft_seconds is None
    assert "without non-empty" in (result.error or "")


def test_streaming_client_fails_without_generated_content() -> None:
    asyncio.run(_streaming_client_fails_without_generated_content())

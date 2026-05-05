"""Async OpenAI-compatible streaming chat client."""

from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass
from typing import Any

import httpx

from inferguard.bench.tokenizer import estimate_messages_tokens, estimate_text_tokens
from inferguard.bench.types import ToolCall


@dataclass(frozen=True)
class ChatResult:
    success: bool
    start_time: float
    end_time: float
    latency_seconds: float
    ttft_seconds: float | None
    output_text: str
    input_tokens: int
    output_tokens: int
    input_tokens_source: str
    output_tokens_source: str
    status_code: int | None = None
    error: str | None = None
    first_sse_seconds: float | None = None
    first_content_token_seconds: float | None = None
    done_seen: bool = False
    valid_content_seen: bool = False
    tool_simulation_seconds: float = 0.0
    engine_processing_seconds: float | None = None
    client_queue_seconds: float | None = None
    network_overhead_seconds: float | None = None
    cached_tokens: int | None = None
    content_token_offsets_seconds: tuple[float, ...] = ()


class OpenAIStreamingChatClient:
    """Minimal streaming client for OpenAI-compatible ``/v1/chat/completions`` APIs."""

    def __init__(
        self,
        endpoint: str,
        *,
        model: str,
        timeout: float = 300.0,
        api_key: str | None = None,
        stream: bool = True,
        include_usage: bool = True,
        continuous_usage_stats: bool = False,
    ) -> None:
        self.endpoint = endpoint.rstrip("/")
        self.model = model
        self.timeout = timeout
        self.api_key = api_key
        self.stream = stream
        self.include_usage = include_usage
        self.continuous_usage_stats = continuous_usage_stats

    async def stream_chat(
        self,
        http: httpx.AsyncClient,
        *,
        messages: list[dict[str, Any]],
        output_tokens: int,
        temperature: float = 0.0,
        metadata: dict[str, Any] | None = None,
        tool_calls: list[ToolCall] | None = None,
        simulate_tools: bool = False,
    ) -> ChatResult:
        if simulate_tools and tool_calls:
            first = await self.stream_chat(
                http,
                messages=messages,
                output_tokens=output_tokens,
                temperature=temperature,
                metadata=metadata,
                simulate_tools=False,
            )
            tool_seconds = 0.0
            for call in tool_calls:
                delay = max(0.0, call.latency_ms) / 1000.0 * max(1, call.count)
                tool_seconds += delay
                await asyncio.sleep(delay)
            second = await self.stream_chat(
                http,
                messages=messages,
                output_tokens=output_tokens,
                temperature=temperature,
                metadata=metadata,
                simulate_tools=False,
            )
            latency = second.end_time - first.start_time
            engine_seconds = first.latency_seconds + second.latency_seconds
            return ChatResult(
                success=first.success and second.success,
                start_time=first.start_time,
                end_time=second.end_time,
                latency_seconds=latency,
                ttft_seconds=first.ttft_seconds,
                output_text=first.output_text + second.output_text,
                input_tokens=first.input_tokens + second.input_tokens,
                output_tokens=first.output_tokens + second.output_tokens,
                input_tokens_source=first.input_tokens_source
                if first.input_tokens_source == second.input_tokens_source
                else "mixed",
                output_tokens_source=first.output_tokens_source
                if first.output_tokens_source == second.output_tokens_source
                else "mixed",
                status_code=second.status_code or first.status_code,
                error=first.error or second.error,
                first_sse_seconds=first.first_sse_seconds,
                first_content_token_seconds=first.first_content_token_seconds,
                done_seen=first.done_seen and second.done_seen,
                valid_content_seen=first.valid_content_seen and second.valid_content_seen,
                tool_simulation_seconds=tool_seconds,
                engine_processing_seconds=engine_seconds,
                client_queue_seconds=0.0,
                network_overhead_seconds=max(0.0, latency - engine_seconds - tool_seconds),
            )
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "max_tokens": output_tokens,
            "temperature": temperature,
            "stream": self.stream,
        }
        if self.stream and self.include_usage:
            stream_options: dict[str, Any] = {"include_usage": True}
            if self.continuous_usage_stats:
                stream_options["continuous_usage_stats"] = True
            payload["stream_options"] = stream_options

        start = time.perf_counter()
        ttft: float | None = None
        first_sse: float | None = None
        first_content_token: float | None = None
        done_seen = False
        valid_content_seen = False
        output_parts: list[str] = []
        prompt_tokens: int | None = None
        completion_tokens: int | None = None
        status_code: int | None = None
        cached_tokens: int | None = None
        content_offsets: list[float] = []
        try:
            headers = _request_headers(metadata, self.api_key)
            if not self.stream:
                return await self._chat_once(
                    http, payload=payload, headers=headers, messages=messages
                )
            async with http.stream(
                "POST", self.endpoint, json=payload, headers=headers
            ) as response:
                status_code = response.status_code
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line or line.startswith(":"):
                        continue
                    if line.startswith("data:"):
                        line = line[len("data:") :].strip()
                    if not line:
                        continue
                    now = time.perf_counter()
                    if first_sse is None:
                        first_sse = now - start
                    if line == "[DONE]":
                        done_seen = True
                        break
                    try:
                        chunk = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    usage = chunk.get("usage")
                    if isinstance(usage, dict):
                        prompt_tokens = _int_or_none(usage.get("prompt_tokens"))
                        completion_tokens = _int_or_none(usage.get("completion_tokens"))
                        cached_tokens = _cached_tokens_from_usage(usage)
                    for choice in chunk.get("choices", []) or []:
                        delta = choice.get("delta") or {}
                        content = delta.get("content")
                        if isinstance(content, str):
                            output_parts.append(content)
                            if content:
                                offset = time.perf_counter() - start
                                content_offsets.append(offset)
                                if first_content_token is None:
                                    first_content_token = offset
                                    ttft = first_content_token
                                    valid_content_seen = True
        except Exception as exc:  # noqa: BLE001 - preserve endpoint error in metric artifact
            end = time.perf_counter()
            output_text = "".join(output_parts)
            return ChatResult(
                success=False,
                start_time=start,
                end_time=end,
                latency_seconds=end - start,
                ttft_seconds=ttft,
                output_text=output_text,
                input_tokens=estimate_messages_tokens(messages),
                output_tokens=estimate_text_tokens(output_text),
                input_tokens_source="estimated",
                output_tokens_source="estimated",
                status_code=status_code,
                error=str(exc),
                first_sse_seconds=first_sse,
                first_content_token_seconds=first_content_token,
                done_seen=done_seen,
                valid_content_seen=valid_content_seen,
                engine_processing_seconds=end - start,
                client_queue_seconds=0.0,
                network_overhead_seconds=0.0,
                content_token_offsets_seconds=tuple(content_offsets),
            )

        end = time.perf_counter()
        output_text = "".join(output_parts)
        success = valid_content_seen
        error = None if success else "stream completed without non-empty generated content"
        return ChatResult(
            success=success,
            start_time=start,
            end_time=end,
            latency_seconds=end - start,
            ttft_seconds=ttft,
            output_text=output_text,
            input_tokens=prompt_tokens
            if prompt_tokens is not None
            else estimate_messages_tokens(messages),
            output_tokens=completion_tokens
            if completion_tokens is not None
            else estimate_text_tokens(output_text),
            input_tokens_source="api_usage" if prompt_tokens is not None else "estimated",
            output_tokens_source="api_usage" if completion_tokens is not None else "estimated",
            status_code=status_code,
            error=error,
            first_sse_seconds=first_sse,
            first_content_token_seconds=first_content_token,
            done_seen=done_seen,
            valid_content_seen=valid_content_seen,
            engine_processing_seconds=end - start,
            client_queue_seconds=0.0,
            network_overhead_seconds=0.0,
            cached_tokens=cached_tokens,
            content_token_offsets_seconds=tuple(content_offsets),
        )

    async def _chat_once(
        self,
        http: httpx.AsyncClient,
        *,
        payload: dict[str, Any],
        headers: dict[str, str],
        messages: list[dict[str, Any]],
    ) -> ChatResult:
        start = time.perf_counter()
        status_code: int | None = None
        try:
            response = await http.post(self.endpoint, json=payload, headers=headers)
            status_code = response.status_code
            response.raise_for_status()
            data = response.json()
        except Exception as exc:  # noqa: BLE001 - preserve endpoint error in metric artifact
            end = time.perf_counter()
            return ChatResult(
                success=False,
                start_time=start,
                end_time=end,
                latency_seconds=end - start,
                ttft_seconds=None,
                output_text="",
                input_tokens=estimate_messages_tokens(messages),
                output_tokens=0,
                input_tokens_source="estimated",
                output_tokens_source="estimated",
                status_code=status_code,
                error=str(exc),
                engine_processing_seconds=end - start,
                client_queue_seconds=0.0,
                network_overhead_seconds=0.0,
            )
        end = time.perf_counter()
        content = _message_content(data)
        usage = data.get("usage") if isinstance(data, dict) else None
        prompt_tokens = (
            _int_or_none(usage.get("prompt_tokens")) if isinstance(usage, dict) else None
        )
        completion_tokens = (
            _int_or_none(usage.get("completion_tokens")) if isinstance(usage, dict) else None
        )
        cached_tokens = _cached_tokens_from_usage(usage) if isinstance(usage, dict) else None
        output_tokens = (
            completion_tokens if completion_tokens is not None else estimate_text_tokens(content)
        )
        return ChatResult(
            success=bool(content),
            start_time=start,
            end_time=end,
            latency_seconds=end - start,
            ttft_seconds=None,
            output_text=content,
            input_tokens=prompt_tokens
            if prompt_tokens is not None
            else estimate_messages_tokens(messages),
            output_tokens=output_tokens,
            input_tokens_source="api_usage" if prompt_tokens is not None else "estimated",
            output_tokens_source="api_usage" if completion_tokens is not None else "estimated",
            status_code=status_code,
            error=None if content else "response completed without generated content",
            done_seen=True,
            valid_content_seen=bool(content),
            engine_processing_seconds=end - start,
            client_queue_seconds=0.0,
            network_overhead_seconds=0.0,
            cached_tokens=cached_tokens,
        )


def _message_content(data: Any) -> str:
    if not isinstance(data, dict):
        return ""
    for choice in data.get("choices", []) or []:
        if not isinstance(choice, dict):
            continue
        message = choice.get("message") or {}
        content = message.get("content") if isinstance(message, dict) else None
        if isinstance(content, str):
            return content
    return ""


def _cached_tokens_from_usage(usage: dict[str, Any]) -> int | None:
    direct = _int_or_none(usage.get("cached_tokens"))
    if direct is not None:
        return direct
    details = usage.get("prompt_tokens_details")
    if isinstance(details, dict):
        return _int_or_none(details.get("cached_tokens"))
    return None


def _int_or_none(value: Any) -> int | None:
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    return None


def _request_headers(metadata: dict[str, Any] | None, api_key: str | None) -> dict[str, str]:
    headers = _customer_headers(metadata)
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    return headers


def _customer_headers(metadata: dict[str, Any] | None) -> dict[str, str]:
    if not metadata:
        return {}
    customer_id = (
        metadata.get("customer_id") or metadata.get("tenant_id") or metadata.get("customer")
    )
    if customer_id in (None, ""):
        return {}
    # Implements S-21 per-customer KV footprint accounting (see docs/inferguard/24).
    return {"X-Customer-Id": str(customer_id)}

"""OpenAI-compatible mock server for runbook and CI dry-runs.

This is deliberately tiny: it serves `/v1/models`, streaming
`/v1/chat/completions`, and engine-shaped `/metrics` without loading weights or
touching a GPU. It is safe for validating InferGuard wiring before GB200 access.
"""

from __future__ import annotations

import argparse
import asyncio
import json
from typing import Any

from aiohttp import web


class MockState:
    def __init__(self, *, engine: str, model: str) -> None:
        self.engine = engine
        self.model = model
        self.active_requests = 0
        self.total_requests = 0
        self.completed_requests = 0
        self.prompt_tokens = 0
        self.output_tokens = 0
        self.ttft_sum = 0.0
        self.tpot_sum = 0.0
        self.kv_sent = 0
        self.kv_recv = 0
        self._lock = asyncio.Lock()

    async def begin(self) -> None:
        async with self._lock:
            self.active_requests += 1
            self.total_requests += 1

    async def end(self, *, prompt_tokens: int, output_tokens: int) -> None:
        async with self._lock:
            self.active_requests = max(0, self.active_requests - 1)
            self.completed_requests += 1
            self.prompt_tokens += prompt_tokens
            self.output_tokens += output_tokens
            self.ttft_sum += 0.01
            self.tpot_sum += max(output_tokens, 1) * 0.002
            self.kv_sent += max(prompt_tokens + output_tokens, 1) * 128
            self.kv_recv += max(output_tokens, 1) * 64

    def metrics_text(self) -> str:
        prefix = "vllm" if self.engine == "vllm" else "sglang"
        count = max(self.completed_requests, 1)
        token_count = max(self.output_tokens, 1)
        if self.engine == "vllm":
            lines = [
                f"{prefix}:gpu_cache_usage_perc {min(0.95, 0.10 + self.total_requests * 0.01):.6f}",
                f"{prefix}:num_requests_running {self.active_requests}",
                f"{prefix}:num_requests_waiting 0",
                f"{prefix}:num_requests_swapped 0",
            ]
        else:
            lines = [
                f"{prefix}:token_usage {min(0.95, 0.08 + self.total_requests * 0.01):.6f}",
                f"{prefix}:num_running_reqs {self.active_requests}",
                f"{prefix}:num_queue_reqs 0",
            ]
        lines.extend(
            [
                f"{prefix}:num_preemptions_total 0",
                f'{prefix}:kv_transfer_sent_bytes_total{{connector="mock"}} {self.kv_sent}',
                f'{prefix}:kv_transfer_recv_bytes_total{{connector="mock"}} {self.kv_recv}',
                f'{prefix}:kv_transfer_errors_total{{connector="mock"}} 0',
                f"{prefix}:time_to_first_token_seconds_sum {self.ttft_sum:.6f}",
                f"{prefix}:time_to_first_token_seconds_count {count}",
                f"{prefix}:time_per_output_token_seconds_sum {self.tpot_sum:.6f}",
                f"{prefix}:time_per_output_token_seconds_count {token_count}",
                "lmcache:hit_rate 0.70",
                'lmcache:tier_usage{tier="cpu"} 1048576',
                'lmcache:tier_usage{tier="local_disk"} 524288',
            ]
        )
        return "\n".join(lines) + "\n"


def make_app(state: MockState) -> web.Application:
    app = web.Application()

    async def models(_request: web.Request) -> web.Response:
        return web.json_response(
            {"object": "list", "data": [{"id": state.model, "object": "model"}]}
        )

    async def metrics(_request: web.Request) -> web.Response:
        return web.Response(text=state.metrics_text(), content_type="text/plain")

    async def chat(request: web.Request) -> web.StreamResponse:
        payload = await request.json()
        messages = payload.get("messages") or []
        max_tokens = int(payload.get("max_tokens") or 16)
        prompt_tokens = _estimate_prompt_tokens(messages)
        await state.begin()
        response = web.StreamResponse(
            status=200,
            headers={"Content-Type": "text/event-stream", "Cache-Control": "no-cache"},
        )
        await response.prepare(request)
        try:
            await _write_sse(response, {"choices": [{"delta": {"role": "assistant"}}]})
            await asyncio.sleep(0.01)
            emitted = min(max_tokens, 16)
            for idx in range(max(1, min(4, emitted))):
                await _write_sse(
                    response, {"choices": [{"delta": {"content": f"mock-token-{idx} "}}]}
                )
                await asyncio.sleep(0.002)
            await _write_sse(
                response,
                {
                    "choices": [{"delta": {}}],
                    "usage": {
                        "prompt_tokens": prompt_tokens,
                        "completion_tokens": emitted,
                        "total_tokens": prompt_tokens + emitted,
                    },
                },
            )
            await response.write(b"data: [DONE]\n\n")
        finally:
            await state.end(prompt_tokens=prompt_tokens, output_tokens=emitted)
        return response

    app.router.add_get("/v1/models", models)
    app.router.add_post("/v1/chat/completions", chat)
    app.router.add_get("/metrics", metrics)
    return app


async def _write_sse(response: web.StreamResponse, payload: dict[str, Any]) -> None:
    await response.write(f"data: {json.dumps(payload, separators=(',', ':'))}\n\n".encode())


def _estimate_prompt_tokens(messages: list[dict[str, Any]]) -> int:
    chars = sum(
        len(str(message.get("content", ""))) for message in messages if isinstance(message, dict)
    )
    return max(1, chars // 4)


def main() -> None:  # pragma: no cover
    parser = argparse.ArgumentParser(description="InferGuard OpenAI-compatible mock server")
    parser.add_argument("--engine", choices=("vllm", "sglang"), default="vllm")
    parser.add_argument("--model", default="mock-dsv4")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8888)
    args = parser.parse_args()
    print(
        f"inferguard mock-openai {args.engine} model={args.model} → http://{args.host}:{args.port}"
    )
    web.run_app(
        make_app(MockState(engine=args.engine, model=args.model)),
        host=args.host,
        port=args.port,
        print=None,
    )


if __name__ == "__main__":  # pragma: no cover
    main()

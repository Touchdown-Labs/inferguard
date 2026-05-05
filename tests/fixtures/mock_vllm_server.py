"""Aiohttp mock vLLM/Dynamo-vLLM servers for InferGuard integration tests."""

from __future__ import annotations

import argparse
import asyncio
import json
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from aiohttp import web

_RIG_PROFILES: dict[str, dict[str, float]] = {
    "h100": {"ttft": 0.09, "tpot": 0.035, "base_cache": 0.18, "active_cache": 0.18},
    "h200": {"ttft": 0.075, "tpot": 0.03, "base_cache": 0.16, "active_cache": 0.16},
    "b200": {"ttft": 0.045, "tpot": 0.018, "base_cache": 0.12, "active_cache": 0.12},
    "b300": {"ttft": 0.038, "tpot": 0.015, "base_cache": 0.10, "active_cache": 0.10},
    "gb200": {"ttft": 0.032, "tpot": 0.014, "base_cache": 0.09, "active_cache": 0.09},
}


class MockVLLMState:
    """Mutable server state shared with tests and sibling integration fixtures."""

    def __init__(
        self,
        rig_profile: str,
        role: str = "prefill",
        *,
        enable_lmcache: bool = False,
        enable_dynamo_kvbm: bool = False,
        enable_sglang_hicache: bool = False,
        canary_fail: bool = False,
        inject_failure_rate: float = 0.0,
        suppress_usage: bool = False,
        simulate_mtp_bug: bool = False,
        ready_after_seconds: float = 0.0,
        metrics_status_code: int = 200,
        model_id: str = "mock-dsv4",
    ) -> None:
        self.rig_profile = rig_profile
        self.role = role
        self.enable_lmcache = enable_lmcache
        self.enable_dynamo_kvbm = enable_dynamo_kvbm
        self.enable_sglang_hicache = enable_sglang_hicache
        self.canary_fail = canary_fail
        self.inject_failure_rate = inject_failure_rate
        self.suppress_usage = suppress_usage
        self.simulate_mtp_bug = simulate_mtp_bug
        self.ready_after_seconds = ready_after_seconds
        self.metrics_status_code = metrics_status_code
        self.model_id = model_id
        self.started_at = time.monotonic()
        self.profile = _RIG_PROFILES[rig_profile]
        self.active_requests = 0
        self.waiting_requests = 0
        self.total_requests = 0
        self.completed_requests = 0
        self.failed_workloads: set[str] = set()
        self.ttft_sum = 0.0
        self.tpot_sum = 0.0
        self.token_count = 0
        self.kv_sent_bytes = 0
        self.kv_recv_bytes = 0
        self.kv_errors = 0
        self.max_cache_usage = self.profile["base_cache"]
        self._lock = asyncio.Lock()

    async def begin_request(self) -> int:
        async with self._lock:
            self.total_requests += 1
            sequence = self.total_requests
            self.active_requests += 1
            self.max_cache_usage = max(self.max_cache_usage, self.gpu_cache_usage)
            return sequence

    async def end_request(self, *, output_tokens: int, failed: bool = False) -> None:
        async with self._lock:
            self.active_requests = max(0, self.active_requests - 1)
            if failed:
                self.kv_errors += 1
                return
            self.completed_requests += 1
            self.ttft_sum += self.profile["ttft"]
            self.tpot_sum += self.profile["tpot"] * max(output_tokens, 1)
            self.token_count += max(output_tokens, 1)
            transfer_bytes = max(output_tokens, 1) * (8192 if self.rig_profile == "gb200" else 2048)
            self.kv_sent_bytes += transfer_bytes if self.role == "prefill" else transfer_bytes // 2
            self.kv_recv_bytes += transfer_bytes // 2 if self.role == "decode" else transfer_bytes // 4
            self.max_cache_usage = max(self.max_cache_usage, self.gpu_cache_usage)

    @property
    def gpu_cache_usage(self) -> float:
        growth = self.active_requests * self.profile["active_cache"]
        history = min(0.18, self.total_requests * 0.015)
        return min(0.96, self.profile["base_cache"] + growth + history)

    def simulate_failure_for_workload(self, workload_class: str) -> None:
        self.failed_workloads.add(workload_class)

    def should_fail(self, messages: list[dict[str, Any]], sequence: int) -> bool:
        if self.canary_fail:
            return True
        blob = "\n".join(str(message.get("content", "")) for message in messages)
        if any(workload in blob for workload in self.failed_workloads):
            return True
        if self.inject_failure_rate <= 0:
            return False
        period = max(1, round(1.0 / min(self.inject_failure_rate, 1.0)))
        return sequence % period == 0

    @property
    def models_ready(self) -> bool:
        return (time.monotonic() - self.started_at) >= self.ready_after_seconds

    def metrics_text(self) -> str:
        count = max(self.completed_requests, 1)
        token_count = max(self.token_count, 1)
        lines = [
                "# HELP vllm:gpu_cache_usage_perc Mock GPU KV cache usage.",
                "# TYPE vllm:gpu_cache_usage_perc gauge",
                f"vllm:gpu_cache_usage_perc {self.gpu_cache_usage:.6f}",
                f"vllm:num_requests_running {self.active_requests}",
                f"vllm:num_requests_waiting {self.waiting_requests}",
                "vllm:num_requests_swapped 0",
                "vllm:num_preemptions_total 0",
                f'vllm:kv_transfer_sent_bytes_total{{connector="nixl"}} {self.kv_sent_bytes}',
                f'vllm:kv_transfer_recv_bytes_total{{connector="nixl"}} {self.kv_recv_bytes}',
                f'vllm:kv_transfer_errors_total{{connector="nixl"}} {self.kv_errors}',
                f"vllm:time_to_first_token_seconds_sum {self.ttft_sum:.6f}",
                f"vllm:time_to_first_token_seconds_count {count}",
                f"vllm:time_per_output_token_seconds_sum {self.tpot_sum:.6f}",
                f"vllm:time_per_output_token_seconds_count {token_count}",
                "",
            ]
        if self.enable_lmcache:
            lines.extend(
                [
                    'vllm:cache_config_info{kv_connector="LMCacheConnectorV1",kv_role="kv_both"} 1',
                    'lmcache:connector_info{connector="LMCacheConnectorV1"} 1',
                    'lmcache_config_info{connector="nixl",mp_mode="true",enabled="true"} 1',
                    "lmcache:num_hit_tokens 90",
                    "lmcache:num_lookup_hits 88",
                    "lmcache:retrieve_hit_rate 0.73",
                    "lmcache:lookup_hit_rate 0.71",
                    "lmcache:lookup_0_hit_requests 2",
                    "lmcache:local_cpu_evict_count 4",
                    "lmcache:local_cpu_evict_keys_count 8",
                    "lmcache:local_cpu_evict_failed_count 0",
                    "lmcache:local_cache_usage 2147483648",
                    "lmcache:remote_cache_usage 536870912",
                    "lmcache:local_storage_usage 1073741824",
                    "lmcache:local_cpu_hot_cache_count 12",
                    "lmcache:hit_rate 0.73",
                    "lmcache:eviction_count 4",
                    'lmcache:tier_usage{tier="cpu"} 2147483648',
                    'lmcache:tier_usage{tier="local_disk"} 1073741824',
                    'lmcache:tier_usage{tier="remote"} 536870912',
                    "lmcache:remote_bytes_sent_total 33554432",
                    "lmcache:remote_bytes_received_total 67108864",
                    "lmcache:queue_depth 2",
                    "",
                ]
            )
        if self.enable_dynamo_kvbm:
            lines.extend(
                [
                    "dynamo:kvbm_block_residency_seconds_sum 42",
                    "dynamo:kvbm_block_residency_seconds_count 7",
                    'dynamo:kvbm_blocks{tier="l1_gpu"} 128',
                    'dynamo:kvbm_blocks{tier="l2_cpu"} 64',
                    'dynamo:kvbm_blocks{tier="l3_storage"} 16',
                    "dynamo:kvbm_evictions_total 3",
                    "dynamo:kvbm_promotions_total 9",
                    "",
                ]
            )
        if self.enable_sglang_hicache:
            lines.extend(
                [
                    "sglang:hicache_l1_hit_count_total 900",
                    "sglang:hicache_l2_hit_count_total 120",
                    "sglang:hicache_l3_hit_count_total 30",
                    "sglang:hicache_lookup_count_total 1100",
                    "sglang:hicache_l2_bytes 4294967296",
                    "sglang:hicache_l3_bytes 8589934592",
                    "",
                ]
            )
        return "\n".join(lines)


@dataclass
class MockServerHandle:
    """Return object for ``start_mock_servers``."""

    rig_profile: str
    prefill_url: str
    metrics_url: str
    teardown: Callable[[], None]
    state: MockVLLMState
    decode_url: str | None = None
    decode_metrics_url: str | None = None
    decode_state: MockVLLMState | None = None

    @property
    def endpoint_url(self) -> str:
        return f"{self.prefill_url}/v1/chat/completions"

    @property
    def base_url(self) -> str:
        return self.prefill_url

    def simulate_failure_for_workload(self, workload_class: str) -> None:
        self.state.simulate_failure_for_workload(workload_class)
        if self.decode_state is not None:
            self.decode_state.simulate_failure_for_workload(workload_class)


class _AiohttpServerThread:
    def __init__(self, state: MockVLLMState, host: str, port: int) -> None:
        self.state = state
        self.host = host
        self.port = port
        self.loop = asyncio.new_event_loop()
        self.runner: web.AppRunner | None = None
        self.site: web.TCPSite | None = None
        self.bound_port: int | None = None
        self._ready = threading.Event()
        self.thread = threading.Thread(target=self._run, daemon=True)

    def start(self) -> str:
        self.thread.start()
        if not self._ready.wait(timeout=5):
            raise RuntimeError("mock vLLM server did not start")
        return f"http://{self.host}:{self.bound_port}"

    def stop(self) -> None:
        if not self.loop.is_running():
            return
        future = asyncio.run_coroutine_threadsafe(self._cleanup(), self.loop)
        future.result(timeout=5)
        self.loop.call_soon_threadsafe(self.loop.stop)
        self.thread.join(timeout=5)

    def _run(self) -> None:
        asyncio.set_event_loop(self.loop)
        self.loop.run_until_complete(self._start())
        self._ready.set()
        self.loop.run_forever()
        self.loop.close()

    async def _start(self) -> None:
        app = _make_app(self.state)
        self.runner = web.AppRunner(app)
        await self.runner.setup()
        self.site = web.TCPSite(self.runner, self.host, self.port)
        await self.site.start()
        sockets = self.site._server.sockets if self.site._server is not None else []  # noqa: SLF001
        self.bound_port = sockets[0].getsockname()[1]

    async def _cleanup(self) -> None:
        if self.runner is not None:
            await self.runner.cleanup()


def start_mock_servers(
    rig_profile: str,
    port: int = 0,
    *,
    enable_lmcache: bool = False,
    enable_dynamo_kvbm: bool = False,
    enable_sglang_hicache: bool = False,
    canary_fail: bool = False,
    inject_failure_rate: float = 0.0,
    suppress_usage: bool = False,
    simulate_mtp_bug: bool = False,
    ready_after_seconds: float = 0.0,
    metrics_status_code: int = 200,
    model_id: str = "mock-dsv4",
) -> MockServerHandle:
    """Start one mock vLLM server, or prefill+decode servers for GB200."""

    if rig_profile not in _RIG_PROFILES:
        raise ValueError(f"unsupported rig_profile: {rig_profile}")

    host = "127.0.0.1"
    prefill_state = MockVLLMState(
        rig_profile,
        role="prefill",
        enable_lmcache=enable_lmcache,
        enable_dynamo_kvbm=enable_dynamo_kvbm,
        enable_sglang_hicache=enable_sglang_hicache,
        canary_fail=canary_fail,
        inject_failure_rate=inject_failure_rate,
        suppress_usage=suppress_usage,
        simulate_mtp_bug=simulate_mtp_bug,
        ready_after_seconds=ready_after_seconds,
        metrics_status_code=metrics_status_code,
        model_id=model_id,
    )
    prefill_thread = _AiohttpServerThread(prefill_state, host, port)
    prefill_url = prefill_thread.start()
    threads = [prefill_thread]
    decode_url = None
    decode_state = None

    if rig_profile == "gb200":
        decode_state = MockVLLMState(
            rig_profile,
            role="decode",
            enable_lmcache=enable_lmcache,
            enable_dynamo_kvbm=enable_dynamo_kvbm,
            enable_sglang_hicache=enable_sglang_hicache,
            canary_fail=canary_fail,
            inject_failure_rate=inject_failure_rate,
            suppress_usage=suppress_usage,
            simulate_mtp_bug=simulate_mtp_bug,
            ready_after_seconds=ready_after_seconds,
            metrics_status_code=metrics_status_code,
            model_id=model_id,
        )
        decode_thread = _AiohttpServerThread(decode_state, host, 0)
        decode_url = decode_thread.start()
        threads.append(decode_thread)

    def teardown() -> None:
        for thread in reversed(threads):
            thread.stop()

    return MockServerHandle(
        rig_profile=rig_profile,
        prefill_url=prefill_url,
        metrics_url=f"{prefill_url}/metrics",
        teardown=teardown,
        state=prefill_state,
        decode_url=decode_url,
        decode_metrics_url=f"{decode_url}/metrics" if decode_url else None,
        decode_state=decode_state,
    )


def _make_app(state: MockVLLMState) -> web.Application:
    app = web.Application()
    app.router.add_get("/v1/models", _models(state))
    app.router.add_post("/v1/chat/completions", _chat_completions(state))
    app.router.add_get("/metrics", _metrics(state))
    return app


def _models(state: MockVLLMState):
    async def handler(_request: web.Request) -> web.Response:
        if not state.models_ready:
            return web.json_response({"error": "starting"}, status=503)
        return web.json_response({"data": [{"id": state.model_id}]})

    return handler


def _chat_completions(state: MockVLLMState):
    async def handler(request: web.Request) -> web.StreamResponse:
        payload = await request.json()
        messages = payload.get("messages") or []
        max_tokens = int(payload.get("max_tokens") or 16)
        sequence = await state.begin_request()
        if state.should_fail(messages, sequence):
            await asyncio.sleep(0.01)
            await state.end_request(output_tokens=0, failed=True)
            return web.json_response({"error": {"message": "simulated workload failure"}}, status=500)

        if not payload.get("stream", False):
            try:
                await asyncio.sleep(state.profile["ttft"] + state.profile["tpot"] * max(1, max_tokens))
                body: dict[str, Any] = {
                    "choices": [
                        {"message": {"role": "assistant", "content": _completion_text(max_tokens)}}
                    ]
                }
                usage = _usage(messages, max_tokens, state)
                if usage is not None:
                    body["usage"] = usage
                return web.json_response(body)
            finally:
                await state.end_request(output_tokens=max_tokens)

        response = web.StreamResponse(
            status=200,
            headers={"Content-Type": "text/event-stream", "Cache-Control": "no-cache"},
        )
        await response.prepare(request)
        try:
            stream_options = payload.get("stream_options") if isinstance(payload, dict) else {}
            include_usage = bool(isinstance(stream_options, dict) and stream_options.get("include_usage"))
            continuous_usage = bool(
                isinstance(stream_options, dict) and stream_options.get("continuous_usage_stats")
            )
            usage = _usage(messages, max_tokens, state)
            await _write_sse(response, {"choices": [{"delta": {"role": "assistant"}}]})
            await asyncio.sleep(state.profile["ttft"])
            chunk_count = min(8, max(2, max_tokens // 8))
            for idx in range(chunk_count):
                chunk: dict[str, Any] = {"choices": [{"delta": {"content": f"tok{idx} "}}]}
                if include_usage and continuous_usage and usage is not None:
                    chunk["usage"] = usage
                await _write_sse(response, chunk)
                await asyncio.sleep(state.profile["tpot"])
            finish_chunk: dict[str, Any] = {"choices": [{"delta": {}, "finish_reason": "stop"}]}
            if include_usage and continuous_usage and usage is not None:
                finish_chunk["usage"] = usage
            await _write_sse(response, finish_chunk)
            if include_usage and usage is not None:
                await _write_sse(response, {"choices": [], "usage": usage})
            await response.write(b"data: [DONE]\n\n")
        finally:
            await state.end_request(output_tokens=max_tokens)
        return response

    return handler


def _metrics(state: MockVLLMState):
    async def handler(_request: web.Request) -> web.Response:
        if state.metrics_status_code != 200:
            return web.Response(text="simulated metrics failure", status=state.metrics_status_code)
        return web.Response(text=state.metrics_text(), content_type="text/plain")

    return handler


async def _write_sse(response: web.StreamResponse, payload: dict[str, Any]) -> None:
    await response.write(f"data: {json.dumps(payload, separators=(',', ':'))}\n\n".encode())


def _usage(messages: list[dict[str, Any]], max_tokens: int, state: MockVLLMState) -> dict[str, int] | None:
    if state.suppress_usage:
        return None
    prompt_tokens = _estimate_prompt_tokens(messages)
    usage = {
        "prompt_tokens": prompt_tokens,
        "completion_tokens": max_tokens,
        "total_tokens": prompt_tokens + max_tokens,
    }
    if state.simulate_mtp_bug:
        usage["cached_tokens"] = 0
    return usage


def _completion_text(max_tokens: int) -> str:
    return "".join(f"tok{idx} " for idx in range(max(1, max_tokens)))


def _estimate_prompt_tokens(messages: list[dict[str, Any]]) -> int:
    chars = sum(len(str(message.get("content", ""))) for message in messages)
    return max(1, chars // 4)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--rig-profile", default="h100", choices=sorted(_RIG_PROFILES))
    parser.add_argument("--model-id", default="mock-dsv4")
    parser.add_argument("--canary-fail", action="store_true")
    parser.add_argument("--slow-startup", type=float, default=0.0)
    parser.add_argument("--inject-metrics-500", action="store_true")
    parser.add_argument("--inject-failure-rate", type=float, default=0.0)
    parser.add_argument("--suppress-usage", action="store_true")
    parser.add_argument("--simulate-mtp-bug", action="store_true")
    parser.add_argument("--enable-lmcache", action="store_true")
    parser.add_argument("--enable-dynamo-kvbm", action="store_true")
    parser.add_argument("--enable-sglang-hicache", action="store_true")
    args = parser.parse_args(argv)
    state = MockVLLMState(
        args.rig_profile,
        enable_lmcache=args.enable_lmcache,
        enable_dynamo_kvbm=args.enable_dynamo_kvbm,
        enable_sglang_hicache=args.enable_sglang_hicache,
        canary_fail=args.canary_fail,
        inject_failure_rate=args.inject_failure_rate,
        suppress_usage=args.suppress_usage,
        simulate_mtp_bug=args.simulate_mtp_bug,
        ready_after_seconds=args.slow_startup,
        metrics_status_code=500 if args.inject_metrics_500 else 200,
        model_id=args.model_id,
    )
    server = _AiohttpServerThread(state, args.host, args.port)
    url = server.start()
    print(url, flush=True)
    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        server.stop()
    return 0


__all__ = ["MockServerHandle", "MockVLLMState", "main", "start_mock_servers"]


if __name__ == "__main__":
    raise SystemExit(main())

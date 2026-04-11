"""Local mock inference endpoint for truthful InferGuard smoke tests.

Provides:
- /metrics
- /v1/models
- /v1/chat/completions (streaming SSE)
- /v1/completions (streaming SSE)
- /health

This proves local control-loop wiring and replay-helper compatibility. It does
not prove live engine behavior.
"""

from __future__ import annotations

import argparse
import asyncio
from dataclasses import dataclass
import json
import signal
import time
from typing import Any

from aiohttp import web


SCENARIOS = ("healthy", "pressure_ramp", "incident", "recovery", "self_repair")


@dataclass(slots=True)
class ScenarioState:
    scenario: str = "healthy"
    start_time: float | None = None

    def elapsed_seconds(self, now: float | None = None) -> float:
        if self.start_time is None:
            return 0.0
        current_time = time.monotonic() if now is None else now
        return max(0.0, current_time - self.start_time)


ENGINE_KEY = web.AppKey("engine", str)
MODEL_ID_KEY = web.AppKey("model_id", str)
SCENARIO_STATE_KEY = web.AppKey("scenario_state", ScenarioState)


def _clamp(value: float, lower: float, upper: float) -> float:
    return max(lower, min(value, upper))


def _lerp(start: float, end: float, progress: float) -> float:
    clamped_progress = _clamp(progress, 0.0, 1.0)
    return start + (end - start) * clamped_progress


def _build_sample(
    *,
    kv_cache_usage: float,
    prefix_cache_hit_rate: float,
    requests_running: int,
    requests_waiting: int,
    requests_swapped: int,
    preemptions_total: int,
    ttft_avg_seconds: float,
    tpot_avg_seconds: float,
    cpu_cache_usage: float = 0.0,
) -> dict[str, float | int]:
    return {
        "kv_cache_usage": kv_cache_usage,
        "cpu_cache_usage": cpu_cache_usage,
        "prefix_cache_hit_rate": prefix_cache_hit_rate,
        "requests_running": requests_running,
        "requests_waiting": requests_waiting,
        "requests_swapped": requests_swapped,
        "preemptions_total": preemptions_total,
        "ttft_avg_seconds": ttft_avg_seconds,
        "ttft_count": 4,
        "tpot_avg_seconds": tpot_avg_seconds,
        "tpot_count": 9,
    }


def _sample_scenario_metrics(scenario: str, elapsed_seconds: float) -> dict[str, float | int]:
    healthy = _build_sample(
        kv_cache_usage=0.41,
        prefix_cache_hit_rate=0.82,
        requests_running=1,
        requests_waiting=0,
        requests_swapped=0,
        preemptions_total=0,
        ttft_avg_seconds=0.10,
        tpot_avg_seconds=0.02,
    )

    if scenario == "healthy":
        return healthy

    if scenario == "pressure_ramp":
        progress = _clamp(elapsed_seconds / 300.0, 0.0, 1.0)
        severe_progress = _clamp((progress - 0.6) / 0.4, 0.0, 1.0)
        swap_progress = _clamp((progress - 0.7) / 0.3, 0.0, 1.0)
        return _build_sample(
            kv_cache_usage=_lerp(0.41, 0.96, progress),
            prefix_cache_hit_rate=_lerp(0.82, 0.18, progress),
            requests_running=int(round(_lerp(1.0, 14.0, progress))),
            requests_waiting=int(round(_lerp(0.0, 16.0, progress))),
            requests_swapped=int(round(_lerp(0.0, 3.0, swap_progress))),
            preemptions_total=int(round(_lerp(0.0, 18.0, severe_progress))),
            ttft_avg_seconds=_lerp(0.10, 0.52, progress),
            tpot_avg_seconds=_lerp(0.02, 0.09, progress),
        )

    if scenario == "incident":
        return _build_sample(
            kv_cache_usage=0.93,
            prefix_cache_hit_rate=0.14,
            requests_running=18,
            requests_waiting=15,
            requests_swapped=3,
            preemptions_total=8,
            ttft_avg_seconds=0.62,
            tpot_avg_seconds=0.11,
        )

    if scenario == "recovery":
        if elapsed_seconds <= 30.0:
            return _build_sample(
                kv_cache_usage=0.94,
                prefix_cache_hit_rate=0.12,
                requests_running=16,
                requests_waiting=14,
                requests_swapped=2,
                preemptions_total=12,
                ttft_avg_seconds=0.58,
                tpot_avg_seconds=0.10,
            )
        if elapsed_seconds >= 210.0:
            recovered = healthy.copy()
            recovered["preemptions_total"] = 12
            return recovered

        progress = (elapsed_seconds - 30.0) / 180.0
        return _build_sample(
            kv_cache_usage=_lerp(0.94, 0.41, progress),
            prefix_cache_hit_rate=_lerp(0.12, 0.82, progress),
            requests_running=int(round(_lerp(16.0, 1.0, progress))),
            requests_waiting=int(round(_lerp(14.0, 0.0, progress))),
            requests_swapped=int(round(_lerp(2.0, 0.0, progress))),
            preemptions_total=12,
            ttft_avg_seconds=_lerp(0.58, 0.10, progress),
            tpot_avg_seconds=_lerp(0.10, 0.02, progress),
        )

    if scenario == "self_repair":
        phase = elapsed_seconds % 40.0
        if phase < 10.0:
            return _build_sample(
                kv_cache_usage=0.92,
                prefix_cache_hit_rate=0.16,
                requests_running=17,
                requests_waiting=14,
                requests_swapped=3,
                preemptions_total=int(round(_lerp(0.0, 8.0, phase / 10.0))),
                ttft_avg_seconds=0.58,
                tpot_avg_seconds=0.11,
            )
        if phase < 20.0:
            return _build_sample(
                kv_cache_usage=0.71,
                prefix_cache_hit_rate=0.38,
                requests_running=9,
                requests_waiting=6,
                requests_swapped=1,
                preemptions_total=8,
                ttft_avg_seconds=0.29,
                tpot_avg_seconds=0.06,
            )
        if phase < 30.0:
            return _build_sample(
                kv_cache_usage=0.44,
                prefix_cache_hit_rate=0.74,
                requests_running=3,
                requests_waiting=1,
                requests_swapped=0,
                preemptions_total=8,
                ttft_avg_seconds=0.12,
                tpot_avg_seconds=0.028,
            )
        return _build_sample(
            kv_cache_usage=0.38,
            prefix_cache_hit_rate=0.83,
            requests_running=2,
            requests_waiting=0,
            requests_swapped=0,
            preemptions_total=8,
            ttft_avg_seconds=0.095,
            tpot_avg_seconds=0.021,
        )

    raise ValueError(f"Unsupported scenario: {scenario}")


def _resolve_sample(state: ScenarioState | None = None, *, now: float | None = None) -> dict[str, float | int]:
    if state is None:
        return _sample_scenario_metrics("healthy", 0.0)
    return _sample_scenario_metrics(state.scenario, state.elapsed_seconds(now))


def build_vllm_metrics(state: ScenarioState | None = None, *, now: float | None = None) -> str:
    sample = _resolve_sample(state, now=now)
    ttft_count = int(sample["ttft_count"])
    tpot_count = int(sample["tpot_count"])
    return f"""# HELP vllm mock metrics
vllm:gpu_cache_usage_perc {float(sample["kv_cache_usage"]):.4f}
vllm:cpu_cache_usage_perc {float(sample["cpu_cache_usage"]):.4f}
vllm:gpu_prefix_cache_hit_rate {float(sample["prefix_cache_hit_rate"]):.4f}
vllm:num_requests_running {int(sample["requests_running"])}
vllm:num_requests_waiting {int(sample["requests_waiting"])}
vllm:num_requests_swapped {int(sample["requests_swapped"])}
vllm:num_preemptions_total {int(sample["preemptions_total"])}
vllm:time_to_first_token_seconds_sum {float(sample["ttft_avg_seconds"]) * ttft_count:.4f}
vllm:time_to_first_token_seconds_count {ttft_count}
vllm:time_per_output_token_seconds_sum {float(sample["tpot_avg_seconds"]) * tpot_count:.4f}
vllm:time_per_output_token_seconds_count {tpot_count}
"""


def build_sglang_metrics(state: ScenarioState | None = None, *, now: float | None = None) -> str:
    sample = _resolve_sample(state, now=now)
    ttft_count = int(sample["ttft_count"])
    tpot_count = int(sample["tpot_count"])
    return f"""# HELP sglang mock metrics
sglang:token_usage {float(sample["kv_cache_usage"]):.4f}
sglang:cache_hit_rate {float(sample["prefix_cache_hit_rate"]):.4f}
sglang:num_running_reqs {int(sample["requests_running"])}
sglang:num_queue_reqs {int(sample["requests_waiting"])}
sglang:num_preemptions_total {int(sample["preemptions_total"])}
sglang:time_to_first_token_seconds_sum {float(sample["ttft_avg_seconds"]) * ttft_count:.4f}
sglang:time_to_first_token_seconds_count {ttft_count}
sglang:time_per_output_token_seconds_sum {float(sample["tpot_avg_seconds"]) * tpot_count:.4f}
sglang:time_per_output_token_seconds_count {tpot_count}
"""


async def handle_metrics(request: web.Request) -> web.Response:
    state = request.app[SCENARIO_STATE_KEY]
    metrics_text = build_sglang_metrics(state) if request.app[ENGINE_KEY] == "sglang" else build_vllm_metrics(state)
    return web.Response(text=metrics_text, content_type="text/plain")


async def handle_models(request: web.Request) -> web.Response:
    return web.json_response({"data": [{"id": request.app[MODEL_ID_KEY]}]})


async def handle_health(request: web.Request) -> web.Response:
    return web.json_response(
        {
            "status": "ok",
            "mock": True,
            "engine": request.app[ENGINE_KEY],
            "scenario": request.app[SCENARIO_STATE_KEY].scenario,
        }
    )


async def _stream_sse(response: web.StreamResponse, payloads: list[dict[str, Any]]) -> None:
    for payload in payloads:
        await response.write(f"data: {json.dumps(payload)}\n\n".encode("utf-8"))
        await asyncio.sleep(0.01)
    await response.write(b"data: [DONE]\n\n")


async def handle_chat_completions(request: web.Request) -> web.StreamResponse:
    body = await request.json()
    max_tokens = int(body.get("max_completion_tokens") or body.get("max_tokens") or 1)
    emitted = "mock-response"
    completion_tokens = min(max_tokens, max(1, len(emitted.split())))

    response = web.StreamResponse(
        status=200,
        headers={
            "Content-Type": "text/event-stream",
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        },
    )
    await response.prepare(request)
    await _stream_sse(
        response,
        [
            {
                "choices": [
                    {
                        "delta": {"content": emitted},
                        "index": 0,
                    }
                ]
            },
            {
                "usage": {
                    "completion_tokens": completion_tokens,
                    "prompt_tokens": 1,
                    "total_tokens": completion_tokens + 1,
                }
            },
        ],
    )
    await response.write_eof()
    return response


async def handle_completions(request: web.Request) -> web.StreamResponse:
    body = await request.json()
    max_tokens = int(body.get("max_tokens") or 1)
    emitted = "mock-response"
    completion_tokens = min(max_tokens, max(1, len(emitted.split())))

    response = web.StreamResponse(
        status=200,
        headers={
            "Content-Type": "text/event-stream",
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        },
    )
    await response.prepare(request)
    await _stream_sse(
        response,
        [
            {"choices": [{"text": emitted, "index": 0}]},
            {
                "usage": {
                    "completion_tokens": completion_tokens,
                    "prompt_tokens": 1,
                    "total_tokens": completion_tokens + 1,
                }
            },
        ],
    )
    await response.write_eof()
    return response


def create_app(engine: str, model_id: str, scenario: str = "healthy") -> web.Application:
    app = web.Application()
    app[ENGINE_KEY] = engine
    app[MODEL_ID_KEY] = model_id
    app[SCENARIO_STATE_KEY] = ScenarioState(scenario=scenario, start_time=time.monotonic())
    app.router.add_get("/metrics", handle_metrics)
    app.router.add_get("/v1/models", handle_models)
    app.router.add_get("/health", handle_health)
    app.router.add_post("/v1/chat/completions", handle_chat_completions)
    app.router.add_post("/v1/completions", handle_completions)
    return app


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a local mock endpoint for InferGuard smoke tests.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=18000)
    parser.add_argument("--engine", choices=["vllm", "sglang"], default="vllm")
    parser.add_argument("--model-id", default="openai/gpt-oss-120b")
    parser.add_argument("--scenario", choices=list(SCENARIOS), default="healthy")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    app = create_app(engine=args.engine, model_id=args.model_id, scenario=args.scenario)
    web.run_app(
        app,
        host=args.host,
        port=args.port,
        handle_signals=True,
        print=lambda message: print(message, flush=True),
    )


if __name__ == "__main__":
    signal.signal(signal.SIGINT, signal.SIG_DFL)
    signal.signal(signal.SIGTERM, signal.SIG_DFL)
    main()

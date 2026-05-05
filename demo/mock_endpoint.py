"""Offline Prometheus fixture server for local testing and demos.

Spins up a small aiohttp server that exposes a ``/metrics`` endpoint in
vLLM or SGLang exposition format. Supports ``--role {prefill|decode|
transfer}`` so you can run two instances on adjacent ports and drive
``inferguard disagg status --prefill ... --decode ...`` against them
without touching a real GPU.

No network egress, no model weights, no dependencies beyond aiohttp.
"""

from __future__ import annotations

import argparse
from typing import Any

from aiohttp import web

SCENARIOS = {
    "healthy": {
        "kv": 0.45,
        "running": 8,
        "waiting": 0,
        "swapped": 0,
        "preempt": 0,
        "ttft_sum": 0.6,
        "ttft_count": 30,
        "tpot_sum": 0.9,
        "tpot_count": 120,
        "kv_sent": 52_428_800,  # 50 MiB
        "kv_recv": 52_428_800,
        "kv_errors": 0,
    },
    "kv_pressure": {
        "kv": 0.91,
        "running": 32,
        "waiting": 12,
        "swapped": 3,
        "preempt": 7,
        "ttft_sum": 3.2,
        "ttft_count": 40,
        "tpot_sum": 1.8,
        "tpot_count": 150,
        "kv_sent": 1_073_741_824,  # 1 GiB
        "kv_recv": 1_073_741_824,
        "kv_errors": 0,
    },
    "transfer_errors": {
        "kv": 0.70,
        "running": 18,
        "waiting": 2,
        "swapped": 0,
        "preempt": 1,
        "ttft_sum": 1.0,
        "ttft_count": 30,
        "tpot_sum": 1.1,
        "tpot_count": 120,
        "kv_sent": 209_715_200,
        "kv_recv": 209_715_200,
        "kv_errors": 42,
    },
    "stall": {
        "kv": 0.60,
        "running": 10,
        "waiting": 4,
        "swapped": 0,
        "preempt": 0,
        "ttft_sum": 2.1,
        "ttft_count": 28,
        "tpot_sum": 1.0,
        "tpot_count": 90,
        "kv_sent": 0,
        "kv_recv": 0,
        "kv_errors": 0,
    },
    "decode_pressure": {
        "kv": 0.55,
        "running": 2,
        "waiting": 0,
        "swapped": 0,
        "preempt": 0,
        "ttft_sum": 0.5,
        "ttft_count": 20,
        "tpot_sum": 0.8,
        "tpot_count": 80,
        "kv_sent": 104_857_600,
        "kv_recv": 104_857_600,
        "kv_errors": 0,
    },
    "prefill_pressure": {
        "kv": 0.82,
        "running": 24,
        "waiting": 8,
        "swapped": 0,
        "preempt": 0,
        "ttft_sum": 2.7,
        "ttft_count": 35,
        "tpot_sum": 0.9,
        "tpot_count": 100,
        "kv_sent": 104_857_600,
        "kv_recv": 104_857_600,
        "kv_errors": 0,
    },
}


def render_vllm(scenario: dict[str, Any], *, connector: str = "nixl") -> str:
    return _render(scenario, engine="vllm", connector=connector)


def render_sglang(scenario: dict[str, Any], *, connector: str = "mooncake") -> str:
    return _render(scenario, engine="sglang", connector=connector)


def _render(scenario: dict[str, Any], *, engine: str, connector: str) -> str:
    prefix = "vllm" if engine == "vllm" else "sglang"
    if engine == "vllm":
        kv_name = f"{prefix}:gpu_cache_usage_perc"
        running = f"{prefix}:num_requests_running"
        waiting = f"{prefix}:num_requests_waiting"
        swapped = f"{prefix}:num_requests_swapped"
    else:
        kv_name = "sglang:token_usage"
        running = "sglang:num_running_reqs"
        waiting = "sglang:num_queue_reqs"
        swapped = "sglang:num_requests_swapped"  # not really a thing; harmless

    lines = [
        f"# HELP {kv_name} KV cache usage ratio.",
        f"# TYPE {kv_name} gauge",
        f"{kv_name} {scenario['kv']}",
        f"{running} {scenario['running']}",
        f"{waiting} {scenario['waiting']}",
        f"{swapped} {scenario['swapped']}",
        f"{prefix}:num_preemptions_total {scenario['preempt']}",
        f'{prefix}:kv_transfer_sent_bytes_total{{connector="{connector}"}} {scenario["kv_sent"]}',
        f'{prefix}:kv_transfer_recv_bytes_total{{connector="{connector}"}} {scenario["kv_recv"]}',
        f'{prefix}:kv_transfer_errors_total{{connector="{connector}"}} {scenario["kv_errors"]}',
        f"{prefix}:time_to_first_token_seconds_sum {scenario['ttft_sum']}",
        f"{prefix}:time_to_first_token_seconds_count {scenario['ttft_count']}",
        f"{prefix}:time_per_output_token_seconds_sum {scenario['tpot_sum']}",
        f"{prefix}:time_per_output_token_seconds_count {scenario['tpot_count']}",
    ]
    return "\n".join(lines) + "\n"


def make_app(
    *,
    engine: str = "vllm",
    scenario: str = "healthy",
    connector: str = "nixl",
) -> web.Application:
    if scenario not in SCENARIOS:
        raise SystemExit(f"Unknown scenario {scenario!r}; try: {', '.join(SCENARIOS)}")
    app = web.Application()

    async def metrics_handler(_request: web.Request) -> web.Response:
        data = SCENARIOS[scenario]
        body = (
            render_vllm(data, connector=connector)
            if engine == "vllm"
            else render_sglang(data, connector=connector)
        )
        return web.Response(text=body, content_type="text/plain")

    async def health_handler(_request: web.Request) -> web.Response:
        return web.Response(text="ok")

    app.router.add_get("/metrics", metrics_handler)
    app.router.add_get("/health", health_handler)
    return app


def main() -> None:  # pragma: no cover
    parser = argparse.ArgumentParser(description="Offline Prometheus fixture server.")
    parser.add_argument("--engine", default="vllm", choices=("vllm", "sglang"))
    parser.add_argument(
        "--role",
        default="prefill",
        choices=("prefill", "decode", "transfer"),
        help="Informational — used to pick a default port.",
    )
    parser.add_argument(
        "--scenario",
        default="healthy",
        choices=tuple(SCENARIOS),
        help="Which scenario to emit.",
    )
    parser.add_argument("--connector", default="nixl")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=None)
    args = parser.parse_args()

    if args.port is None:
        args.port = {"prefill": 18000, "decode": 18001, "transfer": 18002}[args.role]

    app = make_app(engine=args.engine, scenario=args.scenario, connector=args.connector)
    print(
        f"inferguard mock {args.engine} [{args.role}] scenario={args.scenario} → http://{args.host}:{args.port}/metrics"
    )
    web.run_app(app, host=args.host, port=args.port, print=None)


if __name__ == "__main__":  # pragma: no cover
    main()

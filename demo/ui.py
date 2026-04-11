"""InferGuard Demo UI — lightweight web dashboard over the agent loop.

Serves a single-page dashboard at ``/`` and streams agent reports via SSE.
This is a demo/presentation layer that consumes the public ``InferGuardAgent``
and ``InferGuardConfig`` interfaces. It does not modify the core package.

Usage::

    python demo/ui.py --endpoint http://localhost:18000 --port 8080
    python demo/ui.py --endpoint http://localhost:18000 --model openai/gpt-oss-120b --interval 10

Then open http://localhost:8080 in a browser.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import signal
import sys
from pathlib import Path
from typing import Any

from aiohttp import web

# ---------------------------------------------------------------------------
# Ensure the repo src/ is importable when running as a script from demo/
# ---------------------------------------------------------------------------
_REPO_ROOT = Path(__file__).resolve().parent.parent
_SRC_DIR = _REPO_ROOT / "src"
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))

from inferguard.agent import InferGuardAgent  # noqa: E402
from inferguard.config import InferGuardConfig, load_diagnosis_env  # noqa: E402

# impact.py lives alongside this file in demo/
_DEMO_DIR = Path(__file__).resolve().parent
if str(_DEMO_DIR) not in sys.path:
    sys.path.insert(0, str(_DEMO_DIR))

from impact import OperationalImpact, compute_impact  # noqa: E402

STATIC_DIR = Path(__file__).resolve().parent / "static"


# ---------------------------------------------------------------------------
# Proof-level detection (resilient to mock endpoints that do/don't expose it)
# ---------------------------------------------------------------------------

async def _detect_proof_level(endpoint: str) -> str:
    """Probe /health for a mock marker. Returns 'mock', 'live', or 'unknown'."""
    try:
        import httpx
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(f"{endpoint.rstrip('/')}/health")
            if resp.status_code == 200:
                data = resp.json()
                return "mock" if data.get("mock") is True else "live"
    except Exception:
        pass
    return "unknown"


# ---------------------------------------------------------------------------
# Route handlers
# ---------------------------------------------------------------------------

async def handle_index(request: web.Request) -> web.FileResponse:
    return web.FileResponse(STATIC_DIR / "index.html")


async def handle_config(request: web.Request) -> web.Response:
    """Return runtime configuration summary for the UI header."""
    app = request.app
    return web.json_response({
        "endpoint": app["ig_endpoint"],
        "model": app["ig_model"],
        "poll_interval": app["ig_interval"],
        "proof_level": app["ig_proof_level"],
    })


async def handle_scan(request: web.Request) -> web.Response:
    """One-shot agent scan, returns JSON."""
    app = request.app
    config = _build_config(app)
    agent = InferGuardAgent(config, model_name=app["ig_model"])
    try:
        report = await agent.run_once()
        # Prefer proof_level from the agent; fall back to UI-level detection
        if "proof_level" not in report:
            report["proof_level"] = app["ig_proof_level"]
        return web.json_response(report)
    finally:
        await agent.shutdown()


async def handle_stream(request: web.Request) -> web.StreamResponse:
    """SSE endpoint — runs agent watch() and emits JSON events."""
    app = request.app
    config = _build_config(app)

    response = web.StreamResponse(
        status=200,
        headers={
            "Content-Type": "text/event-stream",
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
    await response.prepare(request)

    agent = InferGuardAgent(config, model_name=app["ig_model"])
    reports: list[dict[str, Any]] = []

    try:
        async for report in agent.watch():
            # Prefer proof_level from the agent; fall back to UI-level detection
            if "proof_level" not in report:
                report["proof_level"] = app.get("ig_proof_level", "unknown")

            reports.append(report)
            impact = compute_impact(reports)
            event_data = {**report, "impact": impact.as_dict()}

            payload = f"event: report\ndata: {json.dumps(event_data, default=str)}\n\n"
            await response.write(payload.encode("utf-8"))

    except (asyncio.CancelledError, ConnectionResetError):
        pass
    finally:
        await agent.shutdown()

    return response


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _build_config(app: web.Application) -> InferGuardConfig:
    """Build InferGuardConfig from app state (avoids requiring env vars)."""
    llm_base_url, llm_api_key, llm_model = load_diagnosis_env()
    return InferGuardConfig(
        target_endpoint=app["ig_endpoint"],
        poll_interval_seconds=app["ig_interval"],
        # Pass through optional env-based values
        redis_url=os.environ.get("UPSTASH_REDIS_URL", "").strip(),
        redis_token=os.environ.get("UPSTASH_REDIS_TOKEN", "").strip(),
        vector_url=os.environ.get("UPSTASH_VECTOR_URL", "").strip(),
        vector_token=os.environ.get("UPSTASH_VECTOR_TOKEN", "").strip(),
        llm_base_url=llm_base_url,
        llm_api_key=llm_api_key,
        llm_model=llm_model,
    )


async def _on_startup(app: web.Application) -> None:
    """Detect proof level on server start."""
    app["ig_proof_level"] = await _detect_proof_level(app["ig_endpoint"])
    level = app["ig_proof_level"]
    mode_label = {"mock": "MOCK", "live": "LIVE"}.get(level, "UNKNOWN")
    print(f"  Proof level: {mode_label}", flush=True)


def create_ui_app(
    target_endpoint: str,
    model_name: str = "",
    poll_interval: int = 10,
) -> web.Application:
    """Create the aiohttp Application for the InferGuard demo UI."""
    app = web.Application()
    app["ig_endpoint"] = target_endpoint
    app["ig_model"] = model_name
    app["ig_interval"] = poll_interval
    app["ig_proof_level"] = "unknown"

    app.on_startup.append(_on_startup)

    app.router.add_get("/", handle_index)
    app.router.add_get("/api/config", handle_config)
    app.router.add_get("/api/scan", handle_scan)
    app.router.add_get("/api/stream", handle_stream)
    # Serve static files (CSS, JS, etc. if ever split out)
    if STATIC_DIR.is_dir():
        app.router.add_static("/static/", STATIC_DIR)

    return app


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="InferGuard Demo UI — web dashboard for the agent loop.",
    )
    parser.add_argument(
        "--endpoint",
        default=os.environ.get("TARGET_ENDPOINT", "http://127.0.0.1:18000"),
        help="Inference endpoint URL (default: $TARGET_ENDPOINT or http://127.0.0.1:18000)",
    )
    parser.add_argument("--model", default="", help="Model name hint for the agent.")
    parser.add_argument("--port", type=int, default=8080, help="UI server port (default: 8080).")
    parser.add_argument("--host", default="127.0.0.1", help="UI server bind address.")
    parser.add_argument(
        "--interval", type=int, default=10,
        help="Agent poll interval in seconds (default: 10).",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    app = create_ui_app(
        target_endpoint=args.endpoint,
        model_name=args.model,
        poll_interval=args.interval,
    )
    print(f"\n  InferGuard Demo UI", flush=True)
    print(f"  Endpoint: {args.endpoint}", flush=True)
    print(f"  Model:    {args.model or '(auto-detect)'}", flush=True)
    print(f"  Interval: {args.interval}s", flush=True)
    print(f"\n  Open http://{args.host}:{args.port} in your browser.\n", flush=True)

    web.run_app(
        app,
        host=args.host,
        port=args.port,
        handle_signals=True,
        print=lambda msg: print(f"  {msg}", flush=True),
    )


if __name__ == "__main__":
    signal.signal(signal.SIGINT, signal.SIG_DFL)
    signal.signal(signal.SIGTERM, signal.SIG_DFL)
    main()

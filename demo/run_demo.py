"""InferGuard Demo Runner — single command to launch the full Bronze-mode demo.

Bronze mode (mock):
    python demo/run_demo.py
    python demo/run_demo.py --scenario pressure_ramp

    Starts the mock endpoint (with optional scenario), then starts the
    UI server pointing at it. Available scenarios: healthy, pressure_ramp,
    incident, recovery.

Live / Gold mode (real endpoint):
    python demo/run_demo.py --endpoint http://vllm-host:8000 --model deepseek-ai/DeepSeek-R1-0528

    Skips mock startup entirely and connects the UI to the real endpoint.

Press Ctrl-C to shut everything down.
"""

from __future__ import annotations

import argparse
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

DEMO_DIR = Path(__file__).resolve().parent


def _wait_for_health(url: str, timeout: float = 15.0) -> bool:
    """Poll /health until 200 or timeout."""
    import urllib.request
    import urllib.error

    deadline = time.time() + timeout
    health_url = f"{url.rstrip('/')}/health"

    while time.time() < deadline:
        try:
            req = urllib.request.urlopen(health_url, timeout=2)
            if req.status == 200:
                return True
        except (urllib.error.URLError, OSError):
            pass
        time.sleep(0.5)
    return False


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="InferGuard Demo Runner — launch mock + UI in one command.",
    )
    parser.add_argument(
        "--endpoint",
        default="",
        help=(
            "Live endpoint URL. If provided, the mock server is skipped "
            "and the UI connects directly to this endpoint."
        ),
    )
    parser.add_argument(
        "--scenario",
        default="self_repair",
        choices=["healthy", "pressure_ramp", "incident", "recovery", "self_repair"],
        help="Mock endpoint scenario (default: healthy). Ignored if --endpoint is set.",
    )
    parser.add_argument(
        "--engine",
        default="vllm",
        choices=["vllm", "sglang"],
        help="Mock engine type (default: vllm).",
    )
    parser.add_argument(
        "--model",
        default="openai/gpt-oss-120b",
        help="Model name hint (default: openai/gpt-oss-120b).",
    )
    parser.add_argument(
        "--mock-port", type=int, default=18000,
        help="Port for the mock endpoint (default: 18000).",
    )
    parser.add_argument(
        "--ui-port", type=int, default=8080,
        help="Port for the UI server (default: 8080).",
    )
    parser.add_argument(
        "--interval", type=int, default=10,
        help="Agent poll interval in seconds (default: 10).",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    procs: list[subprocess.Popen] = []

    def _cleanup(signum=None, frame=None) -> None:
        for p in reversed(procs):
            try:
                p.terminate()
            except OSError:
                pass
        for p in procs:
            try:
                p.wait(timeout=5)
            except subprocess.TimeoutExpired:
                p.kill()
        sys.exit(0)

    signal.signal(signal.SIGINT, _cleanup)
    signal.signal(signal.SIGTERM, _cleanup)

    # --- Determine target endpoint ---
    if args.endpoint:
        target = args.endpoint
        print(f"\n  InferGuard Demo — LIVE mode")
        print(f"  Endpoint: {target}")
    else:
        target = f"http://127.0.0.1:{args.mock_port}"
        print(f"\n  InferGuard Demo — MOCK mode (scenario: {args.scenario})")
        print(f"  Starting mock endpoint on port {args.mock_port}...")

        mock_cmd = [
            sys.executable,
            str(DEMO_DIR / "mock_endpoint.py"),
            "--host", "127.0.0.1",
            "--port", str(args.mock_port),
            "--engine", args.engine,
            "--model-id", args.model,
            "--scenario", args.scenario,
        ]

        mock_proc = subprocess.Popen(
            mock_cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )
        procs.append(mock_proc)

        if not _wait_for_health(target, timeout=15.0):
            print("  ERROR: Mock endpoint did not become healthy within 15s.", flush=True)
            _cleanup()
            return

        print(f"  Mock endpoint ready at {target}", flush=True)

    # --- Start UI ---
    print(f"  Starting UI on port {args.ui_port}...", flush=True)

    ui_cmd = [
        sys.executable,
        str(DEMO_DIR / "ui.py"),
        "--endpoint", target,
        "--model", args.model,
        "--port", str(args.ui_port),
        "--interval", str(args.interval),
    ]

    ui_proc = subprocess.Popen(ui_cmd)
    procs.append(ui_proc)

    print(f"\n  ╔══════════════════════════════════════════════╗")
    print(f"  ║  Open http://127.0.0.1:{args.ui_port} in your browser  ║")
    print(f"  ║  Press Ctrl-C to stop.                       ║")
    print(f"  ╚══════════════════════════════════════════════╝\n", flush=True)

    # Wait for UI to exit (or Ctrl-C)
    try:
        ui_proc.wait()
    except KeyboardInterrupt:
        pass
    finally:
        _cleanup()


if __name__ == "__main__":
    main()

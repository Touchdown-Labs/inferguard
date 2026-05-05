"""Synthetic OpenAI-compatible endpoint for InferGuard local harness validation."""

from __future__ import annotations

import argparse
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

SIMULATION_MODE = "synthetic_gpu_mimic"
CLAIM_BOUNDARY = (
    "Synthetic GPU mimic artifacts validate harness parsing and operator workflow only; "
    "they are not publishable benchmark evidence."
)


class SyntheticOpenAIHandler(BaseHTTPRequestHandler):
    """Tiny OpenAI-compatible handler used only for synthetic bundle smoke tests."""

    server_version = "InferGuardSyntheticOpenAI/1.0"

    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/v1/models":
            self.write_json(
                {
                    "object": "list",
                    "data": [{"id": self.server.model_id, "object": "model"}],
                    "simulation_mode": SIMULATION_MODE,
                    "claim_boundary": CLAIM_BOUNDARY,
                }
            )
        elif self.path == "/metrics":
            text = "\n".join(
                [
                    f"# provenance={SIMULATION_MODE}",
                    "synthetic_gpu_util 55",
                    "synthetic_ttft_ms 120",
                    "",
                ]
            )
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; version=0.0.4")
            self.end_headers()
            self.wfile.write(text.encode("utf-8"))
        else:
            self.send_error(404)

    def do_POST(self) -> None:  # noqa: N802
        if self.path != "/v1/chat/completions":
            self.send_error(404)
            return
        length = int(self.headers.get("Content-Length", "0"))
        body = json.loads(self.rfile.read(length) or b"{}")
        if body.get("stream"):
            model_id = body.get("model") or self.server.model_id
            chunks = [
                {
                    "id": "chatcmpl-synthetic",
                    "object": "chat.completion.chunk",
                    "model": model_id,
                    "choices": [{"index": 0, "delta": {"role": "assistant"}, "finish_reason": None}],
                    "simulation_mode": SIMULATION_MODE,
                },
                {
                    "id": "chatcmpl-synthetic",
                    "object": "chat.completion.chunk",
                    "model": model_id,
                    "choices": [{"index": 0, "delta": {"content": "ok"}, "finish_reason": None}],
                    "simulation_mode": SIMULATION_MODE,
                },
                {
                    "id": "chatcmpl-synthetic",
                    "object": "chat.completion.chunk",
                    "model": model_id,
                    "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
                    "simulation_mode": SIMULATION_MODE,
                },
            ]
            if (body.get("stream_options") or {}).get("include_usage"):
                chunks.append(
                    {
                        "id": "chatcmpl-synthetic",
                        "object": "chat.completion.chunk",
                        "model": model_id,
                        "choices": [],
                        "usage": {"prompt_tokens": 16, "completion_tokens": 1, "total_tokens": 17},
                        "simulation_mode": SIMULATION_MODE,
                    }
                )
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.end_headers()
            for chunk in chunks:
                self.wfile.write(f"data: {json.dumps(chunk, sort_keys=True)}\n\n".encode("utf-8"))
            self.wfile.write(b"data: [DONE]\n\n")
            return
        self.write_json(
            {
                "id": "chatcmpl-synthetic",
                "object": "chat.completion",
                "model": body.get("model") or self.server.model_id,
                "choices": [{"index": 0, "message": {"role": "assistant", "content": "ok"}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 16, "completion_tokens": 1, "total_tokens": 17},
                "simulation_mode": SIMULATION_MODE,
                "claim_boundary": CLAIM_BOUNDARY,
            }
        )

    def log_message(self, fmt: str, *args: Any) -> None:
        return

    def write_json(self, payload: dict[str, Any]) -> None:
        raw = json.dumps(payload, sort_keys=True).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)


def serve_synthetic_endpoint(host: str, port: int, model_id: str) -> None:
    """Serve a foreground fake OpenAI-compatible endpoint."""
    server = ThreadingHTTPServer((host, port), SyntheticOpenAIHandler)
    server.model_id = model_id  # type: ignore[attr-defined]
    print(json.dumps({"endpoint": f"http://{host}:{port}", "model": model_id, "simulation_mode": SIMULATION_MODE}))
    server.serve_forever()


def serve_main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Serve a synthetic OpenAI-compatible endpoint.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--model", default=None)
    parser.add_argument("--model-profile", default=None)
    args = parser.parse_args(argv)
    serve_synthetic_endpoint(args.host, args.port, args.model or args.model_profile or "synthetic-gmi-model")
    return 0


__all__ = ["CLAIM_BOUNDARY", "SIMULATION_MODE", "SyntheticOpenAIHandler", "serve_main", "serve_synthetic_endpoint"]

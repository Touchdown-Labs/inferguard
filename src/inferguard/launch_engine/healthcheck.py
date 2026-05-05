"""OpenAI-compatible engine readiness checks for InferGuard launch runs."""

from __future__ import annotations

import json
import time
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlparse, urlunparse

import httpx

from inferguard.launch_engine.types import HealthcheckResult


def run_healthcheck(
    endpoint_url: str,
    *,
    model_id: str | None,
    timeout_seconds: int = 600,
    prompt: str = "Hello, are you up?",
    canary_completion_tokens: int = 16,
    success_status: str = "healthy",
) -> HealthcheckResult:
    base_url = normalize_base_url(endpoint_url)
    models_url = f"{base_url}/v1/models"
    metrics_url = f"{base_url}/metrics"
    chat_url = f"{base_url}/v1/chat/completions"
    timeout = max(0, int(timeout_seconds))
    request_timeout = max(0.5, min(10.0, float(timeout or 1)))
    deadline = time.monotonic() + timeout
    start = time.monotonic()
    first_probe_at = iso_now()
    attempts: list[dict[str, Any]] = []
    selected_model = model_id
    ready_at: str | None = None

    with httpx.Client(timeout=request_timeout) as client:
        while True:
            attempt: dict[str, Any] = {"ts": iso_now(), "url": models_url}
            try:
                response = client.get(models_url)
                attempt["status_code"] = response.status_code
                if response.status_code == 200:
                    payload = response.json()
                    model_ids = _model_ids(payload)
                    attempt["model_ids"] = model_ids
                    selected_model = _select_model(model_ids, selected_model)
                    if selected_model is not None:
                        ready_at = iso_now()
                        attempts.append(attempt)
                        break
                    attempt["error"] = "configured_model_not_listed"
                else:
                    attempt["error"] = f"http_{response.status_code}"
            except Exception as exc:  # noqa: BLE001 - artifact records endpoint readiness failures
                attempt["error"] = f"{type(exc).__name__}: {exc}"
            attempts.append(attempt)
            if time.monotonic() >= deadline:
                return HealthcheckResult(
                    endpoint=base_url,
                    model_id=selected_model or model_id or "unknown",
                    first_probe_at=first_probe_at,
                    ready_at=None,
                    ready_after_seconds=round(time.monotonic() - start, 6),
                    metrics_endpoint_reachable=False,
                    openai_models_endpoint_reachable=False,
                    canary_completion=None,
                    status="failed",
                    failure_reason="healthcheck_timeout",
                    attempts=attempts,
                )
            remaining = max(0.0, deadline - time.monotonic())
            time.sleep(min(2.0, remaining))

        metrics_endpoint_reachable = False
        try:
            metrics_response = client.get(metrics_url)
            metrics_endpoint_reachable = metrics_response.status_code == 200
        except Exception:
            metrics_endpoint_reachable = False

        canary, failure_reason = _run_canary(
            client,
            chat_url,
            model_id=selected_model or model_id or "unknown",
            prompt=prompt,
            output_tokens=canary_completion_tokens,
        )

    ready_after = round(time.monotonic() - start, 6)
    if failure_reason is not None:
        return HealthcheckResult(
            endpoint=base_url,
            model_id=selected_model or model_id or "unknown",
            first_probe_at=first_probe_at,
            ready_at=ready_at,
            ready_after_seconds=ready_after,
            metrics_endpoint_reachable=metrics_endpoint_reachable,
            openai_models_endpoint_reachable=True,
            canary_completion=canary,
            status="failed",
            failure_reason=failure_reason,
            attempts=attempts,
        )

    return HealthcheckResult(
        endpoint=base_url,
        model_id=selected_model or model_id or "unknown",
        first_probe_at=first_probe_at,
        ready_at=ready_at,
        ready_after_seconds=ready_after,
        metrics_endpoint_reachable=metrics_endpoint_reachable,
        openai_models_endpoint_reachable=True,
        canary_completion=canary,
        status=success_status,
        failure_reason=None,
        attempts=attempts,
    )


def normalize_base_url(endpoint_url: str) -> str:
    raw = endpoint_url.rstrip("/")
    parsed = urlparse(raw)
    path = parsed.path.rstrip("/")
    for suffix in ("/v1/chat/completions", "/v1/models", "/metrics"):
        if path.endswith(suffix):
            path = path[: -len(suffix)]
            break
    normalized = parsed._replace(path=path, params="", query="", fragment="")
    return urlunparse(normalized).rstrip("/")


def iso_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _model_ids(payload: Any) -> list[str]:
    if not isinstance(payload, dict):
        return []
    data = payload.get("data")
    if not isinstance(data, list):
        return []
    ids: list[str] = []
    for item in data:
        if isinstance(item, dict) and isinstance(item.get("id"), str):
            ids.append(item["id"])
    return ids


def _select_model(model_ids: list[str], configured: str | None) -> str | None:
    if configured and configured in model_ids:
        return configured
    if configured is None and model_ids:
        return model_ids[0]
    return None


def _run_canary(
    client: httpx.Client,
    chat_url: str,
    *,
    model_id: str,
    prompt: str,
    output_tokens: int,
) -> tuple[dict[str, Any] | None, str | None]:
    request_ts = iso_now()
    start = time.perf_counter()
    first_token_ts: str | None = None
    first_token_at: float | None = None
    done_ts: str | None = None
    output_parts: list[str] = []
    completion_tokens: int | None = None
    finish_reason: str | None = None
    done_seen = False
    payload = {
        "model": model_id,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": int(output_tokens),
        "temperature": 0,
        "stream": True,
        "stream_options": {"include_usage": True},
    }
    try:
        with client.stream("POST", chat_url, json=payload) as response:
            response.raise_for_status()
            for line in response.iter_lines():
                if not line or line.startswith(":"):
                    continue
                if line.startswith("data:"):
                    line = line[len("data:") :].strip()
                if not line:
                    continue
                if line == "[DONE]":
                    done_seen = True
                    done_ts = iso_now()
                    break
                try:
                    chunk = json.loads(line)
                except json.JSONDecodeError:
                    continue
                usage = chunk.get("usage")
                if isinstance(usage, dict) and isinstance(usage.get("completion_tokens"), int):
                    completion_tokens = int(usage["completion_tokens"])
                for choice in chunk.get("choices", []) or []:
                    if not isinstance(choice, dict):
                        continue
                    if choice.get("finish_reason") is not None:
                        finish_reason = str(choice["finish_reason"])
                    delta = choice.get("delta") or {}
                    if not isinstance(delta, dict):
                        continue
                    content = delta.get("content")
                    if isinstance(content, str) and content:
                        output_parts.append(content)
                        if first_token_ts is None:
                            first_token_at = time.perf_counter()
                            first_token_ts = iso_now()
        if done_ts is None:
            done_ts = iso_now()
    except Exception as exc:  # noqa: BLE001 - artifact records canary endpoint failure
        return None, f"canary_failed:{type(exc).__name__}:{exc}"

    completion_text = "".join(output_parts)
    generated_tokens = completion_tokens
    if generated_tokens is None:
        generated_tokens = _estimated_generated_tokens(completion_text)
    ttft_ms = 0.0
    if first_token_at is not None:
        ttft_ms = max(0.0, (first_token_at - start) * 1000.0)
    canary = {
        "request_ts": request_ts,
        "first_token_ts": first_token_ts,
        "done_ts": done_ts,
        "ttft_ms": round(ttft_ms, 6),
        "completion_text": completion_text,
        "completion_tokens": generated_tokens,
        "finish_reason": finish_reason,
        "done_seen": done_seen,
    }
    if generated_tokens < 1 or not completion_text:
        return canary, "canary_no_generated_tokens"
    if finish_reason is None and not done_seen:
        return canary, "canary_missing_finish_reason"
    return canary, None


def _estimated_generated_tokens(text: str) -> int:
    if not text:
        return 0
    pieces = [piece for piece in text.replace("\n", " ").split(" ") if piece]
    return max(1, len(pieces))

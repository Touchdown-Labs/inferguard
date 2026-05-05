"""Agent subprocess tracing and OpenAI-compatible proxy capture."""

from __future__ import annotations

import json
import logging
import os
import subprocess
import threading
import time
import uuid
from collections import Counter
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import httpx

from inferguard.harness.permissions import PermissionPolicy
from inferguard.schemas.agent_trace import (
    AGENT_TRACE_SCHEMA_VERSION,
    Branch,
    ModelCall,
    NodeEvent,
    SummaryEvent,
    ToolCall,
    validate_agent_trace_event,
)

TRACE_FILENAME = "agent-trace.jsonl"
PROMPTS_FILENAME = "prompts-local.jsonl"
DEFAULT_PROXY_HOST = "127.0.0.1"
FRAMEWORK_HOOK_STUBS = {"crewai", "autogen", "claude_code", "cursor_sdk"}
FRAMEWORK_STUB_MESSAGE = (
    "Framework hook only available for LangGraph in v0.5; raw_openai HTTP-proxy mode "
    "works for any framework. Track upstream for v0.6."
)
LOGGER = logging.getLogger(__name__)

try:  # LangGraph/LangChain is optional; duck-typed callbacks still work without it.
    from langchain_core.callbacks import BaseCallbackHandler as _BaseCallbackHandler
except ImportError:  # pragma: no cover - depends on optional langchain-core install
    _BaseCallbackHandler = object


@dataclass(frozen=True)
class TraceRunResult:
    returncode: int
    trace_path: Path
    proxy_url: str | None
    command: tuple[str, ...]


@dataclass(frozen=True)
class ProxyHandle:
    url: str
    base_url: str
    server: ThreadingHTTPServer
    thread: threading.Thread


class AgentTracer:
    """Record ``agent-trace/v1`` JSONL around real agent subprocess traffic."""

    def __init__(
        self,
        *,
        output_dir: Path | str,
        framework: str = "unknown",
        target_endpoint: str | None = None,
        save_prompts: bool = False,
        trace_id: str | None = None,
        rig_label: str | None = None,
        engine: str | None = None,
        permission_policy: PermissionPolicy | None = None,
    ) -> None:
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.trace_path = self.output_dir / TRACE_FILENAME
        self.prompts_path = self.output_dir / PROMPTS_FILENAME
        self.framework = framework
        self.target_endpoint = target_endpoint
        self.save_prompts = save_prompts
        self.trace_id = trace_id or str(uuid.uuid4())
        self.rig_label = rig_label
        self.engine = engine
        self.permission_policy = permission_policy or PermissionPolicy()
        self.started_perf = time.perf_counter()
        self.started_at = _now_iso()
        self.node_counts: Counter[str] = Counter()
        self.total_input_tokens = 0
        self.total_output_tokens = 0
        self.tool_stall_total_seconds = 0.0
        self.tool_wall_total_seconds = 0.0
        self._finalized = False
        self.trace_path.write_text("", encoding="utf-8")
        if self.save_prompts:
            self.prompts_path.write_text("", encoding="utf-8")

    def proxy_env(self, proxy_base_url: str) -> dict[str, str]:
        """Environment variables understood by common OpenAI-compatible clients."""

        return {
            "OPENAI_API_BASE": proxy_base_url,
            "OPENAI_BASE_URL": proxy_base_url,
            "OPENAI_API_BASE_URL": proxy_base_url,
            "INFERGUARD_AGENT_TRACE_ID": self.trace_id,
            "INFERGUARD_AGENT_TRACE_FRAMEWORK": self.framework,
        }

    @contextmanager
    def proxy(self, *, host: str = DEFAULT_PROXY_HOST, port: int = 0) -> Iterator[ProxyHandle]:
        if self.target_endpoint is None:
            raise ValueError("target_endpoint is required for HTTP proxy mode")
        decision = self.permission_policy.check_network(self.target_endpoint)
        decision.raise_if_denied()
        target_endpoint = self.target_endpoint
        tracer = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self) -> None:  # noqa: N802 - stdlib callback name
                length = int(self.headers.get("Content-Length", "0") or 0)
                request_body = self.rfile.read(length) if length else b""
                start = time.perf_counter()
                timestamp_start = time.time()
                status_code = 502
                chunks: list[bytes] = []
                first_byte_at: float | None = None
                headers: dict[str, str] = {}
                try:
                    forward_url = _forward_url(target_endpoint, self.path)
                    with httpx.Client(timeout=None) as client:
                        with client.stream(
                            "POST",
                            forward_url,
                            content=request_body,
                            headers=_forward_headers(self.headers),
                        ) as response:
                            status_code = response.status_code
                            headers = dict(response.headers)
                            self.send_response(status_code)
                            self.send_header(
                                "Content-Type", headers.get("content-type", "application/json")
                            )
                            self.end_headers()
                            for chunk in response.iter_bytes():
                                if first_byte_at is None and chunk:
                                    first_byte_at = time.perf_counter()
                                chunks.append(chunk)
                                self.wfile.write(chunk)
                    response_body = b"".join(chunks)
                except Exception as exc:  # pragma: no cover - exercised via proxy failure tests
                    response_body = json.dumps({"error": str(exc)}).encode("utf-8")
                    self.send_response(status_code)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(response_body)
                finally:
                    end = time.perf_counter()
                    tracer.record_http_exchange(
                        endpoint=target_endpoint,
                        request_body=request_body,
                        response_body=response_body,
                        status_code=status_code,
                        timestamp_start=timestamp_start,
                        timestamp_end=timestamp_start + (end - start),
                        ttft_seconds=(first_byte_at - start) if first_byte_at is not None else end - start,
                    )

            def log_message(self, _format: str, *args: Any) -> None:
                return

        server = ThreadingHTTPServer((host, port), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        actual_port = server.server_address[1]
        url = f"http://{host}:{actual_port}"
        handle = ProxyHandle(url=url, base_url=f"{url}/v1", server=server, thread=thread)
        try:
            yield handle
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)

    def trace_subprocess(
        self,
        command: Sequence[str],
        *,
        cwd: Path | str | None = None,
        env: Mapping[str, str] | None = None,
        timeout: float | None = None,
    ) -> TraceRunResult:
        """Run a command with OpenAI-compatible clients pointed at the local proxy."""

        self.permission_policy.check_command(list(command)).raise_if_denied()
        child_env = dict(os.environ)
        if env:
            child_env.update(env)
        proxy_url: str | None = None
        if self.target_endpoint:
            with self.proxy() as handle:
                proxy_url = handle.base_url
                child_env.update(self.proxy_env(handle.base_url))
                completed = subprocess.run(  # noqa: S603 - user command is explicitly supplied
                    list(command), cwd=cwd, env=child_env, timeout=timeout, check=False
                )
        else:
            completed = subprocess.run(  # noqa: S603 - user command is explicitly supplied
                list(command), cwd=cwd, env=child_env, timeout=timeout, check=False
            )
        status = "success" if completed.returncode == 0 else "error"
        self.finalize(exit_status=status, error_message=None if completed.returncode == 0 else "subprocess failed")
        return TraceRunResult(
            returncode=completed.returncode,
            trace_path=self.trace_path,
            proxy_url=proxy_url,
            command=tuple(command),
        )

    def record_http_exchange(
        self,
        *,
        endpoint: str,
        request_body: bytes,
        response_body: bytes,
        status_code: int,
        timestamp_start: float,
        timestamp_end: float,
        ttft_seconds: float,
    ) -> NodeEvent:
        request_payload = _decode_json(request_body)
        parsed = _parse_openai_response(response_body)
        model = str(request_payload.get("model") or parsed.get("model") or "unknown")
        input_tokens = parsed.get("input_tokens") or _estimate_prompt_tokens(request_payload)
        output_tokens = parsed.get("output_tokens") or _estimate_output_tokens(parsed.get("output_text", ""))
        stop_reason = parsed.get("stop_reason")
        if status_code >= 400:
            stop_reason = "error"
        event = self.record_model_call(
            endpoint=endpoint,
            model=model,
            input_tokens=int(input_tokens),
            output_tokens=int(output_tokens),
            input_tokens_source="api" if parsed.get("input_tokens") is not None else "estimated",
            output_tokens_source="api" if parsed.get("output_tokens") is not None else "estimated",
            ttft_seconds=max(0.0, ttft_seconds),
            tpot_seconds=_safe_tpot(timestamp_end - timestamp_start, ttft_seconds, int(output_tokens)),
            latency_seconds=max(0.0, timestamp_end - timestamp_start),
            tool_choice=_tool_choice(request_payload.get("tool_choice")),
            stream=bool(request_payload.get("stream", True)),
            stop_reason=_stop_reason(stop_reason),
            request_id=str(parsed.get("request_id") or uuid.uuid4()),
            kv_pressure_label="inferred_without_engine_metrics",
            timestamp_start=timestamp_start,
            timestamp_end=timestamp_end,
        )
        if self.save_prompts:
            self._write_prompt_debug(request_payload, parsed)
        return event

    def record_model_call(
        self,
        *,
        endpoint: str,
        model: str,
        input_tokens: int,
        output_tokens: int,
        input_tokens_source: str,
        output_tokens_source: str,
        ttft_seconds: float,
        tpot_seconds: float,
        latency_seconds: float,
        tool_choice: str | None,
        stream: bool,
        stop_reason: str | None,
        request_id: str,
        kv_pressure_label: str,
        timestamp_start: float | None = None,
        timestamp_end: float | None = None,
        parent_node_ids: list[str] | None = None,
    ) -> NodeEvent:
        start = time.time() if timestamp_start is None else timestamp_start
        end = start + latency_seconds if timestamp_end is None else timestamp_end
        event = NodeEvent(
            schema_version=AGENT_TRACE_SCHEMA_VERSION,
            event_type="node",
            trace_id=self.trace_id,
            node_id=str(uuid.uuid4()),
            parent_node_ids=parent_node_ids or [],
            timestamp_start=start,
            timestamp_end=end,
            kind="model_call",
            framework=self.framework,
            model_call=ModelCall(
                endpoint=endpoint,
                model=model,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                input_tokens_source=input_tokens_source,  # type: ignore[arg-type]
                output_tokens_source=output_tokens_source,  # type: ignore[arg-type]
                ttft_seconds=ttft_seconds,
                tpot_seconds=tpot_seconds,
                latency_seconds=latency_seconds,
                tool_choice=tool_choice,  # type: ignore[arg-type]
                stream=stream,
                stop_reason=stop_reason,  # type: ignore[arg-type]
                request_id=request_id,
                kv_pressure_label=kv_pressure_label,  # type: ignore[arg-type]
            ),
        )
        self._append_event(event)
        self.total_input_tokens += input_tokens
        self.total_output_tokens += output_tokens
        self.node_counts["model_call"] += 1
        return event

    def record_tool_call(
        self,
        *,
        name: str,
        wall_time_seconds: float,
        stall_seconds: float,
        result_size_bytes: int,
        result_kind: str = "text",
        is_external: bool = True,
        is_io_bound: bool = True,
        parent_node_ids: list[str] | None = None,
        timestamp_start: float | None = None,
        timestamp_end: float | None = None,
    ) -> NodeEvent:
        now = time.time() if timestamp_start is None else timestamp_start
        end = now + wall_time_seconds if timestamp_end is None else timestamp_end
        event = NodeEvent(
            schema_version=AGENT_TRACE_SCHEMA_VERSION,
            event_type="node",
            trace_id=self.trace_id,
            node_id=str(uuid.uuid4()),
            parent_node_ids=parent_node_ids or [],
            timestamp_start=now,
            timestamp_end=end,
            kind="tool_call",
            framework=self.framework,
            tool_call=ToolCall(
                name=name,
                wall_time_seconds=wall_time_seconds,
                stall_seconds=stall_seconds,
                result_size_bytes=result_size_bytes,
                result_kind=result_kind,  # type: ignore[arg-type]
                is_external=is_external,
                is_io_bound=is_io_bound,
            ),
        )
        self._append_event(event)
        self.tool_stall_total_seconds += stall_seconds
        self.tool_wall_total_seconds += wall_time_seconds
        self.node_counts["tool_call"] += 1
        return event

    def record_branch(
        self,
        *,
        branch_kind: str,
        siblings: list[str],
        parent_node_ids: list[str] | None = None,
        timestamp_start: float | None = None,
        timestamp_end: float | None = None,
    ) -> NodeEvent:
        now = time.time() if timestamp_start is None else timestamp_start
        end = now if timestamp_end is None else timestamp_end
        event = NodeEvent(
            schema_version=AGENT_TRACE_SCHEMA_VERSION,
            event_type="node",
            trace_id=self.trace_id,
            node_id=str(uuid.uuid4()),
            parent_node_ids=parent_node_ids or [],
            timestamp_start=now,
            timestamp_end=end,
            kind="branch",
            framework=self.framework,
            branch=Branch(branch_kind=branch_kind, siblings=siblings),  # type: ignore[arg-type]
        )
        self._append_event(event)
        self.node_counts["branch"] += 1
        return event

    def finalize(
        self,
        *,
        exit_status: str = "success",
        error_message: str | None = None,
        framework_version: dict[str, str] | None = None,
    ) -> SummaryEvent:
        if self._finalized:
            raise RuntimeError("agent trace already finalized")
        total_seconds = time.perf_counter() - self.started_perf
        summary = SummaryEvent(
            schema_version=AGENT_TRACE_SCHEMA_VERSION,
            event_type="summary",
            trace_id=self.trace_id,
            started_at=self.started_at,
            completed_at=_now_iso(),
            total_seconds=total_seconds,
            node_counts=dict(self.node_counts),
            total_tokens={"input": self.total_input_tokens, "output": self.total_output_tokens},
            tool_stall_total_seconds=self.tool_stall_total_seconds,
            tool_stall_pct=(
                self.tool_stall_total_seconds / self.tool_wall_total_seconds
                if self.tool_wall_total_seconds > 0
                else 0.0
            ),
            exit_status=exit_status,  # type: ignore[arg-type]
            error_message=error_message,
            framework_version=framework_version or ({self.framework: "unknown"} if self.framework else {}),
            rig_label=self.rig_label,  # type: ignore[arg-type]
            engine=self.engine,  # type: ignore[arg-type]
            redaction={"prompts_redacted": not self.save_prompts, "tool_args_redacted": True},
        )
        self._append_event(summary)
        self._finalized = True
        return summary

    def _append_event(self, event: NodeEvent | SummaryEvent) -> None:
        data = validate_agent_trace_event(event.as_dict()).as_dict()
        with self.trace_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(data, sort_keys=True, separators=(",", ":")) + "\n")

    def _write_prompt_debug(self, request_payload: dict[str, Any], parsed: dict[str, Any]) -> None:
        with self.prompts_path.open("a", encoding="utf-8") as handle:
            handle.write(
                json.dumps(
                    {
                        "trace_id": self.trace_id,
                        "recorded_at": _now_iso(),
                        "request": request_payload,
                        "response_text": parsed.get("output_text"),
                    },
                    sort_keys=True,
                )
                + "\n"
            )


@dataclass
class _ActiveLangGraphSpan:
    name: str
    started_at: float
    input_tokens: int = 0
    input_tokens_source: str = "estimated"
    args_length_bytes: int = 0


class LangGraphCallback(_BaseCallbackHandler):  # type: ignore[misc]
    """LangGraph/LangChain callback handler that writes ``agent-trace/v1`` nodes.

    The callback deliberately captures shape and timing metadata only. Tool
    argument content is redacted unless ``AgentTracer(save_prompts=True)`` is
    explicitly enabled, in which case arguments are written to the local-only
    ``prompts-local.jsonl`` debug file, not the trace JSONL.
    """

    def __init__(self, tracer: AgentTracer) -> None:
        super().__init__()
        self.tracer = tracer
        self._models: dict[str, _ActiveLangGraphSpan] = {}
        self._tools: dict[str, _ActiveLangGraphSpan] = {}
        self._chains: dict[str, _ActiveLangGraphSpan] = {}

    def on_chat_model_start(self, serialized: Any, messages: Any, **kwargs: Any) -> None:
        run_key = _run_key(kwargs.get("run_id"))
        name = _serialized_name(serialized, kwargs, default="langgraph.chat_model")
        self._models[run_key] = _ActiveLangGraphSpan(
            name=name,
            started_at=time.time(),
            input_tokens=_estimate_langgraph_input_tokens(messages),
            input_tokens_source="estimated",
        )
        if self.tracer.save_prompts:
            self.tracer._write_prompt_debug(
                {
                    "event": "on_chat_model_start",
                    "model": name,
                    "messages": _json_safe(messages),
                },
                {},
            )

    def on_chat_model_end(self, response: Any, **kwargs: Any) -> None:
        run_key = _run_key(kwargs.get("run_id"))
        ended_at = time.time()
        span = self._models.pop(
            run_key,
            _ActiveLangGraphSpan(name="langgraph.chat_model", started_at=ended_at),
        )
        usage = _extract_langgraph_usage(response)
        input_tokens = usage.get("input_tokens", span.input_tokens)
        output_tokens = usage.get("output_tokens", _estimate_output_tokens(_langgraph_output_text(response)))
        input_source = usage.get("input_tokens_source", span.input_tokens_source)
        output_source = usage.get("output_tokens_source", "estimated")
        latency = max(0.0, ended_at - span.started_at)
        self.tracer.record_model_call(
            endpoint="langgraph://chat_model",
            model=str(usage.get("model") or span.name),
            input_tokens=int(input_tokens),
            output_tokens=int(output_tokens),
            input_tokens_source=str(input_source),
            output_tokens_source=str(output_source),
            ttft_seconds=latency if output_tokens else 0.0,
            tpot_seconds=_safe_tpot(latency, 0.0, int(output_tokens)),
            latency_seconds=latency,
            tool_choice=None,
            stream=False,
            stop_reason=_stop_reason(usage.get("stop_reason")),
            request_id=str(kwargs.get("run_id") or uuid.uuid4()),
            kv_pressure_label="inferred_without_engine_metrics",
            timestamp_start=span.started_at,
            timestamp_end=ended_at,
        )

    def on_llm_start(self, serialized: Any, prompts: Any, **kwargs: Any) -> None:
        self.on_chat_model_start(serialized, prompts, **kwargs)

    def on_llm_end(self, response: Any, **kwargs: Any) -> None:
        self.on_chat_model_end(response, **kwargs)

    def on_tool_start(self, serialized: Any, input_str: Any, **kwargs: Any) -> None:
        run_key = _run_key(kwargs.get("run_id"))
        name = _serialized_name(serialized, kwargs, default="langgraph.tool")
        args_length_bytes = _safe_len_bytes(input_str)
        self._tools[run_key] = _ActiveLangGraphSpan(
            name=name,
            started_at=time.time(),
            args_length_bytes=args_length_bytes,
        )
        if self.tracer.save_prompts:
            self.tracer._write_prompt_debug(
                {
                    "event": "on_tool_start",
                    "tool_name": name,
                    "args_length_bytes": args_length_bytes,
                    "args": _json_safe(input_str),
                },
                {},
            )

    def on_tool_end(self, output: Any, **kwargs: Any) -> None:
        run_key = _run_key(kwargs.get("run_id"))
        ended_at = time.time()
        fallback_name = str(kwargs.get("name") or "langgraph.tool")
        span = self._tools.pop(
            run_key,
            _ActiveLangGraphSpan(name=fallback_name, started_at=ended_at),
        )
        self.tracer.record_tool_call(
            name=span.name,
            wall_time_seconds=max(0.0, ended_at - span.started_at),
            stall_seconds=0.0,
            result_size_bytes=_safe_len_bytes(output),
            result_kind=_result_kind(output),
            timestamp_start=span.started_at,
            timestamp_end=ended_at,
        )

    def on_tool_error(self, error: BaseException, **kwargs: Any) -> None:
        self.on_tool_end({"error_type": type(error).__name__}, **kwargs)

    def on_chain_start(self, serialized: Any, inputs: Any, **kwargs: Any) -> None:
        run_key = _run_key(kwargs.get("run_id"))
        name = _serialized_name(serialized, kwargs, default="fan_out")
        self._chains[run_key] = _ActiveLangGraphSpan(name=name, started_at=time.time())
        if self.tracer.save_prompts:
            self.tracer._write_prompt_debug(
                {"event": "on_chain_start", "chain_name": name, "inputs": _json_safe(inputs)},
                {},
            )

    def on_chain_end(self, outputs: Any, **kwargs: Any) -> None:
        run_key = _run_key(kwargs.get("run_id"))
        ended_at = time.time()
        span = self._chains.pop(
            run_key,
            _ActiveLangGraphSpan(name=str(kwargs.get("name") or "fan_out"), started_at=ended_at),
        )
        self.tracer.record_branch(
            branch_kind=_branch_kind_from_chain_name(span.name),
            siblings=[span.name],
            timestamp_start=span.started_at,
            timestamp_end=ended_at,
        )
        if self.tracer.save_prompts:
            self.tracer._write_prompt_debug(
                {"event": "on_chain_end", "chain_name": span.name, "outputs": _json_safe(outputs)},
                {},
            )

    def on_chain_error(self, error: BaseException, **kwargs: Any) -> None:
        self.on_chain_end({"error_type": type(error).__name__}, **kwargs)


LangGraphTraceCallback = LangGraphCallback


def langgraph_callback(tracer: AgentTracer) -> LangGraphCallback:
    return LangGraphCallback(tracer)


def framework_callback(framework: str, tracer: AgentTracer) -> LangGraphCallback | None:
    """Return a framework callback, or raise for hooks not implemented in v0.5."""

    if framework == "langgraph":
        return LangGraphCallback(tracer)
    if framework == "raw_openai":
        return None
    if framework in FRAMEWORK_HOOK_STUBS:
        LOGGER.error("%s requested: %s", framework, FRAMEWORK_STUB_MESSAGE)
        raise NotImplementedError(FRAMEWORK_STUB_MESSAGE)  # noqa: scan-no-stubs explicit-framework-not-supported-loud-error
    raise ValueError(f"unknown framework: {framework}")


def _forward_url(target_endpoint: str, request_path: str) -> str:
    parts = urlsplit(target_endpoint)
    base = f"{parts.scheme}://{parts.netloc}"
    if request_path.startswith("/"):
        return f"{base}{request_path}"
    return f"{base}/{request_path}"


def _forward_headers(headers: Mapping[str, str]) -> dict[str, str]:
    skip = {"host", "content-length", "connection", "accept-encoding"}
    return {key: value for key, value in headers.items() if key.lower() not in skip}


def _decode_json(body: bytes) -> dict[str, Any]:
    try:
        value = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _parse_openai_response(body: bytes) -> dict[str, Any]:
    text = body.decode("utf-8", errors="replace")
    chunks: list[str] = []
    usage: dict[str, Any] | None = None
    stop_reason: str | None = None
    request_id: str | None = None
    model: str | None = None
    for line in text.splitlines():
        if not line.startswith("data:"):
            continue
        payload = line.removeprefix("data:").strip()
        if not payload or payload == "[DONE]":
            continue
        try:
            data = json.loads(payload)
        except json.JSONDecodeError:
            continue
        usage = data.get("usage") or usage
        request_id = data.get("id") or request_id
        model = data.get("model") or model
        for choice in data.get("choices") or []:
            delta = choice.get("delta") or choice.get("message") or {}
            content = delta.get("content")
            if isinstance(content, str):
                chunks.append(content)
            stop_reason = _normalize_stop_reason(choice.get("finish_reason")) or stop_reason
    if not chunks and text.strip().startswith("{"):
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            data = {}
        usage = data.get("usage") or usage
        request_id = data.get("id") or request_id
        model = data.get("model") or model
        for choice in data.get("choices") or []:
            message = choice.get("message") or {}
            content = message.get("content")
            if isinstance(content, str):
                chunks.append(content)
            stop_reason = _normalize_stop_reason(choice.get("finish_reason")) or stop_reason
    return {
        "input_tokens": usage.get("prompt_tokens") if isinstance(usage, dict) else None,
        "output_tokens": usage.get("completion_tokens") if isinstance(usage, dict) else None,
        "output_text": "".join(chunks),
        "stop_reason": stop_reason or "end_turn",
        "request_id": request_id,
        "model": model,
    }


def _estimate_prompt_tokens(payload: dict[str, Any]) -> int:
    messages = payload.get("messages") or []
    if not isinstance(messages, list):
        return 1
    chars = 0
    for message in messages:
        if isinstance(message, dict):
            chars += len(str(message.get("content", "")))
    return max(1, chars // 4)


def _estimate_output_tokens(text: str) -> int:
    return max(1, len(text) // 4) if text else 0


def _safe_tpot(latency: float, ttft: float, output_tokens: int) -> float:
    if output_tokens <= 0:
        return 0.0
    return max(0.0, latency - ttft) / output_tokens


def _tool_choice(value: Any) -> str | None:
    return value if value in {"auto", "required", "none", None} else None


def _stop_reason(value: Any) -> str | None:
    return value if value in {"tool_use", "end_turn", "length", "error", None} else "end_turn"


def _normalize_stop_reason(value: Any) -> str | None:
    if value in {None, "stop"}:
        return "end_turn"
    if value in {"length", "tool_use", "error"}:
        return value
    return None


def _run_key(run_id: Any) -> str:
    return str(run_id or uuid.uuid4())


def _serialized_name(serialized: Any, kwargs: Mapping[str, Any], *, default: str) -> str:
    for key in ("name", "run_name"):
        value = kwargs.get(key)
        if value:
            return str(value)
    if isinstance(serialized, Mapping):
        for key in ("name", "id", "repr"):
            value = serialized.get(key)
            if isinstance(value, str) and value:
                return value
            if isinstance(value, list) and value:
                return ".".join(str(part) for part in value if part)
    value = getattr(serialized, "name", None)
    return str(value) if value else default


def _safe_len_bytes(value: Any) -> int:
    try:
        return len(json.dumps(_json_safe(value), sort_keys=True).encode("utf-8"))
    except (TypeError, ValueError):
        return len(str(value).encode("utf-8", errors="replace"))


def _json_safe(value: Any) -> Any:
    try:
        json.dumps(value)
    except (TypeError, ValueError):
        if isinstance(value, Mapping):
            return {str(key): _json_safe(item) for key, item in value.items()}
        if isinstance(value, (list, tuple)):
            return [_json_safe(item) for item in value]
        return str(value)
    return value


def _result_kind(output: Any) -> str:
    if isinstance(output, Mapping):
        return "json"
    if isinstance(output, bytes):
        return "binary"
    return "text"


def _estimate_langgraph_input_tokens(messages: Any) -> int:
    text = str(_json_safe(messages))
    return max(1, len(text) // 4) if text else 0


def _extract_langgraph_usage(response: Any) -> dict[str, Any]:
    usage: dict[str, Any] = {}
    candidates = [response]
    llm_output = getattr(response, "llm_output", None)
    if isinstance(llm_output, Mapping):
        candidates.append(llm_output)
        token_usage = llm_output.get("token_usage") or llm_output.get("usage")
        if isinstance(token_usage, Mapping):
            candidates.append(token_usage)
        if llm_output.get("model_name"):
            usage["model"] = llm_output.get("model_name")
    generations = getattr(response, "generations", None)
    if generations:
        for generation_group in generations:
            group = generation_group if isinstance(generation_group, list) else [generation_group]
            for generation in group:
                message = getattr(generation, "message", None)
                if message is not None:
                    candidates.append(message)
                generation_info = getattr(generation, "generation_info", None)
                if isinstance(generation_info, Mapping):
                    candidates.append(generation_info)
    for candidate in candidates:
        if isinstance(candidate, Mapping):
            _merge_usage(candidate, usage)
            continue
        usage_metadata = getattr(candidate, "usage_metadata", None)
        if isinstance(usage_metadata, Mapping):
            _merge_usage(usage_metadata, usage)
        response_metadata = getattr(candidate, "response_metadata", None)
        if isinstance(response_metadata, Mapping):
            _merge_usage(response_metadata, usage)
    return usage


def _merge_usage(candidate: Mapping[str, Any], usage: dict[str, Any]) -> None:
    input_tokens = candidate.get("input_tokens") or candidate.get("prompt_tokens")
    output_tokens = candidate.get("output_tokens") or candidate.get("completion_tokens")
    total_usage = candidate.get("token_usage") or candidate.get("usage")
    if isinstance(total_usage, Mapping):
        input_tokens = input_tokens or total_usage.get("prompt_tokens") or total_usage.get("input_tokens")
        output_tokens = (
            output_tokens or total_usage.get("completion_tokens") or total_usage.get("output_tokens")
        )
    if input_tokens is not None:
        usage["input_tokens"] = int(input_tokens)
        usage["input_tokens_source"] = "api"
    if output_tokens is not None:
        usage["output_tokens"] = int(output_tokens)
        usage["output_tokens_source"] = "api"
    for key in ("model", "model_name"):
        if candidate.get(key):
            usage["model"] = candidate[key]
    finish_reason = candidate.get("finish_reason") or candidate.get("stop_reason")
    if finish_reason is not None:
        usage["stop_reason"] = _normalize_stop_reason(finish_reason) or finish_reason


def _langgraph_output_text(response: Any) -> str:
    if isinstance(response, Mapping):
        return str(response.get("content") or response.get("text") or "")
    generations = getattr(response, "generations", None)
    chunks: list[str] = []
    if generations:
        for generation_group in generations:
            group = generation_group if isinstance(generation_group, list) else [generation_group]
            for generation in group:
                text = getattr(generation, "text", None)
                if isinstance(text, str):
                    chunks.append(text)
                message = getattr(generation, "message", None)
                content = getattr(message, "content", None)
                if isinstance(content, str):
                    chunks.append(content)
    if chunks:
        return "".join(chunks)
    content = getattr(response, "content", None)
    return content if isinstance(content, str) else ""


def _branch_kind_from_chain_name(name: str) -> str:
    normalized = name.lower().replace("-", "_").replace(".", "_")
    if normalized in {"speculative", "retry", "fan_out"}:
        return normalized
    if "retry" in normalized:
        return "retry"
    if "spec" in normalized:
        return "speculative"
    return "fan_out"


def _now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


__all__ = [
    "DEFAULT_PROXY_HOST",
    "PROMPTS_FILENAME",
    "TRACE_FILENAME",
    "AgentTracer",
    "LangGraphCallback",
    "LangGraphTraceCallback",
    "ProxyHandle",
    "TraceRunResult",
    "framework_callback",
    "langgraph_callback",
]

"""Minimal MCP server exposing three read-only disagg tools.

Tools:
  - ``disagg_status(prefill_url, decode_url, transfer_url=None, engine="auto")``
  - ``path_trace(sample_size=10)`` — scaffolding; real implementation lives
    in the commercial tier. Returns ``engine_support`` per endpoint instead
    of fabricating correlations.
  - ``recent_events(minutes=10)`` — query the in-process event ring buffer.

``inferguard-mcp`` is installed as a console script when the ``[mcp]``
extra is present.
"""

from __future__ import annotations

import asyncio
from typing import Any

from inferguard.disagg.adapters import scrape
from inferguard.disagg.detect import evaluate
from inferguard.disagg.events import default_buffer
from inferguard.disagg.types import DisaggStatus, EngineName


def _validated_engine(raw: str) -> EngineName | None:
    if raw == "auto":
        return None
    if raw in ("vllm", "sglang", "dynamo", "llm-d"):
        return raw  # type: ignore[return-value]
    return None


async def _collect_status(
    prefill_url: str,
    decode_url: str,
    transfer_url: str | None,
    engine: EngineName | None,
) -> DisaggStatus:
    import httpx

    async with httpx.AsyncClient(timeout=5.0) as client:
        targets = [
            scrape(prefill_url, "prefill", engine, client),
            scrape(decode_url, "decode", engine, client),
        ]
        if transfer_url:
            targets.append(scrape(transfer_url, "transfer", engine, client))
        results = await asyncio.gather(*targets)

    status = DisaggStatus(
        prefill=results[0],
        decode=results[1],
        transfer=results[2] if transfer_url else None,
    )
    findings = evaluate(status)
    return DisaggStatus(
        prefill=status.prefill,
        decode=status.decode,
        transfer=status.transfer,
        findings=findings,
    )


async def tool_disagg_status(
    prefill_url: str,
    decode_url: str,
    transfer_url: str | None = None,
    engine: str = "auto",
) -> dict[str, Any]:
    """Return a full disagg status snapshot (schema v1)."""
    engine_arg = _validated_engine(engine)
    status = await _collect_status(prefill_url, decode_url, transfer_url, engine_arg)
    default_buffer().append(
        status.findings,
        endpoint_urls=[
            status.prefill.endpoint.url,
            status.decode.endpoint.url,
            *([status.transfer.endpoint.url] if status.transfer else []),
        ],
    )
    return status.as_dict()


async def tool_path_trace(sample_size: int = 10) -> dict[str, Any]:
    """Return scaffolded per-request timing with honest support levels.

    In the OSS tier we do not stitch request IDs across prefill/decode —
    that requires either a connector with session-scoped timings or
    external tracing, both of which are out of scope for v0.2.0. We
    return an explicit ``engine_support`` marker so callers don't
    fabricate attributions.
    """
    return {
        "schema_version": "path-trace/v1",
        "samples": [],
        "engine_support": "aggregate_only",
        "note": (
            "Per-session path tracing is not available in the OSS tier. "
            "Use `disagg_status` for aggregate signals."
        ),
        "requested_sample_size": int(sample_size),
    }


async def tool_recent_events(minutes: int = 10) -> dict[str, Any]:
    """Return recent findings from the in-process ring buffer."""
    events = default_buffer().query(minutes=int(minutes))
    return {
        "schema_version": "recent-events/v1",
        "window_minutes": int(minutes),
        "events": events,
    }


def create_mcp_server():  # pragma: no cover - requires optional fastmcp
    """Return a FastMCP server instance with the three tools registered."""
    try:
        from fastmcp import FastMCP
    except ImportError as exc:  # pragma: no cover
        raise SystemExit(
            "inferguard-mcp requires the 'mcp' extra: pip install 'inferguard[mcp]'"
        ) from exc

    server = FastMCP("inferguard")
    server.tool(tool_disagg_status, name="disagg_status")
    server.tool(tool_path_trace, name="path_trace")
    server.tool(tool_recent_events, name="recent_events")
    return server


def main() -> None:  # pragma: no cover - stdio transport path
    server = create_mcp_server()
    server.run()


if __name__ == "__main__":  # pragma: no cover
    main()

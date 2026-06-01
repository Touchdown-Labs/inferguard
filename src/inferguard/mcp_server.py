"""Optional FastMCP server for InferGuard."""

from __future__ import annotations

import os
from typing import Any

from fastmcp import FastMCP

from inferguard.agent import InferGuardAgent
from inferguard.config import InferGuardConfig


def create_mcp_server() -> FastMCP:
    mcp = FastMCP(
        "inferguard",
        instructions="Standalone-first inference monitoring for vLLM and SGLang endpoints.",
    )

    try:  # Optional integration only when a verified Inferscope surface is present.
        from inferscope.server_benchmarks import register_benchmark_tools  # type: ignore
        from inferscope.server_profiling import register_profiling_tools  # type: ignore
    except ImportError:  # pragma: no cover - optional integration path
        register_benchmark_tools = None
        register_profiling_tools = None

    if register_profiling_tools and register_benchmark_tools:
        register_profiling_tools(mcp)
        register_benchmark_tools(mcp)

    @mcp.tool()
    async def tool_inferguard_scan(endpoint: str = "", model: str = "") -> dict[str, Any]:
        """Run one InferGuard scan and return the structured report."""
        if endpoint:
            os.environ["TARGET_ENDPOINT"] = endpoint
        config = InferGuardConfig.from_env()
        agent = InferGuardAgent(config, model_name=model or os.environ.get("INFERGUARD_MODEL_NAME", ""))
        try:
            return await agent.run_once()
        finally:
            await agent.shutdown()

    @mcp.tool()
    async def tool_inferguard_recall(query: str) -> list[dict[str, Any]]:
        """Search similar incidents from vector memory."""
        config = InferGuardConfig.from_env()
        agent = InferGuardAgent(config, model_name=os.environ.get("INFERGUARD_MODEL_NAME", ""))
        try:
            return await agent.memory.find_similar_incidents(query, top_k=5)
        finally:
            await agent.shutdown()

    return mcp

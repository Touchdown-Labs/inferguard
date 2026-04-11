"""Blaxel entrypoint for InferGuard.

Exposes the FastMCP application created by the standalone-first InferGuard
package so Blaxel can discover and host it.
"""

from inferguard.mcp_server import create_mcp_server

app = create_mcp_server()

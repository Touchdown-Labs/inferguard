"""Minimal configuration constants for the OSS inferguard CLI and MCP server.

The OSS tier has no environment dependencies — no egress, no secrets, no auth.
Anything beyond HTTP client defaults belongs in the commercial tier.
"""

from __future__ import annotations

HTTP_TIMEOUT_SECONDS: float = 5.0
"""Default HTTP timeout for /metrics scrapes. CLI callers may override."""

USER_AGENT: str = "inferguard/0.2.0 (+https://github.com/touchdown-labs/inferguard)"
"""User-Agent header for all scrape requests. Identifies us in server logs."""

SECOND_SCRAPE_DELAY_SECONDS: float = 1.0
"""Delta between scrapes when computing rate-of-change findings."""

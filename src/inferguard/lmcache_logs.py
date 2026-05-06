"""Conservative LMCache/vLLM log evidence parsing."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Any

LMCACHE_LOG_SCHEMA_VERSION = "inferguard-lmcache-logs/v1"

_MAX_SNIPPETS_PER_CATEGORY = 6
_MAX_SNIPPET_CHARS = 220

_EVENT_CATEGORIES: tuple[str, ...] = (
    "store",
    "retrieve",
    "prefetch_complete",
    "p2p_peer",
    "p2p_transfer",
    "pd_sender",
    "pd_receiver",
    "health_startup",
)

_CONNECTOR_RE = re.compile(r"\b(LMCacheMPConnector|LMCacheConnectorV1|LMCacheConnector)\b")
_PYTHONHASHSEED_RE = re.compile(
    r"\bPYTHONHASHSEED\b\s*(?:=|:)\s*[\"']?([A-Za-z0-9_.-]+)[\"']?",
    re.IGNORECASE,
)

_BOOL_HINTS: dict[str, re.Pattern[str]] = {
    "enable_p2p": re.compile(r"\benable[_-]?p2p\b\s*(?:=|:)\s*[\"']?(true|false|1|0|yes|no)", re.IGNORECASE),
    "enable_pd": re.compile(r"\benable[_-]?pd\b\s*(?:=|:)\s*[\"']?(true|false|1|0|yes|no)", re.IGNORECASE),
    "enable_async_loading": re.compile(
        r"\benable[_-]?async[_-]?loading\b\s*(?:=|:)\s*[\"']?(true|false|1|0|yes|no)",
        re.IGNORECASE,
    ),
}


@dataclass
class LmcacheLogEvidence:
    """Structured evidence extracted from LMCache and vLLM logs.

    This parser reports observed hints only. It intentionally does not prove
    cache compatibility, hit rate, or transfer correctness from logs alone.
    """

    schema_version: str = LMCACHE_LOG_SCHEMA_VERSION
    line_count: int = 0
    event_counts: dict[str, int] = field(
        default_factory=lambda: {category: 0 for category in _EVENT_CATEGORIES}
    )
    booleans: dict[str, bool] = field(default_factory=dict)
    snippets: dict[str, list[str]] = field(
        default_factory=lambda: {category: [] for category in _EVENT_CATEGORIES}
    )
    config: dict[str, Any] = field(
        default_factory=lambda: {
            "connectors": [],
            "pythonhashseed_seen": False,
            "pythonhashseed_values": [],
            "enable_p2p": None,
            "enable_pd": None,
            "enable_async_loading": None,
            "stale_lmcache_connector_seen": False,
        }
    )
    mode_candidates: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def parse_lmcache_logs(text: str) -> dict[str, Any]:
    """Parse LMCache/vLLM logs into bounded structured evidence.

    The returned dictionary is JSON-serializable and bounded by category-level
    snippet limits. Count fields reflect all matching lines, while snippets are
    short representative lines for auditability.
    """

    evidence = LmcacheLogEvidence()
    connectors: set[str] = set()
    hashseed_values: set[str] = set()
    mode_candidates: set[str] = set()

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        evidence.line_count += 1
        lower = line.lower()

        for connector in _CONNECTOR_RE.findall(line):
            connectors.add(connector)
            if connector == "LMCacheMPConnector":
                mode_candidates.add("mp")
            elif connector == "LMCacheConnectorV1":
                mode_candidates.add("embedded")
            elif connector == "LMCacheConnector":
                evidence.config["stale_lmcache_connector_seen"] = True

        if match := _PYTHONHASHSEED_RE.search(line):
            hashseed_values.add(match.group(1))

        for key, pattern in _BOOL_HINTS.items():
            if match := pattern.search(line):
                value = _parse_bool(match.group(1))
                evidence.config[key] = value
                if key == "enable_p2p" and value is True:
                    mode_candidates.add("p2p")
                if key == "enable_pd" and value is True:
                    mode_candidates.add("disaggregated_prefill")

        for category in _matching_categories(lower):
            _record_event(evidence, category, line)
            if category in {"p2p_peer", "p2p_transfer"}:
                mode_candidates.add("p2p")
            if category in {"pd_sender", "pd_receiver"}:
                mode_candidates.add("disaggregated_prefill")

        if "lmcache server" in lower or "lmcache_mp" in lower:
            mode_candidates.add("mp")
        if "lmcache:" in lower or "lmcacheconnectorv1" in lower:
            mode_candidates.add("embedded")
        if "nixl" in lower and ("prefill" in lower or "decode" in lower or "sender" in lower or "receiver" in lower):
            mode_candidates.add("disaggregated_prefill")

    evidence.config["connectors"] = sorted(connectors)
    evidence.config["pythonhashseed_seen"] = bool(hashseed_values)
    evidence.config["pythonhashseed_values"] = sorted(hashseed_values)
    evidence.mode_candidates = sorted(mode_candidates)
    evidence.booleans = {
        f"has_{category}": count > 0 for category, count in evidence.event_counts.items()
    }
    evidence.booleans.update(
        {
            "has_config_hints": bool(connectors)
            or bool(hashseed_values)
            or any(evidence.config[key] is not None for key in _BOOL_HINTS),
            "has_stale_lmcache_connector": bool(evidence.config["stale_lmcache_connector_seen"]),
        }
    )
    return evidence.as_dict()


def _matching_categories(lower: str) -> list[str]:
    categories: list[str] = []

    if "lmcache" in lower and _has_any(lower, ("store", "storing", "stored", "save", "saving", "saved")):
        categories.append("store")
    if "lmcache" in lower and _has_any(lower, ("retrieve", "retrieving", "retrieved", "lookup hit", "cache hit", "loaded")):
        categories.append("retrieve")
    if "prefetch" in lower and _has_any(lower, ("complete", "completed", "done", "finish", "finished", "loaded", "succeed", "success")):
        categories.append("prefetch_complete")
    is_p2p_transfer = "p2p" in lower and _has_any(
        lower, ("transfer", "transferred", "send", "sent", "recv", "receive", "received", "tokens")
    )
    if (
        "p2p" in lower
        and not is_p2p_transfer
        and _has_any(lower, ("peer", "connect", "connected", "controller", "lookup"))
    ):
        categories.append("p2p_peer")
    if is_p2p_transfer:
        categories.append("p2p_transfer")
    if _is_pd_sender_hint(lower):
        categories.append("pd_sender")
    if _is_pd_receiver_hint(lower):
        categories.append("pd_receiver")
    if _is_health_startup_hint(lower):
        categories.append("health_startup")

    return categories


def _is_pd_sender_hint(lower: str) -> bool:
    has_pd_context = _has_any(lower, ("nixl", "disaggregated", "prefill", "prefiller"))
    return has_pd_context and _has_any(lower, ("sender", "producer", "kv_producer", "kv_both", "prefiller"))


def _is_pd_receiver_hint(lower: str) -> bool:
    has_pd_context = _has_any(lower, ("nixl", "disaggregated", "decode", "decoder"))
    return has_pd_context and _has_any(lower, ("receiver", "consumer", "kv_consumer", "kv_both", "decoder"))


def _is_health_startup_hint(lower: str) -> bool:
    if not _has_any(lower, ("lmcache", "vllm", "uvicorn", "api server")):
        return False
    return _has_any(
        lower,
        (
            "started",
            "starting",
            "startup complete",
            "running on",
            "ready",
            "healthy",
            "health check",
            "server listening",
            "server started",
        ),
    )


def _record_event(evidence: LmcacheLogEvidence, category: str, line: str) -> None:
    evidence.event_counts[category] += 1
    snippets = evidence.snippets[category]
    if len(snippets) < _MAX_SNIPPETS_PER_CATEGORY:
        snippets.append(_snippet(line))


def _snippet(line: str) -> str:
    collapsed = " ".join(line.split())
    if len(collapsed) <= _MAX_SNIPPET_CHARS:
        return collapsed
    return f"{collapsed[: _MAX_SNIPPET_CHARS - 3]}..."


def _has_any(text: str, needles: tuple[str, ...]) -> bool:
    return any(needle in text for needle in needles)


def _parse_bool(value: str) -> bool:
    return value.lower() in {"true", "1", "yes"}


__all__ = ["LMCACHE_LOG_SCHEMA_VERSION", "LmcacheLogEvidence", "parse_lmcache_logs"]

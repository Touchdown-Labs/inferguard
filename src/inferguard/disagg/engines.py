"""Engine auto-detection from a Prometheus exposition blob.

Detection rules are first-match-wins. ``--engine`` on the CLI overrides
this and forces a specific adapter; we still call ``detect_engine`` for
cross-checking and the ``connector_mismatch``-adjacent warning paths.
"""

from __future__ import annotations

from inferguard.disagg.types import EngineName

# Ordered rule table. Each rule is ``(engine, prefix)`` — if ANY metric
# name starts with ``prefix``, the engine wins.
_RULES: list[tuple[EngineName, str]] = [
    ("vllm", "vllm:"),
    ("sglang", "sglang:"),
    ("dynamo", "dynamo_"),
    ("dynamo", "nv_llm_"),
    ("dynamo", "dynamo:"),
    ("lmcache", "lmcache:"),
    ("lmcache", "lmcache_"),
    ("llm-d", "llmd_"),
    ("llm-d", "llm_d_"),
]


def detect_engine(text: str) -> EngineName:
    """Return the first engine whose metric prefix appears in ``text``."""
    # Cheap: iterate lines once, test each against every prefix.
    for raw_line in text.splitlines():
        line = raw_line.lstrip()
        if not line or line.startswith("#"):
            continue
        for engine, prefix in _RULES:
            if line.startswith(prefix):
                return engine
    return "unknown"


__all__ = ["detect_engine", "EngineName"]

"""In-process ring buffer of recent findings for MCP ``recent_events``."""

from __future__ import annotations

import threading
import time
from collections import deque
from typing import Any

from inferguard.disagg.types import DisaggFinding

_DEFAULT_MAXLEN = 1024
_DEFAULT_RETENTION_SECONDS = 3600


class EventBuffer:
    """Thread-safe bounded ring buffer of finding events."""

    def __init__(
        self,
        *,
        maxlen: int = _DEFAULT_MAXLEN,
        retention_seconds: int = _DEFAULT_RETENTION_SECONDS,
    ) -> None:
        self._deque: deque[dict[str, Any]] = deque(maxlen=maxlen)
        self._retention = retention_seconds
        self._lock = threading.Lock()

    def append(
        self,
        findings: list[DisaggFinding],
        endpoint_urls: list[str],
    ) -> None:
        if not findings:
            return
        ts = time.time()
        records = [
            {
                "at": ts,
                "endpoints": list(endpoint_urls),
                "code": f.code,
                "severity": f.severity,
                "message": f.message,
            }
            for f in findings
        ]
        with self._lock:
            self._deque.extend(records)

    def query(self, minutes: int = 10) -> list[dict[str, Any]]:
        cutoff = time.time() - max(minutes, 0) * 60
        with self._lock:
            snapshot = list(self._deque)
        # Respect retention cap and the user-requested window.
        retention_cutoff = time.time() - self._retention
        window_cutoff = max(cutoff, retention_cutoff)
        return [r for r in snapshot if r["at"] >= window_cutoff]

    def __len__(self) -> int:
        with self._lock:
            return len(self._deque)


_default_buffer = EventBuffer()


def default_buffer() -> EventBuffer:
    return _default_buffer


__all__ = ["EventBuffer", "default_buffer"]

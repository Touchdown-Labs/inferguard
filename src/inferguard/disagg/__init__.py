"""Public API for the disaggregated-serving diagnostic surface."""

from inferguard.disagg.adapters import scrape
from inferguard.disagg.detect import evaluate
from inferguard.disagg.types import (
    SCHEMA_VERSION,
    DisaggFinding,
    DisaggSnapshot,
    DisaggStatus,
    EndpointId,
)

__all__ = [
    "DisaggFinding",
    "DisaggSnapshot",
    "DisaggStatus",
    "EndpointId",
    "SCHEMA_VERSION",
    "evaluate",
    "scrape",
]

"""Pure, deterministic detectors.

All rules operate on a ``DisaggStatus`` and return zero or one
``DisaggFinding``. The orchestrator (``evaluate``) runs them in a fixed
order and concatenates the results. No clock reads, no env reads, no
network. Thresholds are intentionally conservative — we prefer an
``info`` / ``warning`` to a false ``critical``.
"""

from __future__ import annotations

from inferguard.disagg.types import DisaggFinding, DisaggStatus

# Thresholds. Kept in one place so they are reviewable as policy.
IMBALANCE_RATIO_LOW = 0.5  # decode-side starved
IMBALANCE_RATIO_HIGH = 2.0  # prefill-side starved
KV_TRANSFER_STALL_MAX_BYTES = 0  # both sides flat = stall

_RULE_ORDER = (
    "endpoint_unreachable",
    "engine_unidentified",
    "connector_mismatch",
    "kv_transfer_errors_present",
    "kv_transfer_stall",
    "prefill_decode_imbalance",
)


def evaluate(status: DisaggStatus) -> list[DisaggFinding]:
    """Run every rule and return their findings in canonical order."""
    findings: list[DisaggFinding] = []
    for rule in _RULE_ORDER:
        result = _RULES[rule](status)
        if result is not None:
            findings.append(result)
    return findings


# --- individual rules -------------------------------------------------------


def rule_endpoint_unreachable(status: DisaggStatus) -> DisaggFinding | None:
    unreachable: list[str] = []
    for snap in _iter_snapshots(status):
        if snap.scrape_error.startswith("unreachable") or snap.scrape_error.startswith("http_"):
            unreachable.append(f"{snap.endpoint.role}={snap.endpoint.url} ({snap.scrape_error})")
    if not unreachable:
        return None
    return DisaggFinding(
        code="endpoint_unreachable",
        severity="critical",
        message="One or more scrape targets failed: " + "; ".join(unreachable),
        evidence={"unreachable": unreachable},
    )


def rule_engine_unidentified(status: DisaggStatus) -> DisaggFinding | None:
    unknowns: list[str] = []
    for snap in _iter_snapshots(status):
        if snap.scrape_error:  # already surfaced by another rule
            continue
        if snap.endpoint.engine == "unknown":
            unknowns.append(f"{snap.endpoint.role}={snap.endpoint.url}")
    if not unknowns:
        return None
    return DisaggFinding(
        code="engine_unidentified",
        severity="warning",
        message="Could not identify serving engine at: " + ", ".join(unknowns),
        evidence={"endpoints": unknowns},
    )


def rule_connector_mismatch(status: DisaggStatus) -> DisaggFinding | None:
    """Warn if prefill and decode report different KV connectors."""
    prefill_conn = status.prefill.endpoint.connector
    decode_conn = status.decode.endpoint.connector
    if not prefill_conn or not decode_conn:
        return None
    if prefill_conn == decode_conn:
        return None
    return DisaggFinding(
        code="connector_mismatch",
        severity="warning",
        message=(
            f"Prefill reports connector={prefill_conn!r}; "
            f"decode reports connector={decode_conn!r}. "
            "Transfers between mismatched connectors are typically silent failures."
        ),
        evidence={"prefill_connector": prefill_conn, "decode_connector": decode_conn},
    )


def rule_kv_transfer_errors_present(status: DisaggStatus) -> DisaggFinding | None:
    errs: dict[str, int] = {}
    for snap in _iter_snapshots(status):
        total = snap.kv_transfer_errors_total
        if total is not None and total > 0:
            errs[f"{snap.endpoint.role}"] = total
    if not errs:
        return None
    total = sum(errs.values())
    severity = "critical" if total >= 100 else "warning"
    return DisaggFinding(
        code="kv_transfer_errors_present",
        severity=severity,
        message=f"KV transfer errors observed: total={total} across {len(errs)} endpoints.",
        evidence={"errors_by_role": errs},
    )


def rule_kv_transfer_stall(status: DisaggStatus) -> DisaggFinding | None:
    """Both sides report zero cumulative transfer bytes despite active requests.

    This is a coarse stall detector — the intent is to catch deployments
    where a KV transfer layer is installed but never actually moves bytes.
    """
    sent = status.prefill.kv_transfer_sent_bytes_total
    recv = status.decode.kv_transfer_recv_bytes_total
    running = max(
        status.prefill.requests_running or 0,
        status.decode.requests_running or 0,
    )
    if sent is None or recv is None:
        return None
    if sent > KV_TRANSFER_STALL_MAX_BYTES or recv > KV_TRANSFER_STALL_MAX_BYTES:
        return None
    if running == 0:
        return None
    return DisaggFinding(
        code="kv_transfer_stall",
        severity="warning",
        message=(
            "KV transfer counters are zero on both sides despite active requests "
            f"(running={running}). The transfer layer may be mis-wired."
        ),
        evidence={
            "prefill_sent_bytes_total": sent,
            "decode_recv_bytes_total": recv,
            "running": running,
        },
    )


def rule_prefill_decode_imbalance(status: DisaggStatus) -> DisaggFinding | None:
    """Warn when prefill / decode queue depths diverge badly."""
    p_run = status.prefill.requests_running
    d_run = status.decode.requests_running
    if p_run is None or d_run is None:
        return None
    if p_run == 0 and d_run == 0:
        return None
    # Guard against zero-division; treat empty side as "1" for ratio purposes.
    p_eff = max(p_run, 1)
    d_eff = max(d_run, 1)
    ratio = p_eff / d_eff
    if IMBALANCE_RATIO_LOW <= ratio <= IMBALANCE_RATIO_HIGH:
        return None
    if ratio < IMBALANCE_RATIO_LOW:
        side, severity = "decode-side pressure", "warning"
    else:
        side, severity = "prefill-side pressure", "warning"
    return DisaggFinding(
        code="prefill_decode_imbalance",
        severity=severity,
        message=(
            f"Prefill/decode running-request ratio = {ratio:.2f} "
            f"(prefill={p_run}, decode={d_run}) → {side}."
        ),
        evidence={
            "prefill_running": p_run,
            "decode_running": d_run,
            "ratio": ratio,
        },
    )


# --- internal ---------------------------------------------------------------


_RULES = {
    "endpoint_unreachable": rule_endpoint_unreachable,
    "engine_unidentified": rule_engine_unidentified,
    "connector_mismatch": rule_connector_mismatch,
    "kv_transfer_errors_present": rule_kv_transfer_errors_present,
    "kv_transfer_stall": rule_kv_transfer_stall,
    "prefill_decode_imbalance": rule_prefill_decode_imbalance,
}


def _iter_snapshots(status: DisaggStatus):
    yield status.prefill
    yield status.decode
    if status.transfer is not None:
        yield status.transfer


__all__ = ["evaluate"]

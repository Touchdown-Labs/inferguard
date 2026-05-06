"""LMCache evidence packet collection for compatibility/debugging workflows."""

from __future__ import annotations

import shutil
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from inferguard.compat import build_compat_report, write_compat_report
from inferguard.lmcache_http import parse_lmcache_http_payloads
from inferguard.io import atomic_write_json, atomic_write_text
from inferguard.lmcache_logs import parse_lmcache_logs
from inferguard.lmcache_otel import parse_lmcache_otel_jsonl
from inferguard.lmcache_trace import parse_lmcache_trace_file

PACKET_SCHEMA_VERSION = "inferguard-lmcache-packet/v1"


@dataclass(frozen=True)
class LmcachePacketOptions:
    """Inputs for a best-effort LMCache packet capture."""

    output_dir: Path
    engine_metrics_url: str | None = None
    lmcache_metrics_url: str | None = None
    engine_metrics_file: Path | None = None
    lmcache_metrics_file: Path | None = None
    lmcache_health_url: str | None = None
    lmcache_health_file: Path | None = None
    lmcache_status_url: str | None = None
    lmcache_status_file: Path | None = None
    engine_log_file: Path | None = None
    lmcache_log_file: Path | None = None
    lmcache_trace_file: Path | None = None
    lmcache_otel_file: Path | None = None
    expect_mode: str = "auto"
    l2_configured: bool = False
    timeout_seconds: float = 10.0
    mp_observability: dict[str, Any] = field(default_factory=dict)


def collect_lmcache_packet(options: LmcachePacketOptions) -> dict[str, Any]:
    """Collect a partial-first LMCache observability packet.

    Network/file failures are recorded in the manifest and do not stop packet
    creation. That matches lab usage: partial evidence is still useful.
    """

    output_dir = Path(options.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    artifacts: dict[str, str] = {}
    sources: dict[str, str] = {}
    errors: list[dict[str, str]] = []

    engine_text = _capture_metrics(
        destination=output_dir / "engine_metrics.prom",
        source_name="engine_metrics",
        url=options.engine_metrics_url,
        source_file=options.engine_metrics_file,
        timeout_seconds=options.timeout_seconds,
        artifacts=artifacts,
        sources=sources,
        errors=errors,
    )
    lmcache_text = _capture_metrics(
        destination=output_dir / "lmcache_metrics.prom",
        source_name="lmcache_metrics",
        url=options.lmcache_metrics_url,
        source_file=options.lmcache_metrics_file,
        timeout_seconds=options.timeout_seconds,
        artifacts=artifacts,
        sources=sources,
        errors=errors,
    )
    health_text = _capture_text(
        destination=output_dir / "lmcache_health.txt",
        source_name="lmcache_health",
        url=options.lmcache_health_url,
        source_file=options.lmcache_health_file,
        timeout_seconds=options.timeout_seconds,
        artifacts=artifacts,
        sources=sources,
        errors=errors,
    )
    status_text = _capture_text(
        destination=output_dir / "lmcache_status.txt",
        source_name="lmcache_status",
        url=options.lmcache_status_url,
        source_file=options.lmcache_status_file,
        timeout_seconds=options.timeout_seconds,
        artifacts=artifacts,
        sources=sources,
        errors=errors,
    )
    http_evidence: dict[str, Any] | None = None
    if health_text or status_text:
        http_evidence = parse_lmcache_http_payloads(
            health_text=health_text,
            status_text=status_text,
        )
        http_evidence_path = output_dir / "lmcache_http_evidence.json"
        atomic_write_json(http_evidence_path, http_evidence)
        artifacts["lmcache_http_evidence"] = str(http_evidence_path)
    engine_log_text = _copy_file(
        destination=output_dir / "engine.log",
        source_name="engine_log",
        source_file=options.engine_log_file,
        artifacts=artifacts,
        sources=sources,
        errors=errors,
    )
    lmcache_log_text = _copy_file(
        destination=output_dir / "lmcache.log",
        source_name="lmcache_log",
        source_file=options.lmcache_log_file,
        artifacts=artifacts,
        sources=sources,
        errors=errors,
    )
    log_evidence: dict[str, Any] | None = None
    combined_log_text = "\n".join(text for text in [engine_log_text, lmcache_log_text] if text)
    if combined_log_text:
        log_evidence = parse_lmcache_logs(combined_log_text)
        log_evidence_path = output_dir / "lmcache_log_evidence.json"
        atomic_write_json(log_evidence_path, log_evidence)
        artifacts["lmcache_log_evidence"] = str(log_evidence_path)
    trace_evidence: dict[str, Any] | None = None
    if options.lmcache_trace_file is not None:
        trace_destination = output_dir / "lmcache_trace.lct"
        _copy_file(
            destination=trace_destination,
            source_name="lmcache_trace",
            source_file=options.lmcache_trace_file,
            artifacts=artifacts,
            sources=sources,
            errors=errors,
        )
        trace_evidence = parse_lmcache_trace_file(options.lmcache_trace_file)
        trace_evidence_path = output_dir / "lmcache_trace_evidence.json"
        atomic_write_json(trace_evidence_path, trace_evidence)
        artifacts["lmcache_trace_evidence"] = str(trace_evidence_path)
    otel_evidence: dict[str, Any] | None = None
    if options.lmcache_otel_file is not None:
        _copy_file(
            destination=output_dir / "lmcache_otel.jsonl",
            source_name="lmcache_otel",
            source_file=options.lmcache_otel_file,
            artifacts=artifacts,
            sources=sources,
            errors=errors,
        )
        otel_evidence = parse_lmcache_otel_jsonl(options.lmcache_otel_file)
        otel_evidence_path = output_dir / "lmcache_otel_evidence.json"
        atomic_write_json(otel_evidence_path, otel_evidence)
        artifacts["lmcache_otel_evidence"] = str(otel_evidence_path)

    report = build_compat_report(
        engine_text=engine_text,
        lmcache_text=lmcache_text,
        engine_source=sources.get("engine_metrics", ""),
        lmcache_source=sources.get("lmcache_metrics", ""),
        expect_mode=options.expect_mode,
        l2_configured=options.l2_configured,
        mp_observability=options.mp_observability,
        lmcache_http_evidence=http_evidence,
        lmcache_trace_evidence=trace_evidence,
        lmcache_otel_evidence=otel_evidence,
    )
    compat_path = output_dir / "lmcache_compat_report.json"
    write_compat_report(report, compat_path)
    artifacts["lmcache_compat_report"] = str(compat_path)

    manifest = {
        "schema_version": PACKET_SCHEMA_VERSION,
        "generated_at": _utc_now_iso(),
        "claim_status": "measured" if engine_text or lmcache_text else "not_proven",
        "expect_mode": options.expect_mode,
        "detected_mode": report.get("detected_mode"),
        "l2_configured": options.l2_configured,
        "sources": sources,
        "artifacts": artifacts,
        "scrape_errors": errors,
        "compat_summary": {
            "failure_reasons": report.get("failure_reasons", []),
            "upstream_questions": report.get("upstream_questions", []),
            "surfaces": report.get("surfaces", {}),
        },
        "http_evidence": http_evidence,
        "log_evidence": log_evidence,
        "trace_evidence": trace_evidence,
        "otel_evidence": otel_evidence,
    }
    manifest_path = output_dir / "packet_manifest.json"
    atomic_write_json(manifest_path, manifest)
    return manifest


def _capture_metrics(
    *,
    destination: Path,
    source_name: str,
    url: str | None,
    source_file: Path | None,
    timeout_seconds: float,
    artifacts: dict[str, str],
    sources: dict[str, str],
    errors: list[dict[str, str]],
) -> str:
    if source_file is not None:
        try:
            text = source_file.read_text(encoding="utf-8")
        except OSError as exc:
            _record_error(errors, source_name, str(source_file), exc)
            return ""
        atomic_write_text(destination, text)
        artifacts[source_name] = str(destination)
        sources[source_name] = str(source_file)
        return text
    return _capture_url(
        destination=destination,
        source_name=source_name,
        url=url,
        timeout_seconds=timeout_seconds,
        artifacts=artifacts,
        sources=sources,
        errors=errors,
    )


def _capture_text(
    *,
    destination: Path,
    source_name: str,
    url: str | None,
    source_file: Path | None,
    timeout_seconds: float,
    artifacts: dict[str, str],
    sources: dict[str, str],
    errors: list[dict[str, str]],
) -> str:
    if source_file is not None:
        try:
            text = source_file.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            _record_error(errors, source_name, str(source_file), exc)
            return ""
        atomic_write_text(destination, text)
        artifacts[source_name] = str(destination)
        sources[source_name] = str(source_file)
        return text
    return _capture_url(
        destination=destination,
        source_name=source_name,
        url=url,
        timeout_seconds=timeout_seconds,
        artifacts=artifacts,
        sources=sources,
        errors=errors,
    )


def _capture_url(
    *,
    destination: Path,
    source_name: str,
    url: str | None,
    timeout_seconds: float,
    artifacts: dict[str, str],
    sources: dict[str, str],
    errors: list[dict[str, str]],
) -> str:
    if not url:
        return ""
    try:
        with urllib.request.urlopen(url, timeout=timeout_seconds) as response:  # noqa: S310 - operator-supplied local URL
            text = response.read().decode("utf-8", errors="replace")
    except (OSError, urllib.error.URLError, TimeoutError) as exc:
        _record_error(errors, source_name, url, exc)
        return ""
    atomic_write_text(destination, text)
    artifacts[source_name] = str(destination)
    sources[source_name] = url
    return text


def _copy_file(
    *,
    destination: Path,
    source_name: str,
    source_file: Path | None,
    artifacts: dict[str, str],
    sources: dict[str, str],
    errors: list[dict[str, str]],
) -> str:
    if source_file is None:
        return ""
    try:
        text = source_file.read_text(encoding="utf-8", errors="replace")
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source_file, destination)
    except OSError as exc:
        _record_error(errors, source_name, str(source_file), exc)
        return ""
    artifacts[source_name] = str(destination)
    sources[source_name] = str(source_file)
    return text


def _record_error(
    errors: list[dict[str, str]], source_name: str, source: str, exc: BaseException
) -> None:
    errors.append(
        {
            "source_name": source_name,
            "source": source,
            "error": f"{type(exc).__name__}: {exc}",
        }
    )


def _utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")

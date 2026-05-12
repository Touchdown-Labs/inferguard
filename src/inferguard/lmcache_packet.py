"""LMCache evidence packet collection for compatibility/debugging workflows."""

from __future__ import annotations

import shutil
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from importlib import import_module
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

from inferguard.compat import (
    _read_l0_boundary_evidence,
    build_compat_report,
    read_sglang_kv_events_evidence,
    write_compat_report,
)
from inferguard.io import atomic_write_json, atomic_write_text
from inferguard.lmcache_http import parse_lmcache_http_payloads
from inferguard.lmcache_logs import parse_lmcache_logs
from inferguard.lmcache_otel import parse_lmcache_otel_jsonl
from inferguard.lmcache_trace import parse_lmcache_trace_file
from inferguard.observability_coverage import (
    build_observability_coverage_report,
    write_observability_coverage_report,
)

PACKET_SCHEMA_VERSION = "inferguard-lmcache-packet/v1"


@dataclass(frozen=True)
class LmcachePacketOptions:
    """Inputs for a best-effort LMCache packet capture."""

    output_dir: Path
    engine_metrics_url: str | None = None
    lmcache_metrics_url: str | None = None
    engine_metrics_file: Path | None = None
    lmcache_metrics_file: Path | None = None
    lmcache_http_base_url: str | None = None
    lmcache_http_thread_name: str | None = None
    lmcache_health_url: str | None = None
    lmcache_health_file: Path | None = None
    lmcache_status_url: str | None = None
    lmcache_status_file: Path | None = None
    lmcache_conf_url: str | None = None
    lmcache_conf_file: Path | None = None
    lmcache_threads_url: str | None = None
    lmcache_threads_file: Path | None = None
    lmcache_periodic_threads_url: str | None = None
    lmcache_periodic_threads_file: Path | None = None
    lmcache_periodic_thread_url: str | None = None
    lmcache_periodic_thread_file: Path | None = None
    lmcache_periodic_threads_health_url: str | None = None
    lmcache_periodic_threads_health_file: Path | None = None
    lmcache_version_url: str | None = None
    lmcache_version_file: Path | None = None
    lmcache_lmc_version_url: str | None = None
    lmcache_lmc_version_file: Path | None = None
    lmcache_commit_id_url: str | None = None
    lmcache_commit_id_file: Path | None = None
    lmcache_quota_url: str | None = None
    lmcache_quota_file: Path | None = None
    engine_log_file: Path | None = None
    lmcache_log_file: Path | None = None
    lmcache_trace_file: Path | None = None
    lmcache_otel_file: Path | None = None
    lmcache_trace_replay_output: Path | None = None
    lmcache_lookup_hash_path: Path | None = None
    lmcache_l0_boundary_evidence_file: Path | None = None
    sglang_kv_events_evidence_file: Path | None = None
    expected_engine: str = "auto"
    expect_mode: str = "auto"
    l2_configured: bool = False
    external_cache_configured: bool = False
    cpu_offload_configured: bool = False
    disaggregated_or_external_cache: bool = False
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
    http_base_url = _normalize_base_url(options.lmcache_http_base_url)
    http_endpoint_errors: dict[str, str] = {}
    health_text = _capture_text(
        destination=output_dir / "lmcache_health.txt",
        source_name="lmcache_health",
        url=options.lmcache_health_url or _join_base(http_base_url, "/api/healthcheck"),
        source_file=options.lmcache_health_file,
        timeout_seconds=options.timeout_seconds,
        artifacts=artifacts,
        sources=sources,
        errors=errors,
    )
    status_text = _capture_text(
        destination=output_dir / "lmcache_status.txt",
        source_name="lmcache_status",
        url=options.lmcache_status_url or _join_base(http_base_url, "/api/status"),
        source_file=options.lmcache_status_file,
        timeout_seconds=options.timeout_seconds,
        artifacts=artifacts,
        sources=sources,
        errors=errors,
    )
    root_text = _capture_optional_http_endpoint(
        output_dir=output_dir,
        endpoint_name="root",
        filename="lmcache_root.txt",
        url=options.lmcache_http_base_url or _join_base(http_base_url, "/"),
        source_file=None,
        timeout_seconds=options.timeout_seconds,
        artifacts=artifacts,
        sources=sources,
        errors=errors,
        endpoint_errors=http_endpoint_errors,
    )
    conf_text = _capture_optional_http_endpoint(
        output_dir=output_dir,
        endpoint_name="conf",
        filename="lmcache_conf.txt",
        url=options.lmcache_conf_url or _join_base(http_base_url, "/conf"),
        source_file=options.lmcache_conf_file,
        timeout_seconds=options.timeout_seconds,
        artifacts=artifacts,
        sources=sources,
        errors=errors,
        endpoint_errors=http_endpoint_errors,
    )
    threads_text = _capture_optional_http_endpoint(
        output_dir=output_dir,
        endpoint_name="threads",
        filename="lmcache_threads.txt",
        url=options.lmcache_threads_url or _join_base(http_base_url, "/threads"),
        source_file=options.lmcache_threads_file,
        timeout_seconds=options.timeout_seconds,
        artifacts=artifacts,
        sources=sources,
        errors=errors,
        endpoint_errors=http_endpoint_errors,
    )
    periodic_threads_text = _capture_optional_http_endpoint(
        output_dir=output_dir,
        endpoint_name="periodic_threads",
        filename="lmcache_periodic_threads.txt",
        url=options.lmcache_periodic_threads_url or _join_base(http_base_url, "/periodic-threads"),
        source_file=options.lmcache_periodic_threads_file,
        timeout_seconds=options.timeout_seconds,
        artifacts=artifacts,
        sources=sources,
        errors=errors,
        endpoint_errors=http_endpoint_errors,
    )
    periodic_thread_path = (
        f"/periodic-threads/{options.lmcache_http_thread_name}"
        if options.lmcache_http_thread_name
        else ""
    )
    periodic_thread_text = _capture_optional_http_endpoint(
        output_dir=output_dir,
        endpoint_name="periodic_thread",
        filename="lmcache_periodic_thread.txt",
        url=options.lmcache_periodic_thread_url or _join_base(http_base_url, periodic_thread_path),
        source_file=options.lmcache_periodic_thread_file,
        timeout_seconds=options.timeout_seconds,
        artifacts=artifacts,
        sources=sources,
        errors=errors,
        endpoint_errors=http_endpoint_errors,
    )
    periodic_threads_health_text = _capture_optional_http_endpoint(
        output_dir=output_dir,
        endpoint_name="periodic_threads_health",
        filename="lmcache_periodic_threads_health.txt",
        url=options.lmcache_periodic_threads_health_url
        or _join_base(http_base_url, "/periodic-threads-health"),
        source_file=options.lmcache_periodic_threads_health_file,
        timeout_seconds=options.timeout_seconds,
        artifacts=artifacts,
        sources=sources,
        errors=errors,
        endpoint_errors=http_endpoint_errors,
    )
    version_text = _capture_optional_http_endpoint(
        output_dir=output_dir,
        endpoint_name="version",
        filename="lmcache_version.txt",
        url=options.lmcache_version_url or _join_base(http_base_url, "/version"),
        source_file=options.lmcache_version_file,
        timeout_seconds=options.timeout_seconds,
        artifacts=artifacts,
        sources=sources,
        errors=errors,
        endpoint_errors=http_endpoint_errors,
    )
    lmc_version_text = _capture_optional_http_endpoint(
        output_dir=output_dir,
        endpoint_name="lmc_version",
        filename="lmcache_lmc_version.txt",
        url=options.lmcache_lmc_version_url or _join_base(http_base_url, "/lmc_version"),
        source_file=options.lmcache_lmc_version_file,
        timeout_seconds=options.timeout_seconds,
        artifacts=artifacts,
        sources=sources,
        errors=errors,
        endpoint_errors=http_endpoint_errors,
    )
    commit_id_text = _capture_optional_http_endpoint(
        output_dir=output_dir,
        endpoint_name="commit_id",
        filename="lmcache_commit_id.txt",
        url=options.lmcache_commit_id_url or _join_base(http_base_url, "/commit_id"),
        source_file=options.lmcache_commit_id_file,
        timeout_seconds=options.timeout_seconds,
        artifacts=artifacts,
        sources=sources,
        errors=errors,
        endpoint_errors=http_endpoint_errors,
    )
    quota_text = _capture_optional_http_endpoint(
        output_dir=output_dir,
        endpoint_name="quota",
        filename="lmcache_quota.txt",
        url=options.lmcache_quota_url or _join_base(http_base_url, "/api/quota"),
        source_file=options.lmcache_quota_file,
        timeout_seconds=options.timeout_seconds,
        artifacts=artifacts,
        sources=sources,
        errors=errors,
        endpoint_errors=http_endpoint_errors,
    )
    skipped_endpoints = _skipped_lmcache_endpoints()
    http_evidence: dict[str, Any] | None = None
    if any(
        [
            root_text,
            health_text,
            status_text,
            conf_text,
            threads_text,
            periodic_threads_text,
            periodic_thread_text,
            periodic_threads_health_text,
            version_text,
            lmc_version_text,
            commit_id_text,
            quota_text,
            http_endpoint_errors,
            skipped_endpoints,
        ]
    ):
        http_evidence = parse_lmcache_http_payloads(
            root_text=root_text,
            health_text=health_text,
            status_text=status_text,
            conf_text=conf_text,
            threads_text=threads_text,
            periodic_threads_text=periodic_threads_text,
            periodic_thread_text=periodic_thread_text,
            periodic_threads_health_text=periodic_threads_health_text,
            extra_payloads={
                "version": version_text,
                "lmc_version": lmc_version_text,
                "commit_id": commit_id_text,
                "quota": quota_text,
            },
            endpoint_errors=http_endpoint_errors,
            skipped_endpoints=skipped_endpoints,
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
    trace_replay_evidence = _copy_and_parse_optional_evidence(
        output_dir=output_dir,
        source_name="lmcache_trace_replay",
        source_path=options.lmcache_trace_replay_output,
        artifact_name="lmcache_trace_replay_artifact",
        evidence_name="lmcache_trace_replay_evidence",
        evidence_filename="lmcache_trace_replay_evidence.json",
        parser_candidates=(
            ("inferguard.lmcache_trace", "parse_lmcache_trace_replay_file"),
            ("inferguard.lmcache_trace", "parse_lmcache_trace_replay_dir"),
            ("inferguard.lmcache_trace_replay", "parse_lmcache_trace_replay_outputs"),
            ("inferguard.lmcache_trace_replay", "parse_lmcache_trace_replay_evidence"),
        ),
        artifacts=artifacts,
        sources=sources,
        errors=errors,
    )
    lookup_hash_evidence = _copy_and_parse_optional_evidence(
        output_dir=output_dir,
        source_name="lmcache_lookup_hash",
        source_path=options.lmcache_lookup_hash_path,
        artifact_name="lmcache_lookup_hash_artifact",
        evidence_name="lmcache_lookup_hash_evidence",
        evidence_filename="lmcache_lookup_hash_evidence.json",
        parser_candidates=(
            ("inferguard.lmcache_lookup_hash", "parse_lmcache_lookup_hash_jsonl"),
            ("inferguard.lmcache_lookup_hash", "parse_lmcache_lookup_hashes"),
            ("inferguard.lmcache_lookup_hash", "parse_lmcache_lookup_hash_evidence"),
        ),
        artifacts=artifacts,
        sources=sources,
        errors=errors,
    )
    l0_boundary_evidence = _copy_and_parse_l0_boundary_evidence(
        output_dir=output_dir,
        source_file=options.lmcache_l0_boundary_evidence_file,
        artifacts=artifacts,
        sources=sources,
        errors=errors,
    )
    sglang_kv_events_evidence = _copy_and_parse_sglang_kv_events_evidence(
        output_dir=output_dir,
        source_file=options.sglang_kv_events_evidence_file,
        artifacts=artifacts,
        sources=sources,
        errors=errors,
    )
    report = build_compat_report(
        engine_text=engine_text,
        lmcache_text=lmcache_text,
        engine_source=sources.get("engine_metrics", ""),
        lmcache_source=sources.get("lmcache_metrics", ""),
        expect_mode=options.expect_mode,
        l2_configured=options.l2_configured,
        mp_observability=options.mp_observability,
        lmcache_http_evidence=http_evidence,
        lmcache_log_evidence=log_evidence,
        lmcache_trace_evidence=trace_evidence,
        lmcache_otel_evidence=otel_evidence,
        lmcache_trace_replay_evidence=trace_replay_evidence,
        lmcache_lookup_hash_evidence=lookup_hash_evidence,
        lmcache_l0_boundary_evidence=l0_boundary_evidence,
    )
    compat_path = output_dir / "lmcache_compat_report.json"
    write_compat_report(report, compat_path)
    artifacts["lmcache_compat_report"] = str(compat_path)

    coverage_report = build_observability_coverage_report(
        engine_text=engine_text,
        lmcache_text=lmcache_text,
        engine_source=sources.get("engine_metrics", ""),
        lmcache_source=sources.get("lmcache_metrics", ""),
        expected_engine=options.expected_engine,
        expect_lmcache_mode=options.expect_mode,
        external_cache_configured=options.external_cache_configured,
        cpu_offload_configured=options.cpu_offload_configured,
        l2_configured=options.l2_configured,
        disaggregated_or_external_cache=options.disaggregated_or_external_cache,
        mp_observability=options.mp_observability,
        lmcache_http_evidence=http_evidence,
        lmcache_log_evidence=log_evidence,
        lmcache_trace_evidence=trace_evidence,
        lmcache_otel_evidence=otel_evidence,
        lmcache_trace_replay_evidence=trace_replay_evidence,
        lmcache_lookup_hash_evidence=lookup_hash_evidence,
        lmcache_l0_boundary_evidence=l0_boundary_evidence,
        sglang_kv_events_evidence=sglang_kv_events_evidence,
    )
    coverage_path = output_dir / "observability_coverage_report.json"
    write_observability_coverage_report(coverage_report, coverage_path)
    artifacts["observability_coverage_report"] = str(coverage_path)

    manifest = {
        "schema_version": PACKET_SCHEMA_VERSION,
        "generated_at": _utc_now_iso(),
        "claim_status": "measured" if engine_text or lmcache_text else "not_proven",
        "expect_mode": options.expect_mode,
        "expected_engine": options.expected_engine,
        "detected_engines": coverage_report.get("detected_engines", []),
        "detected_mode": report.get("detected_mode"),
        "l2_configured": options.l2_configured,
        "coverage_summary": {
            "coverage_gaps": coverage_report.get("coverage_gaps", []),
            "surfaces": coverage_report.get("surfaces", {}),
            "sglang_lmcache_mp_observability": coverage_report.get("sglang_lmcache_mp_observability"),
        },
        "sources": sources,
        "artifacts": artifacts,
        "scrape_errors": errors,
        "skipped_endpoints": skipped_endpoints,
        "compat_summary": {
            "failure_reasons": report.get("failure_reasons", []),
            "upstream_questions": report.get("upstream_questions", []),
            "surfaces": report.get("surfaces", {}),
        },
        "http_evidence": http_evidence,
        "log_evidence": log_evidence,
        "trace_evidence": trace_evidence,
        "otel_evidence": otel_evidence,
        "trace_replay_evidence": trace_replay_evidence,
        "lookup_hash_evidence": lookup_hash_evidence,
        "lmcache_l0_boundary_evidence": l0_boundary_evidence,
        "sglang_kv_events_evidence": sglang_kv_events_evidence,
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
        with urllib.request.urlopen(url, timeout=timeout_seconds) as response:  # noqa: S310  # nosec B310 - operator-supplied local URL.
            text = response.read().decode("utf-8", errors="replace")
    except (OSError, urllib.error.URLError, TimeoutError) as exc:
        _record_error(errors, source_name, url, exc)
        return ""
    atomic_write_text(destination, text)
    artifacts[source_name] = str(destination)
    sources[source_name] = url
    return text


def _capture_optional_http_endpoint(
    *,
    output_dir: Path,
    endpoint_name: str,
    filename: str,
    url: str | None,
    source_file: Path | None,
    timeout_seconds: float,
    artifacts: dict[str, str],
    sources: dict[str, str],
    errors: list[dict[str, str]],
    endpoint_errors: dict[str, str],
) -> str:
    before = len(errors)
    text = _capture_text(
        destination=output_dir / filename,
        source_name=f"lmcache_{endpoint_name}",
        url=url,
        source_file=source_file,
        timeout_seconds=timeout_seconds,
        artifacts=artifacts,
        sources=sources,
        errors=errors,
    )
    if not text and len(errors) > before:
        endpoint_errors[endpoint_name] = errors[-1]["error"]
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


def _copy_path(
    *,
    destination: Path,
    source_name: str,
    source_path: Path | None,
    artifacts: dict[str, str],
    sources: dict[str, str],
    errors: list[dict[str, str]],
) -> Path | None:
    if source_path is None:
        return None
    try:
        if source_path.is_dir():
            if destination.exists():
                shutil.rmtree(destination)
            shutil.copytree(source_path, destination)
        else:
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source_path, destination)
    except OSError as exc:
        _record_error(errors, source_name, str(source_path), exc)
        return None
    artifacts[source_name] = str(destination)
    sources[source_name] = str(source_path)
    return destination


def _copy_and_parse_l0_boundary_evidence(
    *,
    output_dir: Path,
    source_file: Path | None,
    artifacts: dict[str, str],
    sources: dict[str, str],
    errors: list[dict[str, str]],
) -> dict[str, Any] | None:
    if source_file is None:
        return None
    destination = output_dir / "lmcache_l0_boundary_evidence.raw"
    copied = _copy_path(
        destination=destination,
        source_name="lmcache_l0_boundary_evidence",
        source_path=source_file,
        artifacts=artifacts,
        sources=sources,
        errors=errors,
    )
    if copied is None:
        return None
    evidence = _read_l0_boundary_evidence(copied)
    evidence_path = output_dir / "lmcache_l0_boundary_evidence.json"
    atomic_write_json(evidence_path, evidence)
    artifacts["lmcache_l0_boundary_evidence_report"] = str(evidence_path)
    return evidence


def _copy_and_parse_sglang_kv_events_evidence(
    *,
    output_dir: Path,
    source_file: Path | None,
    artifacts: dict[str, str],
    sources: dict[str, str],
    errors: list[dict[str, str]],
) -> dict[str, Any] | None:
    if source_file is None:
        return None
    destination = output_dir / "sglang_kv_events_evidence.raw"
    copied = _copy_path(
        destination=destination,
        source_name="sglang_kv_events_evidence",
        source_path=source_file,
        artifacts=artifacts,
        sources=sources,
        errors=errors,
    )
    if copied is None:
        return None
    evidence = read_sglang_kv_events_evidence(copied)
    evidence_path = output_dir / "sglang_kv_events_evidence.json"
    atomic_write_json(evidence_path, evidence)
    artifacts["sglang_kv_events_evidence_report"] = str(evidence_path)
    return evidence


def _copy_and_parse_optional_evidence(
    *,
    output_dir: Path,
    source_name: str,
    source_path: Path | None,
    artifact_name: str,
    evidence_name: str,
    evidence_filename: str,
    parser_candidates: tuple[tuple[str, str], ...],
    artifacts: dict[str, str],
    sources: dict[str, str],
    errors: list[dict[str, str]],
) -> dict[str, Any] | None:
    if source_path is None:
        return None
    destination = output_dir / source_path.name
    copied_path = _copy_path(
        destination=destination,
        source_name=artifact_name,
        source_path=source_path,
        artifacts=artifacts,
        sources=sources,
        errors=errors,
    )
    if copied_path is None:
        return None
    parser = _resolve_optional_parser(parser_candidates, source_path)
    if parser is None:
        evidence = {
            "schema_version": f"inferguard-{source_name}-evidence/v0",
            "present": True,
            "claim_status": "parser_unavailable",
            "source": str(source_path),
            "artifact": str(copied_path),
            "parser_status": "not_available",
        }
    else:
        try:
            evidence = parser(source_path)
        except Exception as exc:  # noqa: BLE001 - optional lane parser should not break packets
            _record_error(errors, evidence_name, str(source_path), exc)
            evidence = {
                "schema_version": f"inferguard-{source_name}-evidence/v0",
                "present": True,
                "claim_status": "parse_failed",
                "source": str(source_path),
                "artifact": str(copied_path),
                "parser_status": "failed",
                "error": f"{type(exc).__name__}: {exc}",
            }
    evidence_path = output_dir / evidence_filename
    atomic_write_json(evidence_path, evidence)
    artifacts[evidence_name] = str(evidence_path)
    return evidence


def _resolve_optional_parser(
    candidates: tuple[tuple[str, str], ...], source_path: Path
) -> Callable[[Path], dict[str, Any]] | None:
    for module_name, function_name in candidates:
        try:
            module = import_module(module_name)
        except ImportError:
            continue
        parser = getattr(module, function_name, None)
        if callable(parser):
            if function_name.endswith("_dir") and not source_path.is_dir():
                continue
            if function_name.endswith("_file") and source_path.is_dir():
                continue
            if function_name == "parse_lmcache_lookup_hash_jsonl" and source_path.is_dir():
                return lambda path: _parse_lookup_hash_dir_with_parser(parser, path)
            return parser
    return None


def _parse_lookup_hash_dir_with_parser(
    parser: Callable[[Path], dict[str, Any]], directory: Path
) -> dict[str, Any]:
    files = sorted(Path(directory).glob("lookup_hashes_*.jsonl"))
    children = [parser(path) for path in files]
    row_count = sum(int(child.get("row_count") or 0) for child in children)
    malformed_rows = sum(int(child.get("malformed_rows") or 0) for child in children)
    return {
        "schema_version": "inferguard-lmcache-lookup-hash-evidence/v1",
        "present": bool(files),
        "claim_status": "measured" if row_count else "not_proven",
        "source_type": "directory",
        "file_count": len(files),
        "row_count": row_count,
        "malformed_rows": malformed_rows,
        "files": children,
    }


def _skipped_lmcache_endpoints() -> list[dict[str, str]]:
    return [
        {
            "endpoint": "GET /env",
            "reason": "sensitive environment disclosure; collect-lmcache does not fetch it by default",
            "status": "sensitive_skipped",
        },
        {
            "endpoint": "POST /api/clear-cache",
            "reason": "destructive; collect-lmcache records evidence only and does not clear customer caches",
            "status": "destructive_skipped",
        },
        {
            "endpoint": "POST /metrics/reset",
            "reason": "destructive; collect-lmcache records evidence only and does not reset counters",
            "status": "destructive_skipped",
        },
        {
            "endpoint": "quota mutation endpoints",
            "reason": "mutating quota routes are excluded; collect-lmcache only fetches safe GET /api/quota",
            "status": "destructive_skipped",
        },
    ]


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


def _normalize_base_url(url: str | None) -> str | None:
    if not url:
        return None
    return url if url.endswith("/") else f"{url}/"


def _join_base(base_url: str | None, path: str) -> str | None:
    if not base_url or not path:
        return None
    return urljoin(base_url, path.lstrip("/"))

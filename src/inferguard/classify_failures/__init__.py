"""Public entry point for InferGuard failure classification."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from inferguard.classify_failures.patterns import PatternRule, load_patterns
from inferguard.classify_failures.render import render_failure_classification_markdown
from inferguard.classify_failures.types import (
    FAILURE_CLASS_NAMES,
    EvidenceRef,
    FailureClass,
    FailureClassification,
    FailureClassName,
)
from inferguard.io import atomic_write_json

_SUSPICIOUS_WORDS = (
    "error",
    "exception",
    "traceback",
    "panic",
    "failed",
    "failure",
    "fatal",
    "abort",
    "timeout",
)
_MODEL_REQUIRED_KEYS = ("model_type", "hidden_size", "vocab_size")


@dataclass(frozen=True)
class _TextSource:
    path: Path
    rel_path: str
    source_type: str


@dataclass
class _Candidate:
    failure_class: FailureClassName
    confidence: float
    regex_id: str
    claim_status: str
    priority: int
    evidence: list[EvidenceRef] = field(default_factory=list)


def classify(
    job_dir: str | Path,
    *,
    regex_config: str | Path | None = None,
    max_failures: int = 20,
) -> FailureClassification:
    """Classify failures for a job directory or a single failure log."""

    if max_failures <= 0:
        raise ValueError("max_failures must be positive")
    root = Path(job_dir)
    regex_path = Path(regex_config) if regex_config is not None else None
    patterns = load_patterns(regex_path)
    base = root.parent if root.is_file() else root
    sources = _collect_text_sources(root)
    candidates: list[_Candidate] = []

    for source in sources:
        text = _read_text(source.path)
        if not text.strip():
            continue
        candidates.extend(_match_text_source(source, text, patterns))

    if root.is_dir():
        candidates.extend(_classify_healthchecks(root, base))
        candidates.extend(_classify_request_profiles(root, base))
        candidates.extend(_classify_model_configs(root, base))

    xid_evidence = _collect_xid_evidence(root, base) if root.is_dir() else []
    if xid_evidence and not candidates:
        candidates.append(
            _Candidate(
                failure_class="cuda_error",
                confidence=0.55,
                regex_id="dcgm_xid_supporting",
                claim_status="inferred",
                priority=70,
                evidence=list(xid_evidence),
            )
        )

    failures = _rank_failures(candidates, max_failures=max_failures)
    if xid_evidence and failures:
        failures = _attach_supporting_evidence(failures, xid_evidence)

    if not failures:
        unknown = _unknown_evidence(root, sources)
        if unknown is not None:
            failures = (
                FailureClass(
                    rank=1,
                    failure_class="not_enough_evidence",
                    confidence=0.2,
                    evidence=(unknown,),
                    evidence_excerpt=unknown.excerpt,
                    regex_id="unmatched_error_tail",
                    claim_status="not_proven",
                ),
            )
            return FailureClassification(
                job_id=_job_id(root),
                failures=failures,
                top_class="not_enough_evidence",
                claim_status="not_proven",
            )
        return FailureClassification(
            job_id=_job_id(root), failures=(), top_class="none", claim_status="measured"
        )

    top_class = failures[0].failure_class
    claim_status = "not_proven" if top_class == "not_enough_evidence" else failures[0].claim_status
    return FailureClassification(
        job_id=_job_id(root),
        failures=failures,
        top_class=top_class,
        claim_status=claim_status,
    )


def classify_job_failures(job_dir: str | Path) -> FailureClassification:
    """Compatibility alias for the PRD implementation map wording."""

    return classify(job_dir)


def write_failure_classification(
    report: FailureClassification,
    output_dir: str | Path,
    *,
    write_markdown: bool = True,
) -> tuple[Path, ...]:
    """Write JSON and optional markdown artifacts."""

    target = Path(output_dir)
    target.mkdir(parents=True, exist_ok=True)
    json_path = target / "failure_classification.json"
    atomic_write_json(json_path, report.to_dict())
    written = [json_path]
    if write_markdown:
        md_path = target / "failure_classification.md"
        md_path.write_text(render_failure_classification_markdown(report), encoding="utf-8")
        written.append(md_path)
    return tuple(written)


def format_stdout_summary(report: FailureClassification) -> str:
    """Return the locked stdout summary line without a trailing newline."""

    return (
        "inferguard classify-failures: "
        f"failures={len(report.failures)} "
        f"top_class={report.top_class} "
        f"claim={report.claim_status}"
    )


def _collect_text_sources(root: Path) -> list[_TextSource]:
    if root.is_file():
        return [_TextSource(path=root, rel_path=root.name, source_type=_source_type_for_file(root))]
    exact = (
        ("launch/stdout.log", "launch_stdout"),
        ("launch/stderr.log", "launch_stderr"),
        ("preflight/nccl_all_reduce.txt", "nccl"),
        ("preflight/ib_state.txt", "ib_state"),
        ("preflight/nvidia_smi.txt", "nvidia_smi"),
        ("preflight/nvidia_smi_topo.txt", "nvidia_smi_topo"),
    )
    sources: list[_TextSource] = []
    for rel, source_type in exact:
        for path in sorted(root.rglob(rel)):
            sources.append(
                _TextSource(path=path, rel_path=_rel(path, root), source_type=source_type)
            )
    for pattern, source_type in (("slurm-*.out", "slurm_stdout"), ("slurm-*.err", "slurm_stderr")):
        for path in sorted(root.rglob(pattern)):
            sources.append(
                _TextSource(path=path, rel_path=_rel(path, root), source_type=source_type)
            )
    unique: dict[Path, _TextSource] = {}
    for source in sources:
        unique[source.path] = source
    return [unique[path] for path in sorted(unique)]


def _source_type_for_file(path: Path) -> str:
    name = path.name
    if name == "ib_state.txt":
        return "ib_state"
    if name.startswith("slurm-") and name.endswith(".err"):
        return "slurm_stderr"
    if "nccl" in name:
        return "nccl"
    if name.endswith(".out"):
        return "launch_stdout"
    return "launch_stderr"


def _match_text_source(
    source: _TextSource, text: str, patterns: tuple[PatternRule, ...]
) -> list[_Candidate]:
    if source.source_type == "ib_state" and _ib_state_active(text):
        return []
    candidates: list[_Candidate] = []
    compiled = [(rule, rule.compiled()) for rule in patterns]
    for line_no, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue
        for rule, regex in compiled:
            if (
                rule.failure_class == "rdma_inactive"
                and source.source_type == "ib_state"
                and _ib_state_active(text)
            ):
                continue
            if regex.search(line):
                candidates.append(
                    _Candidate(
                        failure_class=rule.failure_class,  # type: ignore[arg-type]
                        confidence=rule.confidence,
                        regex_id=rule.regex_id,
                        claim_status=rule.claim_status,
                        priority=rule.root_cause_priority,
                        evidence=[
                            EvidenceRef(
                                path=source.rel_path,
                                start_line=line_no,
                                end_line=line_no,
                                excerpt=_excerpt(line),
                            )
                        ],
                    )
                )
    if (
        source.source_type == "ib_state"
        and not _ib_state_active(text)
        and _rdma_degraded_text(text)
    ):
        candidates.append(
            _Candidate(
                failure_class="rdma_inactive",
                confidence=0.89,
                regex_id="ib_state_missing_active",
                claim_status="measured",
                priority=80,
                evidence=[
                    EvidenceRef(
                        path=source.rel_path,
                        start_line=1,
                        end_line=max(1, len(text.splitlines())),
                        excerpt=_excerpt(_tail(text)),
                    )
                ],
            )
        )
    return candidates


def _classify_healthchecks(root: Path, base: Path) -> list[_Candidate]:
    candidates: list[_Candidate] = []
    for path in sorted(root.rglob("launch/healthcheck.json")):
        data = _read_json_object(path)
        if not data:
            continue
        status = str(data.get("status") or "").lower()
        ok = data.get("ok")
        if status == "failed" or ok is False:
            reason = (
                data.get("failure_reason")
                or data.get("error")
                or data.get("message")
                or status
                or "failed"
            )
            candidates.append(
                _Candidate(
                    failure_class="endpoint_healthcheck_failure",
                    confidence=0.88,
                    regex_id="healthcheck_status_failed",
                    claim_status="measured",
                    priority=65,
                    evidence=[
                        EvidenceRef(
                            path=_rel(path, base),
                            start_line=1,
                            end_line=1,
                            excerpt=_excerpt(f"healthcheck status failed: {reason}"),
                        )
                    ],
                )
            )
    return candidates


def _classify_request_profiles(root: Path, base: Path) -> list[_Candidate]:
    candidates: list[_Candidate] = []
    for path in sorted(root.rglob("request_profile/requests_profile.jsonl")):
        timeout_count = 0
        connect_count = 0
        unknown_refs: list[EvidenceRef] = []
        for line_no, row in _iter_jsonl(path):
            if not row:
                continue
            error_type = str(row.get("error_type") or "")
            success = row.get("success")
            if error_type == "timeout":
                timeout_count += 1
            elif error_type == "connect_error":
                connect_count += 1
            elif success is False and error_type:
                unknown_refs.append(
                    EvidenceRef(
                        path=_rel(path, base),
                        start_line=line_no,
                        end_line=line_no,
                        excerpt=_excerpt(f"request failure error_type={error_type}"),
                    )
                )
        if timeout_count:
            candidates.append(
                _Candidate(
                    failure_class="client_timeout",
                    confidence=min(0.9, 0.72 + timeout_count * 0.03),
                    regex_id="request_profile_error_type_timeout",
                    claim_status="measured",
                    priority=50,
                    evidence=[
                        EvidenceRef(
                            path=_rel(path, base),
                            start_line=1,
                            end_line=1,
                            excerpt=f"requests_profile timeout rows={timeout_count}",
                        )
                    ],
                )
            )
        if connect_count:
            candidates.append(
                _Candidate(
                    failure_class="endpoint_healthcheck_failure",
                    confidence=min(0.86, 0.7 + connect_count * 0.03),
                    regex_id="request_profile_connect_error",
                    claim_status="measured",
                    priority=65,
                    evidence=[
                        EvidenceRef(
                            path=_rel(path, base),
                            start_line=1,
                            end_line=1,
                            excerpt=f"requests_profile connect_error rows={connect_count}",
                        )
                    ],
                )
            )
        for ref in unknown_refs:
            candidates.append(
                _Candidate(
                    failure_class="not_enough_evidence",
                    confidence=0.2,
                    regex_id="request_profile_unknown_error",
                    claim_status="not_proven",
                    priority=0,
                    evidence=[ref],
                )
            )
    return candidates


def _classify_model_configs(root: Path, base: Path) -> list[_Candidate]:
    candidates: list[_Candidate] = []
    for path in sorted(root.rglob("manifests/model_config_summary.json")):
        data = _read_json_object(path)
        if data is None:
            continue
        missing = data.get("missing_required_keys")
        if isinstance(missing, list):
            missing_keys = [str(key) for key in missing if str(key)]
        else:
            missing_keys = [key for key in _MODEL_REQUIRED_KEYS if key not in data]
        if missing_keys:
            candidates.append(
                _Candidate(
                    failure_class="model_config_mismatch",
                    confidence=0.78,
                    regex_id="model_config_summary_missing_required_key",
                    claim_status="measured",
                    priority=85,
                    evidence=[
                        EvidenceRef(
                            path=_rel(path, base),
                            start_line=1,
                            end_line=1,
                            excerpt=_excerpt(
                                "missing required model config key: "
                                + ", ".join(sorted(missing_keys))
                            ),
                        )
                    ],
                )
            )
    return candidates


def _collect_xid_evidence(root: Path, base: Path) -> list[EvidenceRef]:
    refs: list[EvidenceRef] = []
    for path in sorted(root.rglob("gpu_metrics_timeline.jsonl")):
        for line_no, row in _iter_jsonl(path):
            value = _xid_value(row)
            if value is not None and value > 0:
                refs.append(
                    EvidenceRef(
                        path=_rel(path, base),
                        start_line=line_no,
                        end_line=line_no,
                        excerpt=f"DCGM_FI_DEV_XID_ERRORS={value:g}",
                        label=f"DCGM_FI_DEV_XID_ERRORS={value:g}",
                    )
                )
    return refs


def _xid_value(row: dict[str, Any]) -> float | None:
    candidates = [
        row.get("DCGM_FI_DEV_XID_ERRORS"),
        row.get("dcgm_xid_errors"),
        (row.get("metrics") or {}).get("DCGM_FI_DEV_XID_ERRORS")
        if isinstance(row.get("metrics"), dict)
        else None,
        (row.get("metrics") or {}).get("dcgm_xid_errors")
        if isinstance(row.get("metrics"), dict)
        else None,
        (row.get("fields") or {}).get("DCGM_FI_DEV_XID_ERRORS")
        if isinstance(row.get("fields"), dict)
        else None,
    ]
    for candidate in candidates:
        try:
            value = float(candidate)
        except (TypeError, ValueError):
            continue
        if math.isfinite(value):
            return value
    return None


def _rank_failures(candidates: list[_Candidate], *, max_failures: int) -> tuple[FailureClass, ...]:
    buckets: dict[str, _Candidate] = {}
    for candidate in candidates:
        if candidate.failure_class not in FAILURE_CLASS_NAMES:
            continue
        bucket = buckets.get(candidate.failure_class)
        if bucket is None:
            buckets[candidate.failure_class] = _Candidate(
                failure_class=candidate.failure_class,
                confidence=candidate.confidence,
                regex_id=candidate.regex_id,
                claim_status=candidate.claim_status,
                priority=candidate.priority,
                evidence=list(candidate.evidence),
            )
            continue
        bucket.confidence = max(bucket.confidence, candidate.confidence)
        bucket.priority = max(bucket.priority, candidate.priority)
        if candidate.regex_id not in bucket.regex_id.split("+"):
            bucket.regex_id = "+".join(filter(None, (bucket.regex_id, candidate.regex_id)))
        if bucket.claim_status != "measured" and candidate.claim_status == "measured":
            bucket.claim_status = "measured"
        bucket.evidence.extend(candidate.evidence)

    ranked = sorted(
        buckets.values(),
        key=lambda item: (
            -_aggregate_confidence(item.confidence, len(item.evidence)),
            -item.priority,
            item.failure_class,
        ),
    )
    failures: list[FailureClass] = []
    for rank, item in enumerate(ranked[:max_failures], start=1):
        evidence = tuple(item.evidence)
        failures.append(
            FailureClass(
                rank=rank,
                failure_class=item.failure_class,
                confidence=_aggregate_confidence(item.confidence, len(evidence)),
                evidence=evidence,
                evidence_excerpt=_combined_excerpt(evidence),
                regex_id=item.regex_id,
                claim_status=item.claim_status,  # type: ignore[arg-type]
            )
        )
    return tuple(failures)


def _attach_supporting_evidence(
    failures: tuple[FailureClass, ...],
    evidence: list[EvidenceRef],
) -> tuple[FailureClass, ...]:
    if not failures:
        return failures
    top = failures[0]
    updated_top = FailureClass(
        rank=top.rank,
        failure_class=top.failure_class,
        confidence=top.confidence,
        evidence=tuple([*top.evidence, *evidence]),
        evidence_excerpt=top.evidence_excerpt or _combined_excerpt(evidence),
        regex_id=top.regex_id,
        claim_status=top.claim_status,
    )
    return tuple([updated_top, *failures[1:]])


def _unknown_evidence(root: Path, sources: list[_TextSource]) -> EvidenceRef | None:
    for source in sources:
        text = _read_text(source.path)
        if not text.strip():
            continue
        if (
            root.is_file()
            or source.source_type in {"launch_stderr", "slurm_stderr"}
            or _has_suspicious_word(text)
        ):
            lines = [line for line in text.splitlines() if line.strip()]
            tail_lines = lines[-5:] if lines else [text.strip()]
            start_line = max(1, len(lines) - len(tail_lines) + 1)
            return EvidenceRef(
                path=source.rel_path,
                start_line=start_line,
                end_line=start_line + len(tail_lines) - 1,
                excerpt=_excerpt("\n".join(tail_lines), max_chars=320),
            )
    return None


def _aggregate_confidence(confidence: float, evidence_count: int) -> float:
    return min(0.99, confidence + max(0, evidence_count - 1) * 0.03)


def _combined_excerpt(evidence: tuple[EvidenceRef, ...] | list[EvidenceRef]) -> str:
    excerpts = [ref.excerpt for ref in evidence if ref.excerpt]
    return _excerpt(" | ".join(excerpts), max_chars=320)


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def _read_json_object(path: Path) -> dict[str, Any] | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def _iter_jsonl(path: Path) -> list[tuple[int, dict[str, Any]]]:
    rows: list[tuple[int, dict[str, Any]]] = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return rows
    for line_no, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        try:
            data = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict):
            rows.append((line_no, data))
    return rows


def _ib_state_active(text: str) -> bool:
    return "State: Active" in text


def _rdma_degraded_text(text: str) -> bool:
    lowered = text.lower()
    return any(
        token in lowered
        for token in (
            "state: down",
            "physical state: polling",
            "physical state: disabled",
            "port_down",
            "disabled",
        )
    )


def _has_suspicious_word(text: str) -> bool:
    lowered = text.lower()
    return any(word in lowered for word in _SUSPICIOUS_WORDS)


def _tail(text: str) -> str:
    lines = [line for line in text.splitlines() if line.strip()]
    return "\n".join(lines[-5:]) if lines else text.strip()


def _excerpt(text: str, *, max_chars: int = 240) -> str:
    collapsed = " ".join(text.strip().split())
    if len(collapsed) <= max_chars:
        return collapsed
    return collapsed[: max_chars - 1].rstrip() + "…"


def _rel(path: Path, base: Path) -> str:
    try:
        return path.relative_to(base).as_posix()
    except ValueError:
        return path.as_posix()


def _job_id(root: Path) -> str:
    if root.is_file():
        return root.stem
    if root.name:
        return root.name
    return str(root)


__all__ = [
    "FailureClass",
    "FailureClassification",
    "classify",
    "classify_job_failures",
    "format_stdout_summary",
    "render_failure_classification_markdown",
    "write_failure_classification",
]

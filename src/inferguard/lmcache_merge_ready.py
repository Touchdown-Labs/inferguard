"""Merge-readiness summary for LMCache/vLLM/SGLang observability packet work."""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "inferguard-lmcache-merge-ready/v1"


@dataclass(frozen=True)
class RepoSpec:
    """Repository label/path pair included in a merge-readiness report."""

    name: str
    path: Path


def build_lmcache_merge_ready_report(
    *,
    packet_b_dir: Path | None = None,
    packet_c_dir: Path | None = None,
    repos: list[RepoSpec] | None = None,
    require_cacheblend: bool = True,
) -> dict[str, Any]:
    """Build a local, machine-readable merge-readiness report.

    The report intentionally separates measured packet evidence from repository
    state so the final merge decision can explain both runtime proof and git
    blockers without re-running expensive H100 jobs.
    """

    packet_b = _summarize_packet_b(packet_b_dir) if packet_b_dir else _missing_packet("packet_b")
    packet_c = _summarize_packet_c(packet_c_dir) if packet_c_dir else _missing_packet("packet_c")
    repo_reports = {spec.name: summarize_git_repo(spec.path) for spec in repos or []}
    blockers = _build_blockers(
        packet_b=packet_b,
        packet_c=packet_c,
        repos=repo_reports,
        require_cacheblend=require_cacheblend,
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "merge_ready": not blockers,
        "packets": {
            "packet_b": packet_b,
            "packet_c": packet_c,
        },
        "repos": repo_reports,
        "blockers": blockers,
        "commands": _suggested_commands(packet_b_dir=packet_b_dir, packet_c_dir=packet_c_dir),
    }


def write_lmcache_merge_ready_report(report: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def parse_repo_specs(values: list[str]) -> list[RepoSpec]:
    specs: list[RepoSpec] = []
    for value in values:
        if "=" in value:
            name, raw_path = value.split("=", 1)
        else:
            raw_path = value
            name = Path(value).name or value
        name = name.strip()
        if not name:
            raise ValueError(f"invalid repo spec {value!r}: empty name")
        specs.append(RepoSpec(name=name, path=Path(raw_path).expanduser()))
    return specs


def summarize_git_repo(path: Path) -> dict[str, Any]:
    path = Path(path)
    exists = path.exists()
    is_git = exists and (path / ".git").exists()
    report: dict[str, Any] = {
        "path": str(path),
        "exists": exists,
        "is_git_repo": is_git,
        "branch": None,
        "dirty": None,
        "head": None,
        "upstream": None,
        "ahead": None,
        "behind": None,
        "error": None,
    }
    if not exists:
        report["error"] = "path_missing"
        return report
    if not is_git:
        report["error"] = "not_git_repo"
        return report

    def git(args: list[str]) -> tuple[int, str]:
        proc = subprocess.run(
            ["git", *args],
            cwd=path,
            check=False,
            capture_output=True,
            text=True,
        )
        output = (proc.stdout or proc.stderr).strip()
        return proc.returncode, output

    code, branch = git(["branch", "--show-current"])
    report["branch"] = branch if code == 0 and branch else None
    code, head = git(["rev-parse", "--short", "HEAD"])
    report["head"] = head if code == 0 else None
    code, status = git(["status", "--porcelain"])
    report["dirty"] = bool(status) if code == 0 else None
    code, upstream = git(["rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"])
    upstream_ref = "@{u}" if code == 0 and upstream else None
    if upstream_ref is None:
        upstream = _fallback_upstream_ref(path, report["branch"])
        upstream_ref = upstream
    if upstream_ref and upstream:
        report["upstream"] = upstream
        code, counts = git(["rev-list", "--left-right", "--count", f"HEAD...{upstream_ref}"])
        if code == 0:
            parts = counts.split()
            if len(parts) == 2:
                report["ahead"] = int(parts[0])
                report["behind"] = int(parts[1])
    return report


def _fallback_upstream_ref(path: Path, branch: Any) -> str | None:
    candidates = []
    if branch:
        candidates.append(f"upstream/{branch}")
    candidates.extend(["upstream/dev", "upstream/main"])
    if branch:
        candidates.append(f"origin/{branch}")
    candidates.extend(["origin/dev", "origin/main"])
    for candidate in candidates:
        proc = subprocess.run(
            ["git", "rev-parse", "--verify", "--quiet", candidate],
            cwd=path,
            check=False,
            capture_output=True,
            text=True,
        )
        if proc.returncode == 0:
            return candidate
    return None


def _summarize_packet_b(path: Path) -> dict[str, Any]:
    root = _resolve_packet_root(path)
    compat = _read_json_optional(root / "lmcache_compat_report.json") or _read_json_optional(
        root / "lmcache-packet" / "lmcache_compat_report.json"
    )
    lifecycle = _read_json_optional(root / "packet-b-lifecycle-evidence.json") or {}
    workload = _read_json_optional(root / "workload_manifest.json") or {}
    kv_report = _read_json_optional(root / "agent_kv_offload_report.json") or {}
    coverage = _read_json_optional(root / "observability_coverage.json") or {}
    cacheblend_boundary_evidence = _read_json_optional(
        root / "lmcache_cacheblend_boundary_evidence.json"
    ) or _read_json_optional(root / "lmcache-packet" / "lmcache_cacheblend_boundary_evidence.json")
    metrics = _read_text_optional(root / "lmcache_metrics_loaded.prom") or _read_text_optional(
        root / "lmcache-packet" / "lmcache_metrics.prom"
    )
    lmcache_command = _read_json_optional(root / "lmcache_command.json")
    vllm_command = _read_json_optional(root / "vllm_command.json")
    lmcache_env = _read_json_optional(root / "lmcache_env.json") or {}
    failure_reasons = list((compat or {}).get("failure_reasons") or [])
    l1_failures = _metric_value(metrics, "lmcache_mp_l1_failures")
    if l1_failures is None:
        l1_failures = _compat_l1_failure_total(compat or {}, kv_report)
    cacheblend_measured = _cacheblend_measured(metrics, coverage, cacheblend_boundary_evidence)
    lifecycle_families = _lifecycle_family_statuses(lifecycle, coverage)
    diagnosis_raw = kv_report.get("diagnosis")
    kv_diagnosis = diagnosis_raw if isinstance(diagnosis_raw, dict) else {}
    status = (
        "measured"
        if _is_measured(lifecycle.get("claim_status") or lifecycle.get("acceptance_status"))
        else "missing"
    )
    return {
        "path": str(root),
        "exists": root.exists(),
        "status": status,
        "claim_status": lifecycle.get("claim_status"),
        "acceptance_status": lifecycle.get("acceptance_status"),
        "kv_offload_claim_status": kv_report.get("claim_status")
        or kv_diagnosis.get("claim_status"),
        "compat_failure_count": len(failure_reasons),
        "compat_failure_reasons": failure_reasons,
        "workload_request_count": workload.get("request_count") or workload.get("total_requests"),
        "workload_profile": workload.get("profile") or workload.get("workload_profile"),
        "families": lifecycle_families,
        "metric_family_counts": {
            "l0": _count_metric_names(metrics, "lmcache_mp_l0_"),
            "l1": _count_metric_names(metrics, "lmcache_mp_l1_"),
            "lookup_reuse": _count_metric_names(metrics, "lmcache_mp_lookup_"),
            "cacheblend": _count_cacheblend_metric_names(metrics),
        },
        "l1_failures": l1_failures,
        "cacheblend_measured": cacheblend_measured,
        "cacheblend_boundary_evidence": _cacheblend_boundary_evidence_summary(
            cacheblend_boundary_evidence
        ),
        "config": {
            "lmcache_command": lmcache_command,
            "vllm_kv_transfer_config": _vllm_kv_transfer_config(vllm_command),
            "lmcache_env": lmcache_env,
        },
    }


def _summarize_packet_c(path: Path) -> dict[str, Any]:
    root = _resolve_packet_root(path)
    compat = _read_json_optional(root / "lmcache_compat_report.json") or _read_json_optional(
        root / "lmcache-packet" / "lmcache_compat_report.json"
    )
    coverage = _read_json_optional(root / "observability_coverage.json") or {}
    l2_config = _read_json_optional(root / "lmcache_l2_config.json") or {}
    conf = _read_json_optional(root / "http" / "conf.json") or {}
    lmcache_command = _read_json_optional(root / "lmcache_command.json")
    lmcache_env = _read_json_optional(root / "lmcache_env.json") or {}
    metrics = _read_text_optional(root / "lmcache_metrics_loaded.prom") or _read_text_optional(
        root / "lmcache-packet" / "lmcache_metrics.prom"
    )
    failure_reasons = list((compat or {}).get("failure_reasons") or [])
    l2_files = list(root.rglob("*.data")) if root.exists() else []
    l2_bytes = sum(item.stat().st_size for item in l2_files if item.is_file())
    l2_metric_count = _count_metric_names(metrics, "lmcache_mp_l2_")
    l2_configured = _l2_configured(l2_config, conf)
    status = (
        "measured" if not failure_reasons and l2_configured and l2_metric_count > 0 else "missing"
    )
    return {
        "path": str(root),
        "exists": root.exists(),
        "status": status,
        "l2_configured": l2_configured,
        "l2_cli_argument": l2_config.get("cli_argument"),
        "l2_data_file_count": len(l2_files),
        "l2_data_bytes": l2_bytes,
        "l2_metric_family_count": l2_metric_count,
        "metric_family_counts": {
            "l2": l2_metric_count,
            "l0": _count_metric_names(metrics, "lmcache_mp_l0_"),
            "l1": _count_metric_names(metrics, "lmcache_mp_l1_"),
        },
        "config": {
            "lmcache_command": lmcache_command,
            "lmcache_env": lmcache_env,
            "l2_config": l2_config,
            "http_conf_l2_adapter_config": _http_conf_l2_adapter_config(conf),
            "http_conf_observability": _http_conf_observability(conf),
        },
        "compat_failure_count": len(failure_reasons),
        "compat_failure_reasons": failure_reasons,
        "coverage_gap_count": len(coverage.get("coverage_gaps") or []),
    }


def _build_blockers(
    *,
    packet_b: dict[str, Any],
    packet_c: dict[str, Any],
    repos: dict[str, dict[str, Any]],
    require_cacheblend: bool,
) -> list[dict[str, Any]]:
    blockers: list[dict[str, Any]] = []
    if packet_b.get("status") != "measured":
        blockers.append(
            {
                "code": "packet_b_not_measured",
                "severity": "blocking",
                "detail": packet_b.get("path"),
            }
        )
    if packet_c.get("status") != "measured":
        blockers.append(
            {
                "code": "packet_c_l2_not_measured",
                "severity": "blocking",
                "detail": packet_c.get("path"),
            }
        )
    if require_cacheblend and not packet_b.get("cacheblend_measured"):
        blockers.append(
            {
                "code": "cacheblend_not_measured",
                "severity": "blocking",
                "detail": "no CacheBlend metric/evidence found in Packet B",
            }
        )
    if (packet_b.get("l1_failures") or 0) > 0:
        blockers.append(
            {
                "code": "lmcache_mp_l1_failures_observed",
                "severity": "diagnostic",
                "detail": packet_b.get("l1_failures"),
            }
        )
    for name, repo in repos.items():
        if repo.get("error"):
            blockers.append(
                {
                    "code": "repo_unavailable",
                    "severity": "blocking",
                    "repo": name,
                    "detail": repo.get("error"),
                }
            )
        if repo.get("dirty"):
            blockers.append(
                {
                    "code": "repo_dirty",
                    "severity": "blocking",
                    "repo": name,
                    "detail": repo.get("path"),
                }
            )
        if repo.get("behind"):
            blockers.append(
                {
                    "code": "repo_behind_upstream",
                    "severity": "blocking",
                    "repo": name,
                    "detail": repo.get("behind"),
                }
            )
    return blockers


def _suggested_commands(
    *, packet_b_dir: Path | None, packet_c_dir: Path | None
) -> dict[str, list[str]]:
    commands: dict[str, list[str]] = {
        "verify": [],
        "format": [
            "python -m ruff format src/inferguard/compat.py tests/test_observability_coverage.py scripts/lmcache_mp_modal_packet_lab.py tests/test_lmcache_mp_modal_packet_lab.py"
        ],
    }
    if packet_b_dir:
        commands["verify"].append(
            f"inferguard lmcache-merge-ready --packet-b-dir {packet_b_dir} --json"
        )
    if packet_c_dir:
        commands["verify"].append(
            f"inferguard lmcache-merge-ready --packet-c-dir {packet_c_dir} --json"
        )
    return commands


def _missing_packet(name: str) -> dict[str, Any]:
    return {"path": None, "exists": False, "status": "missing", "packet": name}


def _resolve_packet_root(path: Path) -> Path:
    path = Path(path)
    if (path / "lmcache_compat_report.json").exists() or (path / "lmcache-packet").exists():
        return path
    children = [item for item in path.iterdir()] if path.exists() and path.is_dir() else []
    json_children = [
        item
        for item in children
        if item.is_dir()
        and ((item / "lmcache_compat_report.json").exists() or (item / "lmcache-packet").exists())
    ]
    if len(json_children) == 1:
        return json_children[0]
    return path


def _read_json_optional(path: Path) -> dict[str, Any] | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return None


def _read_text_optional(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return None


def _is_measured(value: Any) -> bool:
    return str(value or "").startswith(("measured", "candidate_measured"))


def _cacheblend_measured(
    metrics: str | None,
    coverage: dict[str, Any],
    boundary_evidence: dict[str, Any] | None = None,
) -> bool:
    if metrics and ("lmcache_blend_" in metrics or "lmcache_cacheblend" in metrics):
        return True
    if boundary_evidence and _is_measured(boundary_evidence.get("claim_status")):
        return True
    for row in coverage.get("families") or []:
        family = str(row.get("family") or "")
        if "cacheblend" in family and row.get("status") == "populated":
            return True
    return False


def _cacheblend_boundary_evidence_summary(
    boundary_evidence: dict[str, Any] | None,
) -> dict[str, Any]:
    if not boundary_evidence:
        return {"present": False, "claim_status": None, "row_count": 0}
    return {
        "present": bool(boundary_evidence.get("present")),
        "claim_status": boundary_evidence.get("claim_status"),
        "row_count": boundary_evidence.get("row_count") or 0,
        "stages": boundary_evidence.get("stages") or [],
        "event_counts": boundary_evidence.get("event_counts") or {},
    }


def _lifecycle_family_statuses(
    lifecycle: dict[str, Any], coverage: dict[str, Any]
) -> dict[str, Any]:
    families = lifecycle.get("families")
    if isinstance(families, dict):
        return families
    result: dict[str, Any] = {}
    for row in coverage.get("families") or []:
        if row.get("surface") == "lmcache_mp":
            result[str(row.get("family"))] = {"status": row.get("status")}
    return result


def _l2_configured(l2_config: dict[str, Any], conf: dict[str, Any]) -> bool:
    if l2_config.get("cli_argument"):
        return True
    adapter_config = _http_conf_l2_adapter_config(conf)
    if isinstance(adapter_config, dict):
        adapters = adapter_config.get("adapters")
        return bool(adapters)
    return False


def _metric_value(metrics: str | None, metric_name: str) -> float | None:
    if not metrics:
        return None
    total = 0.0
    found = False
    for raw_line in metrics.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or not line.startswith(metric_name):
            continue
        parts = line.split()
        if not parts:
            continue
        try:
            total += float(parts[-1])
            found = True
        except ValueError:
            continue
    return total if found else None


def _compat_l1_failure_total(compat: dict[str, Any], kv_report: dict[str, Any]) -> float | None:
    findings = list(compat.get("diagnostic_findings") or [])
    if not findings:
        diagnosis = kv_report.get("diagnosis")
        if isinstance(diagnosis, dict):
            findings.extend(diagnosis.get("compat_diagnostic_findings") or [])
    total = 0.0
    found = False
    for finding in findings:
        if not isinstance(finding, dict) or finding.get("code") != "lmcache_mp_l1_failures":
            continue
        metrics = finding.get("metrics")
        if not isinstance(metrics, dict):
            continue
        for key, value in metrics.items():
            if key.startswith("lmcache_mp_l1_") and key.endswith("_failure_total"):
                try:
                    total += float(value)
                    found = True
                except (TypeError, ValueError):
                    continue
    return total if found else None


def _count_metric_names(metrics: str | None, prefix: str) -> int:
    if not metrics:
        return 0
    names: set[str] = set()
    for raw_line in metrics.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        name = line.split(maxsplit=1)[0].split("{", 1)[0]
        if name.startswith(prefix):
            names.add(name)
    return len(names)


def _count_cacheblend_metric_names(metrics: str | None) -> int:
    if not metrics:
        return 0
    names: set[str] = set()
    for raw_line in metrics.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        name = line.split(maxsplit=1)[0].split("{", 1)[0]
        if "cacheblend" in name or name.startswith("lmcache_blend_"):
            names.add(name)
    return len(names)


def _vllm_kv_transfer_config(command: Any) -> dict[str, Any] | None:
    if not isinstance(command, list):
        return None
    for idx, item in enumerate(command):
        if item != "--kv-transfer-config" or idx + 1 >= len(command):
            continue
        raw_value = command[idx + 1]
        if not isinstance(raw_value, str):
            return None
        try:
            parsed = json.loads(raw_value)
        except json.JSONDecodeError:
            return {"raw": raw_value}
        return parsed if isinstance(parsed, dict) else {"raw": parsed}
    return None


def _http_conf_l2_adapter_config(conf: dict[str, Any]) -> dict[str, Any] | None:
    storage_manager = conf.get("storage_manager") if isinstance(conf, dict) else None
    if isinstance(storage_manager, dict):
        adapter_config = storage_manager.get("l2_adapter_config")
        return adapter_config if isinstance(adapter_config, dict) else None
    adapter_config = conf.get("l2_adapter_config") if isinstance(conf, dict) else None
    return adapter_config if isinstance(adapter_config, dict) else None


def _http_conf_observability(conf: dict[str, Any]) -> dict[str, Any] | None:
    observability = conf.get("observability") if isinstance(conf, dict) else None
    return observability if isinstance(observability, dict) else None

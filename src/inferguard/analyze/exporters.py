"""AgentX/InferenceX-shaped exports for InferGuard analyze reports."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from inferguard.io import atomic_write_json

RLM_TRACE_SCHEMA_VERSION = "inferguard-rlm-trace/v1"

BASE_KEYS = [
    "hw",
    "conc",
    "image",
    "model",
    "infmax_model_prefix",
    "framework",
    "precision",
    "spec_decoding",
    "disagg",
    "scenario_type",
    "is_multinode",
    "tp",
    "ep",
    "dp_attention",
    "offloading",
    "num_requests_total",
    "num_requests_successful",
    "mean_qps",
    "median_qps",
    "p90_qps",
    "p99_qps",
    "p99.9_qps",
    "std_qps",
    "mean_ttft",
    "median_ttft",
    "p90_ttft",
    "p99_ttft",
    "p99.9_ttft",
    "std_ttft",
    "mean_e2el",
    "median_e2el",
    "p90_e2el",
    "p99_e2el",
    "p99.9_e2el",
    "std_e2el",
    "mean_itl",
    "median_itl",
    "p90_itl",
    "p99_itl",
    "p99.9_itl",
    "std_itl",
    "mean_tpot",
    "median_tpot",
    "p90_tpot",
    "p99_tpot",
    "p99.9_tpot",
    "std_tpot",
    "mean_intvty",
    "median_intvty",
    "p90_intvty",
    "p99_intvty",
    "p99.9_intvty",
    "std_intvty",
    "mean_input_tokens",
    "median_input_tokens",
    "p90_input_tokens",
    "p99_input_tokens",
    "p99.9_input_tokens",
    "std_input_tokens",
    "mean_output_tokens_actual",
    "median_output_tokens_actual",
    "p90_output_tokens_actual",
    "p99_output_tokens_actual",
    "p99.9_output_tokens_actual",
    "std_output_tokens_actual",
    "input_tput_tps",
    "output_tput_tps",
    "total_tput_tps",
    "duration_seconds",
    "tput_per_gpu",
    "output_tput_per_gpu",
    "input_tput_per_gpu",
]

MULTINODE_KEYS = [
    "prefill_num_workers",
    "prefill_tp",
    "prefill_ep",
    "prefill_dp_attention",
    "num_prefill_gpu",
    "decode_num_workers",
    "decode_tp",
    "decode_ep",
    "decode_dp_attention",
    "num_decode_gpu",
]


def emit_agentx_shape(report: dict, output_dir: Path) -> list[Path]:
    """Write per-cell agg_*.json files in the AgentX/InferenceX upstream shape.

    For each cell in the report, produces output_dir/agg_<cell_id>.json
    matching the schema in process_agentic_result.py.

    Returns the list of paths written.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for cell in report.get("cells", []):
        cell_id = str(cell.get("cell_id") or "cell")
        payload = _cell_payload(cell)
        path = output_dir / f"agg_{_safe_filename(cell_id)}.json"
        atomic_write_json(path, payload)
        written.append(path)
    return written


def emit_rlm_trace(report: dict[str, Any], path: Path) -> Path:
    """Write an OTel-shaped JSONL trace for downstream RLM/HALO analysis."""
    path.parent.mkdir(parents=True, exist_ok=True)
    trace_id = _hex_id("trace", report, length=32)
    root_span_id = _hex_id("root", report, length=16)
    rows = [_root_rlm_span(report, trace_id, root_span_id)]

    for cell in report.get("cells", []) or []:
        cell_id = str(cell.get("cell_id") or "cell")
        rows.append(_cell_rlm_span(cell, trace_id, root_span_id, cell_id))
        for index, finding in enumerate(cell.get("findings", []) or []):
            rows.append(_finding_rlm_span(finding, trace_id, root_span_id, cell_id, index))

    for index, finding in enumerate(report.get("findings", []) or []):
        if finding.get("cell_id"):
            continue
        rows.append(_finding_rlm_span(finding, trace_id, root_span_id, None, index))

    path.write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows), encoding="utf-8"
    )
    return path


def _cell_payload(cell: dict[str, Any]) -> dict[str, Any]:
    metrics = cell.get("metrics") or {}
    completion = cell.get("completion") or {}
    topology = cell.get("topology") or {}
    is_multinode = _boolish(
        cell.get("is_multinode")
        if cell.get("is_multinode") is not None
        else topology.get("is_multinode")
    )
    out = {key: None for key in BASE_KEYS}
    out.update(
        {
            "_schema_version": "inferguard-agentx-export/v1",
            "hw": _first(cell.get("hardware"), topology.get("hw"), topology.get("runner_type")),
            "conc": cell.get("concurrency"),
            "image": _first(cell.get("image"), topology.get("image")),
            "model": cell.get("model"),
            "infmax_model_prefix": _first(
                cell.get("infmax_model_prefix"), topology.get("model_prefix")
            ),
            "framework": _first(cell.get("framework"), topology.get("framework")),
            "precision": _first(cell.get("precision"), topology.get("precision")),
            "spec_decoding": _first(topology.get("spec_decoding"), "none"),
            "disagg": bool(cell.get("disagg") or is_multinode),
            "scenario_type": _first(
                cell.get("scenario_type"), metrics.get("workload_class"), "agentic-coding"
            ),
            "is_multinode": is_multinode,
            "tp": _intish(_first(topology.get("tp"), metrics.get("tp"))),
            "ep": _intish(_first(topology.get("ep"), topology.get("ep_size"), metrics.get("ep"))),
            "dp_attention": _first(topology.get("dp_attention"), metrics.get("dp_attention")),
            "offloading": _first(topology.get("offloading"), "none"),
            "num_requests_total": completion.get("num_requests_total"),
            "num_requests_successful": completion.get("num_requests_successful"),
        }
    )
    for key in BASE_KEYS:
        if key in metrics:
            out[key] = metrics[key]
    if is_multinode:
        for key in MULTINODE_KEYS:
            if key == "prefill_dp_attention":
                out[key] = _first(
                    topology.get("prefill_dp_attention"), topology.get("prefill_dp_attn")
                )
            elif key == "decode_dp_attention":
                out[key] = _first(
                    topology.get("decode_dp_attention"), topology.get("decode_dp_attn")
                )
            else:
                out[key] = _intish(topology.get(key))
        if out.get("num_prefill_gpu") is None:
            out["num_prefill_gpu"] = _mul(out.get("prefill_num_workers"), out.get("prefill_tp"))
        if out.get("num_decode_gpu") is None:
            out["num_decode_gpu"] = _mul(out.get("decode_num_workers"), out.get("decode_tp"))
    return out


def _root_rlm_span(report: dict[str, Any], trace_id: str, span_id: str) -> dict[str, Any]:
    return {
        "trace_id": trace_id,
        "span_id": span_id,
        "parent_span_id": None,
        "name": "inferguard.analysis",
        "kind": "SPAN_KIND_INTERNAL",
        "status": {"code": _status_code(report.get("run_summary", {}).get("status"))},
        "scope": {"name": "inferguard.rlm_exporter", "version": RLM_TRACE_SCHEMA_VERSION},
        "resource": {
            "attributes": {
                "service.name": "inferguard",
                "service.version": report.get("analyzer", {}).get("inferguard_version"),
            }
        },
        "attributes": {
            "inferguard.schema_version": RLM_TRACE_SCHEMA_VERSION,
            "inferguard.report_schema_version": report.get("schema_version"),
            "inferguard.generated_at": report.get("generated_at"),
            "inferguard.input_root": report.get("input_root"),
            "inferguard.run_summary": report.get("run_summary", {}),
            "inferguard.cross_run": report.get("cross_run", {}),
        },
    }


def _cell_rlm_span(
    cell: dict[str, Any],
    trace_id: str,
    parent_span_id: str,
    cell_id: str,
) -> dict[str, Any]:
    status = cell.get("completion", {}).get("status")
    return {
        "trace_id": trace_id,
        "span_id": _hex_id("cell", cell_id, cell, length=16),
        "parent_span_id": parent_span_id,
        "name": f"inferguard.cell.{cell_id}",
        "kind": "SPAN_KIND_INTERNAL",
        "status": {"code": _status_code(status)},
        "scope": {"name": "inferguard.rlm_exporter", "version": RLM_TRACE_SCHEMA_VERSION},
        "attributes": {
            "inferguard.cell_id": cell_id,
            "inferguard.source_format": cell.get("source_format"),
            "inferguard.hardware": cell.get("hardware"),
            "inferguard.model": cell.get("model"),
            "inferguard.framework": cell.get("framework"),
            "inferguard.precision": cell.get("precision"),
            "inferguard.scenario_type": cell.get("scenario_type"),
            "inferguard.concurrency": cell.get("concurrency"),
            "inferguard.completion": cell.get("completion", {}),
            "inferguard.metrics": cell.get("metrics", {}),
            "inferguard.topology": cell.get("topology", {}),
            "inferguard.artifacts": cell.get("artifacts", {}),
        },
    }


def _finding_rlm_span(
    finding: dict[str, Any],
    trace_id: str,
    parent_span_id: str,
    cell_id: str | None,
    index: int,
) -> dict[str, Any]:
    code = str(finding.get("code") or "unknown")
    severity = str(finding.get("severity") or "").lower()
    return {
        "trace_id": trace_id,
        "span_id": _hex_id("finding", cell_id or "cross-run", index, finding, length=16),
        "parent_span_id": parent_span_id,
        "name": f"inferguard.finding.{code}",
        "kind": "SPAN_KIND_INTERNAL",
        "status": {
            "code": "STATUS_CODE_ERROR" if severity in {"critical", "error"} else "STATUS_CODE_OK"
        },
        "scope": {"name": "inferguard.rlm_exporter", "version": RLM_TRACE_SCHEMA_VERSION},
        "attributes": {
            "inferguard.cell_id": cell_id,
            "inferguard.finding_code": code,
            "inferguard.severity": finding.get("severity"),
            "inferguard.message": finding.get("message"),
            "inferguard.finding": finding,
        },
    }


def _status_code(status: Any) -> str:
    if str(status).lower() in {"failed", "error", "critical"}:
        return "STATUS_CODE_ERROR"
    return "STATUS_CODE_OK"


def _hex_id(*parts: Any, length: int) -> str:
    data = json.dumps(parts, sort_keys=True, default=str)
    return hashlib.sha256(data.encode("utf-8")).hexdigest()[:length]


def _safe_filename(value: str) -> str:
    return "".join(ch if ch.isalnum() or ch in {"-", "_", "."} else "_" for ch in value)


def _first(*values: Any) -> Any:
    for value in values:
        if value not in (None, ""):
            return value
    return None


def _boolish(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


def _intish(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _mul(left: Any, right: Any) -> int | None:
    lval = _intish(left)
    rval = _intish(right)
    if lval is None or rval is None:
        return None
    return lval * rval

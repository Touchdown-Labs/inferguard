"""Slurm-first deployment bundle emitter."""

from __future__ import annotations

import csv
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from inferguard.io import atomic_write_json
from inferguard.router.verdict import RouterVerdict

BUNDLE_SCHEMA_VERSION = "inferguard-deployment-bundle/v1"


class BundleEmitError(RuntimeError):
    """Raised when a bundle cannot be emitted."""


def emit_bundle(verdict_path: Path, output_dir: Path, *, target: str = "slurm") -> dict[str, Any]:
    if target != "slurm":
        raise BundleEmitError("--target currently supports only slurm")
    verdict = RouterVerdict.model_validate(json.loads(verdict_path.read_text(encoding="utf-8")))
    output_dir.mkdir(parents=True, exist_ok=True)
    slurm_dir = output_dir / "slurm"
    slurm_dir.mkdir(exist_ok=True)
    paths = [
        _write_json(output_dir / "verdict.json", verdict.as_dict()),
        _write_text(slurm_dir / "run_recommended_path.sbatch", _render_sbatch(verdict)),
        _write_text(output_dir / "prometheus-rules.yaml", _render_prometheus(verdict)),
        _write_cost_floor(output_dir / "cost-floor.csv", verdict),
        _write_text(output_dir / "RUNBOOK.md", _render_runbook(verdict)),
        _write_json(output_dir / "meta.json", _meta(verdict, target)),
    ]
    return {
        "schema_version": BUNDLE_SCHEMA_VERSION,
        "target": target,
        "output_dir": str(output_dir),
        "paths": [str(path) for path in paths],
        "claim_boundary": "Bundle files are generated deployment scaffolding and require customer review plus canary validation before production use.",
    }


def _render_sbatch(verdict: RouterVerdict) -> str:
    best = verdict.execution_paths[0]
    return "\n".join(
        [
            "#!/usr/bin/env bash",
            "#SBATCH --job-name=inferguard-router-bundle",
            "#SBATCH --nodes=1",
            "#SBATCH --gres=gpu:8",
            "#SBATCH --ntasks-per-node=1",
            "#SBATCH --cpus-per-task=64",
            "#SBATCH --mem=0",
            "#SBATCH --time=04:00:00",
            "#SBATCH --output=logs/%x-%j.out",
            "#SBATCH --error=logs/%x-%j.err",
            "",
            "set -euo pipefail",
            "mkdir -p logs artifacts",
            f"echo 'target={best.target}' | tee artifacts/router_target.env",
            f"echo 'bottleneck={verdict.bottleneck_class.value}' | tee -a artifacts/router_target.env",
            "echo 'TODO: replace this stub with the validated engine launch command for the customer cluster.'",
            "echo 'Run InferGuard benchmark and canary gates before production traffic.'",
            "",
        ]
    )


def _render_prometheus(verdict: RouterVerdict) -> str:
    return "\n".join(
        [
            "groups:",
            "- name: inferguard-router-bundle",
            "  rules:",
            "  - alert: InferGuardHighP99TTFT",
            "    expr: histogram_quantile(0.99, rate(inferguard_ttft_seconds_bucket[5m])) > 2",
            "    for: 10m",
            "    labels:",
            "      severity: warning",
            "    annotations:",
            f"      summary: Router verdict {verdict.bottleneck_class.value} needs validation",
            "",
        ]
    )


def _write_cost_floor(path: Path, verdict: RouterVerdict) -> Path:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle, fieldnames=["route", "confidence", "cost_floor_usd", "notes"]
        )
        writer.writeheader()
        for route in verdict.execution_paths:
            writer.writerow(
                {
                    "route": route.target,
                    "confidence": route.confidence,
                    "cost_floor_usd": "",
                    "notes": "Fill after live benchmark records GPU-hour and request-volume evidence.",
                }
            )
    return path


def _render_runbook(verdict: RouterVerdict) -> str:
    best = verdict.execution_paths[0]
    return "\n".join(
        [
            "# InferGuard Deployment Bundle Runbook",
            "",
            f"- Bottleneck: `{verdict.bottleneck_class.value}`",
            f"- Recommended first route: `{best.target}`",
            f"- Claim label: `{verdict.claim_label}`",
            "",
            "## Steps",
            "",
            "1. Review `verdict.json` and confirm the evidence matches the customer workload.",
            "2. Replace the sbatch launch stub with the cluster-specific engine command.",
            "3. Run baseline before optimized cells.",
            "4. Run canary quality and p99 regression gates.",
            "5. Promote only after live artifacts support the claim.",
            "",
            "## Claim Boundary",
            "",
            verdict.claim_boundary,
            "",
        ]
    )


def _meta(verdict: RouterVerdict, target: str) -> dict[str, Any]:
    return {
        "schema_version": BUNDLE_SCHEMA_VERSION,
        "generated_at": datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "target": target,
        "router_schema_version": verdict.schema_version,
        "bottleneck_class": verdict.bottleneck_class.value,
        "required_repro_fields": [
            "cuda_version",
            "driver_version",
            "container_digest",
            "engine_commit_sha",
            "model_revision",
            "trace_sha256",
        ],
    }


def _write_json(path: Path, data: dict[str, Any]) -> Path:
    atomic_write_json(path, data)
    return path


def _write_text(path: Path, text: str) -> Path:
    path.write_text(text, encoding="utf-8")
    return path

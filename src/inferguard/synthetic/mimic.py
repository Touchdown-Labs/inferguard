"""Synthetic GPU artifact generator for standalone InferGuard bundle smoke tests."""

from __future__ import annotations

import argparse
import json
import math
import os
import shlex
import time
from pathlib import Path
from typing import Any

from inferguard.io import atomic_write_json

from .profiles import (
    MODEL_PROFILES,
    WORKLOAD_PROFILES,
    load_gpu_profile_catalog,
    normalize_engine,
    normalize_hardware,
    normalize_model_profile,
    normalize_workload,
)
from .server import CLAIM_BOUNDARY, SIMULATION_MODE

MVP_REQUIRED_PATHS = {
    "request_profile": [
        "request_profile/requests_profile.jsonl",
        "request_profile/requests_summary.json",
    ],
    "engine_metrics": ["metrics/engine_metrics_timeline.jsonl"],
    "gpu_metrics": ["metrics/gpu_metrics_timeline.jsonl"],
    "metrics_summary": ["metrics/metrics_summary.json"],
    "bottleneck_diagnosis": [
        "diagnosis/bottleneck_diagnosis.json",
        "diagnosis/bottleneck_diagnosis.md",
    ],
    "failure_classification": [
        "diagnosis/failure_classification.json",
        "diagnosis/failure_classification.md",
    ],
    "operator_recommendation": [
        "report/operator_recommendation.json",
        "report/operator_recommendation.md",
    ],
    "launch": [
        "launch/command.json",
        "launch/stdout.log",
        "launch/stderr.log",
        "launch/healthcheck.json",
    ],
    "rdma_health": ["preflight/ib_state.txt"],
    "network_topology": ["preflight/nccl_all_reduce.txt"],
    "multi_node_throughput": ["preflight/nccl_all_reduce.txt"],
    "kv_cache_benefit": [],
}


def load_json_config(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"expected JSON object: {path}")
    return data


def simulate_results(plan_path: Path, gpu_profiles_path: Path | None = None) -> dict[str, Any]:
    """Write synthetic per-job GPU artifacts for an existing matrix_plan.json."""
    plan = load_json_config(plan_path)
    profile_catalog = load_gpu_profile_catalog(gpu_profiles_path)
    profiles = profile_catalog["profiles"]
    jobs = plan.get("jobs") or []
    manifests = []
    for job in jobs:
        hardware = str(job["hardware"])
        hardware = normalize_hardware(hardware, profile_catalog)
        if hardware not in profiles:
            raise ValueError(f"no GPU mimic profile for hardware: {hardware}")
        job = dict(job)
        job["hardware"] = hardware
        manifests.append(simulate_job(job, profiles[hardware], profile_catalog))
    summary = {
        "schema_version": "inferguard-neocloud-gpu-mimic-run/v1",
        "simulation_mode": SIMULATION_MODE,
        "claim_boundary": CLAIM_BOUNDARY,
        "plan": str(plan_path),
        "jobs": len(manifests),
        "manifests": manifests,
    }
    write_json(plan_path.parent / "synthetic_gpu_mimic_summary.json", summary)
    return summary


def simulate_from_options(
    *,
    results_root: str | Path,
    hardware: str,
    model_profile: str,
    workload: str,
    engine: str = "vllm",
    provider: str = "gmi",
    cluster_profile: str | Path | None = None,
    stage: str = "single-node-smoke",
    max_jobs: int | None = 1,
    context_lengths: str | None = None,
    concurrency: str | None = None,
    arrival_mode: str | None = "closed_loop",
    gpu_profiles_path: str | Path | None = None,
) -> dict[str, Any]:
    """Render a one-cell standalone matrix and write synthetic GPU artifacts."""
    if provider != "gmi":
        raise ValueError("simulate-gpu currently supports --provider gmi only")
    root = Path(results_root).resolve()
    root.mkdir(parents=True, exist_ok=True)
    catalog = load_gpu_profile_catalog(gpu_profiles_path)
    profile = load_cluster_profile(cluster_profile) if cluster_profile else None
    plan = build_matrix_plan(
        results_root=root,
        hardware=hardware,
        model_profile=model_profile,
        workload=workload,
        engine=engine,
        profile=profile,
        catalog=catalog,
        stage=stage,
        max_jobs=max_jobs,
        context_lengths=_parse_int_csv(context_lengths) if context_lengths else [8192],
        concurrency=_parse_int_csv(concurrency) if concurrency else [1],
        arrival_modes=[arrival_mode or "closed_loop"],
        cluster_profile_ref=str(cluster_profile) if cluster_profile else None,
    )
    write_matrix_artifacts(root, plan)
    return simulate_results(
        root / "matrix_plan.json", Path(gpu_profiles_path) if gpu_profiles_path else None
    )


def load_cluster_profile(path: str | Path | None) -> dict[str, Any] | None:
    if path is None:
        return None
    profile_path = Path(path)
    if not profile_path.exists():
        raise FileNotFoundError(f"cluster profile does not exist: {profile_path}")
    text = profile_path.read_text(encoding="utf-8")
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        data = parse_simple_yaml(text)
    if not isinstance(data, dict):
        raise ValueError(f"profile did not parse as a mapping: {profile_path}")
    return data


def parse_simple_yaml(text: str) -> dict[str, Any]:
    root: dict[str, Any] = {}
    stack: list[tuple[int, dict[str, Any]]] = [(-1, root)]
    for raw_line in text.splitlines():
        line = raw_line.split("#", 1)[0].rstrip()
        if not line.strip():
            continue
        indent = len(raw_line) - len(raw_line.lstrip(" "))
        while stack and indent <= stack[-1][0]:
            stack.pop()
        parent = stack[-1][1]
        key, sep, value = line.strip().partition(":")
        if not sep:
            raise ValueError(f"expected key/value line: {raw_line!r}")
        if value.strip():
            parent[key.strip()] = parse_scalar(value.strip())
        else:
            child: dict[str, Any] = {}
            parent[key.strip()] = child
            stack.append((indent, child))
    return root


def parse_scalar(value: str) -> Any:
    value = value.strip().strip('"').strip("'")
    if value.startswith("[") and value.endswith("]"):
        inner = value[1:-1].strip()
        return [] if not inner else [parse_scalar(part.strip()) for part in inner.split(",")]
    if value.lower() in {"true", "false"}:
        return value.lower() == "true"
    try:
        return int(value)
    except ValueError:
        try:
            return float(value)
        except ValueError:
            return value


def build_matrix_plan(
    *,
    results_root: Path,
    hardware: str,
    model_profile: str,
    workload: str,
    engine: str,
    profile: dict[str, Any] | None,
    catalog: dict[str, Any],
    stage: str,
    max_jobs: int | None,
    context_lengths: list[int],
    concurrency: list[int],
    arrival_modes: list[str],
    cluster_profile_ref: str | None,
) -> dict[str, Any]:
    hardware_name = normalize_hardware(hardware, catalog)
    engine_name = normalize_engine(engine)
    workload_name = normalize_workload(workload)
    model_profile_name = normalize_model_profile(model_profile)
    profile = profile or default_profile(
        hardware=hardware_name,
        engine=engine_name,
        workload=workload_name,
        model_profile=model_profile_name,
        catalog=catalog,
    )
    profile = ensure_profile_contains_selection(
        profile,
        hardware=hardware_name,
        engine=engine_name,
        workload=workload_name,
        model_profile=model_profile_name,
        catalog=catalog,
    )
    jobs, total_before_limit = expand_jobs(
        profile,
        results_root=results_root,
        context_lengths=context_lengths,
        concurrency=concurrency,
        arrival_modes=arrival_modes,
        max_jobs=max_jobs,
        hardware_filter=hardware_name,
        engine_filter=engine_name,
        model_profile_filter=model_profile_name,
        workload_filter=workload_name,
    )
    return {
        "schema_version": "inferguard-gmi-dsv4-parade-matrix/v1",
        "mode": "dry-run",
        "provider": profile.get("provider", "gmi_cloud"),
        "model_family": profile.get("model_family", "turnkey_gmi_measurement_bundle"),
        "profile": cluster_profile_ref or "packaged-inferguard-synthetic-defaults",
        "results_root": str(results_root),
        "stage": stage,
        "simulation_mode": SIMULATION_MODE,
        "claim_boundary": CLAIM_BOUNDARY,
        "total_jobs_before_limit": total_before_limit,
        "total_jobs": len(jobs),
        "max_jobs": max_jobs,
        "filters": {
            "hardware": hardware_name,
            "arch": None,
            "engine": engine_name,
            "model_profile": model_profile_name,
            "workload": workload_name,
            "claim_level": None,
            "context_lengths": context_lengths,
            "concurrency": concurrency,
            "arrival_modes": arrival_modes,
        },
        "jobs": jobs,
    }


def default_profile(
    *,
    hardware: str,
    engine: str,
    workload: str,
    model_profile: str,
    catalog: dict[str, Any],
) -> dict[str, Any]:
    gpu_profile = catalog["profiles"][hardware]
    model = dict(MODEL_PROFILES[model_profile])
    workload_profile = dict(WORKLOAD_PROFILES.get(workload, {}))
    workload_profile["model_profile"] = model_profile
    return {
        "provider": "gmi_cloud",
        "model_family": "turnkey_gmi_measurement_bundle",
        "hardware": [hardware],
        "engines": [engine],
        "workloads": [workload],
        "context_lengths": [8192],
        "concurrency": [1],
        "arrival_modes": ["closed_loop"],
        "cluster": {
            "partition_env": "GMI_SLURM_PARTITION",
            "account_env": "GMI_SLURM_ACCOUNT",
            "qos_env": "GMI_SLURM_QOS",
            "model_path_env": "GMI_MODEL_PATH",
            "model_config_path_env": "GMI_MODEL_CONFIG_PATH",
            "container_image_env": "GMI_CONTAINER_IMAGE",
            "endpoint_env": "GMI_ENDPOINT",
            "default_endpoint": "http://127.0.0.1:8000/v1/chat/completions",
            "default_time": "01:30:00",
            "default_cpus_per_task": 64,
            "default_mem": "0",
            "default_gpus_per_node": gpu_profile["gpus_per_node"],
        },
        "hardware_profiles": {
            hardware: {
                "gpu_arch": gpu_profile["gpu_arch"],
                "nodes": gpu_profile["nodes"],
                "gpus_per_node": gpu_profile["gpus_per_node"],
                "tensor_parallel_size": gpu_profile["nodes"] * gpu_profile["gpus_per_node"],
            }
        },
        "model_profiles": {model_profile: model},
        "workload_profiles": {workload: workload_profile},
    }


def ensure_profile_contains_selection(
    profile: dict[str, Any],
    *,
    hardware: str,
    engine: str,
    workload: str,
    model_profile: str,
    catalog: dict[str, Any],
) -> dict[str, Any]:
    profile = dict(profile)
    profile.setdefault("hardware", [hardware])
    profile.setdefault("engines", [engine])
    profile.setdefault("workloads", [workload])
    profile.setdefault("cluster", {})
    profile.setdefault("hardware_profiles", {})
    profile.setdefault("model_profiles", {})
    profile.setdefault("workload_profiles", {})
    gpu_profile = catalog["profiles"][hardware]
    profile["hardware_profiles"].setdefault(
        hardware,
        {
            "gpu_arch": gpu_profile["gpu_arch"],
            "nodes": gpu_profile["nodes"],
            "gpus_per_node": gpu_profile["gpus_per_node"],
            "tensor_parallel_size": gpu_profile["nodes"] * gpu_profile["gpus_per_node"],
        },
    )
    profile["model_profiles"].setdefault(model_profile, dict(MODEL_PROFILES[model_profile]))
    profile["workload_profiles"].setdefault(workload, dict(WORKLOAD_PROFILES.get(workload, {})))
    profile["workload_profiles"][workload]["model_profile"] = model_profile
    return profile


def expand_jobs(
    profile: dict[str, Any],
    *,
    results_root: Path,
    context_lengths: list[int],
    concurrency: list[int],
    arrival_modes: list[str],
    max_jobs: int | None,
    hardware_filter: str,
    engine_filter: str,
    model_profile_filter: str,
    workload_filter: str,
) -> tuple[list[dict[str, Any]], int]:
    candidates: list[dict[str, Any]] = []
    for hardware in profile["hardware"]:
        hardware = normalize_hardware(str(hardware))
        if hardware != hardware_filter:
            continue
        hardware_profile = profile["hardware_profiles"][hardware]
        for engine in profile["engines"]:
            engine = normalize_engine(str(engine))
            if engine != engine_filter:
                continue
            for workload in profile["workloads"]:
                workload = normalize_workload(str(workload))
                if workload != workload_filter:
                    continue
                workload_profile = profile["workload_profiles"][workload]
                model_profile_name = normalize_model_profile(
                    str(workload_profile.get("model_profile") or model_profile_filter)
                )
                if model_profile_name != model_profile_filter:
                    continue
                model_profile = profile["model_profiles"][model_profile_name]
                for context_length in context_lengths:
                    for conc in concurrency:
                        for mode in arrival_modes:
                            candidates.append(
                                make_job(
                                    profile,
                                    results_root,
                                    hardware,
                                    hardware_profile,
                                    engine,
                                    workload,
                                    workload_profile,
                                    model_profile_name,
                                    model_profile,
                                    context_length,
                                    conc,
                                    mode,
                                    len(candidates),
                                )
                            )
    total = len(candidates)
    return (candidates[:max_jobs] if max_jobs is not None else candidates), total


def make_job(
    profile: dict[str, Any],
    results_root: Path,
    hardware: str,
    hardware_profile: dict[str, Any],
    engine: str,
    workload: str,
    workload_profile: dict[str, Any],
    model_profile_name: str,
    model_profile: dict[str, Any],
    context_length: int,
    concurrency: int,
    arrival_mode: str,
    index: int,
) -> dict[str, Any]:
    cluster = profile["cluster"]
    job_id = f"gmi-{index:05d}-{hardware}-{engine}-{workload}-{model_profile_name}-ctx{context_length}-c{concurrency}-{arrival_mode}"
    output_dir = results_root / "jobs" / job_id
    model_architecture = {
        "profile": model_profile_name,
        "hf_repo": model_profile.get("hf_repo"),
        "nvidia_quantized_hf_repo": model_profile.get("nvidia_quantized_hf_repo"),
        "architecture_class": model_profile.get("architecture_class"),
        "hf_parameters_m": model_profile.get("hf_parameters_m"),
        "claim_level": model_profile.get("claim_level"),
    }
    env = {
        "GMI_BUNDLE_ROOT": os.environ.get("GMI_BUNDLE_ROOT", "<standalone-bundle>"),
        "GMI_RESULTS_ROOT": str(results_root),
        "GMI_JOB_ID": job_id,
        "GMI_JOB_OUTPUT_DIR": str(output_dir),
        "GMI_HARDWARE": hardware,
        "GMI_GPU_ARCH": hardware_profile["gpu_arch"],
        "GMI_ENGINE": engine,
        "GMI_WORKLOAD": workload,
        "GMI_WORKLOAD_BOTTLENECK_FOCUS": workload_profile.get("bottleneck_focus", "unknown"),
        "GMI_MODEL_PROFILE": model_profile_name,
        "GMI_MODEL_HF_REPO": model_profile.get("hf_repo", ""),
        "GMI_MODEL_ARCHITECTURE_CLASS": model_profile.get("architecture_class", "unknown"),
        "GMI_MODEL_CLAIM_LEVEL": model_profile.get("claim_level", "operator_supplied"),
        "GMI_MODEL_PATH": env_or_placeholder(
            cluster.get("model_path_env"), model_profile.get("hf_repo", "MODEL_PATH_FROM_ENV")
        ),
        "GMI_MODEL_CONFIG_PATH": env_or_placeholder(cluster.get("model_config_path_env"), ""),
        "GMI_CONTAINER_IMAGE": env_or_placeholder(
            cluster.get("container_image_env"), "CONTAINER_IMAGE_FROM_ENV"
        ),
        "GMI_ENDPOINT": env_or_placeholder(
            cluster.get("endpoint_env"),
            cluster.get("default_endpoint", "http://127.0.0.1:8000/v1/chat/completions"),
        ),
        "GMI_CONTEXT_LENGTH": context_length,
        "GMI_CONCURRENCY": concurrency,
        "GMI_ARRIVAL_MODE": arrival_mode,
        "GMI_TENSOR_PARALLEL_SIZE": hardware_profile["tensor_parallel_size"],
        "GMI_SLURM_NODES": hardware_profile["nodes"],
        "GMI_GPUS_PER_NODE": hardware_profile["gpus_per_node"],
        "GMI_CPUS_PER_TASK": cluster.get("default_cpus_per_task", 64),
        "GMI_MEM": cluster.get("default_mem", "0"),
        "GMI_SLURM_TIME": cluster.get("default_time", "01:30:00"),
        "INFERGUARD_SIMULATION_MODE": SIMULATION_MODE,
        "PYTHON_BIN": os.environ.get("PYTHON_BIN", "python3"),
    }
    optional_env(env, "GMI_SLURM_PARTITION", cluster.get("partition_env"))
    optional_env(env, "GMI_SLURM_ACCOUNT", cluster.get("account_env"))
    optional_env(env, "GMI_SLURM_QOS", cluster.get("qos_env"))
    optional_env(env, "GMI_SLURM_CONSTRAINT", hardware_profile.get("constraint_env"))
    return {
        "job_id": job_id,
        "index": index,
        "hardware": hardware,
        "sku": hardware.split("_", 1)[0],
        "gpu_arch": hardware_profile["gpu_arch"],
        "engine": engine,
        "workload": workload,
        "context_length": context_length,
        "concurrency": concurrency,
        "arrival_mode": arrival_mode,
        "model_profile": model_profile_name,
        "model_architecture": model_architecture,
        "bottleneck_focus": workload_profile.get("bottleneck_focus"),
        "output_dir": str(output_dir),
        "env": env,
        "simulation_mode": SIMULATION_MODE,
    }


def env_or_placeholder(env_name: str | None, placeholder: str) -> str:
    if not env_name:
        return placeholder
    return os.environ.get(env_name, f"${{{env_name}}}" if placeholder else "")


def optional_env(env: dict[str, Any], key: str, source_env: str | None) -> None:
    if source_env and os.environ.get(source_env):
        env[key] = os.environ[source_env]


def write_matrix_artifacts(results_root: Path, plan: dict[str, Any]) -> None:
    sbatch_dir = results_root / "sbatch"
    sbatch_dir.mkdir(parents=True, exist_ok=True)
    for job in plan["jobs"]:
        path = sbatch_dir / f"{job['job_id']}.sbatch"
        path.write_text(render_simulation_sbatch(job), encoding="utf-8")
        job["rendered_sbatch"] = str(path)
    write_json(results_root / "matrix_plan.json", plan)
    contract = expected_artifact_contract(plan["jobs"], results_root)
    write_json(results_root / "expected_artifact_contract.json", contract)
    write_json(results_root / "profile_summary.json", build_profile_summary(plan))
    (results_root / "handoff.md").write_text(render_handoff(plan), encoding="utf-8")
    (results_root / "README.md").write_text(render_results_readme(plan), encoding="utf-8")
    write_doctor_artifacts(results_root, plan, contract)


def render_simulation_sbatch(job: dict[str, Any]) -> str:
    env = job["env"]
    lines = [
        "#!/usr/bin/env bash",
        f"# synthetic_gpu_mimic: standalone shape-only sbatch for {job['job_id']}",
        f"#SBATCH --job-name={job['job_id'][:120]}",
        f"#SBATCH --nodes={env['GMI_SLURM_NODES']}",
        f"#SBATCH --gres=gpu:{env['GMI_GPUS_PER_NODE']}",
        "#SBATCH --ntasks-per-node=1",
        f"#SBATCH --cpus-per-task={env['GMI_CPUS_PER_TASK']}",
        f"#SBATCH --mem={env['GMI_MEM']}",
        f"#SBATCH --time={env['GMI_SLURM_TIME']}",
        f"#SBATCH --output={shlex.quote(str(Path(job['output_dir']) / 'slurm-%j.out'))}",
        f"#SBATCH --error={shlex.quote(str(Path(job['output_dir']) / 'slurm-%j.err'))}",
        "",
        "set -euo pipefail",
    ]
    for key, value in sorted(env.items()):
        lines.append(f"export {key}={shlex.quote(str(value))}")
    lines.extend(
        [
            "echo 'synthetic_gpu_mimic sbatch placeholder: use bundle slurm/*.sbatch for live GMI runs.'",
            "",
        ]
    )
    return "\n".join(lines)


def expected_artifact_contract(jobs: list[dict[str, Any]], results_root: Path) -> dict[str, Any]:
    required = [
        "slurm-%j.out",
        "slurm-%j.err",
        "raw/environment.env",
        "preflight/uname.txt",
        "preflight/nvidia_smi.txt",
        "preflight/nvidia_smi_topo.txt",
        "manifests/operator_profile.json",
        "manifests/operator_profile.md",
        "manifests/model_config.json when model config is available",
        "manifests/model_config_summary.json",
        "inferguard_bench/summary.json or healthcheck/healthcheck.json",
    ]
    return {
        "schema_version": "inferguard-gmi-dsv4-artifact-contract/v1",
        "simulation_mode": SIMULATION_MODE,
        "results_root": str(results_root),
        "matrix_level": [
            "matrix_plan.json",
            "profile_summary.json",
            "handoff.md",
            "expected_artifact_contract.json",
            "sbatch/*.sbatch",
        ],
        "per_job": [
            {"job_id": job["job_id"], "output_dir": job["output_dir"], "expected_paths": required}
            for job in jobs
        ],
        "mvp_required_paths": MVP_REQUIRED_PATHS,
        "claim_boundary": "No performance, prefill/decode, KV-cache, or routing claim is valid until live GMI artifacts are present for the relevant cell.",
    }


def build_profile_summary(plan: dict[str, Any]) -> dict[str, Any]:
    jobs = plan["jobs"]
    return {
        "schema_version": "inferguard-gmi-profile-summary/v1",
        "simulation_mode": SIMULATION_MODE,
        "coverage": {
            "skus": sorted({job["sku"] for job in jobs}),
            "gpu_arch": sorted({job["gpu_arch"] for job in jobs}),
            "engines": sorted({job["engine"] for job in jobs}),
            "workloads": sorted({job["workload"] for job in jobs}),
            "model_profiles": sorted({job["model_profile"] for job in jobs}),
        },
        "operator_truth": "HF metadata verifies repo architecture labels; Slurm artifacts must verify the actually loaded config.json and live metrics.",
    }


def render_handoff(plan: dict[str, Any]) -> str:
    return "\n".join(
        [
            "# GMI NeoCloud NVIDIA Harness Handoff",
            "",
            f"- Provider: `{plan.get('provider')}`",
            f"- Stage: `{plan.get('stage')}`",
            f"- Jobs: {plan.get('total_jobs')} / {plan.get('total_jobs_before_limit')} before limit",
            f"- Simulation mode: `{SIMULATION_MODE}`",
            "",
            "## Claim Boundary",
            "",
            CLAIM_BOUNDARY,
            "",
        ]
    )


def render_results_readme(plan: dict[str, Any]) -> str:
    return "\n".join(
        [
            "# InferGuard synthetic GPU mimic output",
            "",
            f"Simulation mode: `{SIMULATION_MODE}`",
            "",
            CLAIM_BOUNDARY,
            "",
            f"Jobs: {plan.get('total_jobs')}",
            "",
        ]
    )


def write_doctor_artifacts(
    results_root: Path, plan: dict[str, Any], contract: dict[str, Any]
) -> None:
    doctor_dir = results_root / "doctor"
    doctor_render_dir = results_root / "doctor-render"
    (doctor_render_dir / "sbatch").mkdir(parents=True, exist_ok=True)
    doctor_dir.mkdir(parents=True, exist_ok=True)
    write_json(
        doctor_dir / "gmi_dsv4_readiness_report.json",
        {
            "schema_version": "inferguard-gmi-readiness-report/v1",
            "simulation_mode": SIMULATION_MODE,
            "status": "synthetic_shape_only",
            "claim_boundary": CLAIM_BOUNDARY,
            "matrix_plan": str(results_root / "matrix_plan.json"),
            "jobs": plan.get("total_jobs", 0),
        },
    )
    write_json(doctor_render_dir / "matrix_plan.json", plan)
    write_json(doctor_render_dir / "expected_artifact_contract.json", contract)
    write_json(doctor_render_dir / "profile_summary.json", build_profile_summary(plan))
    (doctor_render_dir / "handoff.md").write_text(render_handoff(plan), encoding="utf-8")
    for job in plan["jobs"]:
        path = doctor_render_dir / "sbatch" / f"{job['job_id']}.sbatch"
        path.write_text(render_simulation_sbatch(job), encoding="utf-8")


def simulate_job(
    job: dict[str, Any], gpu_profile: dict[str, Any], catalog: dict[str, Any]
) -> dict[str, Any]:
    output_dir = Path(job["output_dir"])
    for rel in (
        "preflight",
        "raw",
        "dcgm",
        "healthcheck",
        "inferguard_bench",
        "manifests",
        "synthetic",
        "logs",
    ):
        (output_dir / rel).mkdir(parents=True, exist_ok=True)
    env = {str(key): str(value) for key, value in (job.get("env") or {}).items()}
    env.update(
        {
            "SLURM_JOB_ID": "synthetic",
            "SLURM_NODELIST": synthetic_nodelist(gpu_profile),
            "SLURM_NNODES": str(gpu_profile["nodes"]),
            "CUDA_VISIBLE_DEVICES": ",".join(
                str(i) for i in range(int(gpu_profile["gpus_per_node"]))
            ),
            "INFERGUARD_SIMULATION_MODE": SIMULATION_MODE,
        }
    )
    write_env(output_dir / "raw" / "environment.env", env)
    (output_dir / "preflight" / "uname.txt").write_text(
        "Linux synthetic-gmi-login 6.8.0-gmi-synthetic #1 SMP x86_64 GNU/Linux\n"
        f"# provenance={SIMULATION_MODE}\n",
        encoding="utf-8",
    )
    (output_dir / "preflight" / "nvidia_smi.txt").write_text(
        render_nvidia_smi(gpu_profile), encoding="utf-8"
    )
    (output_dir / "preflight" / "nvidia_smi_topo.txt").write_text(
        render_nvidia_smi_topo(gpu_profile),
        encoding="utf-8",
    )
    (output_dir / "preflight" / "ib_state.txt").write_text(
        render_ib_state(gpu_profile), encoding="utf-8"
    )
    (output_dir / "preflight" / "nccl_all_reduce.txt").write_text(
        render_nccl_smoke(job, gpu_profile), encoding="utf-8"
    )
    (output_dir / "raw" / "ibv_devinfo.txt").write_text(
        render_ibv_devinfo(gpu_profile), encoding="utf-8"
    )
    (output_dir / "raw" / "nccl_smoke.txt").write_text(
        render_nccl_smoke(job, gpu_profile), encoding="utf-8"
    )
    metrics = synthetic_metrics(job, gpu_profile)
    (output_dir / "dcgm" / "dcgm_metrics.prom").write_text(
        render_dcgm_prom(job, gpu_profile, metrics), encoding="utf-8"
    )
    write_manifests(output_dir, job, gpu_profile, catalog, metrics)
    write_benchmark_outputs(output_dir, job, gpu_profile, metrics)
    manifest = {
        "schema_version": "inferguard-neocloud-gpu-mimic-artifact/v1",
        "simulation_mode": SIMULATION_MODE,
        "claim_boundary": CLAIM_BOUNDARY,
        "job_id": job["job_id"],
        "hardware": job["hardware"],
        "gpu_profile": gpu_profile,
        "generated_paths": sorted(
            str(path.relative_to(output_dir)) for path in output_dir.rglob("*") if path.is_file()
        ),
        "generated_at_unix": int(time.time()),
    }
    write_json(output_dir / "synthetic" / "simulation_manifest.json", manifest)
    return {
        "job_id": job["job_id"],
        "output_dir": str(output_dir),
        "manifest": str(output_dir / "synthetic" / "simulation_manifest.json"),
    }


def synthetic_nodelist(gpu_profile: dict[str, Any]) -> str:
    nodes = int(gpu_profile["nodes"])
    if nodes == 1:
        return "gmi-synth-[0001]"
    return f"gmi-synth-[0001-{nodes:04d}]"


def write_env(path: Path, env: dict[str, str]) -> None:
    path.write_text("".join(f"{key}={env[key]}\n" for key in sorted(env)), encoding="utf-8")


def render_nvidia_smi(gpu_profile: dict[str, Any]) -> str:
    lines = [
        "Sun May  3 12:00:00 2026",
        "+-----------------------------------------------------------------------------------------+",
        "| NVIDIA-SMI 570.00.00              Driver Version: 570.00.00      CUDA Version: 12.8     |",
        "+-----------------------------------------+------------------------+----------------------+",
    ]
    memory = int(gpu_profile["memory_gb_per_gpu"] * 1024)
    for idx in range(int(gpu_profile["gpus_per_node"])):
        used = int(memory * (0.18 + idx * 0.01))
        lines.append(
            f"| {idx:>3}  {gpu_profile['gpu_name']:<32} Off | 00000000:{idx + 16:02X}:00.0 Off |                  0 |"
        )
        lines.append(
            f"| 35%   45C    P0            420W / 700W | {used:>7}MiB / {memory:>7}MiB |     {55 + idx:>3}%      Default |"
        )
    lines.append(
        "+-----------------------------------------------------------------------------------------+"
    )
    lines.append(f"# provenance={SIMULATION_MODE}")
    return "\n".join(lines) + "\n"


def render_nvidia_smi_topo(gpu_profile: dict[str, Any]) -> str:
    gpus = int(gpu_profile["gpus_per_node"])
    header = ["GPU" + str(i) for i in range(gpus)] + ["NIC0", "CPU Affinity"]
    rows = ["\t".join([""] + header)]
    for i in range(gpus):
        cells = []
        for j in range(gpus):
            if i == j:
                cells.append("X")
            elif gpu_profile["topology"] == "single_node_nvlink":
                cells.append("NV18")
            else:
                cells.append("NVL")
        cells.extend(["PIX", "0-63"])
        rows.append("\t".join([f"GPU{i}", *cells]))
    rows.append("NIC0\t" + "\t".join(["PIX"] * gpus) + "\tX\t0-63")
    rows.append("")
    rows.append("Legend: NV18/NVL/PIX are synthetic topology labels for harness validation only.")
    rows.append(f"# provenance={SIMULATION_MODE}")
    return "\n".join(rows) + "\n"


def render_ib_state(gpu_profile: dict[str, Any]) -> str:
    state = "State: Active" if "nvl72" in gpu_profile["topology"] else "State: LinkUp"
    return f"CA 'mlx5_0'\n\tPort 1:\n\t\t{state}\n# provenance={SIMULATION_MODE}\n"


def render_ibv_devinfo(gpu_profile: dict[str, Any]) -> str:
    ports = 8 if "nvl72" in gpu_profile["topology"] else 2
    chunks = []
    for idx in range(ports):
        chunks.append(
            "\n".join(
                [
                    f"hca_id: mlx5_{idx}",
                    "\ttransport: InfiniBand (0)",
                    "\tfw_ver: synthetic",
                    "\tnode_guid: synthetic",
                    "\tphys_port_cnt: 1",
                    "\t\tport: 1",
                    "\t\t\tstate: PORT_ACTIVE (4)",
                    "\t\t\tlink_layer: InfiniBand",
                ]
            )
        )
    return "\n\n".join(chunks) + f"\n\n# provenance={SIMULATION_MODE}\n"


def render_nccl_smoke(job: dict[str, Any], gpu_profile: dict[str, Any]) -> str:
    gpus = int(gpu_profile["nodes"] * gpu_profile["gpus_per_node"])
    base_bw = float(gpu_profile["nvlink_bandwidth_gbps_per_gpu"]) / 16.0
    lines = [
        "# nThread 1 nGpus 1 minBytes 8 maxBytes 134217728 step: 2(factor) warmup iters: 5 iters: 20",
        "# Using synthetic all_reduce_perf output for parser validation only",
        "# bytes     count    type  redop    root     time   algbw   busbw  #wrong",
    ]
    for exp in (20, 24, 27):
        bytes_ = 2**exp
        algbw = base_bw * (0.72 + 0.02 * math.log2(max(gpus, 1)))
        busbw = algbw * 1.82
        lines.append(
            f"{bytes_:>12} {bytes_ // 4:>9}   float    sum      -1   {1000 / algbw:7.2f} {algbw:7.2f} {busbw:7.2f}      0"
        )
    lines.append(f"# job_id={job['job_id']} provenance={SIMULATION_MODE}")
    return "\n".join(lines) + "\n"


def synthetic_metrics(job: dict[str, Any], gpu_profile: dict[str, Any]) -> dict[str, float]:
    context = int(job["context_length"])
    concurrency = int(job["concurrency"])
    params_b = (
        float((job.get("model_architecture") or {}).get("hf_parameters_m") or 1000.0) / 1000.0
    )
    hbm = float(gpu_profile["hbm_bandwidth_tbps_per_gpu"])
    memory = float(gpu_profile["memory_gb_per_gpu"])
    prefill_ms = max(20.0, context / (hbm * 58.0) * (1.0 + params_b / 1800.0))
    decode_tps = max(
        4.0, (hbm * memory * 0.72) / max(1.0, math.sqrt(params_b)) / max(1.0, concurrency / 4.0)
    )
    ttft_ms = prefill_ms + 8.0 * concurrency
    gpu_util = min(97.0, 38.0 + concurrency * 4.5 + context / 8192.0)
    fb_used_gb = min(memory * 0.92, memory * 0.22 + context / 8192.0 * 1.4 + params_b / 120.0)
    return {
        "synthetic_ttft_ms": round(ttft_ms, 3),
        "synthetic_prefill_ms": round(prefill_ms, 3),
        "synthetic_decode_tokens_per_second": round(decode_tps, 3),
        "synthetic_gpu_util": round(gpu_util, 3),
        "synthetic_fb_used_gb": round(fb_used_gb, 3),
        "synthetic_power_watts": round(360.0 + gpu_util * 2.8, 3),
        "synthetic_nvlink_bandwidth_gbps": round(
            float(gpu_profile["nvlink_bandwidth_gbps_per_gpu"]) * gpu_util / 100.0, 3
        ),
    }


def render_dcgm_prom(
    job: dict[str, Any], gpu_profile: dict[str, Any], metrics: dict[str, float]
) -> str:
    lines = [
        f"# provenance={SIMULATION_MODE}",
        "# HELP DCGM_FI_DEV_GPU_UTIL GPU utilization.",
        "# TYPE DCGM_FI_DEV_GPU_UTIL gauge",
    ]
    memory_mib = int(gpu_profile["memory_gb_per_gpu"] * 1024)
    used_mib = int(metrics["synthetic_fb_used_gb"] * 1024)
    for idx in range(int(gpu_profile["gpus_per_node"])):
        labels = f'gpu="{idx}",UUID="GPU-SYNTH-{job["hardware"]}-{idx:02d}",modelName="{gpu_profile["gpu_name"]}"'
        lines.append(
            f"DCGM_FI_DEV_GPU_UTIL{{{labels}}} {metrics['synthetic_gpu_util'] + idx * 0.25:.3f}"
        )
        lines.append(f"DCGM_FI_DEV_FB_USED{{{labels}}} {used_mib + idx * 128}")
        lines.append(f"DCGM_FI_DEV_FB_FREE{{{labels}}} {max(0, memory_mib - used_mib - idx * 128)}")
        lines.append(
            f"DCGM_FI_DEV_POWER_USAGE{{{labels}}} {metrics['synthetic_power_watts'] + idx:.3f}"
        )
        lines.append(
            f"DCGM_FI_PROF_NVLINK_TX_BYTES{{{labels}}} {int(metrics['synthetic_nvlink_bandwidth_gbps'] * 125000000)}"
        )
        lines.append(f"DCGM_FI_DEV_XID_ERRORS{{{labels}}} 0")
    return "\n".join(lines) + "\n"


def write_manifests(
    output_dir: Path,
    job: dict[str, Any],
    gpu_profile: dict[str, Any],
    catalog: dict[str, Any],
    metrics: dict[str, float],
) -> None:
    model_arch = job.get("model_architecture") or {}
    config_summary = {
        "verified_from_config_json": False,
        "synthetic_from_hf_metadata": True,
        "architectures": [model_arch.get("architecture_class")],
        "hf_repo": model_arch.get("hf_repo"),
        "hf_parameters_m": model_arch.get("hf_parameters_m"),
        "simulation_mode": SIMULATION_MODE,
    }
    write_json(output_dir / "manifests" / "model_config_summary.json", config_summary)
    write_json(
        output_dir / "manifests" / "operator_profile.json",
        {
            "schema_version": "inferguard-gmi-operator-profile/v1",
            "simulation_mode": SIMULATION_MODE,
            "claim_boundary": CLAIM_BOUNDARY,
            "job_id": job["job_id"],
            "hardware": job["hardware"],
            "gpu_arch": job["gpu_arch"],
            "engine": job["engine"],
            "workload": job["workload"],
            "bottleneck_focus": job.get("bottleneck_focus"),
            "model_profile": job["model_profile"],
            "model_architecture": model_arch,
            "gpu_profile": gpu_profile,
            "gpu_profile_sources": catalog.get("sources"),
            "synthetic_metrics": metrics,
            "model_config_summary": config_summary,
            "nodes": gpu_profile.get("nodes"),
        },
    )
    (output_dir / "manifests" / "operator_profile.md").write_text(
        "\n".join(
            [
                "# Operator Profile",
                "",
                f"- Simulation mode: `{SIMULATION_MODE}`",
                f"- Hardware: `{job['hardware']}`",
                f"- GPU architecture: `{job['gpu_arch']}`",
                f"- Engine: `{job['engine']}`",
                f"- Workload: `{job['workload']}`",
                f"- Model profile: `{job['model_profile']}`",
                f"- Architecture class: `{model_arch.get('architecture_class')}`",
                "",
                CLAIM_BOUNDARY,
                "",
            ]
        ),
        encoding="utf-8",
    )


def write_benchmark_outputs(
    output_dir: Path,
    job: dict[str, Any],
    gpu_profile: dict[str, Any],
    metrics: dict[str, float],
) -> None:
    healthcheck = {
        "schema_version": "inferguard-healthcheck/v1",
        "simulation_mode": SIMULATION_MODE,
        "status": "pass",
        "endpoint": "synthetic://openai-compatible",
        "checks": [{"name": "models", "status": "pass"}, {"name": "chat", "status": "pass"}],
        "claim_boundary": CLAIM_BOUNDARY,
    }
    write_json(output_dir / "healthcheck" / "healthcheck.json", healthcheck)
    summary = {
        "schema_version": "inferguard-bench-summary/v1",
        "simulation_mode": SIMULATION_MODE,
        "claim_boundary": CLAIM_BOUNDARY,
        "job_id": job["job_id"],
        "hardware": job["hardware"],
        "engine": job["engine"],
        "workload": job["workload"],
        "context_length": job["context_length"],
        "concurrency": job["concurrency"],
        "model_profile": job["model_profile"],
        "gpu_profile": {
            "display_name": gpu_profile["display_name"],
            "gpu_name": gpu_profile["gpu_name"],
            "memory_gb_per_gpu": gpu_profile["memory_gb_per_gpu"],
            "topology": gpu_profile["topology"],
        },
        "metrics": metrics,
    }
    write_json(output_dir / "inferguard_bench" / "summary.json", summary)
    requests_path = output_dir / "inferguard_bench" / "requests.jsonl"
    with requests_path.open("w", encoding="utf-8") as handle:
        for idx in range(max(1, min(int(job["concurrency"]), 16))):
            row = {
                "request_id": f"synthetic-{idx:04d}",
                "simulation_mode": SIMULATION_MODE,
                "prompt_tokens": int(job["context_length"]),
                "completion_tokens": 256,
                "ttft_ms": metrics["synthetic_ttft_ms"] + idx,
                "decode_tokens_per_second": metrics["synthetic_decode_tokens_per_second"],
                "cache_hit": idx % 2 == 0,
            }
            handle.write(json.dumps(row, sort_keys=True) + "\n")


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_json(path, data)


def _parse_int_csv(raw: str) -> list[int]:
    values = [int(item.strip()) for item in raw.split(",") if item.strip()]
    if not values or any(value <= 0 for value in values):
        raise ValueError("CSV override must contain positive integers")
    return values


def simulate_main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path)
    parser.add_argument("--gpu-profiles", "--gpu-mimic-profile", dest="gpu_profiles", type=Path)
    parser.add_argument("--provider", default="gmi")
    parser.add_argument("--results-root", type=Path)
    parser.add_argument("--cluster-profile", type=Path)
    parser.add_argument("--stage", default="single-node-smoke")
    parser.add_argument("--max-jobs", type=int, default=1)
    parser.add_argument("--hardware", default="b200")
    parser.add_argument("--engine", default="vllm")
    parser.add_argument("--model-profile", default="dsv4-pro")
    parser.add_argument("--workload", default="long_context_chat")
    parser.add_argument("--context-lengths")
    parser.add_argument("--concurrency")
    parser.add_argument("--arrival-mode", default="closed_loop")
    args = parser.parse_args(argv)
    if args.plan is not None:
        summary = simulate_results(args.plan, args.gpu_profiles)
    else:
        if args.results_root is None:
            parser.error("--results-root is required when --plan is not supplied")
        summary = simulate_from_options(
            results_root=args.results_root,
            hardware=args.hardware,
            model_profile=args.model_profile,
            workload=args.workload,
            engine=args.engine,
            provider=args.provider,
            cluster_profile=args.cluster_profile,
            stage=args.stage,
            max_jobs=args.max_jobs,
            context_lengths=args.context_lengths,
            concurrency=args.concurrency,
            arrival_mode=args.arrival_mode,
            gpu_profiles_path=args.gpu_profiles,
        )
    print(json.dumps({"simulation_summary": summary["jobs"], "mode": SIMULATION_MODE}, indent=2))
    return 0


__all__ = [
    "CLAIM_BOUNDARY",
    "SIMULATION_MODE",
    "build_matrix_plan",
    "load_json_config",
    "simulate_from_options",
    "simulate_job",
    "simulate_main",
    "simulate_results",
]

import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
RUNNER = REPO_ROOT / "scripts" / "run_neocloud_nvidia_profile.py"


def test_neocloud_profile_render_filters_exact_cell(tmp_path: Path) -> None:
    out = tmp_path / "profile"
    completed = subprocess.run(
        [
            sys.executable,
            str(RUNNER),
            "render",
            "--results-root",
            str(out),
            "--stage",
            "single-node-smoke",
            "--hardware",
            "b200_8gpu",
            "--engine",
            "lmcache_vllm_baseline",
            "--workload",
            "long_context_chat",
            "--model-profile",
            "deepseek_v4_pro",
        ],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    plan = json.loads((out / "matrix_plan.json").read_text(encoding="utf-8"))
    assert plan["total_jobs"] == 1
    job = plan["jobs"][0]
    assert job["hardware"] == "b200_8gpu"
    assert job["gpu_arch"] == "blackwell"
    assert job["model_profile"] == "deepseek_v4_pro"
    assert job["model_architecture"]["architecture_class"] == "deepseek_v4"
    assert (out / "profile_summary.json").exists()
    assert (out / "handoff.md").exists()


def test_neocloud_profile_report_writes_operator_summary(tmp_path: Path) -> None:
    out = tmp_path / "profile"
    completed = subprocess.run(
        [
            sys.executable,
            str(RUNNER),
            "report",
            "--results-root",
            str(out),
            "--stage",
            "single-gpu-canary",
            "--max-jobs",
            "1",
        ],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    report = json.loads((out / "neocloud_nvidia_profile_report.json").read_text(encoding="utf-8"))
    assert report["schema_version"] == "inferguard-neocloud-nvidia-profile-report/v1"
    assert report["provider"] == "gmi_cloud"
    assert report["coverage"]["model_profiles"] == ["tiny_canary"]
    assert "Which model architecture profile was used?" in report["operator_questions_answered"]


def test_neocloud_profile_doctor_uses_readiness_gate(tmp_path: Path) -> None:
    out = tmp_path / "profile"
    completed = subprocess.run(
        [
            sys.executable,
            str(RUNNER),
            "doctor",
            "--results-root",
            str(out),
            "--stage",
            "single-gpu-canary",
            "--max-jobs",
            "1",
        ],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    report = json.loads(
        (out / "doctor" / "gmi_dsv4_readiness_report.json").read_text(encoding="utf-8")
    )
    assert report["schema_version"] == "inferguard-gmi-dsv4-readiness/v1"
    assert any(
        check["name"] == "render.parade_runner" and check["status"] == "pass"
        for check in report["checks"]
    )


def test_neocloud_profile_simulate_generates_gpu_mimic_artifacts(tmp_path: Path) -> None:
    out = tmp_path / "profile"
    completed = subprocess.run(
        [
            sys.executable,
            str(RUNNER),
            "simulate",
            "--results-root",
            str(out),
            "--stage",
            "single-node-smoke",
            "--hardware",
            "b200_8gpu",
            "--engine",
            "lmcache_vllm_baseline",
            "--workload",
            "long_context_chat",
            "--model-profile",
            "deepseek_v4_pro",
            "--context-lengths",
            "32768",
            "--concurrency",
            "4",
            "--arrival-mode",
            "closed_loop",
        ],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    summary = json.loads((out / "synthetic_gpu_mimic_summary.json").read_text(encoding="utf-8"))
    assert summary["simulation_mode"] == "synthetic_gpu_mimic"
    plan = json.loads((out / "matrix_plan.json").read_text(encoding="utf-8"))
    job_dir = Path(plan["jobs"][0]["output_dir"])
    manifest = json.loads(
        (job_dir / "synthetic" / "simulation_manifest.json").read_text(encoding="utf-8")
    )
    assert manifest["simulation_mode"] == "synthetic_gpu_mimic"
    assert "not publishable benchmark evidence" in manifest["claim_boundary"]
    assert "NVIDIA B200" in (job_dir / "preflight" / "nvidia_smi.txt").read_text(encoding="utf-8")
    assert "DCGM_FI_DEV_GPU_UTIL" in (job_dir / "dcgm" / "dcgm_metrics.prom").read_text(
        encoding="utf-8"
    )
    bench = json.loads((job_dir / "inferguard_bench" / "summary.json").read_text(encoding="utf-8"))
    assert bench["metrics"]["synthetic_ttft_ms"] > 0


def test_neocloud_profile_report_flags_simulation_outputs(tmp_path: Path) -> None:
    out = tmp_path / "profile"
    completed = subprocess.run(
        [
            sys.executable,
            str(RUNNER),
            "simulate",
            "--results-root",
            str(out),
            "--stage",
            "single-node-smoke",
            "--hardware",
            "gb200_nvl72",
            "--engine",
            "sglang_baseline",
            "--workload",
            "multi_turn_agentic_coding",
            "--model-profile",
            "kimi_k2_5",
            "--context-lengths",
            "8192",
            "--concurrency",
            "1",
        ],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr

    report_run = subprocess.run(
        [
            sys.executable,
            str(RUNNER),
            "report",
            "--results-root",
            str(out),
            "--completed-results-root",
            str(out),
        ],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert report_run.returncode == 0, report_run.stderr
    report = json.loads((out / "neocloud_nvidia_profile_report.json").read_text(encoding="utf-8"))
    assert report["simulation_mode"] == "synthetic_gpu_mimic"
    assert report["synthetic_manifests"]
    assert "not publishable benchmark evidence" in report["claim_boundary"]


def test_gmi_cloud_catalog_has_verified_public_sources() -> None:
    catalog_path = REPO_ROOT / "configs" / "gmi_cloud_model_catalog.yaml"
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    assert catalog["schema_version"] == "inferguard-gmi-cloud-model-catalog/v1"
    assert (
        catalog["sources"]["gmi_serverless_pricing"]
        == "https://docs.gmicloud.ai/inference-engine/billing/price"
    )
    assert catalog["sources"]["gmi_dedicated_gpu_pricing"] == "https://www.gmicloud.ai/en/pricing"
    assert {gpu["sku"] for gpu in catalog["dedicated_gpu_catalog"]} >= {
        "h100",
        "h200",
        "b200",
        "gb200",
        "gb300",
    }
    models = {model["model_name"]: model for model in catalog["serverless_models"]}
    assert models["DeepSeek-V3.2-Exp"]["architecture"] == "deepseek_v32"
    assert models["GLM-4.6"]["architecture"] == "glm4_moe"
    assert models["Qwen3-30B-A3B"]["architecture"] == "qwen3_moe"


def test_gpu_mimic_profile_catalog_covers_neocloud_skus() -> None:
    catalog_path = REPO_ROOT / "configs" / "neocloud_nvidia_gpu_mimic_profiles.yaml"
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    assert catalog["schema_version"] == "inferguard-neocloud-nvidia-gpu-mimic-profiles/v1"
    assert set(catalog["profiles"]) >= {
        "h100_8gpu",
        "h200_8gpu",
        "b200_8gpu",
        "b300_8gpu",
        "gb200_nvl72",
        "gb300_nvl72",
    }
    assert catalog["profiles"]["gb200_nvl72"]["topology"] == "nvl72_multinode"
    assert catalog["profiles"]["gb300_nvl72"]["spec_confidence"] == "public_spec_partial"

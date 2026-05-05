"""Realistic NeoCloud environment dictionaries for harness env tests."""

from __future__ import annotations

import pytest


@pytest.fixture
def modal_env() -> dict[str, str]:
    return {
        "MODAL_TASK_ID": "ta-123",
        "MODAL_SANDBOX_ID": "sb-abc",
        "MODAL_CLOUD_PROVIDER": "oci",
        "MODAL_REGION": "us-east-1",
        "MODAL_IMAGE_ID": "im-456",
        "MODAL_ENVIRONMENT": "main",
        "MODAL_IS_REMOTE": "1",
        "MODAL_IDENTITY_TOKEN": "token",
    }


@pytest.fixture
def crusoe_env() -> dict[str, str]:
    return {
        "KUBERNETES_SERVICE_HOST": "10.43.0.1",
        "HOSTNAME": "slurm-worker-b200-180gb-sxm-ib.8x-0",
        "POD_LABELS": 'slinky.slurm.net/node-type="b200-180gb-sxm-ib.8x"',
        "SLURM_JOB_ID": "901",
    }


@pytest.fixture
def coreweave_env() -> dict[str, str]:
    return {
        "KUBERNETES_SERVICE_HOST": "10.96.0.1",
        "POD_LABELS": "\n".join(
            [
                'ds.coreweave.com/nvlink.domain="nvl-domain-7"',
                'node.coreweave.cloud/rack="DH4-016-US-EAST-02A"',
                'ib.coreweave.cloud/fabric="fabric-a"',
                'ib.coreweave.cloud/superpod="superpod-east-2"',
            ]
        ),
    }


@pytest.fixture
def lambda_env() -> dict[str, str]:
    return {
        "HOSTNAME": "lambda-1click-hgx-b200-0",
        "LAMBDA_CLUSTER_ID": "lc-123",
        "LAMBDA_ONE_CLICK": "true",
        "GPU_MODEL": "NVIDIA B200 SXM",
    }


@pytest.fixture
def fireworks_env() -> dict[str, str]:
    return {
        "OPENAI_BASE_URL": "https://api.fireworks.ai/inference/v1",
        "INFERGUARD_METRICS_URL": "http://localhost:9466/metrics",
    }


@pytest.fixture
def radixark_env() -> dict[str, str]:
    return {
        "RADIXARK_DEPLOYMENT_ID": "rx-prod-7",
        "SGLANG_ENABLE_METRICS": "1",
        "SGLANG_CONFIG": "/etc/radixark/sglang.yaml",
    }


@pytest.fixture
def sglang_env() -> dict[str, str]:
    return {
        "SGLANG_CONFIG": "/etc/sglang/server.yaml",
        "SERVER_ARGS": "python -m sglang.launch_server --enable-metrics",
    }


@pytest.fixture
def gmi_env() -> dict[str, str]:
    return {
        "GMI_CLUSTER_ENGINE": "cluster-engine",
        "NVIDIA_GPU_NAME": "NVIDIA GB200 NVL72",
        "CUDA_VISIBLE_DEVICES": "0,1,2,3,4,5,6,7",
        "SCRATCH_PATH": "/scratch",
    }

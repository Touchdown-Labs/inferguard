from __future__ import annotations

import sys
import types

import pytest

from inferguard.harness.env import EnvironmentAdapter, RigContext

pytest_plugins = ("tests.fixtures.neocloud_envs",)


@pytest.mark.harness
def test_detects_local_default() -> None:
    context = EnvironmentAdapter.detect({}, file_exists=lambda _path: False)
    assert context.backend == "local"
    assert context.node_count == 1


@pytest.mark.harness
def test_detects_slurm_job_and_expands_nodelist() -> None:
    context = EnvironmentAdapter.detect(
        {"SLURM_JOB_ID": "123", "SLURM_NODELIST": "gpu[01-03]"},
        file_exists=lambda _path: False,
    )
    assert context.backend == "slurm"
    assert context.is_slurm is True
    assert context.job_id == "123"
    assert context.node_list == ["gpu01", "gpu02", "gpu03"]
    assert context.node_count == 3


@pytest.mark.harness
def test_detects_docker_from_dockerenv() -> None:
    context = EnvironmentAdapter.detect({}, file_exists=lambda path: path == "/.dockerenv")
    assert context.backend == "docker"
    assert context.is_docker is True


@pytest.mark.harness
def test_detects_kubernetes_from_service_host() -> None:
    context = EnvironmentAdapter.detect(
        {"KUBERNETES_SERVICE_HOST": "10.0.0.1", "POD_NAMESPACE": "bench"},
        file_exists=lambda _path: False,
    )
    assert context.backend == "kubernetes"
    assert context.is_kubernetes is True
    assert context.metadata["kubernetes_namespace"] == "bench"


@pytest.mark.harness
def test_detects_multi_node_from_world_size() -> None:
    context = EnvironmentAdapter.detect(
        {"WORLD_SIZE": "8", "RANK": "2"}, file_exists=lambda _path: False
    )
    assert context.backend == "multi-node"
    assert context.is_multi_node is True
    assert context.rank == 2
    assert context.world_size == 8


@pytest.mark.harness
def test_detects_multi_node_from_nccl_env() -> None:
    context = EnvironmentAdapter.detect(
        {"NCCL_SOCKET_IFNAME": "eth0"}, file_exists=lambda _path: False
    )
    assert context.backend == "multi-node"
    assert context.is_multi_node is True


@pytest.mark.harness
def test_detects_gmi_scratch_from_env() -> None:
    context = EnvironmentAdapter.detect(
        {"GMI_SCRATCH": "/mnt/gmi/job"}, file_exists=lambda _path: False
    )
    assert context.is_gmi is True
    assert context.scratch_path == "/mnt/gmi/job"


@pytest.mark.harness
def test_detects_gmi_scratch_from_path() -> None:
    context = EnvironmentAdapter.detect({}, file_exists=lambda path: path == "/scratch/gmi")
    assert context.is_gmi is True
    assert context.scratch_path == "/scratch/gmi"


@pytest.mark.harness
def test_detects_disagg_pair_as_logical_endpoint() -> None:
    context = EnvironmentAdapter.detect(
        {"PREFILL_URL": "http://prefill:8000", "DECODE_URL": "http://decode:8000"},
        file_exists=lambda _path: False,
    )
    assert context.backend == "disagg-pair"
    assert (
        context.logical_endpoint == "disagg://prefill=http://prefill:8000;decode=http://decode:8000"
    )


@pytest.mark.harness
def test_explicit_backend_override_wins() -> None:
    context = EnvironmentAdapter.detect(
        {"WARP_ISOLATION_PLATFORM": "DockerSandbox", "SLURM_JOB_ID": "123"},
        file_exists=lambda _path: False,
    )
    assert context.backend == "docker"
    assert context.is_slurm is True


@pytest.mark.harness
def test_resolve_applies_spec_overrides() -> None:
    context = EnvironmentAdapter.resolve(
        {"backend": "ssh", "metrics_url": "http://localhost:9400/metrics"},
        env={},
        file_exists=lambda _path: False,
    )
    assert context.backend == "ssh"
    assert context.metrics_url == "http://localhost:9400/metrics"


@pytest.mark.harness
def test_detects_gpu_count_and_rig_label() -> None:
    context = EnvironmentAdapter.detect(
        {"CUDA_VISIBLE_DEVICES": "0,1,2,3", "NVIDIA_GPU_NAME": "NVIDIA H200 SXM"},
        file_exists=lambda _path: False,
    )
    assert context.gpu_count == 4
    assert context.rig_label == "h200"


@pytest.mark.harness
def test_rig_context_as_dict_contains_backend() -> None:
    assert RigContext(backend="local").as_dict()["backend"] == "local"


@pytest.mark.harness
class TestModalDetection:
    def test_modal_task_id_sets_provider(self, modal_env: dict[str, str]) -> None:
        context = EnvironmentAdapter.detect(modal_env, file_exists=lambda _path: False)

        assert context.backend == "modal"
        assert context.provider == "modal"
        assert context.modal_task_id == "ta-123"
        assert context.modal_cloud_provider == "oci"
        assert context.modal_region == "us-east-1"
        assert context.modal_sandbox is True

    def test_modal_cluster_info_sets_rank_and_world_size(
        self,
        monkeypatch: pytest.MonkeyPatch,
        modal_env: dict[str, str],
    ) -> None:
        experimental = types.SimpleNamespace(
            get_cluster_info=lambda: types.SimpleNamespace(
                rank=1,
                cluster_id="modal-cluster-7",
                container_ips=["10.0.0.10", "10.0.0.11", "10.0.0.12"],
            )
        )
        monkeypatch.setitem(sys.modules, "modal", types.SimpleNamespace(experimental=experimental))
        monkeypatch.setitem(sys.modules, "modal.experimental", experimental)

        context = EnvironmentAdapter.detect(modal_env, file_exists=lambda _path: False)

        assert context.modal_cluster_rank == 1
        assert context.modal_cluster_id == "modal-cluster-7"
        assert context.rank == 1
        assert context.world_size == 3
        assert context.is_multi_node is True

    def test_modal_falls_back_to_world_size(self, modal_env: dict[str, str]) -> None:
        env = {**modal_env, "WORLD_SIZE": "2", "RANK": "1"}
        context = EnvironmentAdapter.detect(env, file_exists=lambda _path: False)

        assert context.provider == "modal"
        assert context.world_size == 2
        assert context.rank == 1
        assert context.is_multi_node is True

    def test_modal_function_id_does_not_trigger_modal_or_coreweave(self) -> None:
        context = EnvironmentAdapter.detect(
            {"MODAL_FUNCTION_ID": "fn-does-not-exist-in-modal-runtime"},
            file_exists=lambda _path: False,
        )

        assert context.provider is None
        assert context.backend == "local"
        assert context.coreweave_rack_id is None


@pytest.mark.harness
class TestCrusoeDetection:
    def test_crusoe_slinky_node_type_from_pod_labels(self, crusoe_env: dict[str, str]) -> None:
        context = EnvironmentAdapter.detect(crusoe_env, file_exists=lambda _path: False)

        assert context.backend == "crusoe"
        assert context.provider == "crusoe"
        assert context.crusoe_node_type == "b200-180gb-sxm-ib.8x"
        assert context.crusoe_managed_via == "slinky-cmk"

    def test_crusoe_h200_shape_from_hostname(self) -> None:
        context = EnvironmentAdapter.detect(
            {
                "KUBERNETES_SERVICE_HOST": "10.43.0.1",
                "HOSTNAME": "train-h200-141gb-sxm-ib.8x-worker-0",
            },
            file_exists=lambda _path: False,
        )

        assert context.provider == "crusoe"
        assert context.crusoe_node_type == "h200-141gb-sxm-ib.8x"

    def test_crusoe_pure_k8s_shape_from_env_node_type(self) -> None:
        context = EnvironmentAdapter.detect(
            {"KUBERNETES_SERVICE_HOST": "10.43.0.1", "CRUSOE_NODE_TYPE": "h100-80gb-sxm-ib.8x"},
            file_exists=lambda _path: False,
        )

        assert context.provider == "crusoe"
        assert context.is_kubernetes is True
        assert context.crusoe_node_type == "h100-80gb-sxm-ib.8x"


@pytest.mark.harness
class TestCoreWeaveDetection:
    def test_coreweave_cks_labels_set_provider(self, coreweave_env: dict[str, str]) -> None:
        context = EnvironmentAdapter.detect(coreweave_env, file_exists=lambda _path: False)

        assert context.backend == "coreweave"
        assert context.provider == "coreweave"
        assert context.coreweave_rack_id == "DH4-016-US-EAST-02A"
        assert context.coreweave_nvlink_domain == "nvl-domain-7"
        assert context.coreweave_ib_fabric == "fabric-a"
        assert context.coreweave_superpod == "superpod-east-2"
        assert context.coreweave_orchestrator == "cks"

    def test_coreweave_sunk_when_k8s_and_slurm_present(
        self,
        coreweave_env: dict[str, str],
    ) -> None:
        env = {**coreweave_env, "SLURM_JOB_ID": "777", "SLURM_NODELIST": "cw[01-02]"}
        context = EnvironmentAdapter.detect(env, file_exists=lambda _path: False)

        assert context.provider == "coreweave"
        assert context.coreweave_orchestrator == "sunk"
        assert context.is_slurm is True

    def test_coreweave_env_does_not_false_positive_as_crusoe(
        self,
        coreweave_env: dict[str, str],
    ) -> None:
        context = EnvironmentAdapter.detect(coreweave_env, file_exists=lambda _path: False)

        assert context.provider == "coreweave"
        assert context.crusoe_node_type is None
        assert context.crusoe_managed_via is None


@pytest.mark.harness
class TestLambdaDetection:
    def test_lambda_one_click_from_env(self, lambda_env: dict[str, str]) -> None:
        context = EnvironmentAdapter.detect(lambda_env, file_exists=lambda _path: False)

        assert context.backend == "lambda"
        assert context.provider == "lambda"
        assert context.lambda_one_click is True
        assert context.lambda_cluster_id == "lc-123"

    def test_lambda_one_click_from_hostname(self) -> None:
        context = EnvironmentAdapter.detect(
            {"HOSTNAME": "lambda-cloud-one-click-gb200-node-0"},
            file_exists=lambda _path: False,
        )

        assert context.provider == "lambda"
        assert context.lambda_one_click is True

    def test_lambda_fallback_from_k8s_infiniband(self) -> None:
        context = EnvironmentAdapter.detect(
            {
                "KUBERNETES_SERVICE_HOST": "10.96.0.1",
                "NCCL_IB_HCA": "mlx5_0,mlx5_1",
                "GPU_MODEL": "NVIDIA H100 SXM",
            },
            file_exists=lambda _path: False,
        )

        assert context.provider == "lambda"
        assert context.lambda_one_click is False
        assert context.is_kubernetes is True


@pytest.mark.harness
class TestFireworksDetection:
    def test_fireworks_endpoint_sets_target_provider(self, fireworks_env: dict[str, str]) -> None:
        context = EnvironmentAdapter.detect(fireworks_env, file_exists=lambda _path: False)

        assert context.provider is None
        assert context.backend == "local"
        assert context.target_provider == "fireworks"
        assert context.fireworks_endpoint == "https://api.fireworks.ai/inference/v1"

    def test_fireworks_disagg_endpoint_preserves_disagg_backend(self) -> None:
        context = EnvironmentAdapter.detect(
            {
                "PREFILL_URL": "https://api.fireworks.ai/inference/v1/prefill",
                "DECODE_URL": "http://decode.internal:8000",
            },
            file_exists=lambda _path: False,
        )

        assert context.backend == "disagg-pair"
        assert context.provider is None
        assert context.target_provider == "fireworks"

    def test_fireworks_target_metadata_does_not_override_modal_provider(
        self,
        modal_env: dict[str, str],
    ) -> None:
        env = {**modal_env, "OPENAI_BASE_URL": "https://api.fireworks.ai/inference/v1"}
        context = EnvironmentAdapter.detect(env, file_exists=lambda _path: False)

        assert context.provider == "modal"
        assert context.backend == "modal"
        assert context.target_provider == "fireworks"


@pytest.mark.harness
class TestRadixArkSGLangDetection:
    def test_radixark_commercial_signal_sets_provider(self, radixark_env: dict[str, str]) -> None:
        context = EnvironmentAdapter.detect(radixark_env, file_exists=lambda _path: False)

        assert context.backend == "radixark"
        assert context.provider == "radixark"
        assert context.engine_provider == "sglang"
        assert context.radixark_deployment_id == "rx-prod-7"
        assert context.sglang_metrics_enabled is True

    def test_sglang_env_sets_engine_provider_without_provider(
        self,
        sglang_env: dict[str, str],
    ) -> None:
        context = EnvironmentAdapter.detect(sglang_env, file_exists=lambda _path: False)

        assert context.provider is None
        assert context.backend == "local"
        assert context.engine_provider == "sglang"
        assert context.sglang_metrics_enabled is True

    def test_gmi_precedence_wins_over_radixark_provider(
        self,
        gmi_env: dict[str, str],
        radixark_env: dict[str, str],
    ) -> None:
        context = EnvironmentAdapter.detect(
            {**radixark_env, **gmi_env}, file_exists=lambda _path: False
        )

        assert context.provider == "gmi"
        assert context.backend == "gmi"
        assert context.engine_provider == "sglang"
        assert context.radixark_deployment_id == "rx-prod-7"


@pytest.mark.harness
class TestGmiDetection:
    def test_gmi_scratch_env_sets_bare_metal_mode(self, gmi_env: dict[str, str]) -> None:
        context = EnvironmentAdapter.detect(gmi_env, file_exists=lambda _path: False)

        assert context.backend == "gmi"
        assert context.provider == "gmi"
        assert context.is_gmi is True
        assert context.gmi_mode == "bare-metal"
        assert context.gmi_gpu_model == "NVIDIA GB200 NVL72"

    def test_gmi_k8s_mode_from_scratch_and_kubernetes(self, gmi_env: dict[str, str]) -> None:
        env = {**gmi_env, "KUBERNETES_SERVICE_HOST": "10.96.0.1"}
        context = EnvironmentAdapter.detect(env, file_exists=lambda _path: False)

        assert context.provider == "gmi"
        assert context.gmi_mode == "k8s"
        assert context.is_kubernetes is True

    def test_gmi_caas_mode_from_container_and_mnt_scratch(self) -> None:
        context = EnvironmentAdapter.detect(
            {"IN_DOCKER": "true", "GPU_MODEL": "NVIDIA H200 SXM"},
            file_exists=lambda path: path == "/mnt/scratch",
        )

        assert context.provider == "gmi"
        assert context.gmi_mode == "caas"
        assert context.scratch_path == "/mnt/scratch"

    def test_gmi_data_path_requires_gpu_or_gmi_signal(self) -> None:
        local_context = EnvironmentAdapter.detect({}, file_exists=lambda path: path == "/data")
        gmi_context = EnvironmentAdapter.detect(
            {"GPU_MODEL": "NVIDIA B200 SXM"},
            file_exists=lambda path: path == "/data",
        )

        assert local_context.provider is None
        assert local_context.backend == "local"
        assert gmi_context.provider == "gmi"
        assert gmi_context.scratch_path == "/data"

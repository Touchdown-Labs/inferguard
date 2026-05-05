"""Environment detection for the InferGuard v0.5 harness layer."""

from __future__ import annotations

import os
import re
from collections.abc import Callable, Mapping
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

FileExists = Callable[[str], bool]


@dataclass(frozen=True)
class RigContext:
    """Detected execution context for an InferGuard harness run.

    Provider-specific fields:
    - ``provider``: execution provider selected by the NeoCloud cascade.
    - ``target_provider`` / ``fireworks_endpoint``: Fireworks AI hosted endpoint metadata.
    - ``engine_provider`` / ``sglang_metrics_enabled``: SGLang/RadixArk engine metadata.
    - ``modal_*``: Modal task, sandbox, region, cloud, and cluster-rank metadata.
    - ``crusoe_*``: Crusoe Slinky/CMK node-type metadata.
    - ``coreweave_*``: CoreWeave CKS/SUNK rack, NVLink, and InfiniBand labels.
    - ``lambda_*``: Lambda 1-Click cluster metadata.
    - ``gmi_*``: GMI Cloud mode and GPU-model metadata.
    - ``radixark_*``: RadixArk commercial SGLang deployment metadata.
    """

    backend: str
    is_slurm: bool = False
    is_docker: bool = False
    is_kubernetes: bool = False
    is_multi_node: bool = False
    is_gmi: bool = False
    job_id: str | None = None
    node_list: list[str] = field(default_factory=list)
    node_count: int = 1
    rank: int | None = None
    world_size: int | None = None
    gpu_count: int | None = None
    rig_label: str | None = None
    scratch_path: str | None = None
    metrics_url: str | None = None
    prefill_url: str | None = None
    decode_url: str | None = None

    provider: str | None = None
    target_provider: str | None = None
    engine_provider: str | None = None

    modal_task_id: str | None = None
    modal_sandbox_id: str | None = None
    modal_cloud_provider: str | None = None
    modal_region: str | None = None
    modal_sandbox: bool | None = None
    modal_cluster_rank: int | None = None
    modal_cluster_id: str | None = None

    crusoe_node_type: str | None = None
    crusoe_managed_via: str | None = None

    coreweave_rack_id: str | None = None
    coreweave_nvlink_domain: str | None = None
    coreweave_ib_fabric: str | None = None
    coreweave_superpod: str | None = None
    coreweave_orchestrator: str | None = None

    lambda_one_click: bool | None = None
    lambda_cluster_id: str | None = None

    fireworks_endpoint: str | None = None

    gmi_mode: str | None = None
    gmi_gpu_model: str | None = None

    radixark_deployment_id: str | None = None
    sglang_metrics_enabled: bool | None = None

    metadata: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    @property
    def logical_endpoint(self) -> str | None:
        if self.prefill_url and self.decode_url:
            return f"disagg://prefill={self.prefill_url};decode={self.decode_url}"
        return self.prefill_url or self.decode_url


class EnvironmentAdapter:
    """Detect local, scheduler, container, Kubernetes, GMI, and NeoCloud surfaces."""

    _cached_context: RigContext | None = None

    def __init__(self, context: RigContext | None = None) -> None:
        self.context = context or self.detect()

    @classmethod
    def clear_cache(cls) -> None:
        cls._cached_context = None

    @classmethod
    def detect(
        cls,
        env: Mapping[str, str] | None = None,
        *,
        file_exists: FileExists | None = None,
        use_cache: bool = False,
    ) -> RigContext:
        if use_cache and cls._cached_context is not None:
            return cls._cached_context
        environ = dict(os.environ if env is None else env)
        exists = file_exists or (lambda path: Path(path).exists())

        labels = _detect_kubernetes_labels(environ, exists)
        explicit = _first(environ, "INFERGUARD_ENV", "WARP_ISOLATION_PLATFORM")
        is_slurm = "SLURM_JOB_ID" in environ or "SLURM_NODELIST" in environ
        is_kubernetes = "KUBERNETES_SERVICE_HOST" in environ or bool(labels)
        is_docker = exists("/.dockerenv") or _truthy(environ.get("IN_DOCKER"))
        world_size = _optional_int(
            _first(environ, "WORLD_SIZE", "OMPI_COMM_WORLD_SIZE", "PMI_SIZE", "SLURM_NTASKS")
        )
        node_count = _detect_node_count(environ)
        is_multi_node = _detect_multi_node(environ, world_size=world_size, node_count=node_count)
        scratch_path = _detect_scratch_path(environ, exists)
        prefill_url = _first(environ, "INFERGUARD_PREFILL_URL", "PREFILL_URL")
        decode_url = _first(environ, "INFERGUARD_DECODE_URL", "DECODE_URL")
        metrics_url = _first(environ, "INFERGUARD_METRICS_URL", "METRICS_URL")
        gpu_count = _detect_gpu_count(environ)
        rig_label = _detect_rig_label(environ)

        base = {
            "gpu_count": gpu_count,
            "is_docker": is_docker,
            "is_kubernetes": is_kubernetes,
            "is_multi_node": is_multi_node,
            "is_slurm": is_slurm,
            "node_count": node_count,
            "rig_label": rig_label,
            "scratch_path": scratch_path,
            "world_size": world_size,
        }
        provider_updates = _detect_provider(environ, exists, labels, base)
        sglang_updates = _detect_radixark_sglang(environ, exists, labels, base) or {}
        fireworks_updates = _detect_fireworks(environ, exists, labels, base) or {}

        provider = provider_updates.get("provider")
        backend = _normalize_backend(explicit) if explicit else "local"
        if not explicit:
            if provider:
                backend = str(provider)
            elif prefill_url and decode_url:
                backend = "disagg-pair"
            elif is_kubernetes:
                backend = "kubernetes"
            elif is_slurm:
                backend = "slurm"
            elif is_docker:
                backend = "docker"
            elif is_multi_node:
                backend = "multi-node"

        context_data: dict[str, Any] = {
            "backend": backend,
            "is_slurm": is_slurm,
            "is_docker": is_docker,
            "is_kubernetes": is_kubernetes,
            "is_multi_node": is_multi_node,
            "is_gmi": bool(scratch_path) or _contains_gmi(environ),
            "job_id": environ.get("SLURM_JOB_ID"),
            "node_list": _expand_nodelist(
                _first(environ, "SLURM_NODELIST", "SLURM_JOB_NODELIST") or ""
            ),
            "node_count": node_count,
            "rank": _optional_int(_first(environ, "RANK", "OMPI_COMM_WORLD_RANK", "PMI_RANK")),
            "world_size": world_size,
            "gpu_count": gpu_count,
            "rig_label": rig_label,
            "scratch_path": scratch_path,
            "metrics_url": metrics_url,
            "prefill_url": prefill_url,
            "decode_url": decode_url,
            "metadata": {
                "kubernetes_namespace": environ.get("POD_NAMESPACE"),
                "slurm_partition": environ.get("SLURM_JOB_PARTITION"),
                "master_addr": environ.get("MASTER_ADDR"),
                "nccl_socket_ifname": environ.get("NCCL_SOCKET_IFNAME"),
                "kubernetes_label_count": len(labels),
            },
        }

        context_data.update(_metadata_only(sglang_updates))
        context_data.update(fireworks_updates)
        context_data.update(provider_updates)
        context_data["backend"] = backend
        context_data["is_multi_node"] = _final_multi_node(context_data)
        context_data["is_gmi"] = bool(context_data.get("is_gmi")) or provider == "gmi"

        context = RigContext(**context_data)
        if use_cache:
            cls._cached_context = context
        return context

    @classmethod
    def resolve(
        cls,
        spec: Mapping[str, Any] | str | None = None,
        *,
        env: Mapping[str, str] | None = None,
        file_exists: FileExists | None = None,
    ) -> RigContext:
        """Resolve a user spec into a single ``RigContext``."""

        context = cls.detect(env, file_exists=file_exists)
        if spec is None:
            return context
        if isinstance(spec, str):
            return _replace_context(context, backend=_normalize_backend(spec))
        overrides = dict(spec)
        backend = _normalize_backend(str(overrides.pop("backend", context.backend)))
        return _replace_context(context, backend=backend, **overrides)

    def metrics_endpoint(self) -> str | None:
        return self.context.metrics_url

    def environment_summary(self) -> dict[str, Any]:
        return self.context.as_dict()


_backend_aliases = {
    "localpty": "local",
    "local": "local",
    "docker": "docker",
    "dockersandbox": "docker",
    "kubernetes": "kubernetes",
    "namespace": "kubernetes",
    "slurm": "slurm",
    "ssh": "ssh",
    "remote": "ssh",
    "cloud": "cloud",
    "disagg": "disagg-pair",
    "disagg-pair": "disagg-pair",
    "multi-node": "multi-node",
    "multinode": "multi-node",
    "modal": "modal",
    "crusoe": "crusoe",
    "coreweave": "coreweave",
    "lambda": "lambda",
    "gmi": "gmi",
    "radixark": "radixark",
}

_COREWEAVE_LABELS = {
    "coreweave_nvlink_domain": "ds.coreweave.com/nvlink.domain",
    "coreweave_rack_id": "node.coreweave.cloud/rack",
    "coreweave_ib_fabric": "ib.coreweave.cloud/fabric",
    "coreweave_superpod": "ib.coreweave.cloud/superpod",
}

_CRUSOE_NODE_TYPES = (
    "b200-180gb-sxm-ib.8x",
    "h200-141gb-sxm-ib.8x",
    "h100-80gb-sxm-ib.8x",
    "a100-80gb-sxm-ib.8x",
)

_GMI_SCRATCH_CANDIDATES = (
    "/mnt/gmi",
    "/scratch/gmi",
    "/gmi/scratch",
    "/scratch",
    "/mnt/scratch",
    "/data",
)

_LAMBDA_SERVERLESS_KEYS = {
    "AWS_LAMBDA_FUNCTION_NAME",
    "AWS_LAMBDA_FUNCTION_VERSION",
    "AWS_LAMBDA_LOG_GROUP_NAME",
    "AWS_LAMBDA_LOG_STREAM_NAME",
    "LAMBDA_RUNTIME_DIR",
    "LAMBDA_TASK_ROOT",
}


def _replace_context(context: RigContext, **overrides: Any) -> RigContext:
    data = context.as_dict()
    data.update(overrides)
    return RigContext(**data)


def _normalize_backend(value: str) -> str:
    key = value.strip().lower().replace("_", "-")
    return _backend_aliases.get(key, key or "local")


def _first(env: Mapping[str, str], *keys: str) -> str | None:
    for key in keys:
        value = env.get(key)
        if value:
            return value
    return None


def _truthy(value: str | None) -> bool:
    return value is not None and value.lower() in {"1", "true", "yes", "on"}


def _optional_int(value: str | None) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except ValueError:
        return None


def _detect_node_count(env: Mapping[str, str]) -> int:
    for key in ("SLURM_NNODES", "SLURM_JOB_NUM_NODES", "NNODES"):
        parsed = _optional_int(env.get(key))
        if parsed and parsed > 0:
            return parsed
    nodes = _expand_nodelist(_first(env, "SLURM_NODELIST", "SLURM_JOB_NODELIST") or "")
    return max(1, len(nodes))


def _detect_multi_node(env: Mapping[str, str], *, world_size: int | None, node_count: int) -> bool:
    if node_count > 1 or (world_size is not None and world_size > 1):
        return True
    return any(
        env.get(key)
        for key in ("MASTER_ADDR", "NCCL_SOCKET_IFNAME", "NCCL_IB_HCA", "OMPI_COMM_WORLD_SIZE")
    )


def _detect_gpu_count(env: Mapping[str, str]) -> int | None:
    explicit = _optional_int(_first(env, "INFERGUARD_GPU_COUNT", "GPU_COUNT", "SLURM_GPUS_ON_NODE"))
    if explicit is not None:
        return explicit
    visible = env.get("CUDA_VISIBLE_DEVICES")
    if visible and visible not in {"", "NoDevFiles"}:
        return len([item for item in visible.split(",") if item.strip()])
    return None


def _detect_rig_label(env: Mapping[str, str]) -> str | None:
    explicit = _first(env, "INFERGUARD_RIG_LABEL", "RIG_LABEL")
    if explicit:
        return explicit.lower()
    haystack = " ".join(
        env.get(key, "") for key in ("NVIDIA_GPU_NAME", "GPU_MODEL", "SLURM_JOB_NAME", "HOSTNAME")
    ).lower()
    for label in ("gb200", "b200", "h200", "h100", "a100"):
        if label in haystack:
            return label
    return None


def _detect_scratch_path(env: Mapping[str, str], exists: FileExists) -> str | None:
    for key in (
        "GMI_SCRATCH",
        "GMI_SCRATCH_PATH",
        "INFERGUARD_GMI_SCRATCH",
        "SCRATCH_PATH",
        "SCRATCH_DIR",
        "LOCAL_SCRATCH",
    ):
        value = env.get(key)
        if value:
            return value
    for candidate in _GMI_SCRATCH_CANDIDATES:
        if candidate == "/data":
            continue
        if exists(candidate):
            return candidate
    if exists("/data") and (
        _contains_gmi(env)
        or _detect_gpu_count(env)
        or _first(env, "NVIDIA_GPU_NAME", "GPU_MODEL", "ACCELERATOR_MODEL")
    ):
        return "/data"
    return None


def _contains_gmi(env: Mapping[str, str]) -> bool:
    return any("gmi" in value.lower() or key.startswith("GMI_") for key, value in env.items())


def _detect_provider(
    env: Mapping[str, str],
    exists: FileExists,
    labels: Mapping[str, str],
    base: Mapping[str, Any],
) -> dict[str, Any]:
    """Apply the provider cascade: Modal → Crusoe → CoreWeave → Lambda → GMI."""

    for detector in (
        _detect_modal,
        _detect_crusoe,
        _detect_coreweave,
        _detect_lambda,
        _detect_gmi,
    ):
        updates = detector(env, exists, labels, base)
        if updates and updates.get("provider"):
            return updates
    radixark = _detect_radixark_sglang(env, exists, labels, base)
    if radixark and radixark.get("provider"):
        return radixark
    return {}


def _detect_modal(
    env: Mapping[str, str],
    _exists: FileExists,
    _labels: Mapping[str, str],
    base: Mapping[str, Any],
) -> dict[str, Any] | None:
    if not env.get("MODAL_TASK_ID"):
        return None

    cluster_info = _modal_cluster_info()
    container_ips = _as_list(_get_value(cluster_info, "container_ips")) or _as_list(
        _get_value(cluster_info, "container_ipv4_ips")
    )
    modal_rank = _optional_int(_stringify(_get_value(cluster_info, "rank")))
    modal_cluster_id = _stringify(_get_value(cluster_info, "cluster_id"))
    world_size = len(container_ips) if container_ips else _optional_int(env.get("WORLD_SIZE"))
    node_count = max(1, world_size or int(base["node_count"]))
    rank = modal_rank if modal_rank is not None else _optional_int(env.get("RANK"))

    return {
        "provider": "modal",
        "modal_task_id": env.get("MODAL_TASK_ID"),
        "modal_sandbox_id": env.get("MODAL_SANDBOX_ID"),
        "modal_cloud_provider": env.get("MODAL_CLOUD_PROVIDER"),
        "modal_region": env.get("MODAL_REGION"),
        "modal_sandbox": bool(env.get("MODAL_SANDBOX_ID")),
        "modal_cluster_rank": rank,
        "modal_cluster_id": modal_cluster_id,
        "rank": rank,
        "world_size": world_size,
        "node_count": node_count,
        "is_multi_node": bool((world_size or 1) > 1 or base["is_multi_node"]),
    }


def _detect_crusoe(
    env: Mapping[str, str],
    _exists: FileExists,
    labels: Mapping[str, str],
    base: Mapping[str, Any],
) -> dict[str, Any] | None:
    node_type = _find_crusoe_node_type(env, labels)
    has_crusoe_hint = any(key.startswith("CRUSOE_") for key in env) or _haystack_contains(
        env,
        "crusoe",
    )
    if not node_type and not (has_crusoe_hint and bool(base["is_kubernetes"])):
        return None

    return {
        "provider": "crusoe",
        "crusoe_node_type": node_type,
        "crusoe_managed_via": "slinky-cmk",
        "is_kubernetes": bool(base["is_kubernetes"]) or "SLURM_JOB_ID" in env,
    }


def _detect_coreweave(
    env: Mapping[str, str],
    _exists: FileExists,
    labels: Mapping[str, str],
    base: Mapping[str, Any],
) -> dict[str, Any] | None:
    values = {
        field: labels.get(label_key) or env.get(_env_name_for_label(label_key))
        for field, label_key in _COREWEAVE_LABELS.items()
    }
    if not any(values.values()):
        return None
    orchestrator = "sunk" if bool(base["is_kubernetes"]) and bool(base["is_slurm"]) else "cks"

    return {
        "provider": "coreweave",
        "coreweave_rack_id": values["coreweave_rack_id"],
        "coreweave_nvlink_domain": values["coreweave_nvlink_domain"],
        "coreweave_ib_fabric": values["coreweave_ib_fabric"],
        "coreweave_superpod": values["coreweave_superpod"],
        "coreweave_orchestrator": orchestrator,
        "is_kubernetes": True,
    }


def _detect_lambda(
    env: Mapping[str, str],
    _exists: FileExists,
    labels: Mapping[str, str],
    base: Mapping[str, Any],
) -> dict[str, Any] | None:
    lambda_keys = [
        key for key in env if key.startswith("LAMBDA_") and key not in _LAMBDA_SERVERLESS_KEYS
    ]
    hostname = env.get("HOSTNAME", "").lower()
    label_haystack = " ".join(labels.values()).lower()
    hostname_signal = any(
        token in hostname for token in ("lambda-cloud", "lambda-gpu", "lambda-1click", "one-click")
    )
    label_signal = "lambda" in label_haystack and (
        "1click" in label_haystack or "one-click" in label_haystack
    )
    one_click = (
        _truthy(_first(env, "LAMBDA_ONE_CLICK", "LAMBDA_1CLICK_CLUSTER"))
        or hostname_signal
        or label_signal
    )
    fallback_k8s_ib = bool(base["is_kubernetes"]) and _has_infiniband_signal(env)
    if not (lambda_keys or hostname_signal or label_signal or fallback_k8s_ib):
        return None

    return {
        "provider": "lambda",
        "lambda_one_click": bool(one_click or lambda_keys),
        "lambda_cluster_id": _first(env, "LAMBDA_CLUSTER_ID", "LAMBDA_ONE_CLICK_CLUSTER_ID"),
        "is_kubernetes": bool(base["is_kubernetes"]),
    }


def _detect_fireworks(
    env: Mapping[str, str],
    _exists: FileExists,
    _labels: Mapping[str, str],
    _base: Mapping[str, Any],
) -> dict[str, Any] | None:
    endpoint_keys = (
        "FIREWORKS_API_BASE",
        "FIREWORKS_BASE_URL",
        "OPENAI_BASE_URL",
        "INFERGUARD_TARGET_URL",
        "INFERGUARD_PREFILL_URL",
        "INFERGUARD_DECODE_URL",
        "PREFILL_URL",
        "DECODE_URL",
    )
    endpoint = next(
        (env[key] for key in endpoint_keys if "fireworks.ai" in env.get(key, "").lower()),
        None,
    )
    if not endpoint:
        return None
    return {
        "target_provider": "fireworks",
        "fireworks_endpoint": endpoint,
    }


def _detect_radixark_sglang(
    env: Mapping[str, str],
    _exists: FileExists,
    _labels: Mapping[str, str],
    _base: Mapping[str, Any],
) -> dict[str, Any] | None:
    has_sglang_env = any(key.startswith("SGLANG_") for key in env)
    text = " ".join(str(value) for value in env.values()).lower()
    has_sglang_text = "sglang" in text
    metrics_enabled = _truthy(_first(env, "SGLANG_ENABLE_METRICS", "SGLANG_METRICS_ENABLED"))
    metrics_enabled = metrics_enabled or "--enable-metrics" in text
    commercial_signal = (
        any(key.startswith("RADIXARK_") for key in env)
        or "radixark" in text
        or _truthy(env.get("SGLANG_COMMERCIAL"))
    )

    if not (has_sglang_env or has_sglang_text or metrics_enabled or commercial_signal):
        return None

    updates: dict[str, Any] = {
        "engine_provider": "sglang",
        "sglang_metrics_enabled": bool(metrics_enabled),
    }
    if commercial_signal:
        updates.update(
            {
                "provider": "radixark",
                "radixark_deployment_id": _first(
                    env,
                    "RADIXARK_DEPLOYMENT_ID",
                    "SGLANG_DEPLOYMENT_ID",
                ),
            }
        )
    return updates


def _detect_gmi(
    env: Mapping[str, str],
    _exists: FileExists,
    _labels: Mapping[str, str],
    base: Mapping[str, Any],
) -> dict[str, Any] | None:
    scratch_path = str(base["scratch_path"]) if base.get("scratch_path") else None
    has_gmi = _contains_gmi(env)
    gpu_model = _first(env, "NVIDIA_GPU_NAME", "GPU_MODEL", "ACCELERATOR_MODEL")
    if scratch_path == "/data" and not (has_gmi or gpu_model or base.get("gpu_count")):
        return None
    if not (has_gmi or scratch_path):
        return None

    if bool(base["is_kubernetes"]):
        mode = "k8s"
    elif bool(base["is_docker"]) or _truthy(env.get("IN_CONTAINER")) or env.get("CONTAINER_IMAGE"):
        mode = "caas"
    else:
        mode = "bare-metal"

    return {
        "provider": "gmi",
        "is_gmi": True,
        "gmi_mode": mode,
        "gmi_gpu_model": gpu_model,
    }


def _metadata_only(updates: Mapping[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in updates.items() if key != "provider"}


def _final_multi_node(data: Mapping[str, Any]) -> bool:
    world_size = data.get("world_size")
    node_count = data.get("node_count")
    return bool(
        data.get("is_multi_node")
        or (isinstance(world_size, int) and world_size > 1)
        or (isinstance(node_count, int) and node_count > 1)
    )


def _modal_cluster_info() -> Any | None:
    try:
        modal_experimental = __import__("modal.experimental", fromlist=["get_cluster_info"])
    except Exception:
        return None
    try:
        return modal_experimental.get_cluster_info()
    except Exception:
        return None


def _get_value(source: Any, key: str) -> Any | None:
    if source is None:
        return None
    if isinstance(source, Mapping):
        return source.get(key)
    return getattr(source, key, None)


def _stringify(value: Any | None) -> str | None:
    if value is None:
        return None
    return str(value)


def _as_list(value: Any | None) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return [value]


def _detect_kubernetes_labels(env: Mapping[str, str], exists: FileExists) -> dict[str, str]:
    labels: dict[str, str] = {}
    for key, value in env.items():
        if key in _COREWEAVE_LABELS.values():
            labels[key] = value
        if key.startswith("POD_LABEL_") or key.startswith("KUBERNETES_LABEL_"):
            labels[_label_name_from_env(key)] = value
    for key in ("KUBERNETES_POD_LABELS", "POD_LABELS", "K8S_POD_LABELS"):
        labels.update(_parse_label_blob(env.get(key, "")))

    label_file = env.get("INFERGUARD_K8S_LABELS_FILE") or "/etc/podinfo/labels"
    if exists(label_file):
        try:
            labels.update(_parse_label_blob(Path(label_file).read_text(encoding="utf-8")))
        except OSError:
            pass
    return labels


def _parse_label_blob(blob: str) -> dict[str, str]:
    labels: dict[str, str] = {}
    for raw_item in re.split(r"[\n;,]+", blob):
        item = raw_item.strip()
        if not item or item.startswith("#") or "=" not in item:
            continue
        key, value = item.split("=", 1)
        labels[key.strip().strip('"')] = value.strip().strip('"')
    return labels


def _label_name_from_env(key: str) -> str:
    name = re.sub(r"^(POD_LABEL_|KUBERNETES_LABEL_)", "", key)
    return name.lower().replace("__", "/").replace("_", ".")


def _env_name_for_label(label_key: str) -> str:
    return f"POD_LABEL_{label_key.upper().replace('/', '__').replace('.', '_').replace('-', '_')}"


def _find_crusoe_node_type(env: Mapping[str, str], labels: Mapping[str, str]) -> str | None:
    haystack = " ".join([*env.values(), *labels.values()]).lower()
    for node_type in _CRUSOE_NODE_TYPES:
        if node_type in haystack:
            return node_type
    for key in ("CRUSOE_NODE_TYPE", "SLURM_NODE_TYPE", "NODE_TYPE", "INSTANCE_TYPE"):
        value = env.get(key, "").lower()
        if value:
            return value
    return None


def _haystack_contains(env: Mapping[str, str], needle: str) -> bool:
    needle = needle.lower()
    return any(needle in key.lower() or needle in value.lower() for key, value in env.items())


def _has_infiniband_signal(env: Mapping[str, str]) -> bool:
    if any(env.get(key) for key in ("NCCL_IB_HCA", "UCX_NET_DEVICES", "INFINIBAND_DEVICE")):
        return True
    return any("infiniband" in value.lower() for value in env.values())


def _expand_nodelist(value: str) -> list[str]:
    if not value:
        return []
    # Handles common Slurm forms like node[01-03,07] and leaves complex forms intact.
    match = re.fullmatch(r"([^\[]+)\[([^\]]+)\]", value)
    if not match:
        return [item for item in value.split(",") if item]
    prefix, ranges = match.groups()
    nodes: list[str] = []
    for part in ranges.split(","):
        if "-" not in part:
            nodes.append(f"{prefix}{part}")
            continue
        start, end = part.split("-", 1)
        width = max(len(start), len(end))
        for number in range(int(start), int(end) + 1):
            nodes.append(f"{prefix}{number:0{width}d}")
    return nodes


__all__ = ["EnvironmentAdapter", "RigContext"]

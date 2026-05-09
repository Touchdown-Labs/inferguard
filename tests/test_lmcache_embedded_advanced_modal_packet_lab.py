from __future__ import annotations

import importlib.util
import json
import sys
import types
from pathlib import Path


def _load_lab_module():
    module_name = "_lmcache_embedded_advanced_modal_packet_lab_test"
    if module_name in sys.modules:
        return sys.modules[module_name]

    class _FakeImage:
        def __init__(self):
            self.calls = []

        @classmethod
        def debian_slim(cls, **kwargs):
            image = cls()
            image.calls.append(("debian_slim", (), kwargs))
            return image

        @classmethod
        def from_registry(cls, *args, **kwargs):
            image = cls()
            image.calls.append(("from_registry", args, kwargs))
            return image

        def apt_install(self, *args):
            self.calls.append(("apt_install", args, {}))
            return self

        def pip_install(self, *args):
            self.calls.append(("pip_install", args, {}))
            return self

        def add_local_file(self, **kwargs):
            self.calls.append(("add_local_file", (), kwargs))
            return self

        def add_local_dir(self, **kwargs):
            self.calls.append(("add_local_dir", (), kwargs))
            return self

        def run_commands(self, *args):
            self.calls.append(("run_commands", args, {}))
            return self

        def env(self, env):
            self.calls.append(("env", (env,), {}))
            return self

    class _FakeVolume:
        @classmethod
        def from_name(cls, *_args, **_kwargs):
            return cls()

        def commit(self):
            return None

    class _FakeApp:
        def __init__(self, *_args, **_kwargs):
            pass

        def function(self, *_args, **_kwargs):
            return lambda fn: fn

        def local_entrypoint(self):
            return lambda fn: fn

    fake_modal = types.SimpleNamespace(Image=_FakeImage, Volume=_FakeVolume, App=_FakeApp)
    sys.modules["modal"] = fake_modal

    path = Path(__file__).resolve().parents[1] / "scripts" / "lmcache_embedded_advanced_modal_packet_lab.py"
    spec = importlib.util.spec_from_file_location(module_name, path)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_embedded_advanced_image_uses_cuda_devel_base_for_local_lmcache_build() -> None:
    lab = _load_lab_module()

    calls = lab.image.calls
    from_registry_args = next(args for name, args, _kwargs in calls if name == "from_registry")
    assert from_registry_args == (lab.CUDA_DEVEL_IMAGE,)
    apt_install_args = next(args for name, args, _kwargs in calls if name == "apt_install")
    assert "build-essential" in apt_install_args
    env_index = next(index for index, (name, _args, _kwargs) in enumerate(calls) if name == "env")
    run_commands_index = next(
        index for index, (name, _args, _kwargs) in enumerate(calls) if name == "run_commands"
    )
    assert env_index < run_commands_index
    runtime_env = calls[env_index][1][0]
    assert runtime_env["CUDA_HOME"] == "/usr/local/cuda"
    assert runtime_env["TORCH_CUDA_ARCH_LIST"] == "9.0"


def test_embedded_advanced_image_avoids_shared_unpinned_runtime_backtracking() -> None:
    lab = _load_lab_module()

    calls = lab.image.calls
    pip_install_args = next(args for name, args, _kwargs in calls if name == "pip_install")
    forbidden_unpinned = {"vllm", "lmcache", "sglang", "transformers"}
    assert not (forbidden_unpinned & set(pip_install_args))
    assert lab.PINNED_VLLM_PACKAGE == "vllm==0.10.2"
    assert lab.PINNED_TRANSFORMERS_PACKAGE == "transformers==4.57.6"
    assert lab.PINNED_TOKENIZERS_PACKAGE == "tokenizers==0.22.2"
    assert lab.PINNED_TRANSFORMERS_PACKAGE in pip_install_args
    assert lab.PINNED_TOKENIZERS_PACKAGE in pip_install_args
    assert any(arg.startswith("vllm==") for arg in pip_install_args)
    assert "sglang" not in pip_install_args
    assert "lmcache" not in pip_install_args
    run_commands_args = next(args for name, args, _kwargs in calls if name == "run_commands")
    assert lab.LMCACHE_LOCAL_INSTALL_COMMAND in run_commands_args
    assert lab.LMCACHE_LOCAL_INSTALL_COMMAND.endswith("--no-build-isolation --no-deps")


def test_h1_uses_tiny_qwen3_tokenizer_with_vllm_compatible_transformers_pin() -> None:
    lab = _load_lab_module()

    assert lab.MODEL == "Qwen/Qwen3-0.6B"
    assert lab.MODEL_MAX_LEN == 8192
    assert lab.PINNED_TRANSFORMERS_PACKAGE == "transformers==4.57.6"
    assert lab.PINNED_TOKENIZERS_PACKAGE == "tokenizers==0.22.2"


def test_h1_image_installs_minimal_lmcache_runtime_deps_without_lifting_tokenizer_pins() -> None:
    lab = _load_lab_module()

    calls = lab.image.calls
    pip_install_args = next(args for name, args, _kwargs in calls if name == "pip_install")
    run_commands_args = next(args for name, args, _kwargs in calls if name == "run_commands")

    assert lab.LMCACHE_LOCAL_INSTALL_COMMAND.endswith("--no-build-isolation --no-deps")
    assert lab.LMCACHE_RUNTIME_DEP_PACKAGES == (
        "aiofile",
        "aiofiles",
        "msgspec",
        "prometheus-client>=0.18.0,<=0.24.1",
        "psutil",
        "opentelemetry-api>=1.20.0,<=1.40.0",
        "opentelemetry-sdk>=1.20.0",
        "opentelemetry-exporter-otlp>=1.20.0",
        "opentelemetry-exporter-prometheus>=0.50b0,<=0.61b0",
        "py-cpuinfo",
        "pyyaml",
        "pyzmq>=25.0.0",
        "sortedcontainers==2.4.0",
    )
    for package in lab.LMCACHE_RUNTIME_DEP_PACKAGES:
        assert package in pip_install_args
    assert "aiofile" in pip_install_args
    assert "aiofiles" in pip_install_args
    assert "sortedcontainers==2.4.0" in pip_install_args
    assert lab.PINNED_TRANSFORMERS_PACKAGE in pip_install_args
    assert lab.PINNED_TOKENIZERS_PACKAGE in pip_install_args
    assert "transformers>=5.4" not in pip_install_args
    assert "python -m pip install -r /opt/lmcache/requirements/common.txt" not in run_commands_args


def test_h2_image_installs_minimal_sglang_runtime_deps_without_lifting_vllm_pins() -> None:
    lab = _load_lab_module()

    calls = lab.image.calls
    pip_install_args = next(args for name, args, _kwargs in calls if name == "pip_install")
    run_commands_args = next(args for name, args, _kwargs in calls if name == "run_commands")

    assert lab.SGLANG_RUNTIME_DEP_PACKAGES == ("orjson", "IPython")
    assert "orjson" in pip_install_args
    assert "IPython" in pip_install_args
    assert lab.PINNED_VLLM_PACKAGE in pip_install_args
    assert lab.PINNED_TRANSFORMERS_PACKAGE in pip_install_args
    assert lab.PINNED_TOKENIZERS_PACKAGE in pip_install_args
    assert "torch==2.11.0" not in pip_install_args
    assert "transformers==5.6.0" not in pip_install_args
    assert lab.SGLANG_LOCAL_INSTALL_COMMAND in run_commands_args
    assert lab.SGLANG_LOCAL_INSTALL_COMMAND.endswith("--no-build-isolation --no-deps")
    assert "python -m pip install -r /opt/sglang/python/requirements.txt" not in run_commands_args


def test_embedded_advanced_image_installs_current_local_inferguard_source() -> None:
    lab = _load_lab_module()

    assert lab.REPO_ROOT == Path(__file__).resolve().parents[1]
    assert lab.MODAL_INFERGUARD_SOURCE == "/opt/inferguard"
    assert lab.MODAL_INFERGUARD_FILES == ("pyproject.toml", "README.md", "LICENSE")
    assert lab.MODAL_INFERGUARD_PACKAGE_DIR == "src/inferguard"
    assert lab.INFERGUARD_LOCAL_INSTALL_COMMAND == "python -m pip install -e /opt/inferguard"

    calls = lab.image.calls
    pip_install_args = next(args for name, args, _kwargs in calls if name == "pip_install")
    assert "inferguard" not in pip_install_args
    assert any(arg.startswith("vllm==") for arg in pip_install_args)
    assert "lmcache" not in pip_install_args
    assert "sglang" not in pip_install_args

    add_local_dirs = [kwargs for name, _args, kwargs in calls if name == "add_local_dir"]
    add_local_dir = next(
        kwargs
        for kwargs in add_local_dirs
        if kwargs["remote_path"] == f"{lab.MODAL_INFERGUARD_SOURCE}/{lab.MODAL_INFERGUARD_PACKAGE_DIR}"
    )
    assert add_local_dir == {
        "local_path": str(lab.REPO_ROOT / lab.MODAL_INFERGUARD_PACKAGE_DIR),
        "remote_path": f"{lab.MODAL_INFERGUARD_SOURCE}/{lab.MODAL_INFERGUARD_PACKAGE_DIR}",
        "copy": True,
        "ignore": lab.MODAL_SOURCE_IGNORE,
    }
    assert "**/__pycache__/**" in lab.MODAL_SOURCE_IGNORE
    assert "**/*.pyc" in lab.MODAL_SOURCE_IGNORE
    run_commands_args = next(args for name, args, _kwargs in calls if name == "run_commands")
    assert run_commands_args[-1] == lab.INFERGUARD_LOCAL_INSTALL_COMMAND
    assert any("pip install -e /opt/lmcache" in command for command in run_commands_args)


def test_packet_specs_cover_h1_h2_h3_without_claiming_live_validation() -> None:
    lab = _load_lab_module()

    specs = lab.packet_specs()

    assert set(specs) == {"h1", "h2", "h3-cacheblend", "h3-p2p", "h3-pd"}
    assert specs["h1"].sdlc_id == "H1"
    assert specs["h2"].sdlc_id == "H2"
    assert {specs[key].sdlc_id for key in ("h3-cacheblend", "h3-p2p", "h3-pd")} == {"H3"}
    assert all(
        spec.score_status == "runner_scaffold_only_not_live_validated" for spec in specs.values()
    )


def test_h1_vllm_embedded_command_uses_current_lmcacheconnectorv1_contract(tmp_path: Path) -> None:
    lab = _load_lab_module()
    spec = lab.PACKETS["h1"]

    cmd = lab._build_vllm_embedded_command(tmp_path, spec)
    env = lab._build_runner_env(tmp_path, spec)
    lab._write_lmcache_config(tmp_path, spec)
    proof_path = lab._write_launch_proof(tmp_path, spec)

    assert cmd[:3] == ["vllm", "serve", lab.MODEL]
    assert "--kv-offloading-backend" not in cmd
    assert "lmcache" not in cmd
    assert "--kv-transfer-config" in cmd
    transfer_config = json.loads(cmd[cmd.index("--kv-transfer-config") + 1])
    assert transfer_config == {"kv_connector": "LMCacheConnectorV1", "kv_role": "kv_both"}
    assert "LMCacheMPConnector" not in json.dumps(cmd)
    assert env["LMCACHE_CONFIG_FILE"] == str(tmp_path / lab.LMCACHE_CONFIG_FILE)
    assert env["PROMETHEUS_MULTIPROC_DIR"] == str(tmp_path / lab.PROMETHEUS_MULTIPROC_DIRNAME)

    config = json.loads((tmp_path / lab.LMCACHE_CONFIG_FILE).read_text(encoding="utf-8"))
    proof = json.loads(proof_path.read_text(encoding="utf-8"))
    assert "LMCacheConnectorV1" in config["expected_connector_evidence"]
    assert "--kv-transfer-config" in config["expected_connector_evidence"]
    assert proof["expect_lmcache_mode"] == "embedded"
    assert proof["claim_status"] == "runner_scaffold_only_not_live_validated"
    assert proof["environment"]["PROMETHEUS_MULTIPROC_DIR"] == str(
        tmp_path / lab.PROMETHEUS_MULTIPROC_DIRNAME
    )
    assert any("LMCacheConnectorV1" in item for item in proof["required_live_proof"])


def test_h1_prepares_shared_prometheus_multiproc_dir_for_embedded_metrics(tmp_path: Path) -> None:
    lab = _load_lab_module()
    metrics_dir = tmp_path / lab.PROMETHEUS_MULTIPROC_DIRNAME
    metrics_dir.mkdir()
    stale = metrics_dir / "counter_123.db"
    stale.write_text("stale", encoding="utf-8")

    prepared = lab._prepare_prometheus_multiproc_dir(tmp_path)

    assert prepared == metrics_dir
    assert prepared.exists()
    assert list(prepared.iterdir()) == []


def test_h2_sglang_source_binding_is_exported_into_modal_runtime() -> None:
    lab = _load_lab_module()

    calls = lab.image.calls
    env_call = next(args for name, args, _kwargs in calls if name == "env")
    runtime_env = env_call[0]
    run_commands_args = next(args for name, args, _kwargs in calls if name == "run_commands")

    assert lab.SGLANG_LOCAL_SOURCE is not None
    assert runtime_env[lab.SGLANG_LOCAL_SOURCE_ENV] == lab.MODAL_SGLANG_SOURCE
    assert runtime_env["INFERGUARD_H_SGLANG_SOURCE_REF"] == str(lab.SGLANG_LOCAL_SOURCE)
    assert lab.SGLANG_LOCAL_INSTALL_COMMAND in run_commands_args
    assert lab.SGLANG_LOCAL_INSTALL_COMMAND.endswith("--no-build-isolation --no-deps")


def test_h2_sglang_command_uses_enable_lmcache_and_layerwise_evidence(tmp_path: Path) -> None:
    lab = _load_lab_module()
    spec = lab.PACKETS["h2"]

    cmd = lab._build_sglang_embedded_command()
    lab._write_lmcache_config(tmp_path, spec)
    proof_path = lab._write_launch_proof(tmp_path, spec)

    assert cmd[:3] == ["python3", "-m", "sglang.launch_server"]
    assert "--enable-lmcache" in cmd
    assert cmd[cmd.index("--model-path") + 1] == lab.MODEL
    config = json.loads((tmp_path / lab.LMCACHE_CONFIG_FILE).read_text(encoding="utf-8"))
    proof = json.loads(proof_path.read_text(encoding="utf-8"))
    assert "LMCacheLayerwiseConnector" in config["expected_connector_evidence"]
    assert "LMCRadixCache" in config["expected_cache_evidence"]
    assert proof["expected_engine"] == "sglang"
    assert any("LMCacheLayerwiseConnector" in item for item in proof["required_live_proof"])


def test_h3_cacheblend_wires_otel_and_cacheblend_reports(tmp_path: Path) -> None:
    lab = _load_lab_module()
    spec = lab.PACKETS["h3-cacheblend"]
    packet_dir = tmp_path / "lmcache-packet"
    packet_dir.mkdir()
    (tmp_path / lab.LMCACHE_OTEL_FILE).write_text('{"name":"cb.lookup"}\n', encoding="utf-8")
    (packet_dir / "lmcache_otel_evidence.json").write_text(
        '{"claim_status":"measured"}', encoding="utf-8"
    )

    env = lab._build_runner_env(tmp_path, spec)
    lab._write_lmcache_config(tmp_path, spec)
    collect = lab._build_collect_lmcache_cmd(tmp_path, spec)
    compat = lab._build_lmcache_compat_cmd(tmp_path, spec)
    coverage = lab._build_observability_coverage_cmd(tmp_path, spec)

    assert env["INFERGUARD_H3_REGISTER_VLLM_MODEL"] == "1"
    assert env["PYTHONPATH"] == str(tmp_path)
    assert env["LMCACHE_ENABLE_BLENDING"] == "True"
    assert env["LMCACHE_USE_LAYERWISE"] == "True"
    assert env["OTEL_EXPORTER_OTLP_ENDPOINT"] == f"http://127.0.0.1:{lab.OTLP_GRPC_PORT}"
    assert collect[collect.index("--lmcache-otel-file") + 1] == str(
        tmp_path / lab.LMCACHE_OTEL_FILE
    )
    assert compat[compat.index("--expect-mode") + 1] == "auto"
    assert compat[compat.index("--lmcache-otel-evidence-file") + 1] == str(
        packet_dir / "lmcache_otel_evidence.json"
    )
    assert coverage[coverage.index("--expect-lmcache-mode") + 1] == "auto"
    assert coverage[coverage.index("--lmcache-otel-evidence-file") + 1] == str(
        packet_dir / "lmcache_otel_evidence.json"
    )
    assert "--external-cache-configured" in coverage
    config = json.loads((tmp_path / lab.LMCACHE_CONFIG_FILE).read_text(encoding="utf-8"))
    assert config["enable_blending"] is True
    assert config["use_layerwise"] is True
    assert lab.LMCACHE_OTEL_FILE in lab._required_artifacts(spec)
    assert "vllm_cacheblend_model_tracker_patch.json" in lab._required_artifacts(spec)


def test_h3_cacheblend_model_tracker_patch_registers_loaded_vllm_model(tmp_path: Path) -> None:
    lab = _load_lab_module()

    source = lab._patch_vllm_cacheblend_model_tracker.__doc__ or ""
    patch_log = lab._patch_vllm_cacheblend_model_tracker(tmp_path)
    sitecustomize = tmp_path / "sitecustomize.py"
    patch = json.loads(patch_log.read_text(encoding="utf-8"))
    sitecustomize_text = sitecustomize.read_text(encoding="utf-8")

    assert "VLLMModelTracker.get_model(ENGINE_NAME)" in source
    assert "GPUWorker.load_model" in source
    assert patch_log.name == "vllm_cacheblend_model_tracker_patch.json"
    assert sitecustomize.exists()
    assert patch["patch_target"] == str(sitecustomize)
    assert patch["engine_name"] == "vllm-instance"
    assert patch["applied"] is True
    assert "INFERGUARD_H3_REGISTER_VLLM_MODEL" in sitecustomize_text
    assert "from lmcache.integration.vllm.utils import ENGINE_NAME" in sitecustomize_text
    assert "VLLMModelTracker.register_model(ENGINE_NAME, self.model_runner.model)" in sitecustomize_text


def test_h3_cacheblend_model_tracker_patch_is_created_before_engine_launch(tmp_path: Path, monkeypatch) -> None:
    lab = _load_lab_module()
    spec = lab.PACKETS["h3-cacheblend"]
    events: list[str] = []

    def fake_patch(run_dir: Path):
        events.append("patch")
        path = run_dir / "vllm_cacheblend_model_tracker_patch.json"
        path.write_text("{}", encoding="utf-8")
        (run_dir / "sitecustomize.py").write_text("", encoding="utf-8")
        return path

    def fake_launch(*_args, **_kwargs):
        events.append("launch")
        raise RuntimeError("stop before Modal engine launch")

    monkeypatch.setattr(lab, "OUT_ROOT", tmp_path)
    monkeypatch.setattr(lab, "_patch_vllm_cacheblend_model_tracker", fake_patch)
    monkeypatch.setattr(lab, "_prepare_prometheus_multiproc_dir", lambda _run_dir: None)
    monkeypatch.setattr(lab, "_write_env_snapshot", lambda _run_dir: None)
    monkeypatch.setattr(lab, "_write_lmcache_config", lambda run_dir, _spec: run_dir / lab.LMCACHE_CONFIG_FILE)
    monkeypatch.setattr(lab, "_write_launch_proof", lambda run_dir, _spec: run_dir / lab.RUNNER_PROOF_FILE)
    monkeypatch.setattr(lab, "_start_otel_collector", lambda _run_dir: (None, None))
    monkeypatch.setattr(lab, "_launch_engine", fake_launch)
    monkeypatch.setattr(lab, "_terminate", lambda _proc: None)
    monkeypatch.setattr(lab, "_close_handles", lambda _handles: None)
    monkeypatch.setattr(lab.volume, "commit", lambda: None)

    try:
        lab._run_packet(spec)
    except RuntimeError as exc:
        assert "stop before Modal engine launch" in str(exc)
    else:
        raise AssertionError("expected fake launch to stop packet run")

    assert events == ["patch", "launch"]


def test_h3_p2p_writes_two_engine_peer_scaffold(tmp_path: Path) -> None:
    lab = _load_lab_module()
    spec = lab.PACKETS["h3-p2p"]

    primary_env = lab._build_runner_env(tmp_path, spec)
    secondary_env = lab._build_runner_env(tmp_path, spec, role="secondary")
    proof_path = lab._write_launch_proof(tmp_path, spec)
    coverage = lab._build_observability_coverage_cmd(tmp_path, spec)

    assert primary_env["LMCACHE_ENABLE_P2P"] == "True"
    assert primary_env["LMCACHE_INSTANCE_ID"] == "inferguard-peer-a"
    assert secondary_env["LMCACHE_INSTANCE_ID"] == "inferguard-peer-b"
    assert primary_env["PYTHONHASHSEED"] == "0"
    assert secondary_env["PYTHONHASHSEED"] == "0"
    proof = json.loads(proof_path.read_text(encoding="utf-8"))
    assert proof["secondary_command"] is not None
    assert proof["secondary_environment"]["LMCACHE_ENABLE_P2P"] == "True"
    assert "secondary_engine.log" in lab._required_artifacts(spec)
    assert "combined_engine_metrics_loaded.prom" in lab._required_artifacts(spec)
    assert any(
        item.endswith("combined_engine_metrics_loaded.prom")
        for item in lab._build_collect_lmcache_cmd(tmp_path, spec)
    )
    assert any(
        item.endswith("combined_engine_metrics_loaded.prom")
        for item in lab._build_lmcache_compat_cmd(tmp_path, spec)
    )
    assert any(item.endswith("combined_engine_metrics_loaded.prom") for item in coverage)
    assert "--disaggregated-or-external-cache" in coverage
    assert coverage[coverage.index("--expect-lmcache-mode") + 1] == "embedded"


def test_combined_secondary_metrics_file_preserves_primary_and_secondary(tmp_path: Path) -> None:
    lab = _load_lab_module()
    (tmp_path / "engine_metrics_loaded.prom").write_text("vllm:prefix_cache_hits_total 1\n", encoding="utf-8")
    (tmp_path / "secondary_engine_metrics_loaded.prom").write_text(
        "vllm:kv_transfer_recv_bytes_total 2\n", encoding="utf-8"
    )

    combined = lab._write_combined_metrics(tmp_path, "loaded")

    text = combined.read_text(encoding="utf-8")
    assert "inferguard_source_file=engine_metrics_loaded.prom" in text
    assert "inferguard_source_file=secondary_engine_metrics_loaded.prom" in text
    assert "vllm:prefix_cache_hits_total 1" in text
    assert "vllm:kv_transfer_recv_bytes_total 2" in text


def test_h3_pd_writes_prefill_decode_nixl_scaffold(tmp_path: Path) -> None:
    lab = _load_lab_module()
    spec = lab.PACKETS["h3-pd"]

    primary_cmd = lab._build_engine_command(tmp_path, spec, port=spec.primary_port)
    secondary_cmd = lab._build_engine_command(tmp_path, spec, role="secondary", port=spec.secondary_port)
    primary_env = lab._build_runner_env(tmp_path, spec)
    secondary_env = lab._build_runner_env(tmp_path, spec, role="secondary")
    proof_path = lab._write_launch_proof(tmp_path, spec)

    assert "--kv-transfer-config" in primary_cmd
    assert "NixlConnector" in primary_cmd[primary_cmd.index("--kv-transfer-config") + 1]
    assert "kv_producer" in primary_cmd[primary_cmd.index("--kv-transfer-config") + 1]
    assert "kv_consumer" in secondary_cmd[secondary_cmd.index("--kv-transfer-config") + 1]
    assert primary_env["LMCACHE_ENABLE_PD"] == "True"
    assert primary_env["LMCACHE_PD_ROLE"] == "prefill"
    assert secondary_env["LMCACHE_PD_ROLE"] == "decode"
    assert primary_env["LMCACHE_NIXL_ROLE"] == "producer"
    assert secondary_env["LMCACHE_NIXL_ROLE"] == "consumer"
    proof = json.loads(proof_path.read_text(encoding="utf-8"))
    assert any("NIXL" in item for item in proof["required_live_proof"])
    assert proof["secondary_environment"]["LMCACHE_PD_ROLE"] == "decode"


def test_summary_marks_missing_required_and_score_status(tmp_path: Path) -> None:
    lab = _load_lab_module()
    spec = lab.PACKETS["h1"]
    (tmp_path / "env.txt").write_text("python", encoding="utf-8")

    lab._write_summary_and_index(tmp_path, spec)

    summary = (tmp_path / "summary.md").read_text(encoding="utf-8")
    index = json.loads((tmp_path / "artifact_index.json").read_text(encoding="utf-8"))
    assert "Score status: `runner_scaffold_only_not_live_validated`" in summary
    assert "## Missing Required" in summary
    assert "`engine.log`" in summary
    assert any(item["path"] == "env.txt" for item in index)


def test_embedded_advanced_packet_command_script_lists_exact_modal_functions() -> None:
    path = Path(__file__).resolve().parents[1] / "scripts" / "lmcache_embedded_advanced_packet_commands.py"
    spec = importlib.util.spec_from_file_location("_lmcache_embedded_advanced_packet_commands_test", path)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)

    commands = module.packet_commands()
    assert commands["H1"] == (
        "modal run scripts/lmcache_embedded_advanced_modal_packet_lab.py::"
        "run_packet_h1_embedded_vllm"
    )
    assert commands["H2"].endswith("::run_packet_h2_sglang_embedded")
    assert commands["H3-cacheblend"].endswith("::run_packet_h3_cacheblend")
    assert commands["H3-p2p"].endswith("::run_packet_h3_p2p")
    assert commands["H3-pd"].endswith("::run_packet_h3_pd")


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
    assert pip_install_args == lab._modal_runtime_packages()
    assert "vllm" in pip_install_args
    assert "lmcache" in pip_install_args
    assert "sglang" in pip_install_args
    assert lab._modal_runtime_packages({lab.MODAL_ENGINE_PACKAGES_ENV: "vllm"}) == (
        "vllm",
        "lmcache",
        "hf-transfer",
        "huggingface-hub",
        "nvidia-cuda-runtime-cu12",
    )

    add_local_dir = next(kwargs for name, _args, kwargs in calls if name == "add_local_dir")
    assert add_local_dir == {
        "local_path": str(lab.REPO_ROOT / lab.MODAL_INFERGUARD_PACKAGE_DIR),
        "remote_path": f"{lab.MODAL_INFERGUARD_SOURCE}/{lab.MODAL_INFERGUARD_PACKAGE_DIR}",
        "copy": True,
    }
    run_commands_args = next(args for name, args, _kwargs in calls if name == "run_commands")
    assert run_commands_args == (lab.INFERGUARD_LOCAL_INSTALL_COMMAND,)


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


def test_h1_vllm_embedded_command_uses_lmcacheconnectorv1_path(tmp_path: Path) -> None:
    lab = _load_lab_module()
    spec = lab.PACKETS["h1"]

    cmd = lab._build_vllm_embedded_command(tmp_path, spec)
    env = lab._build_runner_env(tmp_path, spec)
    lab._write_lmcache_config(tmp_path, spec)
    proof_path = lab._write_launch_proof(tmp_path, spec)

    assert cmd[:3] == ["vllm", "serve", lab.MODEL]
    assert cmd[cmd.index("--kv-offloading-backend") + 1] == "lmcache"
    assert "LMCacheMPConnector" not in json.dumps(cmd)
    assert env["LMCACHE_CONFIG_FILE"] == str(tmp_path / lab.LMCACHE_CONFIG_FILE)

    config = json.loads((tmp_path / lab.LMCACHE_CONFIG_FILE).read_text(encoding="utf-8"))
    proof = json.loads(proof_path.read_text(encoding="utf-8"))
    assert "LMCacheConnectorV1" in config["expected_connector_evidence"]
    assert proof["expect_lmcache_mode"] == "embedded"
    assert proof["claim_status"] == "runner_scaffold_only_not_live_validated"
    assert any("LMCacheConnectorV1" in item for item in proof["required_live_proof"])


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
    collect = lab._build_collect_lmcache_cmd(tmp_path, spec)
    compat = lab._build_lmcache_compat_cmd(tmp_path, spec)
    coverage = lab._build_observability_coverage_cmd(tmp_path, spec)

    assert env["LMCACHE_ENABLE_CACHEBLEND"] == "True"
    assert env["LMCACHE_ENABLE_BLENDING"] == "True"
    assert env["LMCACHE_BLEND_SPECIAL_STR"] == " # # "
    assert env["LMCACHE_USE_LAYERWISE"] == "True"
    assert env["LMCACHE_BLEND_CHECK_LAYERS"] == "1"
    assert env["LMCACHE_BLEND_RECOMPUTE_RATIOS"] == "0.15"
    assert json.loads(env["LMCACHE_EXTRA_CONFIG"])["enable_sparse"] is True
    assert env["VLLM_USE_V1"] == "0"
    assert env["OTEL_EXPORTER_OTLP_TRACES_ENDPOINT"].endswith("/v1/traces")
    assert env["OTEL_EXPORTER_OTLP_PROTOCOL"] == "http/protobuf"
    cmd = lab._build_engine_command(tmp_path, spec)
    assert cmd[cmd.index("--kv-offloading-size") + 1] == "8"
    assert "--no-enable-prefix-caching" in cmd
    assert "--disable-hybrid-kv-cache-manager" in cmd
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
    assert lab.LMCACHE_OTEL_FILE in lab._required_artifacts(spec)


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


def test_health_failure_message_includes_service_log_tail(tmp_path: Path, capsys) -> None:
    lab = _load_lab_module()
    service_log = tmp_path / "engine.log"
    service_log.write_text("line1\nline2\nline3\n", encoding="utf-8")

    message = lab._health_failure_message(
        "primary engine",
        "primary engine exited before health passed with code 1",
        service_log,
    )

    captured = capsys.readouterr()
    assert "engine.log" in message
    assert "line1" in message
    assert "line3" in message
    assert "--- primary engine log tail:" in captured.err
    assert "line3" in captured.err


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


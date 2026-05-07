from __future__ import annotations

import importlib.util
import json
import sys
import types
from pathlib import Path


def _load_lab_module():
    module_name = "_lmcache_mp_modal_packet_lab_test"
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

    path = Path(__file__).resolve().parents[1] / "scripts" / "lmcache_mp_modal_packet_lab.py"
    spec = importlib.util.spec_from_file_location(module_name, path)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_modal_image_installs_current_local_inferguard_source() -> None:
    lab = _load_lab_module()

    assert not hasattr(lab, "INFERGUARD_PACKAGE")
    assert lab.REPO_ROOT == Path(__file__).resolve().parents[1]
    assert lab.MODAL_INFERGUARD_SOURCE == "/opt/inferguard"
    assert lab.MODAL_INFERGUARD_FILES == ("pyproject.toml", "README.md", "LICENSE")
    assert lab.MODAL_INFERGUARD_PACKAGE_DIR == "src/inferguard"
    assert lab.INFERGUARD_LOCAL_INSTALL_COMMAND == "python -m pip install -e /opt/inferguard"

    calls = lab.image.calls
    pip_install_args = next(args for name, args, _kwargs in calls if name == "pip_install")
    assert "inferguard" not in pip_install_args
    assert not any("git+https://github.com/Touchdown-Labs/inferguard" in arg for arg in pip_install_args)

    add_local_files = [kwargs for name, _args, kwargs in calls if name == "add_local_file"]
    assert add_local_files == [
        {
            "local_path": str(lab.REPO_ROOT / "pyproject.toml"),
            "remote_path": f"{lab.MODAL_INFERGUARD_SOURCE}/pyproject.toml",
            "copy": True,
        },
        {
            "local_path": str(lab.REPO_ROOT / "README.md"),
            "remote_path": f"{lab.MODAL_INFERGUARD_SOURCE}/README.md",
            "copy": True,
        },
        {
            "local_path": str(lab.REPO_ROOT / "LICENSE"),
            "remote_path": f"{lab.MODAL_INFERGUARD_SOURCE}/LICENSE",
            "copy": True,
        },
    ]
    add_local_dir = next(kwargs for name, _args, kwargs in calls if name == "add_local_dir")
    assert add_local_dir == {
        "local_path": str(lab.REPO_ROOT / lab.MODAL_INFERGUARD_PACKAGE_DIR),
        "remote_path": f"{lab.MODAL_INFERGUARD_SOURCE}/{lab.MODAL_INFERGUARD_PACKAGE_DIR}",
        "copy": True,
    }
    assert add_local_dir["local_path"] != str(lab.REPO_ROOT)
    run_commands_args = next(args for name, args, _kwargs in calls if name == "run_commands")
    assert run_commands_args == (lab.INFERGUARD_LOCAL_INSTALL_COMMAND,)

    call_names = [name for name, _args, _kwargs in calls]
    assert call_names.index("add_local_file") > call_names.index("pip_install")
    assert call_names.index("add_local_dir") > call_names.index("add_local_file")
    assert call_names.index("run_commands") > call_names.index("add_local_dir")


def test_packet_a_lmcache_command_enables_trace_and_lookup_hash(tmp_path: Path) -> None:
    lab = _load_lab_module()

    cmd = lab._build_lmcache_command(tmp_path)

    assert cmd[:2] == ["lmcache", "server"]
    assert cmd[cmd.index("--trace-level") + 1] == "storage"
    assert cmd[cmd.index("--trace-output") + 1] == str(tmp_path / "lmcache_trace.lct")
    assert cmd[cmd.index("--lookup-hash-log-dir") + 1] == str(tmp_path / "lookup_hashes")
    assert cmd[cmd.index("--lookup-hash-log-rotation-interval") + 1] == "21600"
    assert cmd[cmd.index("--lookup-hash-log-rotation-max-size") + 1] == "104857600"
    assert cmd[cmd.index("--lookup-hash-log-max-files") + 1] == "10"
    assert "--metrics-sample-rate" in cmd
    assert cmd[cmd.index("--metrics-sample-rate") + 1] == "1.0"


def test_trace_replay_command_mirrors_required_lmcache_launch_config(tmp_path: Path) -> None:
    lab = _load_lab_module()

    replay = lab._build_trace_replay_command(tmp_path)
    lmcache = lab._build_lmcache_command(tmp_path)

    assert replay[:3] == ["lmcache", "trace", "replay"]
    assert replay[3] == str(tmp_path / "lmcache_trace.lct")
    assert replay[replay.index("--output-dir") + 1] == str(tmp_path / "trace-replay")
    assert replay[replay.index("--jsonl-out") + 1] == str(tmp_path / "trace-replay" / "trace_replay.jsonl")
    assert replay[replay.index("--l1-size-gb") + 1] == lmcache[lmcache.index("--l1-size-gb") + 1]
    assert replay[replay.index("--eviction-policy") + 1] == lmcache[lmcache.index("--eviction-policy") + 1]
    assert "--disable-metrics" in replay


def test_packet_b_uses_sampled_lifecycle_reuse_eviction_workload(tmp_path: Path) -> None:
    lab = _load_lab_module()
    spec = lab.PACKETS["b"]

    cmd = lab._build_lmcache_command(tmp_path, spec)

    assert spec.workload == "reuse_eviction"
    assert cmd[cmd.index("--metrics-sample-rate") + 1] == "1.0"
    assert cmd[cmd.index("--event-bus-queue-size") + 1] == "10000"
    assert cmd[cmd.index("--eviction-policy") + 1] == "LRU"


def test_packet_c_wires_l2_config_and_strict_report_flags(tmp_path: Path) -> None:
    lab = _load_lab_module()
    spec = lab.PACKETS["c"]
    (tmp_path / "lmcache-packet").mkdir()
    (tmp_path / "lmcache-packet" / "lmcache_trace_replay_evidence.json").write_text("{}", encoding="utf-8")

    config_path = lab._write_l2_config(tmp_path, spec)
    env = lab._build_lmcache_env(tmp_path, spec)
    collect = lab._build_collect_lmcache_cmd(tmp_path, spec)
    compat = lab._build_lmcache_compat_cmd(tmp_path, spec)
    coverage = lab._build_observability_coverage_cmd(tmp_path, spec)

    assert config_path == tmp_path / "lmcache_l2_config.json"
    config = json.loads(config_path.read_text(encoding="utf-8"))
    assert config["adapter"] == "fs"
    assert env["LMCACHE_CONFIG_FILE"] == str(config_path)
    assert env["LMCACHE_L2_ADAPTER"] == "fs"
    assert "--l2-configured" in collect
    assert "--l2-configured" in compat
    assert "--l2-configured" in coverage
    assert "lmcache_l2_config.json" in lab._required_artifacts(spec)


def test_packet_d_wires_otel_collector_evidence_into_reports(tmp_path: Path) -> None:
    lab = _load_lab_module()
    spec = lab.PACKETS["d"]
    packet_dir = tmp_path / "lmcache-packet"
    packet_dir.mkdir()
    (tmp_path / "lmcache_otel.jsonl").write_text('{"name":"mp.store"}\n', encoding="utf-8")
    (packet_dir / "lmcache_otel_evidence.json").write_text('{"claim_status":"measured"}', encoding="utf-8")

    cmd = lab._build_lmcache_command(tmp_path, spec)
    env = lab._build_lmcache_env(tmp_path, spec)
    collect = lab._build_collect_lmcache_cmd(tmp_path, spec)
    compat = lab._build_lmcache_compat_cmd(tmp_path, spec)
    coverage = lab._build_observability_coverage_cmd(tmp_path, spec)

    assert "--enable-tracing" in cmd
    assert env["OTEL_EXPORTER_OTLP_TRACES_ENDPOINT"].endswith("/v1/traces")
    assert collect[collect.index("--lmcache-otel-file") + 1] == str(tmp_path / "lmcache_otel.jsonl")
    assert "--mp-tracing-enabled" in collect
    assert "--mp-tracing-enabled" in compat
    assert compat[compat.index("--lmcache-otel-evidence-file") + 1] == str(
        packet_dir / "lmcache_otel_evidence.json"
    )
    assert coverage[coverage.index("--lmcache-otel-evidence-file") + 1] == str(
        packet_dir / "lmcache_otel_evidence.json"
    )
    assert "lmcache_otel.jsonl" in lab._required_artifacts(spec)


def test_packet_f_uses_cache_salt_workload_and_isolated_lru(tmp_path: Path) -> None:
    lab = _load_lab_module()
    spec = lab.PACKETS["f"]

    cmd = lab._build_lmcache_command(tmp_path, spec)

    assert spec.enable_cache_salt is True
    assert spec.workload == "cache_salt_isolated_lru"
    assert cmd[cmd.index("--eviction-policy") + 1] == "IsolatedLRU"


def test_packet_a_collect_command_uses_saved_safe_http_and_optional_outputs(tmp_path: Path) -> None:
    lab = _load_lab_module()
    (tmp_path / "http").mkdir()
    (tmp_path / "http" / "periodic_thread.json").write_text('{"name":"eviction"}', encoding="utf-8")
    (tmp_path / "trace-replay").mkdir()
    (tmp_path / "lookup_hashes").mkdir()

    cmd = lab._build_collect_lmcache_cmd(tmp_path)

    assert "--lmcache-http-base-url" in cmd
    assert cmd[cmd.index("--lmcache-health-file") + 1] == str(tmp_path / "http" / "healthcheck.json")
    assert cmd[cmd.index("--lmcache-status-file") + 1] == str(tmp_path / "http" / "status.json")
    assert cmd[cmd.index("--lmcache-conf-file") + 1] == str(tmp_path / "http" / "conf.json")
    assert cmd[cmd.index("--lmcache-threads-file") + 1] == str(tmp_path / "http" / "threads.json")
    assert cmd[cmd.index("--lmcache-periodic-thread-file") + 1] == str(
        tmp_path / "http" / "periodic_thread.json"
    )
    assert cmd[cmd.index("--lmcache-trace-replay-output") + 1] == str(tmp_path / "trace-replay")
    assert cmd[cmd.index("--lmcache-lookup-hash-path") + 1] == str(tmp_path / "lookup_hashes")
    assert cmd[cmd.index("--mp-trace-recording-enabled")] == "--mp-trace-recording-enabled"


def test_packet_a_report_commands_fail_loudly_and_include_extra_evidence(tmp_path: Path) -> None:
    lab = _load_lab_module()
    packet_dir = tmp_path / "lmcache-packet"
    packet_dir.mkdir()
    for name in ("lmcache_trace_replay_evidence.json", "lmcache_lookup_hash_evidence.json"):
        (packet_dir / name).write_text("{}", encoding="utf-8")

    compat = lab._build_lmcache_compat_cmd(tmp_path)
    coverage = lab._build_observability_coverage_cmd(tmp_path)

    assert compat[compat.index("--fail-on") + 1] == "missing-required"
    assert "--lmcache-log-evidence-file" in compat
    assert "--lmcache-trace-replay-evidence-file" in compat
    assert "--lmcache-lookup-hash-evidence-file" in compat
    assert "--lmcache-log-evidence-file" in coverage
    assert "--lmcache-trace-replay-evidence-file" in coverage
    assert "--lmcache-lookup-hash-evidence-file" in coverage


def test_packet_a_summary_marks_missing_required_artifacts(tmp_path: Path) -> None:
    lab = _load_lab_module()
    (tmp_path / "env.txt").write_text("python", encoding="utf-8")

    lab._write_summary_and_index(tmp_path)

    summary = (tmp_path / "summary.md").read_text(encoding="utf-8")
    index = json.loads((tmp_path / "artifact_index.json").read_text(encoding="utf-8"))
    assert "## Missing Required" in summary
    assert "`vllm.log`" in summary
    assert any(item["path"] == "env.txt" for item in index)


def test_packet_command_script_lists_exact_modal_functions() -> None:
    import importlib.util

    path = Path(__file__).resolve().parents[1] / "scripts" / "lmcache_mp_packet_commands.py"
    spec = importlib.util.spec_from_file_location("_lmcache_mp_packet_commands_test", path)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)

    commands = module.packet_commands()
    assert commands["A"] == "modal run scripts/lmcache_mp_modal_packet_lab.py::run_packet_a"
    assert commands["F"].endswith("::run_packet_f")

from __future__ import annotations

import importlib.util
import json
import os
import sys
import types
from pathlib import Path

_LMCACHE_SOURCE_ENV_KEYS = (
    "INFERGUARD_LMCACHE_LOCAL_SOURCE",
    "INFERGUARD_LMCACHE_GIT_REF",
    "INFERGUARD_LMCACHE_GIT_REPO",
    "INFERGUARD_LMCACHE_PIP_SPEC",
    "INFERGUARD_PACKET_A_LMCACHE_LOCAL_SOURCE",
    "INFERGUARD_PACKET_A_LMCACHE_GIT_REF",
    "INFERGUARD_PACKET_A_LMCACHE_GIT_REPO",
    "INFERGUARD_PACKET_A_LMCACHE_PIP_SPEC",
)


def _load_lab_module(env: dict[str, str] | None = None):
    module_name = "_lmcache_mp_modal_packet_lab_test"
    sys.modules.pop(module_name, None)

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

    saved_env = {key: os.environ.get(key) for key in _LMCACHE_SOURCE_ENV_KEYS}
    for key in _LMCACHE_SOURCE_ENV_KEYS:
        os.environ.pop(key, None)
    if env:
        os.environ.update(env)

    path = Path(__file__).resolve().parents[1] / "scripts" / "lmcache_mp_modal_packet_lab.py"
    spec = importlib.util.spec_from_file_location(module_name, path)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    assert spec.loader is not None
    try:
        spec.loader.exec_module(module)
    finally:
        for key, value in saved_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
    return module


def test_modal_image_installs_current_local_inferguard_source() -> None:
    lab = _load_lab_module()

    assert not hasattr(lab, "INFERGUARD_PACKAGE")
    assert lab.REPO_ROOT == Path(__file__).resolve().parents[1]
    assert lab.MODAL_INFERGUARD_SOURCE == "/opt/inferguard"
    assert lab.MODAL_INFERGUARD_FILES == ("pyproject.toml", "README.md", "LICENSE")
    assert lab.MODAL_INFERGUARD_PACKAGE_DIR == "src/inferguard"
    assert lab.INFERGUARD_LOCAL_INSTALL_COMMAND == "python -m pip install -e /opt/inferguard"

    assert lab.LMCACHE_INSTALL_PLAN.source_kind == "pypi"
    assert lab.LMCACHE_INSTALL_PLAN.source_ref == "lmcache"
    assert lab.UPSTREAM_LMCACHE_MP_PROMETHEUS_FAMILIES == (
        "lmcache_mp_lookup_requested_tokens_total",
        "lmcache_mp_lookup_hit_tokens_total",
        "lmcache_mp_l1_memory_usage_bytes",
    )
    assert lab.LMCACHE_METRICS_URL == "http://127.0.0.1:8080/metrics"
    assert lab.LMCACHE_METRICS_URLS == (
        "http://127.0.0.1:8080/metrics",
        "http://127.0.0.1:9090/metrics",
    )

    calls = lab.image.calls
    pip_install_args = next(args for name, args, _kwargs in calls if name == "pip_install")
    assert "inferguard" not in pip_install_args
    assert "lmcache" in pip_install_args
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
    add_local_dirs = [kwargs for name, _args, kwargs in calls if name == "add_local_dir"]
    assert add_local_dirs == [
        {
            "local_path": str(lab.REPO_ROOT / lab.MODAL_INFERGUARD_PACKAGE_DIR),
            "remote_path": f"{lab.MODAL_INFERGUARD_SOURCE}/{lab.MODAL_INFERGUARD_PACKAGE_DIR}",
            "copy": True,
        }
    ]
    assert add_local_dirs[0]["local_path"] != str(lab.REPO_ROOT)
    run_commands_args = next(args for name, args, _kwargs in calls if name == "run_commands")
    assert run_commands_args == (lab.INFERGUARD_LOCAL_INSTALL_COMMAND,)

    call_names = [name for name, _args, _kwargs in calls]
    assert call_names.index("add_local_file") > call_names.index("pip_install")
    assert call_names.index("add_local_dir") > call_names.index("add_local_file")
    assert call_names.index("run_commands") > call_names.index("add_local_dir")


def test_modal_image_can_install_lmcache_from_local_checkout(tmp_path: Path) -> None:
    lab = _load_lab_module({"INFERGUARD_LMCACHE_LOCAL_SOURCE": str(tmp_path)})

    assert lab.LMCACHE_INSTALL_PLAN.source_kind == "local"
    assert lab.LMCACHE_INSTALL_PLAN.local_source == tmp_path
    calls = lab.image.calls
    assert calls[0] == (
        "from_registry",
        (lab.CUDA_DEVEL_IMAGE,),
        {"add_python": "3.11"},
    )
    apt_install_args = next(args for name, args, _kwargs in calls if name == "apt_install")
    assert "build-essential" in apt_install_args
    pip_install_args = next(args for name, args, _kwargs in calls if name == "pip_install")
    assert "lmcache" not in pip_install_args
    build_env = next(
        args[0]
        for name, args, _kwargs in calls
        if name == "env" and args[0].get("CUDA_HOME") == "/usr/local/cuda"
    )
    assert build_env["TORCH_CUDA_ARCH_LIST"] == "9.0"
    assert build_env["CC"] == "gcc"
    assert build_env["CXX"] == "g++"

    add_local_dirs = [kwargs for name, _args, kwargs in calls if name == "add_local_dir"]
    assert add_local_dirs[0] == {
        "local_path": str(tmp_path),
        "remote_path": lab.MODAL_LMCACHE_SOURCE,
        "copy": True,
    }
    assert add_local_dirs[1]["remote_path"] == (
        f"{lab.MODAL_INFERGUARD_SOURCE}/{lab.MODAL_INFERGUARD_PACKAGE_DIR}"
    )
    for dep in lab.LMCACHE_SOURCE_BUILD_DEPS:
        assert dep in pip_install_args
    runtime_env = calls[-1][1][0]
    assert runtime_env["INFERGUARD_LMCACHE_SOURCE_KIND"] == "local"
    assert runtime_env["INFERGUARD_LMCACHE_SOURCE_REF"] == str(tmp_path)
    assert runtime_env["INFERGUARD_PACKET_A_LMCACHE_SOURCE_KIND"] == "local"
    assert runtime_env["INFERGUARD_PACKET_A_LMCACHE_SOURCE_REF"] == str(tmp_path)
    run_commands_args = next(args for name, args, _kwargs in calls if name == "run_commands")
    assert run_commands_args == (
        "python -m pip install -e /opt/lmcache --no-build-isolation",
        lab.INFERGUARD_LOCAL_INSTALL_COMMAND,
    )


def test_modal_image_can_install_lmcache_from_git_ref() -> None:
    lab = _load_lab_module(
        {
            "INFERGUARD_LMCACHE_GIT_REPO": "https://github.com/LMCache/LMCache.git",
            "INFERGUARD_LMCACHE_GIT_REF": "b1-metrics-ref",
        }
    )

    assert lab.LMCACHE_INSTALL_PLAN.source_kind == "git"
    assert lab.LMCACHE_INSTALL_PLAN.source_ref == "b1-metrics-ref"
    calls = lab.image.calls
    assert calls[0] == (
        "from_registry",
        (lab.CUDA_DEVEL_IMAGE,),
        {"add_python": "3.11"},
    )
    pip_install_args = next(args for name, args, _kwargs in calls if name == "pip_install")
    assert "lmcache" not in pip_install_args
    assert "git+https://github.com/LMCache/LMCache.git@b1-metrics-ref" not in pip_install_args
    for dep in lab.LMCACHE_SOURCE_BUILD_DEPS:
        assert dep in pip_install_args
    run_commands_args = next(args for name, args, _kwargs in calls if name == "run_commands")
    assert run_commands_args == (
        "python -m pip install git+https://github.com/LMCache/LMCache.git@b1-metrics-ref --no-build-isolation",
        lab.INFERGUARD_LOCAL_INSTALL_COMMAND,
    )


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
    replay = lab._build_trace_replay_command(tmp_path, spec)

    assert spec.workload == "reuse_eviction"
    assert spec.output_slug == "packet-b-lifecycle-reuse-eviction"
    assert lab._run_dir_for_packet(spec, "20260101T000000Z") == (
        lab.OUT_ROOT / "packet-b-lifecycle-reuse-eviction" / "20260101T000000Z"
    )
    assert cmd[cmd.index("--metrics-sample-rate") + 1] == "1.0"
    assert cmd[cmd.index("--l1-size-gb") + 1] == "1"
    assert replay[replay.index("--l1-size-gb") + 1] == "1"
    assert cmd[cmd.index("--event-bus-queue-size") + 1] == "10000"
    assert cmd[cmd.index("--eviction-policy") + 1] == "LRU"
    assert "workload_manifest.json" in lab._required_artifacts(spec)
    assert "packet-b-lifecycle-evidence.json" in lab._required_artifacts(spec)
    assert "traffic.log" in lab._required_artifacts(spec)
    assert "traffic_requests.jsonl" in lab._optional_artifacts(spec)


def test_packet_b_workload_manifest_describes_lifecycle_pressure(tmp_path: Path) -> None:
    lab = _load_lab_module()
    spec = lab.PACKETS["b"]

    lab._write_workload_manifest(tmp_path, spec, 48)

    manifest = json.loads((tmp_path / "workload_manifest.json").read_text(encoding="utf-8"))
    assert manifest["packet_id"] == "b"
    assert manifest["workload"] == "reuse_eviction"
    assert manifest["metrics_sample_rate"] == 1.0
    assert manifest["l1_size_gb"] == "1"
    assert manifest["raw_prompts_recorded"] is False
    assert [phase["phase"] for phase in manifest["phases"]] == ["warm", "pressure", "retest"]
    assert [phase["request_count"] for phase in manifest["phases"]] == [12, 28, 8]
    assert set(manifest["required_packet_b_telemetry"]) == set(lab.PACKET_B_REQUIRED_TELEMETRY)


def test_packet_b_lifecycle_evidence_requires_sampled_l0_l1_reuse_and_eviction(
    tmp_path: Path,
) -> None:
    lab = _load_lab_module()
    spec = lab.PACKETS["b"]
    (tmp_path / "lmcache_metrics_loaded.prom").write_text(
        "\n".join(
            [
                "lmcache_mp_lookup_requested_tokens_total 100",
                "lmcache_mp_lookup_hit_tokens_total 70",
                "lmcache_mp_l1_chunk_reuse_gap_seconds_count 4",
                "lmcache_mp_l0_block_lifetime_seconds_count 4",
                "lmcache_mp_real_reuse_gap_seconds_count 2",
                "lmcache_mp_l1_evicted_keys_total 3",
                "lmcache_mp_l0_l1_store_throughput_gbs_count 2",
                "",
            ]
        ),
        encoding="utf-8",
    )

    lab._write_packet_b_lifecycle_evidence(tmp_path, spec)

    evidence = json.loads((tmp_path / "packet-b-lifecycle-evidence.json").read_text(encoding="utf-8"))
    assert evidence["claim_status"] == "measured"
    assert evidence["metrics_sample_rate"] == 1.0
    assert evidence["missing_required_families"] == []
    assert evidence["required_families"]["l1_eviction"]["status"] == "populated"


def test_packet_b_validation_records_warning_when_lifecycle_evidence_not_measured(tmp_path: Path) -> None:
    lab = _load_lab_module()
    spec = lab.PACKETS["b"]
    for rel in lab._required_artifacts(spec):
        path = tmp_path / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("x", encoding="utf-8")
    (tmp_path / "packet-b-lifecycle-evidence.json").write_text(
        json.dumps(
            {
                "claim_status": "not_proven",
                "missing_required_families": ["l0_lifecycle"],
            }
        ),
        encoding="utf-8",
    )

    lab._validate_required_artifacts(tmp_path, spec)

    warnings = (tmp_path / "validation_warnings.log").read_text(encoding="utf-8")
    assert "l0_lifecycle" in warnings


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
    assert "- LMCache install source: `pypi` (`lmcache`)" in summary
    assert "`vllm.log`" in summary
    assert any(item["path"] == "env.txt" for item in index)


def test_packet_a_summary_uses_runtime_lmcache_install_source(tmp_path: Path, monkeypatch) -> None:
    lab = _load_lab_module()
    monkeypatch.setenv("INFERGUARD_LMCACHE_SOURCE_KIND", "local")
    monkeypatch.setenv("INFERGUARD_LMCACHE_SOURCE_REF", "/Users/chen/Projects/LMCache")

    lab._write_summary_and_index(tmp_path)

    summary = (tmp_path / "summary.md").read_text(encoding="utf-8")
    assert "- LMCache install source: `local` (`/Users/chen/Projects/LMCache`)" in summary


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

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
        @classmethod
        def debian_slim(cls, **_kwargs):
            return cls()

        def apt_install(self, *_args):
            return self

        def pip_install(self, *_args):
            return self

        def env(self, _env):
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
    sys.modules.setdefault("modal", fake_modal)

    path = Path(__file__).resolve().parents[1] / "scripts" / "lmcache_mp_modal_packet_lab.py"
    spec = importlib.util.spec_from_file_location(module_name, path)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


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

from __future__ import annotations

import asyncio
import json
import re
import threading
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from aiohttp import web

from inferguard.collect_metrics import (
    CollectMetricsOptions,
    collect_metrics,
    normalize_dcgm_sample,
    normalize_engine_sample,
)
from inferguard.collect_metrics.normalize import VLLM_LOCKED_METRICS, build_metrics_summary
from inferguard.collect_metrics.types import ENGINE_GROUPS, GpuMetricsSample
from inferguard.compat import build_compat_report_from_paths

FIXTURES = Path(__file__).parent / "fixtures"


def _fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def _engine_rows(engine: str, text: str) -> list[dict[str, Any]]:
    normalized = normalize_engine_sample(engine, text)
    rows: list[dict[str, Any]] = []
    for group in ENGINE_GROUPS:
        group_data = normalized["groups"][group]
        rows.append(
            {
                "group": group,
                "source_metrics": list(group_data.get("source_metrics", [])),
                "normalized": {
                    key: value
                    for key, value in group_data.items()
                    if key not in {"claim_status", "claim_status_per_field", "source_metrics"}
                },
                "claim_status": group_data.get("claim_status") or "not_proven",
                "claim_status_per_field": group_data.get("claim_status_per_field") or {},
            }
        )
    return rows


def _summary_from_engine(engine: str, text: str) -> dict[str, Any]:
    data = build_metrics_summary(
        engine=engine,
        duration_seconds=1,
        engine_rows=_engine_rows(engine, text),
        gpu_rows=[],
        sample_count=1,
        dcgm_sample_count=0,
        generated_at="2026-05-04T00:00:00Z",
    )
    return data["groups"]


def _summary_from_dcgm(text: str) -> dict[str, Any]:
    gpu_rows = [
        GpuMetricsSample(**row).as_dict()
        for row in normalize_dcgm_sample(
            text,
            observed_at="2026-05-04T00:00:00Z",
            sequence=0,
            timestamp_window_seconds=5,
        )
    ]
    data = build_metrics_summary(
        engine="vllm",
        duration_seconds=1,
        engine_rows=[],
        gpu_rows=gpu_rows,
        sample_count=0,
        dcgm_sample_count=len(gpu_rows),
        generated_at="2026-05-04T00:00:00Z",
    )
    return data["groups"]


def test_parse_vllm_fixture() -> None:
    text = _fixture("vllm.txt")
    parsed = normalize_engine_sample("vllm", text)
    observed = parsed["observed_metrics"]

    for metric in VLLM_LOCKED_METRICS:
        fixture_contains_metric = metric in text or f"{metric}_" in text
        if fixture_contains_metric:
            assert metric in observed or any(key.startswith(f"{metric}_") for key in observed)

    assert "vllm:request_success_total" in observed
    assert "vllm:gpu_cache_usage_perc" in observed


def test_parse_sglang_fixture() -> None:
    summary = _summary_from_engine("sglang", _fixture("sglang.txt"))

    assert summary["prefix_cache"]["hit_rate"] is not None
    assert summary["kv_cache"]["token_usage"] is not None
    assert summary["kv_cache"]["kv_transfer_sent_bytes_total"] is not None


def test_sglang_engine_groups() -> None:
    summary = _summary_from_engine("sglang", _fixture("sglang.txt"))

    for group in {"prefill", "decode", "queue", "prefix_cache"}:
        assert summary[group]["claim_status"] == "measured"


def test_parse_lmcache_fixture() -> None:
    summary = _summary_from_engine("lmcache", _fixture("lmcache_metrics/full.prom"))

    assert summary["lmcache"]["retrieve_hit_rate"] is not None
    assert summary["lmcache"]["connector"] == "LMCacheConnectorV1"


def test_lmcache_connector_v1() -> None:
    summary = _summary_from_engine("lmcache", _fixture("lmcache_metrics/with_v1_connector.prom"))

    assert summary["lmcache"]["connector"] == "LMCacheConnectorV1"


def test_lmcache_mp_metrics_are_measured() -> None:
    summary = _summary_from_engine("lmcache", _fixture("lmcache_metrics/mp.prom"))

    lmcache = summary["lmcache"]
    assert lmcache["claim_status"] == "measured"
    assert lmcache["mp_mode_enabled"] is True
    assert lmcache["connector"] == "LMCacheMPConnector"
    assert lmcache["backend"] == "mp"
    assert lmcache["lookup_requested_tokens"] == 10000
    assert lmcache["lookup_hit_tokens"] == 6200
    assert lmcache["lookup_hit_rate"] == 0.62
    assert lmcache["l1_memory_usage_bytes"] == 2147483648
    assert lmcache["l1_chunk_reuse_gap_seconds"] == 3.0
    assert lmcache["l2_store_completed"] == 7
    assert lmcache["event_bus_queue_depth"] == 0


def test_real_modal_mp_slice_surfaces_storage_l0_and_vllm_external_prefix() -> None:
    summary = _summary_from_engine("lmcache", _fixture("lmcache_metrics/mp_modal_real_slice.prom"))

    lmcache = summary["lmcache"]
    prefix = summary["prefix_cache"]
    assert lmcache["claim_status"] == "measured"
    assert lmcache["mp_mode_enabled"] is True
    assert lmcache["sm_read_requests"] == 149
    assert lmcache["sm_write_succeed_keys"] == 1843
    assert lmcache["l1_evicted_keys"] == 1650
    assert lmcache["l0_block_lifetime_seconds"] > 400
    assert prefix["external_queries"] == 643697
    assert prefix["external_hits"] == 0
    assert prefix["prompt_tokens_external_kv_transfer"] == 0
    assert prefix["prompt_tokens_cached_total"] == 1281008


def test_vllm_simple_cpu_offload_metrics_are_normalized() -> None:
    summary = _summary_from_engine("vllm", _fixture("vllm_simple_cpu_offload.prom"))

    kv_cache = summary["kv_cache"]
    assert kv_cache["claim_status"] == "measured"
    assert kv_cache["kv_offload_bytes_gpu_to_cpu"] == 13870000000
    assert kv_cache["kv_offload_bytes_cpu_to_gpu"] == 4770000000
    assert kv_cache["simple_cpu_offload_total_blocks"] == 1024
    assert kv_cache["simple_cpu_offload_usage_perc"] == 0.75
    assert kv_cache["simple_cpu_offload_pending_loads"] == 2
    assert kv_cache["simple_cpu_offload_pending_stores"] == 3


def test_lmcache_compat_report_distinguishes_mp_and_external_prefix() -> None:
    report = build_compat_report_from_paths(
        engine_metrics_file=FIXTURES / "lmcache_metrics/mp_modal_real_slice.prom",
        lmcache_metrics_file=FIXTURES / "lmcache_metrics/mp_modal_real_slice.prom",
        expect_mode="mp",
    )

    assert report["observed"]["lmcache_mp"] is True
    assert report["observed"]["lmcache_embedded"] is False
    assert report["detected_mode"] == "mp"
    families = {(row["surface"], row["family"]): row for row in report["families"]}
    assert families[("lmcache_mp", "storage_manager")]["status"] == "populated"
    assert families[("lmcache_mp", "lookup_tokens")]["status"] == "missing"
    assert families[("lmcache_mp", "l2_counters")]["status"] == "not_applicable"
    assert families[("vllm_prefix_cache", "external_prefix")]["status"] == "populated"
    assert {
        item["code"] for item in report["upstream_questions"]
    } >= {
        "lmcache_mp_lookup_counters_missing",
        "vllm_external_prefix_no_hits",
    }


def test_lmcache_compat_report_marks_l2_required_when_configured() -> None:
    report = build_compat_report_from_paths(
        engine_metrics_file=FIXTURES / "lmcache_metrics/mp_modal_real_slice.prom",
        lmcache_metrics_file=FIXTURES / "lmcache_metrics/mp_modal_real_slice.prom",
        expect_mode="mp",
        l2_configured=True,
    )

    families = {(row["surface"], row["family"]): row for row in report["families"]}
    assert families[("lmcache_mp", "l2_counters")]["status"] == "missing"
    assert any(
        item["code"] == "lmcache_mp_family_missing" and item["family"] == "l2_counters"
        for item in report["failure_reasons"]
    )


def test_dynamo_kvbm() -> None:
    summary = _summary_from_engine("dynamo-sglang", _fixture("dynamo_kvbm.txt"))

    assert summary["kv_cache"]["dynamo_kvbm_l1_count"] is not None
    assert summary["kv_cache"]["dynamo_kvbm_l2_count"] is not None
    assert summary["kv_cache"]["dynamo_kvbm_l3_count"] is not None


def test_parse_dcgm_fixture() -> None:
    summary = _summary_from_dcgm(_fixture("dcgm.txt"))

    assert summary["gpu_util"]["DCGM_FI_DEV_GPU_UTIL"]["p95"] is not None
    assert summary["hbm"]["DCGM_FI_DEV_FB_USED"]["max_mib"] > 0


def test_empty_endpoint() -> None:
    engine_rows = _engine_rows("vllm", _fixture("empty.txt"))
    gpu_rows = [
        GpuMetricsSample(**row).as_dict()
        for row in normalize_dcgm_sample(
            _fixture("empty.txt"),
            observed_at="2026-05-04T00:00:00Z",
            sequence=0,
            timestamp_window_seconds=5,
        )
    ]
    data = build_metrics_summary(
        engine="vllm",
        duration_seconds=1,
        engine_rows=engine_rows,
        gpu_rows=gpu_rows,
        sample_count=1,
        dcgm_sample_count=len(gpu_rows),
        generated_at="2026-05-04T00:00:00Z",
    )

    assert all(data["groups"][group]["claim_status"] == "not_proven" for group in data["groups"])


def test_v0_kv_fallback() -> None:
    summary = _summary_from_engine("vllm", _fixture("vllm_v0_only.txt"))

    assert summary["kv_cache"]["usage_fraction_source"] == "vllm:gpu_cache_usage_perc"


def test_v1_kv_preferred() -> None:
    summary = _summary_from_engine("vllm", _fixture("vllm_v1_both.txt"))

    assert summary["kv_cache"]["usage_fraction_source"] == "vllm:kv_cache_usage_perc"
    assert summary["kv_cache"]["usage_fraction"] == 0.66


def test_scrape_failure_graceful(tmp_path: Path) -> None:
    server = _MetricsServer(
        {
            "/metrics": (500, "engine unavailable"),
            "/dcgm": (200, _fixture("dcgm.txt")),
        }
    )
    base_url = server.start()
    try:
        summary = collect_metrics(
            CollectMetricsOptions(
                engine="vllm",
                engine_metrics_url=f"{base_url}/metrics",
                dcgm_metrics_url=f"{base_url}/dcgm",
                duration_seconds=0.01,
                interval_seconds=0.01,
                output_dir=tmp_path,
                keep_raw_samples=True,
            ),
            emit=None,
        ).as_dict()
    finally:
        server.stop()

    assert summary["queue"]["claim_status"] == "not_proven"
    raw_rows = [
        json.loads(line)
        for line in (tmp_path / "raw_samples.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert any(row["source"] == "engine" and row["scrape_error"] == "http_500" for row in raw_rows)


def test_collect_metrics_writes_lmcache_compat_report_without_dcgm(tmp_path: Path) -> None:
    server = _MetricsServer(
        {
            "/metrics": (200, _fixture("vllm.txt")),
            "/lmcache": (200, _fixture("lmcache_metrics/mp_modal_real_slice.prom")),
        }
    )
    base_url = server.start()
    try:
        summary = collect_metrics(
            CollectMetricsOptions(
                engine="vllm",
                engine_metrics_url=f"{base_url}/metrics",
                dcgm_metrics_url=None,
                lmcache_metrics_url=f"{base_url}/lmcache",
                duration_seconds=0.01,
                interval_seconds=0.01,
                output_dir=tmp_path,
                keep_raw_samples=True,
            ),
            emit=None,
        ).as_dict()
    finally:
        server.stop()

    assert summary["dcgm_sample_count"] == 0
    compat = json.loads((tmp_path / "lmcache_compat_report.json").read_text(encoding="utf-8"))
    assert compat["detected_mode"] == "mp"
    raw_rows = [
        json.loads(line)
        for line in (tmp_path / "raw_samples.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert any(row["source"] == "lmcache" for row in raw_rows)


def test_dcgm_schema_locked(tmp_path: Path) -> None:
    server = _MetricsServer(
        {
            "/metrics": (200, _fixture("vllm.txt")),
            "/dcgm": (200, _fixture("dcgm.txt")),
        }
    )
    base_url = server.start()
    try:
        collect_metrics(
            CollectMetricsOptions(
                engine="vllm",
                engine_metrics_url=f"{base_url}/metrics",
                dcgm_metrics_url=f"{base_url}/dcgm",
                duration_seconds=0.01,
                interval_seconds=0.01,
                output_dir=tmp_path,
            ),
            emit=None,
        )
    finally:
        server.stop()

    first = json.loads((tmp_path / "gpu_metrics_timeline.jsonl").read_text(encoding="utf-8").splitlines()[0])
    assert first["schema_version"] == "dcgm-correlated/v1"


def test_stdout_summary_format(tmp_path: Path) -> None:
    server = _MetricsServer(
        {
            "/metrics": (200, _fixture("vllm.txt")),
            "/dcgm": (200, _fixture("dcgm.txt")),
        }
    )
    base_url = server.start()
    lines: list[str] = []
    try:
        collect_metrics(
            CollectMetricsOptions(
                engine="vllm",
                engine_metrics_url=f"{base_url}/metrics",
                dcgm_metrics_url=f"{base_url}/dcgm",
                duration_seconds=0.01,
                interval_seconds=0.01,
                output_dir=tmp_path,
            ),
            emit=lines.append,
        )
    finally:
        server.stop()

    assert re.match(
        r"^inferguard collect-metrics: engine=\w+ samples=\d+ dcgm_samples=\d+ duration=[\d.]+ kv_cache_max=[\d.]+ gpu_util_p95=[\d.]+ hbm_used_p95_mib=\d+$",
        lines[0],
    )


def test_sm_active_optin() -> None:
    summary = _summary_from_dcgm(_fixture("dcgm_with_sm_active.txt"))

    assert summary["gpu_util"]["DCGM_FI_PROF_SM_ACTIVE"]["p95"] is not None


class _MetricsServer:
    def __init__(self, routes: Mapping[str, tuple[int, str]]) -> None:
        self.routes = dict(routes)
        self.loop = asyncio.new_event_loop()
        self.runner: web.AppRunner | None = None
        self.site: web.TCPSite | None = None
        self.bound_port: int | None = None
        self._ready = threading.Event()
        self.thread = threading.Thread(target=self._run, daemon=True)

    def start(self) -> str:
        self.thread.start()
        if not self._ready.wait(timeout=5):
            raise RuntimeError("metrics test server did not start")
        return f"http://127.0.0.1:{self.bound_port}"

    def stop(self) -> None:
        if not self.loop.is_running():
            return
        future = asyncio.run_coroutine_threadsafe(self._cleanup(), self.loop)
        future.result(timeout=5)
        self.loop.call_soon_threadsafe(self.loop.stop)
        self.thread.join(timeout=5)

    def _run(self) -> None:
        asyncio.set_event_loop(self.loop)
        self.loop.run_until_complete(self._start())
        self._ready.set()
        self.loop.run_forever()
        self.loop.close()

    async def _start(self) -> None:
        app = web.Application()
        for path in self.routes:
            app.router.add_get(path, self._handle)
        self.runner = web.AppRunner(app)
        await self.runner.setup()
        self.site = web.TCPSite(self.runner, "127.0.0.1", 0)
        await self.site.start()
        sockets = self.site._server.sockets if self.site._server is not None else []  # noqa: SLF001
        self.bound_port = sockets[0].getsockname()[1]

    async def _cleanup(self) -> None:
        if self.runner is not None:
            await self.runner.cleanup()

    async def _handle(self, request: web.Request) -> web.Response:
        status, text = self.routes.get(request.path, (404, "missing"))
        return web.Response(status=status, text=text)

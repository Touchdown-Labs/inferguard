from __future__ import annotations

import json
import struct
from pathlib import Path

from typer.testing import CliRunner

from inferguard.cli import app
from inferguard.lmcache_packet import LmcachePacketOptions, collect_lmcache_packet


def test_collect_lmcache_packet_writes_partial_first_artifacts(tmp_path: Path) -> None:
    lmcache_metrics = tmp_path / "lmcache.prom"
    engine_metrics = tmp_path / "engine.prom"
    lmcache_log = tmp_path / "lmcache.log"
    lmcache_health = tmp_path / "health.json"
    lmcache_status = tmp_path / "status.json"
    lmcache_trace = tmp_path / "trace.lct"
    lmcache_otel = tmp_path / "otel.jsonl"
    lmcache_metrics.write_text(
        """
target_info{service_instance_id="mp-a"} 1
lmcache_mp_sm_read_requests_total 10
lmcache_mp_sm_write_requests_total 5
lmcache_mp_l1_read_keys_total 9
lmcache_mp_l1_write_keys_total 7
lmcache_mp_lookup_requested_tokens_total{model_name="Qwen/Qwen3-8B",cache_salt="tenant-a"} 100
lmcache_mp_lookup_hit_tokens_total{model_name="Qwen/Qwen3-8B",cache_salt="tenant-a"} 40
""",
        encoding="utf-8",
    )
    engine_metrics.write_text(
        "vllm:external_prefix_cache_queries_total 100\n"
        "vllm:external_prefix_cache_hits_total 40\n",
        encoding="utf-8",
    )
    lmcache_log.write_text("Prefetch request completed (L1+L2): 4/10 prefix hits\n", encoding="utf-8")
    lmcache_health.write_text('{"is_healthy": true, "status": "ok"}', encoding="utf-8")
    lmcache_status.write_text('{"engine_type": "mp", "chunk_size": 256}', encoding="utf-8")
    _write_lct(
        lmcache_trace,
        [
            {"magic": "LMCT", "trace_level": "storage"},
            {"qualname": "StorageManager.reserve_write", "relative_ts": 0.1},
        ],
    )
    lmcache_otel.write_text('{"name": "mp.store", "duration_ms": 3}\n', encoding="utf-8")
    output_dir = tmp_path / "packet"

    manifest = collect_lmcache_packet(
        LmcachePacketOptions(
            output_dir=output_dir,
            engine_metrics_file=engine_metrics,
            lmcache_metrics_file=lmcache_metrics,
            lmcache_health_file=lmcache_health,
            lmcache_status_file=lmcache_status,
            lmcache_log_file=lmcache_log,
            lmcache_trace_file=lmcache_trace,
            lmcache_otel_file=lmcache_otel,
            expect_mode="mp",
            mp_observability={"event_bus_queue_size": 10000, "metrics_sample_rate": 0.01},
        )
    )

    assert manifest["claim_status"] == "measured"
    assert manifest["detected_mode"] == "mp"
    assert manifest["scrape_errors"] == []
    assert (output_dir / "engine_metrics.prom").exists()
    assert (output_dir / "lmcache_metrics.prom").exists()
    assert (output_dir / "lmcache.log").exists()
    assert (output_dir / "lmcache_http_evidence.json").exists()
    assert (output_dir / "lmcache_log_evidence.json").exists()
    assert (output_dir / "lmcache_trace_evidence.json").exists()
    assert (output_dir / "lmcache_otel_evidence.json").exists()
    assert manifest["http_evidence"]["booleans"]["is_healthy"] is True
    assert manifest["log_evidence"]["event_counts"]["prefetch_complete"] == 1
    assert manifest["trace_evidence"]["claim_status"] == "measured"
    assert manifest["otel_evidence"]["claim_status"] == "measured"
    report = json.loads((output_dir / "lmcache_compat_report.json").read_text(encoding="utf-8"))
    assert report["lmcache_mp_observability"]["service_instance_ids"] == ["mp-a"]
    assert report["lmcache_mp_observability"]["cache_salt_values"] == ["tenant-a"]


def test_collect_lmcache_packet_records_failed_inputs(tmp_path: Path) -> None:
    manifest = collect_lmcache_packet(
        LmcachePacketOptions(
            output_dir=tmp_path / "packet",
            lmcache_metrics_file=tmp_path / "missing.prom",
            expect_mode="mp",
        )
    )

    assert manifest["claim_status"] == "not_proven"
    assert manifest["detected_mode"] == "unknown"
    assert manifest["scrape_errors"][0]["source_name"] == "lmcache_metrics"
    assert (tmp_path / "packet" / "lmcache_compat_report.json").exists()
    assert (tmp_path / "packet" / "packet_manifest.json").exists()


def test_collect_lmcache_cli_writes_packet(tmp_path: Path) -> None:
    metrics = tmp_path / "lmcache.prom"
    metrics.write_text("lmcache_mp_sm_read_requests_total 2\n", encoding="utf-8")
    output_dir = tmp_path / "packet"

    result = CliRunner().invoke(
        app,
        [
            "collect-lmcache",
            "--output-dir",
            str(output_dir),
            "--lmcache-metrics-file",
            str(metrics),
            "--expect-mode",
            "mp",
            "--json",
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["detected_mode"] == "mp"
    assert (output_dir / "packet_manifest.json").exists()


def _write_lct(path: Path, records: list[dict[str, object]]) -> None:
    chunks = []
    for record in records:
        payload = json.dumps(record).encode("utf-8")
        chunks.append(struct.pack(">I", len(payload)) + payload)
    path.write_bytes(b"".join(chunks))

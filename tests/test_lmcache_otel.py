from __future__ import annotations

import json
from pathlib import Path

from inferguard.lmcache_otel import parse_lmcache_otel_jsonl


def test_lmcache_otel_parses_mp_spans(tmp_path: Path) -> None:
    spans = tmp_path / "otel.jsonl"
    spans.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "name": "mp.store",
                        "duration_ms": 12,
                        "attributes": {"device": "cuda:0", "stored_count": 8},
                    }
                ),
                json.dumps(
                    {
                        "name": "mp.lookup_prefetch",
                        "start_time_unix_nano": 100,
                        "end_time_unix_nano": 1_000_000_100,
                        "attributes": {"found_count": 4},
                    }
                ),
                json.dumps({"name": "unrelated", "duration_ms": 99}),
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    evidence = parse_lmcache_otel_jsonl(spans)

    assert evidence["claim_status"] == "measured"
    assert evidence["span_count"] == 3
    assert evidence["lmcache_span_count"] == 2
    assert evidence["span_counts"]["mp.store"] == 1
    assert evidence["latency_seconds"]["mp.store"]["max"] == 0.012
    assert "stored_count" in evidence["attribute_keys"]


def test_lmcache_otel_records_bad_json_without_crashing(tmp_path: Path) -> None:
    spans = tmp_path / "bad.jsonl"
    spans.write_text('{"name": "mp.store"}\nnot-json\n', encoding="utf-8")

    evidence = parse_lmcache_otel_jsonl(spans)

    assert evidence["claim_status"] == "measured"
    assert evidence["parse_errors"]


def test_lmcache_otel_parses_otlp_json_export(tmp_path: Path) -> None:
    spans = tmp_path / "otlp.json"
    spans.write_text(
        json.dumps(
            {
                "resourceSpans": [
                    {
                        "scopeSpans": [
                            {
                                "spans": [
                                    {
                                        "name": "mp.retrieve",
                                        "startTimeUnixNano": "1000",
                                        "endTimeUnixNano": "2001000",
                                        "attributes": [
                                            {"key": "device", "value": {"stringValue": "cuda:0"}},
                                            {"key": "retrieved_count", "value": {"intValue": "8"}},
                                        ],
                                    }
                                ]
                            }
                        ]
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    evidence = parse_lmcache_otel_jsonl(spans)

    assert evidence["claim_status"] == "measured"
    assert evidence["span_count"] == 1
    assert evidence["span_counts"]["mp.retrieve"] == 1
    assert evidence["latency_seconds"]["mp.retrieve"]["max"] == 0.002
    assert "retrieved_count" in evidence["attribute_keys"]


def test_lmcache_otel_distinguishes_request_mp_and_cacheblend_spans(tmp_path: Path) -> None:
    spans = tmp_path / "cacheblend.jsonl"
    spans.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "name": "request",
                        "duration_ms": 50,
                        "attributes": {
                            "requested_tokens": 100,
                            "hit_tokens": 40,
                            "hit_rate": 0.4,
                        },
                    }
                ),
                json.dumps({"name": "mp.store", "duration_ms": 2}),
                json.dumps({"name": "cb.request", "duration_ms": 12}),
                json.dumps({"name": "cb.lookup", "duration_ms": 3}),
                json.dumps({"name": "cb.store_pre_computed", "duration_ms": 4}),
                json.dumps({"name": "cb.retrieve", "duration_ms": 5}),
                json.dumps({"name": "cb.store_final", "duration_ms": 6}),
                json.dumps({"name": "cb.fingerprints.registered", "attributes": {"count": 2}}),
                json.dumps({"name": "cb.chunks.evicted", "attributes": {"count": 1}}),
            ]
        ),
        encoding="utf-8",
    )

    evidence = parse_lmcache_otel_jsonl(spans)

    assert evidence["claim_status"] == "measured"
    assert evidence["lmcache_span_count"] == 9
    assert evidence["mp_span_count"] == 1
    assert evidence["request_span_count"] == 1
    assert evidence["cacheblend_span_count"] == 5
    assert evidence["cacheblend_point_span_count"] == 2
    assert evidence["span_groups"]["mp"]["span_counts"]["mp.store"] == 1
    assert evidence["span_groups"]["cacheblend"]["span_counts"]["cb.lookup"] == 1
    assert evidence["span_groups"]["cacheblend_point"]["span_counts"]["cb.chunks.evicted"] == 1
    assert evidence["span_groups"]["request"]["span_counts"]["request"] == 1
    assert evidence["request_attributes"]["hit_tokens"]["max"] == 40.0
    assert evidence["request_attributes"]["requested_tokens"]["max"] == 100.0
    assert evidence["request_attributes"]["hit_rate"]["max"] == 0.4

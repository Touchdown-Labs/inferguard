from inferguard.lmcache_logs import LMCACHE_LOG_SCHEMA_VERSION, parse_lmcache_logs


def test_parse_lmcache_logs_extracts_mp_store_retrieve_and_prefetch_evidence() -> None:
    report = parse_lmcache_logs(
        """
INFO 05-06 12:00:01 [config.py:91] kv_transfer_config={"kv_connector":"LMCacheMPConnector","kv_role":"kv_both"}
INFO 05-06 12:00:02 [server.py:44] LMCache server started and ready on 0.0.0.0:9090
INFO 05-06 12:00:05 [storage_manager.py:170] LMCache stored 64 chunks for request req-a in L1
INFO 05-06 12:00:06 [lookup.py:88] LMCache retrieve cache hit for 4096 tokens request req-b
INFO 05-06 12:00:07 [prefetcher.py:221] L2 prefetch completed loaded_keys=12 failed_keys=0
"""
    )

    assert report["schema_version"] == LMCACHE_LOG_SCHEMA_VERSION
    assert report["line_count"] == 5
    assert report["event_counts"]["store"] == 1
    assert report["event_counts"]["retrieve"] == 1
    assert report["event_counts"]["prefetch_complete"] == 1
    assert report["event_counts"]["health_startup"] == 1
    assert report["booleans"]["has_store"] is True
    assert report["config"]["connectors"] == ["LMCacheMPConnector"]
    assert "mp" in report["mode_candidates"]
    assert report["snippets"]["store"] == [
        "INFO 05-06 12:00:05 [storage_manager.py:170] LMCache stored 64 chunks for request req-a in L1"
    ]


def test_parse_lmcache_logs_extracts_p2p_pd_and_config_hints() -> None:
    report = parse_lmcache_logs(
        """
INFO engine config PYTHONHASHSEED=42 enable_p2p=True enable_pd=true enable_async_loading=false
INFO connector {"kv_connector":"LMCacheConnectorV1","kv_role":"kv_both"}
INFO p2p controller connected peer=engine-1 url=tcp://10.0.0.4:8200
INFO P2P transfer sent 8192 tokens to peer engine-1 over NIXL
INFO NIXL PD sender prefiller registered kv_producer port=6001
INFO NIXL PD receiver decoder registered kv_consumer port=6002
"""
    )

    assert report["event_counts"]["p2p_peer"] == 1
    assert report["event_counts"]["p2p_transfer"] == 1
    assert report["event_counts"]["pd_sender"] == 1
    assert report["event_counts"]["pd_receiver"] == 1
    assert report["booleans"]["has_config_hints"] is True
    assert report["config"]["connectors"] == ["LMCacheConnectorV1"]
    assert report["config"]["pythonhashseed_seen"] is True
    assert report["config"]["pythonhashseed_values"] == ["42"]
    assert report["config"]["enable_p2p"] is True
    assert report["config"]["enable_pd"] is True
    assert report["config"]["enable_async_loading"] is False
    assert report["mode_candidates"] == ["disaggregated_prefill", "embedded", "p2p"]


def test_parse_lmcache_logs_bounds_snippets_and_flags_legacy_connector() -> None:
    long_line = "INFO LMCache stored " + ("chunk " * 80)
    report = parse_lmcache_logs(
        "\n".join(
            [
                "INFO config kv_connector=LMCacheConnector",
                long_line,
                "INFO LMCache stored request=req-1",
                "INFO LMCache stored request=req-2",
                "INFO LMCache stored request=req-3",
                "INFO LMCache stored request=req-4",
                "INFO LMCache stored request=req-5",
                "INFO LMCache stored request=req-6",
                "INFO LMCache stored request=req-7",
            ]
        )
    )

    assert report["event_counts"]["store"] == 8
    assert len(report["snippets"]["store"]) == 6
    assert len(report["snippets"]["store"][0]) <= 220
    assert report["snippets"]["store"][0].endswith("...")
    assert report["config"]["connectors"] == ["LMCacheConnector"]
    assert report["config"]["stale_lmcache_connector_seen"] is True
    assert report["booleans"]["has_stale_lmcache_connector"] is True


def test_parse_lmcache_logs_is_conservative_for_unrelated_logs() -> None:
    report = parse_lmcache_logs(
        """
INFO application request stored profile data
WARNING peer disconnected from unrelated service
INFO cache warming finished
"""
    )

    assert report["event_counts"] == {
        "store": 0,
        "retrieve": 0,
        "prefetch_complete": 0,
        "p2p_peer": 0,
        "p2p_transfer": 0,
        "p2p_transfer_failure": 0,
        "p2p_transfer_speed": 0,
        "pd_sender": 0,
        "pd_receiver": 0,
        "pd_role_mismatch": 0,
        "pd_stall": 0,
        "nixl_proxy": 0,
        "nixl_request": 0,
        "health_startup": 0,
    }
    assert report["mode_candidates"] == []
    assert report["config"]["connectors"] == []


def test_parse_lmcache_logs_extracts_p2p_failures_speed_and_nixl_request_findings() -> None:
    report = parse_lmcache_logs(
        """
WARN p2p transfer failed request_id=req-7 peer=decode-1 error=connection refused retry=1
INFO P2P transfer bandwidth 12.5 GB/s peer=decode-1 tokens=8192
INFO NIXL proxy started for disaggregated prefill port=7676
INFO NIXL transfer request request_id=req-8 state=queued
"""
    )

    assert report["event_counts"]["p2p_transfer_failure"] == 1
    assert report["event_counts"]["p2p_transfer_speed"] == 1
    assert report["event_counts"]["nixl_proxy"] == 1
    assert report["event_counts"]["nixl_request"] == 1
    assert report["numeric_hints"]["p2p_transfer_speed"][0]["value"] == 12.5
    assert report["numeric_hints"]["p2p_transfer_speed"][0]["unit"] == "GB/s"
    codes = {finding["code"] for finding in report["findings"]}
    assert "lmcache_log_p2p_transfer_failure" in codes
    assert "lmcache_log_p2p_transfer_speed_hint" in codes
    assert "lmcache_log_nixl_proxy_indicator" in codes
    assert "lmcache_log_nixl_request_indicator" in codes
    assert {finding["evidence_status"] for finding in report["findings"]} == {"parser_only"}
    assert report["mode_candidates"] == ["disaggregated_prefill", "p2p"]


def test_parse_lmcache_logs_extracts_pd_role_mismatch_and_stall_findings() -> None:
    report = parse_lmcache_logs(
        """
ERROR NIXL PD role mismatch expected prefill got decode kv_role=kv_consumer endpoint=prefill-a
WARN disaggregated prefill stalled waiting for decode response request_id=req-9 timeout_ms=5000
"""
    )

    assert report["event_counts"]["pd_role_mismatch"] == 1
    assert report["event_counts"]["pd_stall"] == 1
    codes = [finding["code"] for finding in report["findings"]]
    assert codes == ["lmcache_log_pd_role_mismatch", "lmcache_log_pd_stall"]

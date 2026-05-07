from inferguard.lmcache_http import parse_lmcache_http_payloads


def test_lmcache_http_parses_healthy_status() -> None:
    evidence = parse_lmcache_http_payloads(
        root_text="OK",
        health_text='{"is_healthy": true, "status": "ok"}',
        status_text='{"engine_type": "mp", "chunk_size": 256, "active_sessions": 3, "registered_gpu_ids": [0]}',
        conf_text='{"prometheus_port": 9090, "event_bus": {"queue_size": 10000}}',
        threads_text='{"threads": [{"name": "EventBusDrain", "alive": true}]}',
        periodic_threads_text='{"periodic_threads": ["eviction"]}',
        periodic_thread_text='{"name": "eviction", "healthy": true}',
        periodic_threads_health_text='{"healthy": true}',
    )

    assert evidence["booleans"]["has_root"] is True
    assert evidence["booleans"]["has_health"] is True
    assert evidence["booleans"]["has_status"] is True
    assert evidence["booleans"]["has_conf"] is True
    assert evidence["booleans"]["has_threads"] is True
    assert evidence["booleans"]["has_periodic_thread"] is True
    assert evidence["booleans"]["is_healthy"] is True
    assert evidence["endpoints"]["status"]["fields"]["chunk_size"] == 256
    assert evidence["endpoints"]["conf"]["fields"]["event_bus"]["queue_size"] == 10000


def test_lmcache_http_reports_unhealthy_failure() -> None:
    evidence = parse_lmcache_http_payloads(
        health_text='{"healthy": false, "failure_reason": "periodic thread stalled"}'
    )

    assert evidence["booleans"]["is_healthy"] is False
    assert evidence["failure_reasons"][0]["code"] == "lmcache_http_health_unhealthy"
    assert "periodic thread stalled" in evidence["failure_reasons"][0]["message"]


def test_lmcache_http_records_unavailable_and_skipped_endpoints() -> None:
    evidence = parse_lmcache_http_payloads(
        endpoint_errors={"threads": "HTTPError: 404"},
        skipped_endpoints=[{"endpoint": "POST /api/clear-cache", "reason": "destructive"}],
    )

    assert evidence["endpoints"]["threads"]["present"] is False
    assert evidence["endpoints"]["threads"]["status"] == "unavailable"
    assert evidence["skipped_endpoints"][0]["endpoint"] == "POST /api/clear-cache"

from inferguard.lmcache_http import parse_lmcache_http_payloads


def test_lmcache_http_parses_healthy_status() -> None:
    evidence = parse_lmcache_http_payloads(
        health_text='{"is_healthy": true, "status": "ok"}',
        status_text='{"engine_type": "mp", "chunk_size": 256, "active_sessions": 3, "registered_gpu_ids": [0]}',
    )

    assert evidence["booleans"]["has_health"] is True
    assert evidence["booleans"]["has_status"] is True
    assert evidence["booleans"]["is_healthy"] is True
    assert evidence["endpoints"]["status"]["fields"]["chunk_size"] == 256


def test_lmcache_http_reports_unhealthy_failure() -> None:
    evidence = parse_lmcache_http_payloads(
        health_text='{"healthy": false, "failure_reason": "periodic thread stalled"}'
    )

    assert evidence["booleans"]["is_healthy"] is False
    assert evidence["failure_reasons"][0]["code"] == "lmcache_http_health_unhealthy"
    assert "periodic thread stalled" in evidence["failure_reasons"][0]["message"]

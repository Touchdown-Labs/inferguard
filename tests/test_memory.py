"""Tests for memory module behavior with mocked HTTP clients."""

from __future__ import annotations

from unittest.mock import Mock, patch

import pytest

from inferguard.memory import MemoryStore, UpstashRedis, UpstashVector


@pytest.mark.asyncio
async def test_redis_set_payload() -> None:
    with patch("httpx.AsyncClient") as mock_client:
        instance = mock_client.return_value.__aenter__.return_value
        response = Mock()
        response.json.return_value = {"result": "OK"}
        response.raise_for_status = Mock()
        instance.post.return_value = response

        redis = UpstashRedis("https://fake.upstash.io", "fake-token")
        await redis.set("key", "value", ex=60)

        instance.post.assert_called_once()
        assert instance.post.call_args.kwargs["json"] == ["SET", "key", "value", "EX", 60]


@pytest.mark.asyncio
async def test_vector_query_payload() -> None:
    with patch("httpx.AsyncClient") as mock_client:
        instance = mock_client.return_value.__aenter__.return_value
        response = Mock()
        response.json.return_value = {
            "result": [
                {
                    "id": "inc-1",
                    "score": 0.95,
                    "metadata": {"diagnosis": "kv_saturation"},
                }
            ]
        }
        response.raise_for_status = Mock()
        instance.post.return_value = response

        vector = UpstashVector("https://fake.upstash.io", "fake-token")
        results = await vector.query("KV cache high", top_k=3)

        assert len(results) == 1
        assert results[0]["metadata"]["diagnosis"] == "kv_saturation"
        assert instance.post.call_args.kwargs["json"] == {
            "data": "KV cache high",
            "topK": 3,
            "includeMetadata": True,
        }


@pytest.mark.asyncio
async def test_memory_store_no_creds_graceful_degradation() -> None:
    store = MemoryStore(redis=None, vector=None)
    await store.store_snapshot({"timestamp": 1.0, "kv": 0.9})
    await store.log_event("test", {})
    await store.save_state({"hello": "world"})
    assert await store.load_state() == {}
    assert await store.find_similar_incidents("test") == []
    assert await store.load_incident_metrics("inc-1") == {}


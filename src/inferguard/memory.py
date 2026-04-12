"""Upstash Redis and Vector memory client helpers."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any

import httpx
import structlog

log = structlog.get_logger()


class UpstashRedis:
    """Minimal Upstash Redis REST client."""

    def __init__(self, url: str, token: str):
        self.url = url.rstrip("/")
        self.token = token
        self._headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

    async def _cmd(self, *args: str | int | float) -> Any:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(self.url, headers=self._headers, json=list(args))
            response.raise_for_status()
            return response.json().get("result")

    async def set(self, key: str, value: str, ex: int | None = None) -> None:
        if ex is not None:
            await self._cmd("SET", key, value, "EX", ex)
            return
        await self._cmd("SET", key, value)

    async def get(self, key: str) -> str | None:
        result = await self._cmd("GET", key)
        return None if result is None else str(result)

    async def xadd(self, stream: str, fields: dict[str, str], maxlen: int = 10000) -> str:
        args: list[str | int] = ["XADD", stream, "MAXLEN", "~", maxlen, "*"]
        for key, value in fields.items():
            args.extend([key, value])
        result = await self._cmd(*args)
        return "" if result is None else str(result)

    async def xrange(
        self,
        stream: str,
        start: str = "-",
        end: str = "+",
        count: int = 100,
    ) -> list[Any]:
        result = await self._cmd("XRANGE", stream, start, end, "COUNT", count)
        return result or []

    async def scan_keys(self, pattern: str, count: int = 200) -> list[str]:
        """Minimal non-cursor SCAN helper. v5.2 cap: 200 keys per call is
        enough for a 10-minute snapshot window at 10s poll intervals (=60
        snapshots). Returns an empty list on any error so callers can
        degrade gracefully.
        """
        try:
            result = await self._cmd("SCAN", 0, "MATCH", pattern, "COUNT", count)
        except Exception:
            return []
        if not isinstance(result, list) or len(result) < 2:
            return []
        keys = result[1]
        if not isinstance(keys, list):
            return []
        return [str(k) for k in keys]


class UpstashVector:
    """Minimal Upstash Vector REST client using text auto-embedding."""

    def __init__(self, url: str, token: str):
        self.url = url.rstrip("/")
        self.token = token
        self._headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

    async def upsert(self, doc_id: str, text: str, metadata: dict[str, Any]) -> None:
        payload = [{"id": doc_id, "data": text, "metadata": metadata}]
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(f"{self.url}/upsert", headers=self._headers, json=payload)
            response.raise_for_status()

    async def query(self, text: str, top_k: int = 3) -> list[dict[str, Any]]:
        payload = {"data": text, "topK": top_k, "includeMetadata": True}
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(f"{self.url}/query", headers=self._headers, json=payload)
            response.raise_for_status()
            return response.json().get("result", [])

    async def update_metadata(self, doc_id: str, metadata_update: dict[str, Any]) -> None:
        payload = {"id": doc_id, "metadataUpdateMode": "PATCH", "metadata": metadata_update}
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(f"{self.url}/update", headers=self._headers, json=payload)
            response.raise_for_status()


@dataclass(slots=True)
class Incident:
    id: str
    timestamp: float
    engine: str
    anomaly_reasons: list[str]
    severity: str
    metrics_snapshot: dict[str, Any]
    diagnosis: str = ""
    recommended_fix: str = ""
    resolution_effective: bool | None = None


class MemoryStore:
    """Three-tier memory facade over Redis and Vector."""

    STREAM_KEY = "inferguard:events"
    STATE_KEY = "inferguard:state"
    SNAPSHOT_PREFIX = "inferguard:snapshot:"
    INCIDENT_METRICS_PREFIX = "inferguard:incident_metrics:"

    def __init__(self, redis: UpstashRedis | None, vector: UpstashVector | None):
        self.redis = redis
        self.vector = vector

    async def store_snapshot(self, snapshot_dict: dict[str, Any]) -> None:
        if not self.redis:
            return
        key = f"{self.SNAPSHOT_PREFIX}{int(float(snapshot_dict['timestamp']))}"
        await self.redis.set(key, json.dumps(snapshot_dict, default=str), ex=3600)

    async def log_event(self, event_type: str, data: dict[str, Any]) -> None:
        if not self.redis:
            return
        fields = {
            "type": event_type,
            "ts": str(time.time()),
            "data": json.dumps(data, default=str),
        }
        await self.redis.xadd(self.STREAM_KEY, fields)

    async def store_incident(self, incident: Incident) -> None:
        text = f"Engine: {incident.engine}. " + " ".join(incident.anomaly_reasons)
        if incident.diagnosis:
            text += f" Diagnosis: {incident.diagnosis}"
        if incident.recommended_fix:
            text += f" Fix: {incident.recommended_fix}"

        if self.vector:
            await self.vector.upsert(
                incident.id,
                text,
                {
                    "timestamp": incident.timestamp,
                    "engine": incident.engine,
                    "severity": incident.severity,
                    "diagnosis": incident.diagnosis,
                    "recommended_fix": incident.recommended_fix,
                    "resolution_effective": incident.resolution_effective,
                },
            )

        if self.redis:
            await self.log_event(
                "incident",
                {
                    "id": incident.id,
                    "severity": incident.severity,
                    "reasons": incident.anomaly_reasons,
                    "diagnosis": incident.diagnosis,
                    "fix": incident.recommended_fix,
                },
            )

    async def find_similar_incidents(self, description: str, top_k: int = 3) -> list[dict[str, Any]]:
        if not self.vector:
            return []
        return await self.vector.query(description, top_k=top_k)

    async def save_state(self, state: dict[str, Any]) -> None:
        if not self.redis:
            return
        await self.redis.set(self.STATE_KEY, json.dumps(state, default=str))

    async def load_state(self) -> dict[str, Any]:
        if not self.redis:
            return {}
        raw = await self.redis.get(self.STATE_KEY)
        if not raw:
            return {}
        return json.loads(raw)

    async def save_incident_metrics(self, incident_id: str, snapshot: dict[str, Any]) -> None:
        if not self.redis:
            return
        key = f"{self.INCIDENT_METRICS_PREFIX}{incident_id}"
        await self.redis.set(key, json.dumps(snapshot, default=str), ex=86400)

    async def load_incident_metrics(self, incident_id: str) -> dict[str, Any]:
        if not self.redis:
            return {}
        raw = await self.redis.get(f"{self.INCIDENT_METRICS_PREFIX}{incident_id}")
        if not raw:
            return {}
        return json.loads(raw)

    async def load_window_snapshots(self, window_seconds: int = 600) -> list[dict[str, Any]]:
        """Read the last N seconds of metric snapshots from Redis.

        Keys live at `inferguard:snapshot:{unix_ts_int}`. Uses SCAN to find
        matching keys, filters by the timestamp suffix against
        `time.time() - window_seconds`, GETs each, and returns deserialized
        snapshot dicts ordered by timestamp ascending. Graceful empty list
        if Redis is not provisioned.
        """
        if not self.redis:
            return []
        try:
            keys = await self.redis.scan_keys(f"{self.SNAPSHOT_PREFIX}*")
        except Exception:
            return []
        if not keys:
            return []
        cutoff = int(time.time() - max(window_seconds, 0))
        wanted: list[tuple[int, str]] = []
        for k in keys:
            suffix = k.rsplit(":", 1)[-1]
            try:
                ts = int(suffix)
            except ValueError:
                continue
            if ts >= cutoff:
                wanted.append((ts, k))
        wanted.sort(key=lambda x: x[0])
        snapshots: list[dict[str, Any]] = []
        for _, k in wanted[-120:]:  # cap at 120 to keep the sandbox payload lean
            try:
                raw = await self.redis.get(k)
                if raw:
                    snapshots.append(json.loads(raw))
            except Exception:
                continue
        return snapshots

    async def load_event_log_tail(self, count: int = 50) -> list[dict[str, Any]]:
        """Read the last N events from the inferguard:events Redis stream.

        Parses the stream entry field dicts into plain dicts. Returns in
        chronological order. Empty list if Redis is unavailable.
        """
        if not self.redis:
            return []
        try:
            raw_entries = await self.redis.xrange(self.STREAM_KEY, count=count)
        except Exception:
            return []
        entries: list[dict[str, Any]] = []
        for entry in raw_entries or []:
            # Upstash XRANGE entries are [id, [field1, value1, field2, value2, ...]]
            if not isinstance(entry, list) or len(entry) != 2:
                continue
            entry_id, fields = entry
            if not isinstance(fields, list):
                continue
            parsed: dict[str, Any] = {"_id": str(entry_id)}
            for i in range(0, len(fields) - 1, 2):
                key = str(fields[i])
                value = fields[i + 1]
                if key == "data" and isinstance(value, str):
                    try:
                        parsed[key] = json.loads(value)
                        continue
                    except json.JSONDecodeError:
                        pass
                parsed[key] = value
            entries.append(parsed)
        return entries

    async def update_incident_resolution(
        self,
        incident_id: str,
        resolved: bool,
        *,
        improvements: list[str] | None = None,
        regressions: list[str] | None = None,
        observed_kv_reduction: float | None = None,
        observed_accuracy_delta_pp: float | None = None,
        observed_overhead_s: float | None = None,
        action_type: str | None = None,
    ) -> None:
        if self.vector:
            try:
                metadata_update: dict[str, Any] = {
                    "resolution_effective": resolved,
                    "resolution_checked_at": time.time(),
                    "improvements": improvements or [],
                    "regressions": regressions or [],
                }
                # v5.2: persist observed compaction outcomes into the Vector row
                # so the learning loop has labeled training rows for the MAD
                # threshold policy (PRD v5.1 §P write-side gap closure).
                if observed_kv_reduction is not None:
                    metadata_update["observed_kv_reduction"] = float(observed_kv_reduction)
                if observed_accuracy_delta_pp is not None:
                    metadata_update["observed_accuracy_delta_pp"] = float(observed_accuracy_delta_pp)
                if observed_overhead_s is not None:
                    metadata_update["observed_overhead_s"] = float(observed_overhead_s)
                if action_type is not None:
                    metadata_update["action_type"] = str(action_type)
                await self.vector.update_metadata(incident_id, metadata_update)
            except Exception as exc:  # pragma: no cover - network failure path
                log.warning("resolution_update_failed", id=incident_id, error=str(exc))

        if self.redis:
            await self.log_event(
                "resolution_check",
                {
                    "incident_id": incident_id,
                    "resolved": resolved,
                    "improvements": improvements or [],
                    "regressions": regressions or [],
                },
            )


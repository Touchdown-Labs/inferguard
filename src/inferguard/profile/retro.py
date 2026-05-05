"""Minimal retro profile helper for existing profile/timeline JSONL files."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from inferguard.io import atomic_write_json
from inferguard.profile.render import summary_markdown
from inferguard.profile.types import ProfileSummary


class ProfileRetroError(RuntimeError):
    """Raised when a retro input cannot be read."""


def run_profile_retro(input_path: Path, output_dir: Path) -> ProfileSummary:
    """Summarize an existing JSONL profile/timeline file.

    PR-T1 keeps retro intentionally small: it counts rows and preserves the
    profile schema family so operators can point the command at a prior
    ``profile.jsonl`` without rerunning live scrapes.
    """
    if not input_path.exists():
        raise ProfileRetroError(f"input file does not exist: {input_path}")
    rows = _read_jsonl(input_path)
    profile_id = _profile_id(rows, input_path)
    summary = ProfileSummary(
        profile_id=profile_id,
        duration_seconds=0.0,
        sample_count=len(rows),
        engine=_engine(rows),
        highest_kv_cache_usage=_highest_kv(rows),
        max_requests_waiting=_max_waiting(rows),
        preemptions_total_delta=None,
        prefix_cache_hit_rate_observed=None,
        recommendation="Retro summary generated from existing JSONL; rerun profile live for trend findings.",
        findings=[],
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    atomic_write_json(output_dir / "profile_summary.json", summary.as_dict())
    (output_dir / "profile.md").write_text(summary_markdown(summary), encoding="utf-8")
    return summary


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as fp:
        for line_number, line in enumerate(fp, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ProfileRetroError(f"invalid JSONL at line {line_number}: {exc}") from exc
            if isinstance(payload, dict):
                rows.append(payload)
    return rows


def _profile_id(rows: list[dict[str, Any]], path: Path) -> str:
    for row in rows:
        profile_id = row.get("profile_id")
        if profile_id:
            return str(profile_id)
    return f"retro_{path.stem}"


def _engine(rows: list[dict[str, Any]]) -> str:
    for row in reversed(rows):
        snapshot = row.get("snapshot") or row.get("disagg_snapshot") or {}
        endpoint = snapshot.get("endpoint") or {}
        engine = endpoint.get("engine")
        if engine:
            return str(engine)
    return "unknown"


def _highest_kv(rows: list[dict[str, Any]]) -> float | None:
    values: list[float] = []
    for row in rows:
        snapshot = row.get("snapshot") or row.get("disagg_snapshot") or {}
        value = snapshot.get("kv_cache_usage")
        if value is not None:
            values.append(float(value))
    return max(values) if values else None


def _max_waiting(rows: list[dict[str, Any]]) -> int | None:
    values: list[int] = []
    for row in rows:
        snapshot = row.get("snapshot") or row.get("disagg_snapshot") or {}
        value = snapshot.get("requests_waiting")
        if value is not None:
            values.append(int(value))
    return max(values) if values else None

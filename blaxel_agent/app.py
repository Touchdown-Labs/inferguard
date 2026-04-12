"""FastAPI entrypoint for InferGuard L3 Blaxel brain."""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI

from blaxel_agent.brain import InferGuardBrain

app = FastAPI(title="InferGuard Blaxel Agent", version="0.1.0")


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "layer": "L3", "mode": "blaxel_agent"}


@app.post("/investigate")
async def investigate(body: dict[str, Any]) -> dict[str, Any]:
    advisories = await InferGuardBrain().investigate(body)
    return {"advisories": advisories}


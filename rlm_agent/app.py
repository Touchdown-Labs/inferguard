"""FastAPI entrypoint for InferGuard L3 RLM agent brain."""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI

from rlm_agent.brain import InferGuardBrain

app = FastAPI(title="InferGuard RLM Agent", version="0.1.0")


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "layer": "L3", "mode": "rlm_agent"}


@app.post("/investigate")
async def investigate(body: dict[str, Any]) -> dict[str, Any]:
    advisories = await InferGuardBrain().investigate(body)
    return {"advisories": advisories}


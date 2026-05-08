#!/usr/bin/env python3
"""Minimal Modal dispatch smoke test.

Run this before expensive H100 packet labs when Modal is accepting app creation
but not starting function tasks.

Usage:
    modal run scripts/modal_dispatch_smoke.py::smoke
"""

from __future__ import annotations

import modal

app = modal.App("inferguard-modal-dispatch-smoke")


@app.function(timeout=120)
def smoke() -> str:
    print("inferguard modal dispatch smoke started")
    return "ok"


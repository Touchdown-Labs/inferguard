"""Optional psutil CPU timeline sampler for InferGuard bench runs."""

from __future__ import annotations

import json
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

CPU_TIMELINE_SCHEMA_VERSION = "inferguard-cpu-timeline/v1"


@dataclass
class CpuTraceSampler:
    path: Path
    engine_match: str | None = None
    interval_seconds: float = 0.1
    _thread: threading.Thread | None = None
    _stop: threading.Event | None = None
    _psutil: Any = None
    _last_ctx_switches: int | None = None
    _captured: int = 0

    @property
    def captured_count(self) -> int:
        return self._captured

    def start(self) -> bool:
        try:
            import psutil  # type: ignore[import-not-found]
        except ImportError:
            print("cpu trace disabled: psutil is not installed", file=sys.stderr)
            return False
        self._psutil = psutil
        self.path.write_text("", encoding="utf-8")
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, name="inferguard-cpu-trace", daemon=True)
        self._thread.start()
        return True

    def stop(self) -> None:
        if self._stop is None or self._thread is None:
            return
        self._stop.set()
        self._thread.join(timeout=max(1.0, self.interval_seconds * 2))

    def _run(self) -> None:
        assert self._stop is not None
        sequence = 0
        while not self._stop.is_set():
            try:
                sample = self._sample(sequence)
                with self.path.open("a", encoding="utf-8") as handle:
                    handle.write(json.dumps(sample, sort_keys=True) + "\n")
                self._captured += 1
                sequence += 1
            except Exception as exc:  # noqa: BLE001 - sampler is best-effort sidecar
                print(f"cpu trace sample failed: {exc}", file=sys.stderr)
            self._stop.wait(self.interval_seconds)

    def _sample(self, sequence: int) -> dict[str, Any]:
        psutil = self._psutil
        stats = psutil.cpu_stats()
        ctx_switches = int(getattr(stats, "ctx_switches", 0))
        prev_ctx = self._last_ctx_switches
        self._last_ctx_switches = ctx_switches
        proc = psutil.Process()
        proc_ctx = proc.num_ctx_switches()
        voluntary = int(getattr(proc_ctx, "voluntary", 0))
        involuntary = int(getattr(proc_ctx, "involuntary", 0))
        return {
            "schema_version": CPU_TIMELINE_SCHEMA_VERSION,
            "observed_at": time.time(),
            "sequence": sequence,
            "per_cpu_utilization": psutil.cpu_percent(interval=None, percpu=True),
            "ctx_switches_delta": None if prev_ctx is None else max(0, ctx_switches - prev_ctx),
            "gil_pressure_heuristic": voluntary / max(1, involuntary),
            "client_context_switches": {
                "voluntary": voluntary,
                "involuntary": involuntary,
            },
            "engine_process_count": self._engine_process_count(),
        }

    def _engine_process_count(self) -> int | None:
        if not self.engine_match:
            return None
        count = 0
        needle = self.engine_match.lower()
        for proc in self._psutil.process_iter(["cmdline"]):
            try:
                cmdline = " ".join(proc.info.get("cmdline") or []).lower()
            except Exception:  # noqa: BLE001 - process may disappear
                continue
            if needle in cmdline:
                count += 1
        return count

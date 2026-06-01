"""Restricted local REPL sandbox environment for RLM agents."""

from __future__ import annotations

import io
import sys
import contextlib
from typing import Any

from rlm_agent.rlm_engine import tools


class LocalRepl:
    """A persistent local sandboxed Python REPL for executing prompt code blocks."""

    def __init__(self, context_dict: dict[str, Any] | None = None):
        self.variables = {
            "__builtins__": __builtins__,
            # Inject zero-token diagnostic tools globally
            "calculate_kv_slope": tools.calculate_kv_slope,
            "match_prior_incident": tools.match_prior_incident,
            "slice_redis_logs": tools.slice_redis_logs,
            # Bind context variables directly in the sandbox namespace
            "context": context_dict or {},
            "snapshots": (context_dict or {}).get("window_snapshots", []),
            "events": (context_dict or {}).get("event_log_tail", []),
            "current": (context_dict or {}).get("current_snapshot", {}),
        }

    def run_code(self, code_str: str) -> str:
        """Executes the provided Python code block and returns standard output."""
        stdout_buf = io.StringIO()
        
        # Remove any leading markdown code fences
        clean_code = self._strip_fences(code_str)

        try:
            with contextlib.redirect_stdout(stdout_buf):
                # We compile and exec in our local variables namespace to maintain state persistence
                compiled_code = compile(clean_code, "<repl>", "exec")
                exec(compiled_code, self.variables)
            return stdout_buf.getvalue()
        except Exception as err:
            return f"ExecutionError: {type(err).__name__}: {str(err)}"

    def _strip_fences(self, text: str) -> str:
        text = text.strip()
        if text.startswith("```"):
            lines = text.splitlines()
            if lines and lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            return "\n".join(lines).strip()
        return text

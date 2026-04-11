"""Config fix generation for supported inference engines."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class RemediationResult:
    description: str
    config_diff: dict[str, str]
    launch_command: str
    explanation: str
    model_notes: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, object]:
        return {
            "description": self.description,
            "config_diff": dict(self.config_diff),
            "launch_command": self.launch_command,
            "explanation": self.explanation,
            "model_notes": list(self.model_notes),
        }


def _detect_model_family(model_name: str) -> str:
    lower = model_name.lower() if model_name else ""
    if "deepseek" in lower and ("r1" in lower or "v3" in lower):
        return "deepseek-distill" if "distill" in lower else "deepseek-r1"
    if "qwen3.5" in lower or "qwen-3.5" in lower:
        return "qwen35"
    if "gpt-oss" in lower or "gptoss" in lower:
        return "gpt-oss"
    return "unknown"


def generate_fix(
    failure_mode: str,
    engine: str,
    current_metrics: dict[str, Any],
    diagnosis_action: str,
    model_name: str = "",
) -> RemediationResult:
    del current_metrics  # reserved for future richer tailoring

    diff: dict[str, str] = {}
    description = "No automated fix available. See diagnosis for manual steps."
    explanation = diagnosis_action
    model_notes: list[str] = []
    family = _detect_model_family(model_name)

    if family == "deepseek-r1":
        model_notes.append(
            "DeepSeek-R1 uses MLA, so elevated apparent KV pressure is more severe than on standard GQA models."
        )
    elif family == "qwen35":
        model_notes.append(
            "Qwen3.5 hybrid models can under-report pressure in standard KV metrics; concurrency cuts matter early."
        )
    elif family == "gpt-oss":
        model_notes.append(
            "GPT-OSS uses more standard serving interpretation, but queueing and prefix reuse still depend on workload shape."
        )

    if failure_mode == "kv_saturation":
        diff["--kv-cache-dtype"] = "fp8_e4m3"
        diff["--gpu-memory-utilization"] = "0.95"
        description = "Reduce KV pressure with FP8 KV cache and a higher GPU memory utilization cap."
        if family == "deepseek-r1":
            diff["--max-num-seqs"] = "64"
            model_notes.append("DeepSeek-R1 often needs aggressive concurrency reduction before other tuning helps.")

    elif failure_mode == "prefix_cache_miss":
        if engine == "sglang":
            diff["--schedule-policy"] = "lpm"
            description = "Use longest-prefix-match scheduling to improve prefix reuse."
        else:
            diff["--enable-prefix-caching"] = ""
            description = "Enable prefix caching to improve prompt reuse."

    elif failure_mode == "queue_backup":
        diff["--max-num-seqs"] = "512"
        if engine == "sglang":
            diff["--chunked-prefill-size"] = "8192"
            description = "Raise sequence capacity and chunked prefill to drain queue pressure."
        else:
            diff["--enable-chunked-prefill"] = ""
            description = "Raise sequence capacity and enable chunked prefill to drain queue pressure."

    elif failure_mode == "preemption_storm":
        diff["--kv-cache-dtype"] = "fp8_e4m3"
        diff["--max-num-seqs"] = "128"
        description = "Cut concurrency and reduce KV pressure to stop preemptions."
        if family == "deepseek-r1":
            diff["--max-num-seqs"] = "32"

    elif failure_mode == "swap_thrash":
        if engine == "vllm":
            diff["--swap-space"] = "0"
        diff["--kv-cache-dtype"] = "fp8_e4m3"
        description = "Avoid CPU swap thrash and move memory pressure back to GPU-friendly settings."

    elif failure_mode == "ttft_regression":
        if engine == "sglang":
            diff["--schedule-policy"] = "lpm"
            diff["--chunked-prefill-size"] = "4096"
            description = "Use LPM scheduling and smaller prefill chunks to improve TTFT."
        else:
            diff["--enable-prefix-caching"] = ""
            diff["--enable-chunked-prefill"] = ""
            description = "Enable prefix caching and chunked prefill to improve TTFT."

    if engine == "sglang":
        parts = ["python -m sglang.launch_server", f"  --model-path {model_name or '<MODEL>'}"]
        for flag, value in diff.items():
            parts.append(f"  {flag} {value}" if value else f"  {flag}")
        parts.append("  --enable-metrics")
        if family in {"deepseek-r1", "qwen35", "gpt-oss"}:
            parts.append("  --trust-remote-code")
        if family == "deepseek-r1":
            parts.append("  --enable-dp-attention")
    else:
        parts = [f"vllm serve {model_name or '<MODEL>'}"]
        for flag, value in diff.items():
            parts.append(f"  {flag} {value}" if value else f"  {flag}")
        if family in {"deepseek-r1", "qwen35", "gpt-oss"}:
            parts.append("  --trust-remote-code")
        if family == "deepseek-r1":
            parts.extend(
                [
                    "  --block-size 1",
                    "  --enable-reasoning",
                    "  --reasoning-parser deepseek_r1",
                ]
            )

    return RemediationResult(
        description=description,
        config_diff=diff,
        launch_command=" \\\n".join(parts),
        explanation=explanation,
        model_notes=model_notes,
    )


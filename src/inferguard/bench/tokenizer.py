"""Cheap token estimation utilities.

InferGuard Bench intentionally avoids tokenizer dependencies. Estimates are labeled as
``estimated`` in artifacts and should not be treated as exact model tokenization.
"""

from __future__ import annotations

from typing import Any


def estimate_text_tokens(text: str) -> int:
    if not text:
        return 0
    return max(1, round(len(text) / 4))


def estimate_messages_tokens(messages: list[dict[str, Any]]) -> int:
    total = 0
    for message in messages:
        total += 4
        content = message.get("content", "")
        total += estimate_text_tokens(content if isinstance(content, str) else str(content))
    return total

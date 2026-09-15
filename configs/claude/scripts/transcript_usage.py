"""Validate usage records shared by local attribution reports."""

from __future__ import annotations

import sys
from collections import Counter

_warnings: Counter[str] = Counter()


def warn_skipped(reason: str) -> None:
    """Bound diagnostics per process without printing any transcript payload."""
    _warnings[reason] += 1
    if _warnings[reason] <= 20:
        print(f"transcript-usage: skipped {reason}", file=sys.stderr)
    elif _warnings[reason] == 21:
        print(
            f"transcript-usage: further {reason} diagnostics suppressed; evidence incomplete",
            file=sys.stderr,
        )


def usage_key(record: dict, message: dict, requests: dict) -> str | tuple[str, int]:
    """Missing IDs cannot deduplicate safely; retain rows and flag uncertainty."""
    key = record.get("requestId") or message.get("id")
    if isinstance(key, str) and key:
        return key
    warn_skipped("deduplication for missing request ID; counts may be overstated")
    return ("missing-id", len(requests))


def usage_message(record: object) -> tuple[dict, dict] | None:
    """Return an assistant usage pair, or reject malformed shapes/token counts."""
    if not isinstance(record, dict):
        raise ValueError("record must be an object")
    if record.get("type") != "assistant":
        return None
    message = record.get("message")
    if not isinstance(message, dict):
        raise ValueError("message must be an object")
    if "model" in message and not isinstance(message["model"], str):
        raise ValueError("model must be a string")
    content = message.get("content", [])
    if not isinstance(content, list):
        raise ValueError("content must be an array")
    for block in content:
        if not isinstance(block, dict):
            raise ValueError("content block must be an object")
        for key in ("type", "name"):
            if key in block and not isinstance(block[key], str):
                raise ValueError("block label must be a string")
    usage = message.get("usage")
    if usage is None:
        return None
    if not isinstance(usage, dict):
        raise ValueError("usage must be an object")
    for key in (
        "input_tokens",
        "output_tokens",
        "cache_read_input_tokens",
        "cache_creation_input_tokens",
    ):
        value = usage.get(key, 0)
        if value is not None and (type(value) is not int or value < 0):
            raise ValueError("token count must be nonnegative integer")
    return (message, usage) if usage else None

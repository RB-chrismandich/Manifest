#!/usr/bin/env python3
"""Ingest Claude Code transcripts into scrubbed, noise-stripped session JSON.

Passive replacement for the retired SkillClaw capture proxy. Reads
~/.claude/projects/**/*.jsonl, normalizes conversation turns, truncates noisy
tool payloads, filters by recency, skips still-being-written files, and tracks
processed sessions incrementally.

Usage:
    skillclaw_ingest.py <transcripts_dir> <out_dir> [--state FILE]
        [--window-days N] [--settle-minutes N] [--max-tool-output-chars N]
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

DEFAULT_MAX_TOOL_OUTPUT = 500


def _truncate(text: str, limit: int) -> tuple[str, bool]:
    if len(text) <= limit:
        return text, False
    return text[:limit] + f"…[+{len(text) - limit} chars truncated]", True


def normalize_content(content, max_tool_output_chars: int = DEFAULT_MAX_TOOL_OUTPUT) -> list[dict]:
    """Normalize a message.content (str or block list) into kept blocks."""
    if isinstance(content, str):
        return [{"kind": "text", "text": content}] if content.strip() else []
    if not isinstance(content, list):
        return []
    out: list[dict] = []
    for block in content:
        if not isinstance(block, dict):
            continue
        bt = block.get("type")
        if bt == "text":
            txt = block.get("text", "")
            if txt.strip():
                out.append({"kind": "text", "text": txt})
        elif bt == "thinking":
            txt = block.get("thinking", "")
            if txt.strip():
                out.append({"kind": "thinking", "text": txt})
        elif bt == "tool_use":
            raw_input = block.get("input", {})
            trimmed = {}
            if isinstance(raw_input, dict):
                for k, v in raw_input.items():
                    if isinstance(v, str):
                        trimmed[k] = _truncate(v, max_tool_output_chars)[0]
                    else:
                        trimmed[k] = v
            else:
                trimmed = raw_input
            out.append({"kind": "tool_use", "name": block.get("name", "?"),
                        "input": trimmed})
        elif bt == "tool_result":
            raw = block.get("content", "")
            if not isinstance(raw, str):
                raw = json.dumps(raw)
            text, truncated = _truncate(raw, max_tool_output_chars)
            out.append({"kind": "tool_result", "output": text,
                        "is_error": bool(block.get("is_error", False)),
                        "truncated": truncated})
    return out

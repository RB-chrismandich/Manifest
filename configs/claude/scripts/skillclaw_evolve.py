#!/usr/bin/env python3
"""Distill SKILL.md candidates from ingested sessions via `claude -p` (Max-backed).

Replaces the retired `skillclaw evolve` binary. Map-reduces sessions through the
headless Claude CLI: chunks that exceed the token budget are distilled
independently (map), then merged (reduce). No proxy, no API key.

Usage:
    skillclaw_evolve.py <sessions_dir> <evolved_dir> [--template FILE]
        [--token-budget N]
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

DEFAULT_TOKEN_BUDGET = 100_000
_SKILL_RE = re.compile(r"~~~skill name=(?P<name>[^\n]+)\n(?P<body>.*?)~~~", re.DOTALL)


def estimate_tokens(text: str) -> int:
    """Cheap heuristic: ~4 chars per token."""
    return len(text) // 4


def _render_session(s: dict) -> str:
    lines = [f"### session {s.get('session_id', '?')}"]
    for turn in s.get("turns", []):
        for b in turn["blocks"]:
            if b["kind"] in ("text", "thinking"):
                lines.append(f"[{turn['role']}/{b['kind']}] {b['text']}")
            elif b["kind"] == "tool_use":
                lines.append(f"[tool_use {b['name']}] {json.dumps(b['input'])}")
            elif b["kind"] == "tool_result":
                lines.append(f"[tool_result err={b['is_error']}] {b['output']}")
    return "\n".join(lines)


def load_sessions(sessions_dir) -> list[dict]:
    sessions_dir = Path(sessions_dir).expanduser()
    out = []
    for f in sorted(sessions_dir.glob("*.json")):
        try:
            out.append(json.loads(f.read_text(encoding="utf-8")))
        except json.JSONDecodeError:
            continue
    return out


def build_prompt(template: str, sessions: list[dict], library_names: list[str]) -> str:
    library = "\n".join(f"- {n}" for n in library_names) or "(empty)"
    rendered = "\n\n".join(_render_session(s) for s in sessions) or "(none)"
    return template.replace("{{LIBRARY}}", library).replace("{{SESSIONS}}", rendered)


def parse_candidates(output: str) -> list[dict]:
    return [{"name": m.group("name").strip(), "content": m.group("body")}
            for m in _SKILL_RE.finditer(output)]


def chunk_sessions(sessions: list[dict], token_budget: int) -> list[list[dict]]:
    """Greedily pack sessions into chunks whose rendered size stays under budget.

    A single session larger than the budget gets its own chunk (it cannot be
    split further here; the renderer already truncated tool noise upstream).
    """
    if not sessions:
        return []
    chunks: list[list[dict]] = []
    current: list[dict] = []
    current_tokens = 0
    for s in sessions:
        cost = estimate_tokens(_render_session(s))
        if current and current_tokens + cost > token_budget:
            chunks.append(current)
            current, current_tokens = [], 0
        current.append(s)
        current_tokens += cost
    if current:
        chunks.append(current)
    return chunks

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


def subprocess_runner(prompt: str) -> str:
    """Default runner: invoke headless `claude -p` (Max-backed)."""
    proc = subprocess.run(["claude", "-p", prompt], capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"claude -p failed: {proc.stderr.strip()}")
    return proc.stdout


def write_candidates(candidates: list[dict], evolved_dir: Path) -> list[str]:
    evolved_dir = Path(evolved_dir).expanduser()
    written = []
    for c in candidates:
        d = evolved_dir / c["name"]
        d.mkdir(parents=True, exist_ok=True)
        (d / "SKILL.md").write_text(c["content"], encoding="utf-8")
        written.append(c["name"])
    return written


def _library_names(skills_dir: Path) -> list[str]:
    """Skill directory names under a skills root (each holding a SKILL.md)."""
    base = Path(skills_dir).expanduser()
    return sorted(p.parent.name for p in base.glob("*/SKILL.md")) if base.exists() else []


def evolve(sessions_dir, evolved_dir, template_path, *,
           committed_dir=None, token_budget=DEFAULT_TOKEN_BUDGET, runner=subprocess_runner) -> dict:
    """Map-reduce sessions into SKILL.md candidates. Returns a summary dict.

    The prompt's "existing library" is the committed library (committed_dir) so
    the model does not re-propose already-merged skills; it falls back to
    evolved_dir only when no committed library is supplied.
    """
    sessions = load_sessions(sessions_dir)
    template = Path(template_path).expanduser().read_text(encoding="utf-8")
    library = _library_names(committed_dir if committed_dir is not None else evolved_dir)
    if not sessions:
        return {"candidates": 0, "chunks": 0, "written": []}

    chunks = chunk_sessions(sessions, token_budget)
    mapped: list[dict] = []
    for chunk in chunks:
        out = runner(build_prompt(template, chunk, library))
        mapped.extend(parse_candidates(out))

    # reduce: dedupe by name (last write wins); a single chunk skips a 2nd call
    if len(chunks) > 1 and mapped:
        deduped = {}
        for c in mapped:
            deduped[c["name"]] = c
        mapped = list(deduped.values())

    written = write_candidates(mapped, evolved_dir)
    return {"candidates": len(written), "chunks": len(chunks), "written": written}


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("sessions_dir")
    ap.add_argument("evolved_dir")
    ap.add_argument("--template", default="~/.claude/prompts/skillclaw_evolve.md")
    ap.add_argument("--committed-dir",
                    help="committed skill library shown to the model (avoids re-proposals)")
    ap.add_argument("--token-budget", type=int, default=DEFAULT_TOKEN_BUDGET)
    args = ap.parse_args(argv)
    try:
        summary = evolve(args.sessions_dir, args.evolved_dir, args.template,
                         committed_dir=args.committed_dir, token_budget=args.token_budget)
    except (RuntimeError, FileNotFoundError) as e:
        print(f"skillclaw_evolve: {e}", file=sys.stderr)
        return 1
    print(json.dumps(summary))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

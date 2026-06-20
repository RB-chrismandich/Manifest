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


def parse_transcript(path: Path, max_tool_output_chars: int = DEFAULT_MAX_TOOL_OUTPUT) -> dict | None:
    """Parse one transcript .jsonl into a session record, or None if no turns.

    Defensive: skips unparseable lines (including a truncated trailing line from
    a still-active session) rather than raising.
    """
    session_id = path.stem
    cwd = git_branch = None
    turns: list[dict] = []
    with path.open(encoding="utf-8", errors="replace") as fh:
        for line in fh:
            # ⚡ Bolt: Fast-path bypass for string allocation overhead (.strip) and
            # json.loads exception overhead. Transcript files are consistently formatted
            # so we only incur parsing costs when the line looks exactly like our target.
            if not line or line[0] != "{":
                continue
            try:
                obj = json.loads(line)
            except ValueError:
                continue  # partial/corrupt line — skip
            if type(obj) is not dict or obj.get("type") not in ("user", "assistant"):
                continue
            session_id = obj.get("sessionId", session_id)
            cwd = obj.get("cwd", cwd)
            git_branch = obj.get("gitBranch", git_branch)
            msg = obj.get("message", {})
            blocks = normalize_content(msg.get("content"), max_tool_output_chars)
            if blocks:
                turns.append({"role": msg.get("role", "?"), "blocks": blocks})
    if not turns:
        return None
    return {"session_id": session_id, "cwd": cwd, "git_branch": git_branch, "turns": turns}


def within_window(mtime: float, now: float, window_days: int) -> bool:
    """True if mtime falls within the last window_days from now."""
    return (now - mtime) <= window_days * 86400


def is_settled(mtime: float, now: float, settle_minutes: int) -> bool:
    """True if the file has been idle long enough to be safely read."""
    return (now - mtime) >= settle_minutes * 60


def load_state(state_path: Path) -> dict:
    try:
        return json.loads(state_path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def save_state(state_path: Path, state: dict) -> None:
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(json.dumps(state, indent=2), encoding="utf-8")


def ingest(transcripts_dir, out_dir, state_path, *, window_days, settle_minutes,
           max_tool_output_chars, now=None) -> dict:
    """Ingest new, settled, in-window transcripts into out_dir. Returns counts."""
    now = time.time() if now is None else now
    transcripts_dir = Path(transcripts_dir).expanduser()
    out_dir = Path(out_dir).expanduser()
    out_dir.mkdir(parents=True, exist_ok=True)
    state_path = Path(state_path).expanduser()
    state = load_state(state_path)

    summary = {"ingested": 0, "skipped_old": 0, "skipped_unsettled": 0,
               "skipped_seen": 0, "skipped_empty": 0}
    for f in sorted(transcripts_dir.rglob("*.jsonl")):
        mtime = f.stat().st_mtime
        if not within_window(mtime, now, window_days):
            summary["skipped_old"] += 1
            continue
        if not is_settled(mtime, now, settle_minutes):
            summary["skipped_unsettled"] += 1
            continue
        key = str(f)
        if state.get(key) == mtime:
            summary["skipped_seen"] += 1
            continue
        rec = parse_transcript(f, max_tool_output_chars)
        if rec is None:
            summary["skipped_empty"] += 1
            state[key] = mtime
            continue
        (out_dir / f"{rec['session_id']}.json").write_text(
            json.dumps(rec, indent=2), encoding="utf-8")
        state[key] = mtime
        summary["ingested"] += 1
    save_state(state_path, state)
    return summary


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("transcripts_dir")
    ap.add_argument("out_dir")
    ap.add_argument("--state", default="~/.skillclaw/.ingest-state.json")
    ap.add_argument("--window-days", type=int, default=30)
    ap.add_argument("--settle-minutes", type=int, default=5)
    ap.add_argument("--max-tool-output-chars", type=int, default=DEFAULT_MAX_TOOL_OUTPUT)
    args = ap.parse_args(argv)
    summary = ingest(args.transcripts_dir, args.out_dir, args.state,
                     window_days=args.window_days, settle_minutes=args.settle_minutes,
                     max_tool_output_chars=args.max_tool_output_chars)
    print(json.dumps(summary))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

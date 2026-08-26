#!/usr/bin/env python3
"""skill_usage_report.py - measure real skill usage from Claude Code transcripts.

Scans Claude Code JSONL transcripts for Skill-tool invocations and slash
command usage, and reports counts per skill/command plus session coverage.

Claude Code writes one JSONL ``assistant`` line per content block of a single
API response (see token_cost_report.py's docstring), which raised the
question of whether a single Skill tool_use block -- or a slash-command text
block -- could appear on more than one sibling line and get double-counted.
Checked against the full corpus: 0 duplicate Skill tool_use ids and 0
duplicate command-name text blocks across sibling lines of the same
requestId (348 Skill blocks == 348 distinct tool_use ids). Each content
block is written exactly once, so no dedup is needed here -- unlike
token_cost_report.py, where the repeated `usage` object on every sibling
line does need deduping.

Usage:
  skill_usage_report.py [--root DIR] [--since ISO8601] [--until ISO8601] [--json PATH]

Options:
  --root DIR   directory to scan (default: ~/.claude/projects)
  --since TS   ignore records with a top-level timestamp before TS
  --until TS   ignore records with a top-level timestamp after TS
  --json PATH  also write the machine-readable report to PATH
Exit codes: 0 ok, 2 usage / unusable input (bad --since/--until value,
unreadable transcript root, no transcripts found, unwritable --json path).
"""

from __future__ import annotations

import argparse
import collections
import json
import os
import re
import sys
from datetime import UTC, datetime
from pathlib import Path

PROG = "skill_usage_report.py"
DEFAULT_ROOT = "~/.claude/projects"
CMD_RE = re.compile(r"<command-name>/?([A-Za-z0-9:_-]+)</command-name>")


def err(msg: str) -> None:
    print(f"{PROG}: {msg}", file=sys.stderr)


def _parse_ts(raw: str | None) -> datetime | None:
    """Parse a top-level transcript ``timestamp`` (or a --since/--until bound).

    Returns None on missing/unparseable input so callers can treat that as
    "unknown" rather than silently including or excluding the record.
    """
    if not raw:
        return None
    try:
        dt = datetime.fromisoformat(raw.strip())
    except ValueError:
        return None
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=UTC)


def scan(root: Path, since: datetime | None, until: datetime | None) -> dict:
    """Walk ``root`` for ``*.jsonl`` transcripts and tally skill/command usage."""
    boundary_active = since is not None or until is not None
    counts: collections.Counter = collections.Counter()

    skill_tool = collections.Counter()  # model-invoked via Skill tool
    slash_cmd = collections.Counter()  # user-typed slash commands
    first_seen: dict[str, str] = {}
    last_seen: dict[str, str] = {}
    per_project = collections.defaultdict(collections.Counter)
    sessions_with_skill = collections.defaultdict(set)
    total_sessions: set[str] = set()

    files = 0
    for dirpath, _, names in os.walk(root):
        proj = os.path.basename(dirpath)
        for n in names:
            if not n.endswith(".jsonl"):
                continue
            files += 1
            path = os.path.join(dirpath, n)
            sid = f"{proj}/{n}"
            total_sessions.add(sid)
            try:
                with open(path, errors="replace") as fh:
                    for line in fh:
                        if "Skill" not in line and "command-name" not in line:
                            continue
                        if not line or (line[0] != "{" and line.lstrip()[:1] != "{"):
                            continue
                        try:
                            d = json.loads(line)
                        except json.JSONDecodeError:
                            continue

                        # NOTE: every count from here down is gated by the
                        # since/until filter (when active) so that a fixed
                        # --until yields byte-identical totals on a live,
                        # append-only corpus -- do not count anything above
                        # this filter into a reported/self-check figure, or
                        # new session data written between runs will make
                        # "deterministic" output drift.
                        ts = d.get("timestamp", "")
                        if boundary_active:
                            ts_dt = _parse_ts(ts)
                            if ts_dt is None:
                                counts["skipped_no_timestamp"] += 1
                                continue
                            if since is not None and ts_dt < since:
                                continue
                            if until is not None and ts_dt > until:
                                continue
                        counts["records_in_range"] += 1
                        counts["records_seen"] += 1

                        m = d.get("message") or {}
                        c = m.get("content")
                        blocks = (
                            c
                            if isinstance(c, list)
                            else (
                                [{"type": "text", "text": c}]
                                if isinstance(c, str)
                                else []
                            )
                        )
                        for b in blocks:
                            if not isinstance(b, dict):
                                continue
                            if b.get("type") == "tool_use" and b.get("name") == "Skill":
                                s = (b.get("input") or {}).get("skill")
                                if s:
                                    skill_tool[s] += 1
                                    per_project[proj][s] += 1
                                    sessions_with_skill[s].add(sid)
                                    if ts:
                                        first_seen[s] = min(first_seen.get(s, ts), ts)
                                        last_seen[s] = max(last_seen.get(s, ts), ts)
                            txt = b.get("text") if b.get("type") == "text" else None
                            if txt:
                                for cmd in CMD_RE.findall(txt):
                                    slash_cmd[cmd] += 1
                                    sessions_with_skill[cmd].add(sid)
                                    if ts:
                                        first_seen[cmd] = min(
                                            first_seen.get(cmd, ts), ts
                                        )
                                        last_seen[cmd] = max(last_seen.get(cmd, ts), ts)
            except OSError:
                continue

    return {
        "files": files,
        "sessions": len(total_sessions),
        "skill_tool": skill_tool.most_common(),
        "slash_cmd": slash_cmd.most_common(),
        "first_seen": first_seen,
        "last_seen": last_seen,
        "sessions_per_skill": {k: len(v) for k, v in sessions_with_skill.items()},
        "records_seen": counts["records_seen"],
        "records_in_range": counts["records_in_range"],
        "skipped_no_timestamp": counts["skipped_no_timestamp"],
    }


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog=PROG,
        description=(
            "Measure Skill-tool and slash-command usage from Claude Code "
            "JSONL transcripts."
        ),
    )
    p.add_argument(
        "--root",
        default=DEFAULT_ROOT,
        help="directory to scan (default: %(default)s)",
    )
    p.add_argument(
        "--since",
        metavar="ISO8601",
        default=None,
        help="ignore records with a timestamp before this value",
    )
    p.add_argument(
        "--until",
        metavar="ISO8601",
        default=None,
        help="ignore records with a timestamp after this value",
    )
    p.add_argument(
        "--json",
        metavar="PATH",
        default=None,
        help="also write the machine-readable report to PATH",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    # --help must succeed before any filesystem access (repo convention:
    # cli-audit-help). argparse handles -h/--help here, before scan() ever
    # touches --root, and the default is expanded at runtime, not import time.
    args = _build_parser().parse_args(argv)
    root = Path(args.root).expanduser()

    since_dt = _parse_ts(args.since) if args.since is not None else None
    if args.since is not None and since_dt is None:
        err(f"invalid --since timestamp: {args.since!r}")
        return 2
    until_dt = _parse_ts(args.until) if args.until is not None else None
    if args.until is not None and until_dt is None:
        err(f"invalid --until timestamp: {args.until!r}")
        return 2

    if args.since is not None and args.until is not None and since_dt > until_dt:
        err(f"--since {args.since!r} is after --until {args.until!r}")
        return 2

    # A mistyped --root must not read as "this corpus has no skill usage".
    if not root.is_dir():
        err(f"transcript root not found: {root}")
        return 2

    out = scan(root, since_dt, until_dt)
    # The raw files/sessions walk counts grow with the corpus regardless of
    # --until, so they are reported on stdout but kept OUT of the snapshot —
    # otherwise a committed baseline shows a spurious diff on every rerun.
    files_walked = out.pop("files")
    sessions_walked = out.pop("sessions")
    out["scan"] = {
        "root": str(root),
        "since": args.since,
        "until": args.until,
        "records_seen": out.pop("records_seen"),
        "records_in_range": out.pop("records_in_range"),
        "skipped_no_timestamp": out.pop("skipped_no_timestamp"),
    }

    # No transcripts at all is operator error (wrong root). Zero *matches* in a
    # walked corpus is a legitimate result, so only the former is fatal.
    if not files_walked:
        err(f"no .jsonl transcripts found under {root}")
        return 2

    if args.json:
        try:
            # Trailing newline keeps the committed snapshot stable under
            # pre-commit's end-of-file-fixer across regenerations.
            Path(args.json).write_text(json.dumps(out, indent=1) + "\n")
        except OSError as exc:
            err(f"cannot write {args.json}: {exc}")
            return 2
    print(f"scanned {files_walked} files / {sessions_walked} sessions")
    print(
        f"distinct Skill-tool skills: {len(out['skill_tool'])}  "
        f"total calls: {sum(c for _, c in out['skill_tool'])}"
    )
    print(
        f"distinct slash commands:    {len(out['slash_cmd'])}  "
        f"total: {sum(c for _, c in out['slash_cmd'])}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())

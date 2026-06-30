#!/usr/bin/env python3
"""Redact secrets from captured SkillClaw session files before evolution.

Defense-in-depth for the capture honeypot (spec §6): even with chmod 700, we
strip API keys and auth headers from session payloads at rest. Run as a sweep
before evolve/promote. Idempotent.

Usage:
    skillclaw_scrub.py <sessions_dir>     # scrub all *.json/*.jsonl in place
    skillclaw_scrub.py --check <dir>      # exit 1 if any secret remains
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

REDACTED = "[REDACTED]"

# Ordered, conservative patterns. Each captures the *secret span* only.
_PATTERNS = [
    re.compile(r"sk-ant-[A-Za-z0-9_-]{8,}"),
    re.compile(r"sk-proj-[A-Za-z0-9_-]{8,}"),
    re.compile(r"sk-[A-Za-z0-9_-]{16,}"),
    re.compile(r"(?i)(authorization:\s*bearer\s+)([A-Za-z0-9._-]+)"),
    re.compile(r"(?i)(x-api-key:\s*)([A-Za-z0-9._-]+)"),
    re.compile(r"(?i)(anthropic-api-key:\s*)([A-Za-z0-9._-]+)"),
]


def redact_text(text: str) -> str:
    """Return text with all known secret patterns replaced by REDACTED."""
    out = text
    for pat in _PATTERNS:
        if pat.groups == 2:
            out = pat.sub(lambda m: m.group(1) + REDACTED, out)
        else:
            out = pat.sub(REDACTED, out)
    return out


def scrub_file(path: Path) -> bool:
    """Rewrite path in place if it contains secrets. Return True if changed."""
    original = path.read_text(encoding="utf-8", errors="replace")
    cleaned = redact_text(original)
    if cleaned != original:
        path.write_text(cleaned, encoding="utf-8")
        return True
    return False


def _iter_session_files(root: Path):
    for ext in ("*.json", "*.jsonl", "*.txt"):
        yield from root.rglob(ext)


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("directory")
    ap.add_argument("--check", action="store_true", help="exit 1 if secrets remain")
    args = ap.parse_args(argv)

    root = Path(args.directory).expanduser()
    if not root.is_dir():
        print(f"skillclaw_scrub: not a directory: {root}", file=sys.stderr)
        return 2

    leaked = False
    changed = 0
    for f in _iter_session_files(root):
        if args.check:
            if redact_text(
                f.read_text(encoding="utf-8", errors="replace")
            ) != f.read_text(encoding="utf-8", errors="replace"):
                print(f"secret found in {f}", file=sys.stderr)
                leaked = True
        else:
            if scrub_file(f):
                changed += 1
    if args.check:
        return 1 if leaked else 0
    print(f"scrubbed {changed} file(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

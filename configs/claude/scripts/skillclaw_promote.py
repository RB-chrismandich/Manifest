#!/usr/bin/env python3
"""Classify evolved SkillClaw skills vs the committed library and validate them.

Pure logic for the promote bridge. Emits JSON the shell orchestrator consumes:
which skills to promote (NEW or CHANGED) and which were dropped (failed
validation), with reasons. No git side effects here.

Usage:
    skillclaw_promote.py <evolved_dir> <committed_dir> [--skill NAME]
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

FRONTMATTER_KEYS = ("name", "description")


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def parse_frontmatter(text: str) -> dict | None:
    """Return YAML-ish frontmatter as a dict, or None if absent/malformed."""
    if not text.startswith("---"):
        return None
    end = text.find("\n---", 3)
    if end == -1:
        return None
    block = text[3:end].strip().splitlines()
    fm: dict[str, str] = {}
    for line in block:
        if ":" in line:
            k, _, v = line.partition(":")
            fm[k.strip()] = v.strip()
    return fm


def validate_skill(skill_md: Path) -> tuple[bool, str]:
    """Validate a SKILL.md has name+description frontmatter. (bool, reason)."""
    text = _read(skill_md)
    fm = parse_frontmatter(text)
    if fm is None:
        return False, "missing or malformed frontmatter"
    for key in FRONTMATTER_KEYS:
        if not fm.get(key):
            return False, f"frontmatter missing required key: {key}"
    return True, ""


def classify(evolved_dir: Path, committed_dir: Path) -> list[dict]:
    """Classify each evolved skill as NEW/CHANGED/UNCHANGED vs committed."""
    out: list[dict] = []
    for skill_md in sorted(evolved_dir.glob("*/SKILL.md")):
        name = skill_md.parent.name
        committed = committed_dir / name / "SKILL.md"
        if not committed.exists():
            status = "NEW"
        elif _read(committed) == _read(skill_md):
            status = "UNCHANGED"
        else:
            status = "CHANGED"
        out.append({"name": name, "status": status, "path": str(skill_md)})
    return out


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("evolved_dir")
    ap.add_argument("committed_dir")
    ap.add_argument("--skill", help="restrict to a single skill name")
    ap.add_argument("--rejected-dir", help="copy invalid candidates here for inspection")
    args = ap.parse_args(argv)

    evolved = Path(args.evolved_dir).expanduser()
    committed = Path(args.committed_dir).expanduser()
    if not evolved.is_dir():
        print(f"skillclaw_promote: evolved dir not found: {evolved}", file=sys.stderr)
        return 2

    candidates = classify(evolved, committed)
    promote, dropped = [], []
    for c in candidates:
        if args.skill and c["name"] != args.skill:
            continue
        if c["status"] == "UNCHANGED":
            continue
        ok, reason = validate_skill(Path(c["path"]))
        if ok:
            promote.append(c)
        else:
            dropped.append({**c, "reason": reason})

    if args.rejected_dir:
        rej = Path(args.rejected_dir).expanduser()
        for d in dropped:
            dest = rej / d["name"]
            dest.mkdir(parents=True, exist_ok=True)
            shutil.copy(d["path"], dest / "SKILL.md")

    json.dump({"promote": promote, "dropped": dropped}, sys.stdout, indent=2)
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

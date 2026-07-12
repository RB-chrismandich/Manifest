#!/usr/bin/env python3
"""Generate configs/cursor/agents/*.md from configs/claude/agents/*.md.

configs/claude/agents/*.md are the six pilotfish role-agents (spec
481-pilotfish-orchestration), authored with Claude Code's agent frontmatter
(name, description, model: haiku|sonnet|opus, effort: low|medium|high). Cursor
2.x reads its own `~/.cursor/agents/*.md` with a DIFFERENT frontmatter schema
(name, description, model: "inherit" or a Cursor model ID, readonly,
is_background) and has no `effort` field at all — a raw `effort:` line or a
bare `opus`/`sonnet`/`haiku` `model:` value is invalid Cursor frontmatter.

This generator ports the six role-agents into that schema (spec 2026-07-11
cursor-feature-parity, WS-5):

  - model: always "inherit" — Cursor manages its own model economy, and a
    Cursor model ID (e.g. "claude-opus-4-8[effort=high]") would re-drift on
    every Cursor model catalog change; "inherit" is Cursor-version-agnostic.
  - effort: dropped entirely (not a valid Cursor field).
  - readonly: true for the three read-only/verification roles (scout,
    Explore, verifier); false for the three roles that edit files
    (mech-executor, executor, security-executor).
  - is_background: true for roles suited to unattended background execution
    (scout, Explore, mech-executor, verifier — read-only or fully-specified/
    mechanical); omitted (Cursor default) for executor and security-executor,
    whose judgment/security-sensitive work should stay foreground/supervised.
  - body: copied verbatim from the source — only the frontmatter differs.

Invoked from generate_cursor_rules.sh (guarded on python3+pyyaml, mirroring
the mcp.json/commands-index.mdc generators) so a single command keeps rules +
mcp.json + agents in sync; CI/pre-commit fail on
`git status --porcelain configs/cursor/agents/`.

CLI:
    generate_cursor_agents.py            regenerate configs/cursor/agents/*.md
    generate_cursor_agents.py --dry-run  report would-create/would-update/would-remove; write nothing
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml

PROG = "generate_cursor_agents.py"

_REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_SRC = _REPO_ROOT / "configs" / "claude" / "agents"
DEFAULT_OUTPUT = _REPO_ROOT / "configs" / "cursor" / "agents"

# Cursor-side role classification not derivable from Claude frontmatter (Claude
# agents carry no readonly/is_background fields). Keep in sync with
# PILOTFISH_AGENT_FILES (bootstrap/lib/common.sh) if roles are added/renamed.
READONLY_ROLES = {"scout", "Explore", "verifier"}
BACKGROUND_ROLES = {"scout", "Explore", "mech-executor", "verifier"}

FRONTMATTER_DELIM = "---\n"


def err(msg: str) -> None:
    print(f"{PROG}: {msg}", file=sys.stderr)


def parse_agent(path: Path) -> tuple[dict, str]:
    """Split a Claude agent .md into (frontmatter dict, raw body).

    The body retains its original leading blank line and trailing content
    byte-for-byte — only the frontmatter block is regenerated.
    """
    text = path.read_text(encoding="utf-8")
    if not text.startswith(FRONTMATTER_DELIM):
        raise ValueError(f"{path}: does not start with a YAML frontmatter block")
    rest = text[len(FRONTMATTER_DELIM) :]
    end = rest.find("\n---\n")
    if end == -1:
        raise ValueError(f"{path}: unterminated frontmatter block")
    fm = yaml.safe_load(rest[:end]) or {}
    if not isinstance(fm, dict):
        raise ValueError(f"{path}: frontmatter is not a mapping")
    for required in ("name", "description"):
        if required not in fm:
            raise ValueError(f"{path}: frontmatter missing required key '{required}'")
    body = rest[end + len("\n---\n") :]
    return fm, body


def build_cursor_frontmatter(fm: dict) -> dict:
    """Claude frontmatter -> Cursor-native frontmatter (name/description kept,
    effort dropped, model forced to inherit, readonly/is_background added)."""
    name = fm["name"]
    out = {
        "name": name,
        "description": fm["description"],
        "model": "inherit",
        "readonly": name in READONLY_ROLES,
    }
    if name in BACKGROUND_ROLES:
        out["is_background"] = True
    return out


def render(fm: dict, body: str) -> str:
    front = yaml.safe_dump(
        fm,
        sort_keys=False,
        default_flow_style=False,
        allow_unicode=True,
        width=100000,
    ).rstrip("\n")
    return f"---\n{front}\n---\n{body}"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog=PROG,
        description="Generate configs/cursor/agents/*.md from configs/claude/agents/*.md.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="report would-create/would-update/would-remove without writing",
    )
    parser.add_argument(
        "--src",
        default=str(DEFAULT_SRC),
        help="source Claude agents dir (default: configs/claude/agents)",
    )
    parser.add_argument(
        "--output",
        default=str(DEFAULT_OUTPUT),
        help="destination Cursor agents dir (default: configs/cursor/agents)",
    )
    args = parser.parse_args(argv)

    src_dir = Path(args.src)
    out_dir = Path(args.output)

    if not src_dir.is_dir():
        err(f"{src_dir}: not found")
        return 2

    source_files = sorted(p for p in src_dir.glob("*.md") if p.is_file())
    if not source_files:
        err(f"{src_dir}: no agent .md files found")
        return 2

    created = updated = unchanged = removed = 0
    valid_names = {p.name for p in source_files}

    for src_path in source_files:
        try:
            fm, body = parse_agent(src_path)
        except ValueError as exc:
            err(str(exc))
            return 2
        content = render(build_cursor_frontmatter(fm), body)
        out_path = out_dir / src_path.name
        existing = out_path.read_text(encoding="utf-8") if out_path.exists() else None
        if existing == content:
            unchanged += 1
            continue
        verb = "update" if existing is not None else "create"
        if args.dry_run:
            print(f"[DRY-RUN] Would {verb}: {out_path}")
        else:
            out_dir.mkdir(parents=True, exist_ok=True)
            out_path.write_text(content, encoding="utf-8")
        if verb == "update":
            updated += 1
        else:
            created += 1

    # Prune orphan generated agents so a renamed/removed source role never
    # leaves a stale Cursor-side file (mirrors generate_cursor_rules.sh's
    # rule pruning, WS-3 / #505).
    if out_dir.is_dir():
        for existing_path in sorted(out_dir.glob("*.md")):
            if existing_path.name in valid_names:
                continue
            if args.dry_run:
                print(f"[DRY-RUN] would remove: {existing_path}")
            else:
                existing_path.unlink()
            removed += 1

    print(
        f"Cursor agents: {created} created, {updated} updated, "
        f"{unchanged} unchanged, {removed} removed"
        + (
            " (--dry-run, not written)"
            if args.dry_run and (created or updated or removed)
            else ""
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Generate configs/cursor/agents/*.md from Claude agent-frontmatter sources.

Two independent Manifest role-agent sets share this one Cursor-side output dir
(disjoint filenames, each gated by its own bootstrap toggle):

  - configs/claude/agents/*.md — the six pilotfish cost-tiered roles (spec
    481-pilotfish-orchestration).
  - configs/claude/agents-devpanel/*.md — the five devpanel critic-gated
    roles (developer/debugger/tester + spec-guard/chaos-engineer).

Both are authored with Claude Code's agent frontmatter (name, description,
model: haiku|sonnet|opus, effort: low|medium|high). Cursor 2.x reads its own
`~/.cursor/agents/*.md` with a DIFFERENT frontmatter schema (name,
description, model: "inherit" or a Cursor model ID, readonly, is_background)
and has no `effort` field at all — a raw `effort:` line or a bare
`opus`/`sonnet`/`haiku` `model:` value is invalid Cursor frontmatter.

This generator ports every role-agent found across the source dir(s) into that
schema (spec 2026-07-11 cursor-feature-parity, WS-5; extended for devpanel):

  - model: always "inherit" — Cursor manages its own model economy, and a
    Cursor model ID (e.g. "claude-opus-4-8[effort=high]") would re-drift on
    every Cursor model catalog change; "inherit" is Cursor-version-agnostic.
  - effort: dropped entirely (not a valid Cursor field).
  - readonly: true for read-only/verification roles (scout, Explore,
    verifier, spec-guard, chaos-engineer); false for roles that edit files
    (mech-executor, executor, security-executor, developer, debugger, tester).
  - is_background: true for roles suited to unattended background execution
    (scout, Explore, mech-executor, verifier, spec-guard, chaos-engineer —
    read-only, fully-specified/mechanical, or a bounded independent check);
    omitted (Cursor default) for executor, security-executor, developer,
    debugger, tester, whose judgment-heavy work should stay
    foreground/supervised.
  - body: copied verbatim from the source — only the frontmatter differs.

Invoked from generate_cursor_rules.sh (guarded on python3+pyyaml, mirroring
the mcp.json/commands-index.mdc generators) so a single command keeps rules +
mcp.json + agents in sync; CI/pre-commit fail on
`git status --porcelain configs/cursor/agents/`.

CLI:
    generate_cursor_agents.py            regenerate configs/cursor/agents/*.md from all default sources
    generate_cursor_agents.py --dry-run  report would-create/would-update/would-remove; write nothing
    generate_cursor_agents.py --src DIR  process only DIR (repeatable; overrides the defaults)
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import yaml

PROG = "generate_cursor_agents.py"

_REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_SRCS = [
    _REPO_ROOT / "configs" / "claude" / "agents",
    _REPO_ROOT / "configs" / "claude" / "agents-devpanel",
]
DEFAULT_OUTPUT = _REPO_ROOT / "configs" / "cursor" / "agents"

# Cursor-side role classification not derivable from Claude frontmatter (Claude
# agents carry no readonly/is_background fields). Keep in sync with
# PILOTFISH_AGENT_FILES / DEVPANEL_AGENT_FILES (bootstrap/lib/common.sh) if
# roles are added/renamed.
READONLY_ROLES = {"scout", "Explore", "verifier", "spec-guard", "chaos-engineer"}
BACKGROUND_ROLES = {
    "scout",
    "Explore",
    "mech-executor",
    "verifier",
    "spec-guard",
    "chaos-engineer",
}

FRONTMATTER_DELIM = "---\n"

# Provenance manifest: maps each generated filename -> the basename of the
# source dir it came from. Written into out_dir itself (not the *.md glob, so
# it never confuses the role-file counts/tests). Required because out_dir is
# SHARED across independently-toggleable role sets (pilotfish, devpanel, …):
# without recorded provenance, an invocation scoped to only one source dir
# (explicit --src, or a future partial default) cannot tell "this existing
# file is a true orphan (its own source dir lost it)" from "this existing
# file simply belongs to a role set I'm not processing right now" — and would
# silently delete the latter. See the orphan-pruning guard in main() below.
MANIFEST_NAME = ".sources.json"


def err(msg: str) -> None:
    print(f"{PROG}: {msg}", file=sys.stderr)


def load_manifest(out_dir: Path) -> dict[str, str]:
    path = out_dir / MANIFEST_NAME
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    return data if isinstance(data, dict) else {}


def save_manifest(out_dir: Path, manifest: dict[str, str]) -> None:
    path = out_dir / MANIFEST_NAME
    path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


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
        description="Generate configs/cursor/agents/*.md from Claude agent-frontmatter sources.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="report would-create/would-update/would-remove without writing",
    )
    parser.add_argument(
        "--src",
        action="append",
        default=None,
        help="source Claude agents dir; repeatable "
        "(default: configs/claude/agents + configs/claude/agents-devpanel)",
    )
    parser.add_argument(
        "--output",
        default=str(DEFAULT_OUTPUT),
        help="destination Cursor agents dir (default: configs/cursor/agents)",
    )
    args = parser.parse_args(argv)

    # Explicit --src dirs must each exist (existing hermetic-test contract: a
    # missing explicit source is a hard error). Default dirs are best-effort —
    # a repo/sandbox that only has one of the two role sets (e.g. devpanel not
    # yet added, or a partial fixture) silently skips the other rather than
    # failing; only zero total source files across all defaults is an error.
    explicit = bool(args.src)
    src_dirs = [Path(s) for s in args.src] if explicit else list(DEFAULT_SRCS)
    out_dir = Path(args.output)

    source_files: list[Path] = []
    seen_names: dict[str, Path] = {}
    for src_dir in src_dirs:
        if not src_dir.is_dir():
            if explicit:
                err(f"{src_dir}: not found")
                return 2
            continue
        dir_files = sorted(p for p in src_dir.glob("*.md") if p.is_file())
        for p in dir_files:
            if p.name in seen_names:
                err(
                    f"{p.name}: defined in both {seen_names[p.name]} and {p} — filenames must be unique across source dirs"
                )
                return 2
            seen_names[p.name] = p
        source_files.extend(dir_files)

    if not source_files:
        err(f"{', '.join(str(d) for d in src_dirs)}: no agent .md files found")
        return 2

    created = updated = unchanged = removed = 0
    valid_names = {p.name for p in source_files}
    processed_dir_names = {d.name for d in src_dirs}
    manifest = load_manifest(out_dir) if out_dir.is_dir() else {}

    for src_path in source_files:
        manifest[src_path.name] = src_path.parent.name
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
    # rule pruning, WS-3 / #505) — but ONLY within the scope of the source
    # dir(s) this run actually processed. out_dir is shared across
    # independently-toggleable role sets (e.g. pilotfish + devpanel); an
    # existing file whose recorded provenance points at a source dir NOT
    # processed this run is left untouched, not treated as an orphan, even
    # though it isn't in this run's valid_names. Unknown provenance (no
    # manifest entry — a hand-authored or pre-manifest file) is also left
    # alone rather than assumed-orphaned.
    if out_dir.is_dir():
        for existing_path in sorted(out_dir.glob("*.md")):
            if existing_path.name in valid_names:
                continue
            owner = manifest.get(existing_path.name)
            if owner not in processed_dir_names:
                continue
            if args.dry_run:
                print(f"[DRY-RUN] would remove: {existing_path}")
            else:
                existing_path.unlink()
            del manifest[existing_path.name]
            removed += 1

    if not args.dry_run:
        out_dir.mkdir(parents=True, exist_ok=True)
        save_manifest(out_dir, manifest)

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

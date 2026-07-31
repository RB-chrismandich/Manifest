#!/usr/bin/env python3
"""Render the Manifest command catalog into docs/COMMANDS.md (spec 362, US1).

RETAINED DELIBERATELY — feature 522 / T029. The APM migration replaces the three
per-harness generators (cursor rules, agents, mcp) with a targeted build, and it
does NOT replace this one. Two reasons, and the first is the load-bearing one:

  1. This produces REPOSITORY DOCUMENTATION, not per-harness deploy config. It
     renders docs/COMMANDS.md and injects a command index into
     configs/gemini/GEMINI.md and AGENTS.md — files that live in the repo and are
     read by humans and by agents reading the repo, not files deployed into an
     assistant home. Nothing about who deploys ~/.claude changes that.
  2. apm's own target matrix generates no catalog or documentation index. There
     is no target to migrate this to, so "replace it with the build tool" has no
     referent.

US2's "no hand-run generator remains" claim explicitly does not cover this
script. If a future change migrates it anyway, that claim needs revisiting
rather than this comment being deleted.

The command reference is GENERATED from the skill source of truth, never hand
edited — that is the only way to satisfy FR-004 / SC-002 (zero drift). The
generated table lives inside a marker-delimited block so the surrounding
hand-written guide prose is preserved; a `--check` mode (mirroring
``version_pin.sh --check``) fails when the committed block has drifted from a
fresh render, and is wired into CI.

CLI:
    generate_commands_doc.py            render → overwrite the generated block
    generate_commands_doc.py --check    diff vs committed (0 in-sync, 1 drift, 2 error)
    generate_commands_doc.py --compact  print the compact guide index to stdout

Env overrides (tests): COMMANDS_DOC_PATH plus the COMMAND_CATALOG_* family.
"""

from __future__ import annotations

import argparse
import difflib
import os
import re
import sys
from pathlib import Path

import command_catalog as cc

PROG = "generate_commands_doc.py"

_REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_DOC = _REPO_ROOT / "docs" / "COMMANDS.md"

BEGIN_MARKER = (
    "<!-- BEGIN GENERATED COMMANDS (command_catalog.py) — do not edit by hand -->"
)
END_MARKER = "<!-- END GENERATED COMMANDS -->"

# Compact, description-less index injected into always-loaded platform guides
# (FR-009 / SC-006). Volatile, so CI drift-checks it alongside docs/COMMANDS.md.
INDEX_BEGIN = "<!-- BEGIN COMMAND INDEX (generate_commands_doc.py --inject-guides) -->"
INDEX_END = "<!-- END COMMAND INDEX -->"
# Always-loaded markdown guides that receive the compact index (repo-root rel).
GUIDE_TARGETS = ("configs/gemini/GEMINI.md", "AGENTS.md")


def err(msg: str) -> None:
    print(f"{PROG}: {msg}", file=sys.stderr)


# --------------------------------------------------------------------------- #
# Rendering
# --------------------------------------------------------------------------- #
def _escape_cell(text: str) -> str:
    return " ".join(text.split()).replace("|", "\\|")


def _grouped(catalog: dict):
    """Yield (label, [commands]) in taxonomy order, uncategorized last."""
    labels = {c["key"]: c["label"] for c in catalog["categories"]}
    labels[cc.UNCATEGORIZED] = "Uncategorized"
    order = {c["key"]: c["order"] for c in catalog["categories"]}
    order[cc.UNCATEGORIZED] = max(order.values(), default=0) + 1
    keys = sorted(
        {c["category"] for c in catalog["commands"]}, key=lambda k: order.get(k, 999)
    )
    for key in keys:
        members = sorted(
            (c for c in catalog["commands"] if c["category"] == key),
            key=lambda c: c["name"],
        )
        if members:
            yield labels.get(key, key), members


def render_section(catalog: dict) -> str:
    """The marker-delimited generated block (deterministic)."""
    lines = [
        BEGIN_MARKER,
        "<!-- Regenerate: configs/claude/scripts/generate_commands_doc.py -->",
        "",
        f"_{len(catalog['commands'])} commands, generated from "
        f"`.apm/skills/*/SKILL.md`._",
        "",
    ]
    for label, members in _grouped(catalog):
        lines.append(f"### {label}")
        lines.append("")
        lines.append("| Command | Description | When to use | Status |")
        lines.append("|---------|-------------|-------------|--------|")
        for c in members:
            av = c["availability"]
            status = (
                "available"
                if av["status"] == "available"
                else f"unavailable — {av['reason']}"
            )
            lines.append(
                f"| `{command_name(c['name'], 'claude')}` | {_escape_cell(c['description'])} "
                f"| {_escape_cell(c['when_to_use'])} | {status} |"
            )
        lines.append("")
    lines.append(END_MARKER)
    return "\n".join(lines)


def render_compact_index(catalog: dict) -> str:
    """Description-less index for always-loaded guides (FR-009 / SC-006).

    Category headers + `/name` links only; full text lives in /help and
    docs/COMMANDS.md (neither always-loaded).
    """
    lines = []
    for label, members in _grouped(catalog):
        names = " · ".join(
            f"`{command_name(c['name'], 'sibling')}`"
            for c in members
            if c["availability"]["status"] == "available"
        )
        if names:
            lines.append(f"- **{label}**: {names}")
    lines.append("")
    lines.append("Run `/help <query>` for descriptions and when-to-use.")
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# Injection into a host document
# --------------------------------------------------------------------------- #
def extract_section(doc_text: str) -> str | None:
    start = doc_text.find(BEGIN_MARKER)
    end = doc_text.find(END_MARKER)
    if start == -1 or end == -1 or end < start:
        return None
    return doc_text[start : end + len(END_MARKER)]


def inject(doc_text: str, section: str) -> str:
    """Replace the marked block, or append it when no markers are present."""
    existing = extract_section(doc_text)
    if existing is not None:
        return doc_text.replace(existing, section)
    # Normalize trailing newlines so the append seam is exactly one blank line
    # (avoids an MD012 multiple-blank-lines lint error).
    base = doc_text.rstrip("\n")
    return f"{base}\n\n## Command Reference\n\n{section}\n"


def write_doc(doc_path: str, catalog: dict, base_text: str | None = None) -> None:
    p = Path(doc_path)
    if base_text is not None:
        base = base_text
    elif p.exists():
        base = p.read_text(encoding="utf-8")
    else:
        base = ""
    out = inject(base, render_section(catalog))
    if not out.endswith("\n"):
        out += "\n"
    p.write_text(out, encoding="utf-8")


def check_doc(doc_path: str, catalog: dict) -> int:
    p = Path(doc_path)
    if not p.exists():
        err(f"{doc_path}: not found (run generate_commands_doc.py to create it)")
        return 2
    try:
        current = p.read_text(encoding="utf-8")
        expected = render_section(catalog)
        actual = extract_section(current)
        if actual is None:
            err(f"{doc_path}: no generated block found — regenerate")
            return 1
        # Byte-exact comparison: a `.strip()` here would mask trailing/leading
        # whitespace drift and weaken the FR-004/SC-002 zero-drift guarantee.
        # Both `actual` (marker-anchored slice) and `expected` (render_section)
        # start at BEGIN_MARKER and end at END_MARKER, so they match exactly
        # when in sync.
        if actual == expected:
            return 0
        diff = difflib.unified_diff(
            actual.splitlines(),
            expected.splitlines(),
            fromfile="committed",
            tofile="expected",
            lineterm="",
        )
        print("\n".join(diff))
        err(f"{doc_path}: out of date — run generate_commands_doc.py")
        return 1
    except Exception as exc:
        err(f"{doc_path}: {exc}")
        return 2


# --------------------------------------------------------------------------- #
# Compact-index injection into always-loaded platform guides (T015 / FR-009)
# --------------------------------------------------------------------------- #
def _index_block(catalog: dict) -> str:
    # The index packs each category's `/name` links onto one line, which exceeds
    # the 120-col MD013 limit by design (it is a dense always-loaded index, not
    # prose). Scope a markdownlint disable to the generated block so the linted
    # always-loaded guides (AGENTS.md) stay green without relaxing the repo rule.
    return "\n".join(
        [
            INDEX_BEGIN,
            "<!-- markdownlint-disable MD013 -->",
            "",
            render_compact_index(catalog),
            "",
            "<!-- markdownlint-enable MD013 -->",
            INDEX_END,
        ]
    )


def extract_index(text: str) -> str | None:
    start = text.find(INDEX_BEGIN)
    end = text.find(INDEX_END)
    if start == -1 or end == -1 or end < start:
        return None
    return text[start : end + len(INDEX_END)]


def inject_index(text: str, block: str) -> str:
    existing = extract_index(text)
    if existing is not None:
        return text.replace(existing, block)
    base = text.rstrip("\n")  # exactly one blank line at the append seam (MD012)
    return f"{base}\n\n## Command Index\n\n{block}\n"


# --------------------------------------------------------------------------- #
# Naming era (T1.2, spec 674)
# --------------------------------------------------------------------------- #
# Post-cutover a skill is reachable only as `<bundle>:<skill>`, and the two
# audiences diverge: docs/COMMANDS.md and /help must show what a Claude Code
# user types, while the Gemini/Codex/Cursor index must keep showing BARE names,
# because those harnesses read the sibling skills tree and never learn about
# plugins. One string cannot serve both, which is why this forks.
#
# Default is bare/bare and MUST stay that way until the bundles are installed:
# emitting `/manifest-forge:git-commit` today documents a command that returns
# Unknown command. Phase 4 flips SKILL_NAME_ERA=qualified once install lands.
def _bundle_map() -> dict:
    """skill -> bundle from skill_policies.yml, or {} when unreadable."""
    registry = os.environ.get(
        "MANIFEST_SKILL_REGISTRY",
        str(_REPO_ROOT / "configs" / "claude" / "config" / "skill_policies.yml"),
    )
    try:
        text = Path(registry).read_text(encoding="utf-8")
    except OSError:
        return {}
    mapping, bundle, seen = {}, None, False
    for line in text.splitlines():
        if line.startswith("bundles:"):
            seen = True
            continue
        if not seen or not line.strip() or line.lstrip().startswith("#"):
            continue
        if re.match(r"^  [A-Za-z0-9_-]+:", line):
            bundle = line.strip().split(":", 1)[0]
        elif line.startswith("    - ") and bundle:
            mapping[line.strip()[2:].strip()] = bundle
        elif not line.startswith(" "):
            seen = False
    return mapping


def command_name(skill: str, audience: str) -> str:
    """The slash command a reader of `audience` should type for `skill`.

    audience is "claude" (COMMANDS.md, /help) or "sibling" (the injected guide
    index). Siblings always get bare names; Claude gets whatever the era says.
    """
    era = os.environ.get("SKILL_NAME_ERA", "bare")
    if audience == "sibling" or era != "qualified":
        return f"/{skill}"
    bundle = _bundle_map().get(skill)
    return f"/{bundle}:{skill}" if bundle else f"/{skill}"


def _guide_paths():
    # GUIDANCE_GUIDE_PATHS (colon-separated) overrides the always-loaded guide
    # targets — empty value skips the guide-index check entirely. Tests that
    # build a fixture catalog (overriding COMMAND_CATALOG_SKILLS_DIR) set this so
    # `--check` does not compare the REAL repo guides against a fixture catalog.
    override = os.environ.get("GUIDANCE_GUIDE_PATHS")
    if override is not None:
        return [(p, Path(p)) for p in override.split(":") if p]
    return [(rel, _REPO_ROOT / rel) for rel in GUIDE_TARGETS]


def inject_guides(catalog: dict, write: bool = True):
    """Inject (or check) the compact index in each always-loaded guide.

    Returns a list of (relpath, in_sync_bool, exists_bool).
    """
    block = _index_block(catalog)
    results = []
    for rel, path in _guide_paths():
        if not path.exists():
            results.append((rel, True, False))
            continue
        current = path.read_text(encoding="utf-8")
        updated = inject_index(current, block)
        in_sync = updated == current
        if write and not in_sync:
            path.write_text(updated, encoding="utf-8")
        results.append((rel, in_sync, True))
    return results


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def _doc_path() -> str:
    return os.environ.get("COMMANDS_DOC_PATH") or str(DEFAULT_DOC)


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog=PROG, description="Generate docs/COMMANDS.md from the skill catalog."
    )
    p.add_argument(
        "--check",
        action="store_true",
        help="diff vs committed doc + guide indexes (0 in-sync, 1 drift, 2 error)",
    )
    p.add_argument(
        "--compact", action="store_true", help="print the compact guide index to stdout"
    )
    p.add_argument(
        "--inject-guides",
        action="store_true",
        help="inject the compact index into the always-loaded platform guides",
    )
    p.add_argument(
        "--platform", default=None, help="platform for availability resolution"
    )
    return p


def main(argv=None) -> int:
    # --help precedes any catalog/config load (cli-audit-help).
    args = _build_parser().parse_args(argv)
    try:
        catalog = cc.build_catalog(platform=args.platform)
    except cc.CatalogError as exc:
        err(str(exc))
        return 2
    if args.compact:
        print(render_compact_index(catalog))
        return 0
    doc = _doc_path()
    if args.check:
        rc = check_doc(doc, catalog)
        for rel, in_sync, exists in inject_guides(catalog, write=False):
            if exists and not in_sync:
                err(
                    f"{rel}: command index out of date — run "
                    f"generate_commands_doc.py --inject-guides"
                )
                rc = rc or 1
        return rc
    if args.inject_guides:
        for rel, in_sync, exists in inject_guides(catalog, write=True):
            if not exists:
                print(f"skip {rel} (absent)")
            else:
                print(f"{'unchanged' if in_sync else 'updated'} {rel}")
        return 0
    write_doc(doc, catalog)
    print(f"Wrote generated command block to {doc}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

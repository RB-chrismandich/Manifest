#!/usr/bin/env python3
"""Reject a bare `agent:` value in SKILL.md frontmatter.

`context: fork` skills may declare `agent: <name>` to pick which subagent the
fork spawns. Claude Code's own schema for that field is an unconstrained
string -- a bare name that does not resolve to an installed agent silently
falls back to the built-in `general-purpose` agent, with **no error and no
warning** (spec:
docs/superpowers/specs/2026-08-19-marketplace-restructure-design.md, Phase 1
item 1.4). That failure mode is invisible until someone notices the wrong
agent ran.

This gate closes it structurally: every `agent:` value must be namespaced as
`plugin:agent`, the same fully-qualified form already required for skill and
command invocation everywhere else in this repository
(`docs/PLUGIN_RELEASE.md`: reachable only as `<bundle>:<name>`). A bare name
-- no colon, or a colon-free identifier -- is rejected before it can misload
silently at runtime.

As of this gate's introduction, zero SKILL.md files in this repository
declare `agent:` at all (see `--report` below), so today the gate is purely
preventative: `context: fork` + `agent:` has not seen adoption yet. It exists
so the first skill to adopt the field cannot ship a bare, silently-misloading
name.
"""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]

# `plugin:agent` -- a plugin/bundle identifier, a literal colon, then an
# agent identifier. Both segments are the kebab-case names used throughout
# this repository for bundles and agents; neither may be empty, and a
# second colon (e.g. an accidental `plugin:agent:extra`) is rejected rather
# than guessed at.
_QUALIFIED_AGENT_RE = re.compile(
    r"^[A-Za-z0-9][A-Za-z0-9_-]*:[A-Za-z0-9][A-Za-z0-9_-]*$"
)


@dataclass(frozen=True)
class Violation:
    path: Path
    value: str
    message: str

    def as_json(self, root: Path) -> dict[str, Any]:
        item = asdict(self)
        try:
            item["path"] = str(self.path.relative_to(root))
        except ValueError:
            item["path"] = str(self.path)
        return item


@dataclass(frozen=True)
class ScanReport:
    violations: tuple[Violation, ...]
    agent_field_users: tuple[Path, ...]


def _extract_frontmatter(text: str) -> str | None:
    """Return the raw YAML frontmatter block, or ``None`` if there is none."""
    if not text.startswith("---\n"):
        return None
    end = text.find("\n---", 4)
    if end == -1:
        return None
    return text[4:end]


def _skill_files(repo_root: Path) -> list[Path]:
    plugins = repo_root / "plugins"
    if not plugins.is_dir():
        return []
    files: list[Path] = []
    for bundle_dir in sorted(
        p for p in plugins.iterdir() if p.is_dir() and not p.name.startswith(".")
    ):
        skills_root = bundle_dir / "skills"
        if not skills_root.is_dir():
            continue
        for skill_dir in sorted(p for p in skills_root.iterdir() if p.is_dir()):
            candidate = skill_dir / "SKILL.md"
            if candidate.is_file():
                files.append(candidate)
    return files


def _agent_value(path: Path) -> tuple[bool, str | None]:
    """Return ``(has_agent_field, value)`` for one SKILL.md's frontmatter.

    ``value`` is ``None`` when the field is present but not a plain string
    (e.g. a list or mapping) -- still a violation, reported with the raw
    frontmatter type rather than a coerced guess.
    """
    raw = path.read_text(encoding="utf-8")
    frontmatter = _extract_frontmatter(raw)
    if frontmatter is None:
        return False, None
    try:
        document = yaml.safe_load(frontmatter)
    except yaml.YAMLError:
        return False, None
    if not isinstance(document, dict) or "agent" not in document:
        return False, None
    value = document["agent"]
    return True, value


def scan(repo_root: Path = ROOT) -> ScanReport:
    """Return every non-namespaced `agent:` value under ``repo_root``."""
    repo_root = repo_root.resolve()
    violations: list[Violation] = []
    users: list[Path] = []
    for skill_path in _skill_files(repo_root):
        has_agent, value = _agent_value(skill_path)
        if not has_agent:
            continue
        users.append(skill_path)
        if not isinstance(value, str) or not _QUALIFIED_AGENT_RE.match(value):
            violations.append(
                Violation(
                    skill_path,
                    repr(value),
                    f"agent: {value!r} is not namespaced as `plugin:agent` -- "
                    "an unqualified name silently falls back to "
                    "general-purpose with no error",
                )
            )
    return ScanReport(tuple(violations), tuple(users))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", dest="as_json")
    parser.add_argument(
        "--report",
        action="store_true",
        help="Print how many skills declare `agent:` at all, then exit 0 "
        "without failing on unqualified values.",
    )
    parser.add_argument("--repo-root", type=Path, default=ROOT)
    args = parser.parse_args(argv)
    report = scan(args.repo_root)

    if args.report:
        root = args.repo_root.resolve()
        print(f"SKILL.md files declaring agent: {len(report.agent_field_users)}")
        for path in report.agent_field_users:
            try:
                display = path.relative_to(root)
            except ValueError:
                display = path
            print(f"  {display}")
        return 0

    if args.as_json:
        print(
            json.dumps(
                {
                    "violations": [
                        item.as_json(args.repo_root.resolve())
                        for item in report.violations
                    ],
                    "agent_field_users": len(report.agent_field_users),
                },
                indent=2,
                sort_keys=True,
            )
        )
    else:
        for violation in report.violations:
            try:
                display = violation.path.relative_to(args.repo_root.resolve())
            except ValueError:
                display = violation.path
            print(f"{display}: {violation.message}")
    return 1 if report.violations else 0


if __name__ == "__main__":
    raise SystemExit(main())

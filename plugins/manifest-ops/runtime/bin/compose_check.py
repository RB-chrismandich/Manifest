#!/usr/bin/env python3
"""Audit docker-compose files against the Ten Commandments (DC-001..DC-010).

Drives the check: loads the rule registry, finds compose files, applies bypass
markers, and renders the report. The rules themselves live in compose_rules.py
and the document model in compose_model.py.

Advisory by default — exit 0 even with findings, so the save hook never blocks
an edit. ``--strict`` flips findings to exit 1 for CI use.
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from compose_model import (
    Context,
    Finding,
    MissingDependency,
    build_context,
    load_yaml_with_lines,
)
from compose_rules import run_rules

CONFIG_PATH = (
    Path(__file__).resolve().parent.parent / "config" / "compose_commandments.yml"
)
SEVERITY_ORDER = {"high": 0, "medium": 1, "low": 2}

# --strict exit contract. 0 is reserved for "every target was read and is
# compliant" — never for "nothing could be read", which is how a gate goes
# falsely green.
EXIT_VIOLATIONS = 1  # files were audited; rules were broken
EXIT_UNAUDITED = 2  # one or more targets could not be audited at all
SKIP_DIRS = {".git", "node_modules", ".venv", "venv", ".tox", "dist", "build"}


def load_config(path: Path = CONFIG_PATH) -> dict[str, Any]:
    """Load the rule registry."""
    return load_yaml_with_lines(path.read_text(encoding="utf-8"))


def is_compose_file(path: Path, cfg: dict[str, Any]) -> bool:
    """True when the filename matches a recognised compose filename pattern."""
    return any(fnmatch.fnmatch(path.name, pat) for pat in cfg.get("filenames", []))


def is_bypassed(ctx: Context, finding: Finding) -> bool:
    """True when a bypass marker covers this finding.

    A marker on the offending line always applies. The whole service block
    counts ONLY for a finding with no offending line of its own — a missing key
    anchors to the service header, and there is nothing else to annotate.
    Expanding for findings that DO point at a key would let one marker anywhere
    in a service suppress unrelated rules across the whole block, which is
    broader than the line-scoped bypass the docs promise.
    """
    marker = ctx.cfg.get("bypass_marker", "")
    if not marker:
        return False
    candidates = [finding.line]
    span = ctx.ranges.get(finding.service or "")
    if span and finding.line == span[0]:
        candidates = list(range(span[0], span[1] + 1))
    return any(
        _marker_covers(ctx, marker, number, finding.rule_id) for number in candidates
    )


def _marker_covers(ctx: Context, marker: str, number: int, rule_id: str) -> bool:
    """True when line ``number`` carries a marker applying to ``rule_id``."""
    if not 1 <= number <= len(ctx.raw_lines):
        return False
    text = ctx.raw_lines[number - 1]
    if marker not in text:
        return False
    named = re.findall(r"DC-\d{3}", text.split(marker, 1)[1])
    return not named or rule_id in named


def check_file(
    path: Path, cfg: dict[str, Any], only: list[str] | None = None
) -> list[Finding]:
    """Run every enabled rule over one compose file, minus bypassed findings."""
    text = path.read_text(encoding="utf-8")
    if cfg.get("file_bypass_marker", "\0") in text:
        return []
    ctx = build_context(path, cfg, text)
    if ctx is None:
        return []
    kept = [f for f in run_rules(ctx, only) if not is_bypassed(ctx, f)]
    kept.sort(key=lambda f: (SEVERITY_ORDER.get(f.severity, 9), f.rule_id, f.line))
    return kept


def discover(target: Path, cfg: dict[str, Any]) -> list[Path]:
    """Compose files under ``target``, or ``target`` itself when it is a file."""
    if target.is_file():
        return [target]
    return [
        candidate
        for candidate in sorted(target.rglob("*"))
        if candidate.is_file()
        and is_compose_file(candidate, cfg)
        and not SKIP_DIRS.intersection(candidate.parts)
    ]


def _display_path(path: Path) -> str:
    """Path relative to the working directory when possible, else absolute."""
    try:
        return str(path.relative_to(Path.cwd()))
    except ValueError:
        return str(path)


def render_text(
    path: Path, findings: list[Finding], cfg: dict[str, Any], limit: int = 0
) -> str:
    """Human-readable report for one file. Empty string when clean.

    Every finding keeps its own ``file:line`` so a terminal or editor can jump
    to it; the commandment and its remedy print once per rule rather than once
    per finding, which is what made the raw output unreadable.

    ``limit`` caps how many findings are printed. Findings arrive sorted by
    severity, so a cap shows the worst first. Real compose files run ~5 findings
    per service, and the save hook audits the WHOLE file on every edit — without
    a cap, touching one line of a 26-service stack emits 134 findings.
    """
    if not findings:
        return ""
    by_id = {rule["id"]: rule for rule in cfg.get("rules", [])}
    shown = _display_path(path)
    lines = [f"docker-compose commandments — {shown}"]
    visible = findings[:limit] if limit else findings
    cited: set[str] = set()
    for finding in visible:
        rule = by_id.get(finding.rule_id, {})
        scope = f"[{finding.service}] " if finding.service else ""
        lines.append(
            f"  {shown}:{finding.line}  {finding.rule_id} "
            f"{finding.severity:<6} {scope}{finding.message}"
        )
        if finding.rule_id in cited:
            continue
        cited.add(finding.rule_id)
        lines.append(
            f"      {rule.get('commandment', '')} — {rule.get('fix', '')}".rstrip()
        )
        hint = rule.get("delegate_hint")
        if hint:
            lines.append(f"      {hint}")
    hidden = len(findings) - len(visible)
    if hidden:
        # Never let a cap read as "that was all of it".
        lines.append(
            f"  … {hidden} more not shown. Full report: compose_check.py {shown}"
        )
    lines.append(
        f"  {len(findings)} finding(s). Suppress one with a trailing "
        f"`# {cfg.get('bypass_marker')} DC-NNN` comment."
    )
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="compose_check.py",
        # Explicit compact usage: the auto-generated one wraps to three lines and
        # pushes --help past the repo's 15-line ceiling.
        usage="compose_check.py [options] [target]",
        description="Audit docker-compose files against the Ten Commandments (DC-001..DC-010).",
    )
    parser.add_argument(
        "target", nargs="?", default=".", help="compose file or dir (default: .)"
    )
    parser.add_argument("--json", action="store_true", help="emit findings as JSON")
    parser.add_argument(
        "--rule", action="append", metavar="ID", help="limit to one rule (repeatable)"
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="CI gate: 1 = violations, 2 = could not audit",
    )
    parser.add_argument(
        "--limit", type=int, default=0, metavar="N", help="print at most N findings"
    )
    parser.add_argument(
        "--list-rules", action="store_true", help="print the registry and exit"
    )
    return parser


def _collect(
    target: Path, cfg: dict[str, Any], only: list[str] | None
) -> tuple[dict[str, list[Finding]], list[str]]:
    """Check every discovered file. Returns (results, unaudited).

    ``unaudited`` names every target that could NOT be checked. It is returned
    rather than only logged because a file that failed to parse produces zero
    findings, and zero findings is indistinguishable from "clean" at the exit
    code unless the caller is told the difference.
    """
    results: dict[str, list[Finding]] = {}
    unaudited: list[str] = []
    for path in discover(target, cfg):
        try:
            results[str(path)] = check_file(path, cfg, only)
        except MissingDependency:
            raise
        # constitution: exempt C-ERR — one unparseable compose file must not abort
        # the sweep over the rest; the failure is named on stderr AND recorded in
        # `unaudited`, so --strict cannot report a pass over a file it never read.
        except Exception as exc:
            print(f"compose_check.py: skipped {path}: {exc}", file=sys.stderr)
            unaudited.append(str(path))
    return results, unaudited


def _degraded(strict: bool, message: str) -> int:
    """Report an audit that could not run. Advisory: 0. Gating: EXIT_UNAUDITED.

    The whole point of --strict is that a green exit means "these files were
    read and are compliant". An unmet dependency means nothing was read, so
    under --strict that must not look like a pass.
    """
    print(f"compose_check.py: {message}", file=sys.stderr)
    return EXIT_UNAUDITED if strict else 0


def _rules_are_known(cfg: dict[str, Any], requested: list[str] | None) -> bool:
    """False (having said why) when ``--rule`` names an id the registry lacks.

    A mistyped id matches nothing, so every rule is filtered out and the report
    comes back empty — which under ``--strict`` is exit 0. A typo must not be
    able to turn the gate into a silent no-op.
    """
    unknown = sorted(set(requested or []) - {r.get("id") for r in cfg.get("rules", [])})
    if unknown:
        print(
            f"compose_check.py: unknown rule id(s): {', '.join(unknown)}. "
            "See --list-rules.",
            file=sys.stderr,
        )
    return not unknown


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        cfg = load_config()
    except MissingDependency as exc:
        return _degraded(args.strict, str(exc))
    except OSError as exc:
        print(f"compose_check.py: cannot read rule registry: {exc}", file=sys.stderr)
        return 2

    if args.list_rules:
        for rule in cfg.get("rules", []):
            print(f"{rule['id']}  {rule['severity']:<6}  {rule['commandment']}")
        return 0

    if not _rules_are_known(cfg, args.rule):
        return 2

    target = Path(os.path.expanduser(args.target)).resolve()
    if not target.exists():
        print(f"compose_check.py: no such path: {target}", file=sys.stderr)
        return 2

    try:
        results, unaudited = _collect(target, cfg, args.rule)
    except MissingDependency as exc:
        return _degraded(args.strict, str(exc))

    total = sum(len(items) for items in results.values())
    if args.json:
        payload = {
            path: [vars(f) for f in findings] for path, findings in results.items()
        }
        print(
            json.dumps(
                {"findings": payload, "total": total, "unaudited": unaudited}, indent=2
            )
        )
    else:
        for path, findings in results.items():
            report = render_text(Path(path), findings, cfg, args.limit)
            if report:
                print(report)

    if not args.strict:
        return 0
    if unaudited:
        # Distinct from EXIT_VIOLATIONS on purpose: "I could not read these" is
        # a different fact from "I read these and they are wrong", and a CI job
        # should be able to tell them apart.
        print(
            f"compose_check.py: {len(unaudited)} file(s) could not be audited; "
            "not reporting a pass.",
            file=sys.stderr,
        )
        return EXIT_UNAUDITED
    return EXIT_VIOLATIONS if total else 0


if __name__ == "__main__":
    sys.exit(main())

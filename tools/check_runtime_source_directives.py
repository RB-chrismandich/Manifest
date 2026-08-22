#!/usr/bin/env python3
"""Fail when a vendored ``runtime/bin/**.sh`` script sources a target absent
from its own bundle.

Spec §4 Phase 1 item 1.3's own requirement
(``docs/superpowers/specs/2026-08-19-marketplace-restructure-design.md``):
"the bundle-local link checker (§4 1.4) must cover script-to-script calls,
not only SKILL.md references ... It must cover source/. directives, or the
next such dependency is missed the same way" -- named after
``pr_merge_loop.sh`` sourcing ``pr_merge_loop_gh.sh``, a dependency no
SKILL.md ever mentions.

Deliberately a SEPARATE scan from ``check_bundle_link_references.py``'s
``_skill_files()``/``_scan_file()``: those run the path-token/bare-reference
scanners meant for SKILL.md prose, scoped to ``skills/<name>/**``. Running
that same logic over a vendored script's own header comments (e.g. a
``# Contract: specs/.../x.md`` doc pointer) would misattribute ordinary
monorepo-only prose as a citation defect -- a different failure mode than an
unresolvable ``source`` target, so this module only ever looks for
``source``/``.`` directive lines under ``runtime/bin/**``, nothing else.

Only the two variable-prefixed forms actually used in this repo today
(grep-verified across every ``plugins/*/runtime/bin/**/*.sh``) are resolved:

- ``${SCRIPT_DIR}/x.sh`` / ``$SCRIPT_DIR/x.sh`` -- relative to the citing
  script's own directory (the ``SCRIPT_DIR="$(cd "$(dirname
  "${BASH_SOURCE[0]}")" && pwd)"`` convention every vendored script uses).
- ``${FORGE_RUNTIME_DIR}/bin/x.sh`` / ``$FORGE_RUNTIME_DIR/bin/x.sh`` --
  relative to the bundle's ``runtime/bin/`` directory.

A ``source``/``.`` target using any other form (a literal relative path, a
different variable) is left unresolved rather than guessed at, matching
``check_bundle_link_references.py``'s stated philosophy for every other
citation kind.
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

_SOURCE_DIRECTIVE_RE = re.compile(
    r'^[ \t]*(?:source|\.)[ \t]+"?'
    r"(\$\{SCRIPT_DIR\}|\$SCRIPT_DIR|\$\{FORGE_RUNTIME_DIR\}/bin|\$FORGE_RUNTIME_DIR/bin)"
    r'/([A-Za-z0-9_./-]+\.sh)"?[ \t]*$',
    re.MULTILINE,
)

# (path, line, kind, value, message) -- the same five-field shape
# check_bundle_link_references.py's Violation dataclass takes positionally;
# kept as plain tuples here so this module has no import dependency on that
# one (only the reverse: it imports this module).
Finding = tuple[Path, int, str, str, str]


def _line_number(text: str, start: int) -> int:
    return text.count("\n", 0, start) + 1


def _runtime_bin_files(bundle_dir: Path) -> list[Path]:
    """Every shell script under a bundle's ``runtime/bin/**``."""
    bin_root = bundle_dir / "runtime" / "bin"
    if not bin_root.is_dir():
        return []
    return sorted(p for p in bin_root.rglob("*.sh") if p.is_file())


def scan_file(path: Path, bundle_dir: Path) -> list[Finding]:
    try:
        raw = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return []
    findings: list[Finding] = []
    for match in _SOURCE_DIRECTIVE_RE.finditer(raw):
        var, rel = match.group(1), match.group(2)
        base = (
            path.parent
            if var in ("${SCRIPT_DIR}", "$SCRIPT_DIR")
            else bundle_dir / "runtime" / "bin"
        )
        target = base / rel
        if target.is_file():
            continue
        findings.append(
            (
                path,
                _line_number(raw, match.start()),
                "missing-source-target",
                match.group(0).strip(),
                f"sources {rel!r} via {var}, but {target} does not exist",
            )
        )
    return findings


def scan_bundle(bundle_dir: Path) -> list[Finding]:
    findings: list[Finding] = []
    for file_path in _runtime_bin_files(bundle_dir):
        findings.extend(scan_file(file_path, bundle_dir))
    return findings


def _bundle_dirs(repo_root: Path) -> list[Path]:
    plugins = repo_root / "plugins"
    if not plugins.is_dir():
        return []
    return sorted(
        p for p in plugins.iterdir() if p.is_dir() and not p.name.startswith(".")
    )


def scan(repo_root: Path = ROOT) -> list[Finding]:
    """Return every missing-source-target finding under ``repo_root``."""
    repo_root = repo_root.resolve()
    findings: list[Finding] = []
    for bundle_dir in _bundle_dirs(repo_root):
        findings.extend(scan_bundle(bundle_dir))
    return sorted(findings, key=lambda item: (str(item[0]), item[1], item[2], item[3]))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=ROOT)
    args = parser.parse_args(argv)
    repo_root = args.repo_root.resolve()
    findings = scan(repo_root)
    for path, line, kind, _value, message in findings:
        try:
            display = path.relative_to(repo_root)
        except ValueError:
            display = path
        print(f"{display}:{line}: {kind}: {message}")
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())

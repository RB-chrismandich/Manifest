#!/usr/bin/env python3
"""Expand cross-skill reference tokens for the era being materialised (T1.1, spec 674).

There is no string that works in both eras. A bare ``/project-verify`` resolves
today and becomes an Unknown command once skills are plugin-scoped; a qualified
``/manifest-code-quality:project-verify`` resolves then and is an Unknown command
now. Post-cutover the failure is silent: the sub-agent that hit it improvises and
reports success.

So a skill body carries ``[[skill:<name>]]`` and whatever materialises the tree
expands it. Nothing substitutes anything into a SKILL.md today -- deploy is rsync
with a cp fallback -- which is exactly why the token cannot simply be written
into bodies ahead of the expansion point existing. This module IS that expansion,
landed early so Phase 3's mirror wires it rather than designs it.

``[[...]]`` rather than ``{{...}}`` on purpose: three skill bodies already carry
GitHub Actions ``${{ }}`` expressions, and a rewriter that has to tell those from
a Manifest token is one that will eventually get it wrong.

Exit codes: 0 success, 1 an unknown skill name, 2 usage or unreadable registry.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

USAGE = """\
Usage: skill_ref.py --mode {bare|qualified|check} [--registry FILE] [--help]

Expands [[skill:<name>]] tokens read from stdin, writing the result to stdout.

  --mode bare       [[skill:x]] -> /x                  (pre-cutover)
  --mode qualified  [[skill:x]] -> /<bundle>:x         (post-cutover)
  --mode check      list referenced skills, rewrite nothing
  --registry FILE   skill_policies.yml (default: alongside this script's config)

An unknown skill name exits 1 rather than passing the token through: a token
that reaches a shipped body is the silent failure this exists to prevent.
"""

TOKEN = re.compile(r"\[\[skill:([A-Za-z0-9_-]+)\]\]")

DEFAULT_REGISTRY = Path(__file__).resolve().parents[1] / "config" / "skill_policies.yml"


def err(message: str) -> None:
    """Diagnostics go to stderr so stdout stays a clean rewritten document."""
    print(f"skill_ref.py: {message}", file=sys.stderr)


def load_bundles(path: Path) -> dict[str, str]:
    """Map skill name -> bundle, parsed from skill_policies.yml's `bundles:` block.

    Deliberately a line scan rather than a yaml import: this runs in the deploy
    path, where a missing PyYAML on a slim host must not be the reason a skill
    body ships with an unexpanded token in it.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        err(f"unreadable registry {path}: {exc}")
        raise SystemExit(2) from exc

    mapping: dict[str, str] = {}
    bundle: str | None = None
    in_bundles = False
    for line in text.splitlines():
        if line.startswith("bundles:"):
            in_bundles = True
            continue
        if not in_bundles or not line.strip() or line.lstrip().startswith("#"):
            continue
        if re.match(r"^  [A-Za-z0-9_-]+:", line):
            bundle = line.strip().split(":", 1)[0]
        elif line.startswith("    - ") and bundle:
            mapping[line.strip()[2:].strip()] = bundle
        elif not line.startswith(" "):
            in_bundles = False
    if not mapping:
        err(f"registry {path} declares no bundle assignments")
        raise SystemExit(2)
    return mapping


def expand(
    text: str, mode: str, bundles: dict[str, str]
) -> tuple[str, list[str], list[str]]:
    """Return (rewritten text, skills referenced, names not in the registry)."""
    seen: list[str] = []
    unknown: list[str] = []

    def replace(match: re.Match[str]) -> str:
        name = match.group(1)
        seen.append(name)
        if name not in bundles:
            unknown.append(name)
            return match.group(0)
        if mode == "qualified":
            return f"/{bundles[name]}:{name}"
        return f"/{name}"

    if mode == "check":
        for match in TOKEN.finditer(text):
            name = match.group(1)
            seen.append(name)
            if name not in bundles:
                unknown.append(name)
        return text, seen, unknown
    return TOKEN.sub(replace, text), seen, unknown


def main(argv: list[str]) -> int:
    """Rewrite stdin to stdout. Never emits a partially-expanded document: an
    unknown name fails the whole run so a token cannot reach a shipped body."""
    if "--help" in argv or "-h" in argv:
        print(USAGE, end="")
        return 0

    mode, registry = None, DEFAULT_REGISTRY
    index = 0
    while index < len(argv):
        token = argv[index]
        if token == "--mode" and index + 1 < len(argv):
            index += 1
            mode = argv[index]
        elif token == "--registry" and index + 1 < len(argv):
            index += 1
            registry = Path(argv[index])
        else:
            err(f"unknown or incomplete argument: {token}")
            return 2
        index += 1

    if mode not in ("bare", "qualified", "check"):
        err("--mode must be one of: bare, qualified, check")
        return 2

    bundles = load_bundles(registry)
    text = sys.stdin.read()
    rewritten, seen, unknown = expand(text, mode, bundles)

    if unknown:
        for name in sorted(set(unknown)):
            err(f"no such skill in the registry: {name}")
        return 1

    if mode == "check":
        for name in sorted(set(seen)):
            print(f"{name}\t{bundles[name]}")
        return 0

    sys.stdout.write(rewritten)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

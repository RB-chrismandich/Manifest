#!/usr/bin/env python3
"""Expand portable ``[[skill:name]]`` cross-skill reference tokens."""

from __future__ import annotations

import re
import sys
from pathlib import Path

USAGE = """\
Usage: skill_ref.py --mode {bare|qualified|check} [--registry FILE] [--help]

Expands [[skill:<name>]] tokens read from stdin, writing the result to stdout.

  --mode bare       [[skill:x]] -> /x
  --mode qualified  [[skill:x]] -> /<bundle>:x
  --mode check      list referenced skills, rewrite nothing
  --registry FILE   skill_policies.yml

An unknown skill name exits 1 rather than passing the token through.
"""

TOKEN = re.compile(r"\[\[skill:([A-Za-z0-9_-]+)\]\]")

DEFAULT_REGISTRY = (
    Path(__file__).resolve().parents[1]
    / "configs"
    / "claude"
    / "config"
    / "skill_policies.yml"
)


def err(message: str) -> None:
    """Write diagnostics to stderr so stdout stays a clean document."""
    print(f"skill_ref.py: {message}", file=sys.stderr)


def load_bundles(path: Path) -> dict[str, str]:
    """Map skill names to bundles from the registry's ``bundles`` block."""
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
    """Return rewritten text, referenced skills, and unknown skill names."""
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
    """Run the fail-closed stdin-to-stdout token rewriter."""
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

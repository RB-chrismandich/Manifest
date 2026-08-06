#!/usr/bin/env python3
"""Search the generated, bundle-adjacent Manifest command catalog."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

CATALOG = Path(__file__).resolve().parents[1] / "catalog/commands.json"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("query", nargs="?")
    parser.add_argument("--all", action="store_true", dest="show_all")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--category")
    parser.add_argument("--limit", type=int, default=30)
    return parser


def load_catalog() -> dict:
    try:
        document = json.loads(CATALOG.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(
            f"unable to load adjacent catalog {CATALOG}: {error}"
        ) from error
    if not isinstance(document, dict) or not isinstance(document.get("commands"), list):
        raise ValueError(f"{CATALOG}: expected an object with commands[]")
    return document


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        catalog = load_catalog()
    except ValueError as error:
        print(f"command_catalog.py: {error}", file=sys.stderr)
        return 2
    commands = catalog["commands"]
    if args.category:
        commands = [item for item in commands if item.get("category") == args.category]
    if args.query:
        query = args.query.casefold()
        commands = [
            item
            for item in commands
            if query
            in " ".join(
                str(item.get(field, ""))
                for field in ("name", "qualified_name", "description", "category")
            ).casefold()
        ]
    if args.json:
        print(json.dumps({**catalog, "commands": commands}, indent=2, sort_keys=True))
        return 0
    visible = commands if args.show_all else commands[: max(args.limit, 0)]
    for item in visible:
        print(f"/{item['qualified_name']} - {item['description']}")
    if not visible:
        print(f'No command matches "{args.query or args.category or ""}".')
    elif len(visible) < len(commands):
        print(f"... {len(commands) - len(visible)} more - narrow with /help <query>")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

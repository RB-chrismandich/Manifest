#!/usr/bin/env python3
"""Append and query bundle-owned learning records in XDG data storage."""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

CATEGORIES = {"pattern", "antipattern", "tool-discovery", "config-insight"}


def entries_path() -> Path:
    data_home = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local/share"))
    return data_home / "manifest/knowledge/entries.jsonl"


def load_entries(path: Path) -> list[dict]:
    if not path.exists():
        return []
    entries: list[dict] = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError as error:
            raise ValueError(f"{path}:{number}: invalid JSON: {error}") from error
        if isinstance(record, dict):
            entries.append(record)
    return entries


def append_entry(path: Path, record: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = (json.dumps(record, sort_keys=True) + "\n").encode()
    descriptor = os.open(path, os.O_APPEND | os.O_CREAT | os.O_WRONLY, 0o600)
    try:
        os.write(descriptor, payload)
    finally:
        os.close(descriptor)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    add = subparsers.add_parser("add")
    add.add_argument("--category", required=True, choices=sorted(CATEGORIES))
    add.add_argument("--language", default="general")
    add.add_argument("--text", required=True)
    add.add_argument("--source", default="session")
    query = subparsers.add_parser("query")
    query.add_argument("term")
    listing = subparsers.add_parser("list")
    listing.add_argument("category", nargs="?", choices=sorted(CATEGORIES))
    subparsers.add_parser("stats")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    path = entries_path()
    try:
        entries = load_entries(path)
    except ValueError as error:
        print(f"learning_capture.py: {error}", file=sys.stderr)
        return 2
    if args.command == "add":
        record = {
            "category": args.category,
            "created": datetime.now(UTC).isoformat(),
            "language": args.language,
            "source": args.source,
            "text": args.text,
        }
        append_entry(path, record)
        print(json.dumps(record, sort_keys=True))
        return 0
    if args.command == "query":
        term = args.term.casefold()
        entries = [
            entry
            for entry in entries
            if term in json.dumps(entry, sort_keys=True).casefold()
        ]
    elif args.command == "list" and args.category:
        entries = [entry for entry in entries if entry.get("category") == args.category]
    elif args.command == "stats":
        print(
            json.dumps(
                {
                    "categories": Counter(
                        str(entry.get("category", "unknown")) for entry in entries
                    ),
                    "languages": Counter(
                        str(entry.get("language", "general")) for entry in entries
                    ),
                    "total": len(entries),
                },
                sort_keys=True,
            )
        )
        return 0
    print(json.dumps({"entries": entries}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

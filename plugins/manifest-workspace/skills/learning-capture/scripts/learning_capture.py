#!/usr/bin/env python3
"""Capture and query bundle-owned learning records using only stdlib JSONL."""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import sys
import tempfile
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

CATEGORIES = ("antipattern", "config_insight", "pattern", "tool_discovery")
CONFIDENCE = ("high", "medium", "low")
SUPPORTED_COMMANDS = (
    "add",
    "contract",
    "increment",
    "list",
    "query",
    "stats",
    "sync-docs",
)
SUPPORTED_OPTIONS = (
    "--category",
    "--confidence",
    "--description",
    "--detection-cue",
    "--format",
    "--language",
    "--output",
    "--prevention-rule",
    "--provenance",
    "--severity",
    "--source",
    "--tag",
    "--tags",
    "--text",
    "--title",
)


def entries_path() -> Path:
    """Return the XDG-owned JSONL source of truth."""
    data_home = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local/share"))
    return data_home / "manifest/knowledge/entries.jsonl"


def load_entries(path: Path) -> list[dict[str, object]]:
    """Load validated JSON objects without hiding malformed persisted data."""
    if not path.exists():
        return []
    entries: list[dict[str, object]] = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError as error:
            raise ValueError(f"{path}:{number}: invalid JSON: {error}") from error
        if not isinstance(record, dict):
            raise ValueError(f"{path}:{number}: record must be a JSON object")
        entries.append(record)
    return entries


def append_entry(path: Path, record: dict[str, object]) -> None:
    """Append one record atomically at the operating-system write boundary."""
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = (json.dumps(record, sort_keys=True) + "\n").encode()
    descriptor = os.open(path, os.O_APPEND | os.O_CREAT | os.O_WRONLY, 0o600)
    try:
        os.write(descriptor, payload)
    finally:
        os.close(descriptor)


def replace_entries(path: Path, entries: list[dict[str, object]]) -> None:
    """Replace JSONL atomically while preserving every logical record."""
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(dir=path.parent, prefix=".entries.")
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            for entry in entries:
                handle.write(json.dumps(entry, sort_keys=True) + "\n")
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
    except (OSError, TypeError):
        with contextlib.suppress(OSError):
            os.unlink(temporary)
        raise


def normalize_category(value: str) -> str:
    """Accept legacy underscores and newer hyphenated spellings."""
    normalized = value.replace("-", "_")
    if normalized not in CATEGORIES:
        raise argparse.ArgumentTypeError(
            f"invalid category {value!r}; choose from {', '.join(CATEGORIES)}"
        )
    return normalized


def _add_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--category", required=True, type=normalize_category)
    parser.add_argument("--language", required=True)
    parser.add_argument("--text")
    parser.add_argument("--title")
    parser.add_argument("--description")
    parser.add_argument("--tags")
    parser.add_argument("--confidence", choices=CONFIDENCE, default="medium")
    parser.add_argument("--source", default="session")
    parser.add_argument("--severity")
    parser.add_argument("--detection-cue")
    parser.add_argument("--prevention-rule")
    parser.add_argument("--provenance")


def build_parser() -> argparse.ArgumentParser:
    """Define the stable compatibility surface consumed by other bundles."""
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    _add_arguments(subparsers.add_parser("add"))
    query = subparsers.add_parser("query")
    query.add_argument("term", nargs="?")
    query.add_argument("--category", type=normalize_category)
    query.add_argument("--language")
    query.add_argument("--tag")
    query.add_argument("--format", choices=("json", "llm", "text"))
    listing = subparsers.add_parser("list")
    listing.add_argument("category", nargs="?", type=normalize_category)
    subparsers.add_parser("stats")
    increment = subparsers.add_parser("increment")
    increment.add_argument("entry_id")
    sync = subparsers.add_parser("sync-docs")
    sync.add_argument("--output", type=Path, default=Path("docs/KNOWLEDGE_BASE.md"))
    subparsers.add_parser("contract")
    return parser


def _next_id(entries: list[dict[str, object]]) -> str:
    numbers = []
    for entry in entries:
        identifier = str(entry.get("id", ""))
        if identifier.startswith("KB-") and identifier[3:].isdigit():
            numbers.append(int(identifier[3:]))
    return f"KB-{max(numbers, default=0) + 1:03d}"


def _record_from_args(
    args: argparse.Namespace, entries: list[dict[str, object]]
) -> dict[str, object]:
    description = args.description or args.text
    if not description:
        raise ValueError("add requires --description or --text")
    title = args.title or str(description).splitlines()[0][:80]
    today = datetime.now(UTC).date().isoformat()
    record: dict[str, object] = {
        "category": args.category,
        "confidence": args.confidence,
        "created": today,
        "description": description,
        "id": _next_id(entries),
        "language": args.language,
        "last_seen": today,
        "occurrences": 1,
        "source": args.source,
        "text": description,
        "title": title,
    }
    optional = {
        "detection_cue": args.detection_cue,
        "prevention_rule": args.prevention_rule,
        "provenance": args.provenance,
        "severity": args.severity,
    }
    record.update({key: value for key, value in optional.items() if value})
    if args.tags:
        record["tags"] = [tag.strip() for tag in args.tags.split(",") if tag.strip()]
    return record


def _matching_entries(
    entries: list[dict[str, object]], args: argparse.Namespace
) -> list[dict[str, object]]:
    matched = []
    for entry in entries:
        if args.category and entry.get("category") != args.category:
            continue
        if args.language and entry.get("language") != args.language:
            continue
        if args.tag and args.tag not in entry.get("tags", []):
            continue
        if args.term and args.term.casefold() not in json.dumps(entry).casefold():
            continue
        matched.append(entry)
    confidence = {"high": 0, "medium": 1, "low": 2}
    return sorted(
        matched,
        key=lambda entry: (
            confidence.get(str(entry.get("confidence")), 3),
            str(entry.get("last_seen", "")),
        ),
    )


def _render_llm(entries: list[dict[str, object]], language: str | None) -> str:
    if not entries:
        return ""
    lines = [f"## Known Issues: {language or 'all languages'}", ""]
    labels = {
        "antipattern": "Antipatterns",
        "config_insight": "Config Insights",
        "pattern": "Patterns",
        "tool_discovery": "Tool Discoveries",
    }
    for category in CATEGORIES:
        category_entries = [
            entry for entry in entries[:10] if entry.get("category") == category
        ]
        if not category_entries:
            continue
        lines.extend((f"### {labels[category]}", ""))
        for entry in category_entries:
            description = " ".join(str(entry.get("description", "")).split())[:150]
            lines.append(
                f"- **{entry.get('id', '?')}** ({entry.get('confidence', '?')}): "
                f"{entry.get('title', 'Untitled')} — {description}"
            )
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _render_text(entries: list[dict[str, object]]) -> str:
    if not entries:
        return "No matching entries found.\n"
    lines = [f"Found {len(entries)} matching entries:", ""]
    for entry in entries:
        lines.append(f"[{entry.get('id', '?')}] {entry.get('title', 'Untitled')}")
        lines.append(str(entry.get("description", "")))
        lines.append("")
    return "\n".join(lines)


def _sync_docs(entries: list[dict[str, object]], output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Knowledge Base",
        "",
        "> Generated from XDG-owned `entries.jsonl` by `learning-capture sync-docs`.",
        "",
    ]
    for category in CATEGORIES:
        lines.extend((f"## {category.replace('_', ' ').title()}", ""))
        category_entries = [
            entry for entry in entries if entry.get("category") == category
        ]
        if not category_entries:
            lines.extend(("_No entries yet._", ""))
            continue
        for entry in category_entries:
            lines.extend(
                (
                    f"### {entry.get('id', '?')}: {entry.get('title', 'Untitled')}",
                    "",
                    str(entry.get("description", "")),
                    "",
                )
            )
    output.write_text("\n".join(lines), encoding="utf-8")


def _handle_add(
    args: argparse.Namespace, entries: list[dict[str, object]], path: Path
) -> None:
    if len(entries) >= 500:
        raise ValueError("knowledge base is capped at 500 entries")
    record = _record_from_args(args, entries)
    append_entry(path, record)
    print(json.dumps(record, sort_keys=True))


def _handle_increment(
    args: argparse.Namespace, entries: list[dict[str, object]], path: Path
) -> None:
    record = next((item for item in entries if item.get("id") == args.entry_id), None)
    if record is None:
        raise ValueError(f"entry {args.entry_id} not found")
    record["occurrences"] = int(record.get("occurrences", 1)) + 1
    record["last_seen"] = datetime.now(UTC).date().isoformat()
    replace_entries(path, entries)
    print(json.dumps(record, sort_keys=True))


def _handle_query(args: argparse.Namespace, entries: list[dict[str, object]]) -> None:
    matched = _matching_entries(entries, args)
    output_format = args.format or ("json" if args.term else "text")
    if output_format == "llm":
        print(_render_llm(matched, args.language), end="")
    elif output_format == "text":
        print(_render_text(matched), end="")
    else:
        print(json.dumps({"entries": matched}, indent=2, sort_keys=True))


def _render_stats(entries: list[dict[str, object]]) -> str:
    return json.dumps(
        {
            "categories": Counter(
                str(item.get("category", "unknown")) for item in entries
            ),
            "confidences": Counter(
                str(item.get("confidence", "unknown")) for item in entries
            ),
            "languages": Counter(
                str(item.get("language", "general")) for item in entries
            ),
            "total": len(entries),
        },
        sort_keys=True,
    )


def _dispatch(
    args: argparse.Namespace, entries: list[dict[str, object]], path: Path
) -> None:
    if args.command == "contract":
        print(
            json.dumps({"commands": SUPPORTED_COMMANDS, "options": SUPPORTED_OPTIONS})
        )
        return
    if args.command == "add":
        _handle_add(args, entries, path)
        return
    if args.command == "increment":
        _handle_increment(args, entries, path)
        return
    if args.command == "query":
        _handle_query(args, entries)
        return
    if args.command == "list":
        listed = (
            entries
            if not args.category
            else [entry for entry in entries if entry.get("category") == args.category]
        )
        print(json.dumps({"entries": listed}, indent=2, sort_keys=True))
        return
    if args.command == "sync-docs":
        _sync_docs(entries, args.output)
        print(json.dumps({"entries": len(entries), "output": str(args.output)}))
        return
    print(_render_stats(entries))


def main(argv: list[str] | None = None) -> int:
    """Execute one compatibility command against the XDG JSONL store."""
    args = build_parser().parse_args(argv)
    path = entries_path()
    try:
        _dispatch(args, load_entries(path), path)
    except (OSError, TypeError, ValueError) as error:
        print(f"learning_capture.py: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

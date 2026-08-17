"""Strict parsers for Devin's human-readable native plugin output."""

import re
from collections.abc import Mapping
from typing import Any

_ANSI = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")
_PLUGIN_ID_PATTERN = r"(?:[A-Za-z0-9][A-Za-z0-9._-]*/)?[A-Za-z0-9][A-Za-z0-9._-]*"
_PLUGIN_ID = re.compile(_PLUGIN_ID_PATTERN)
_PLUGIN_VERSION_PATTERN = r"(?:v?\d+(?:\.\d+)+(?:[-+][0-9A-Za-z.-]+)?|unversioned)"
_LIST_ROW = re.compile(
    rf"^(?P<name>{_PLUGIN_ID_PATTERN})\s+"
    rf"(?P<version>{_PLUGIN_VERSION_PATTERN})(?:\s+.*)?$",
    re.IGNORECASE,
)
_LIST_SEPARATOR = re.compile(r"^[+|│─━═┄┈╌╍┅┉┴┬┼= _-]+$")
_LIST_HEADINGS = frozenset(
    {"installed", "plugin", "plugins", "name", "version", "blocked", "status"}
)


def _list_plugin_ids(stdout: str) -> tuple[set[str], str | None]:
    plain = _ANSI.sub("", stdout).strip()
    if not plain:
        return set(), "devin plugins list returned an empty inventory"
    plugin_ids: set[str] = set()
    saw_empty_inventory = False
    for line_number, raw_line in enumerate(plain.splitlines(), start=1):
        line = _normalized_list_line(raw_line)
        if not line:
            continue
        if line.lower() == "no plugins installed.":
            saw_empty_inventory = True
            continue
        if _is_list_header(line) or _LIST_SEPARATOR.fullmatch(line):
            continue
        match = _LIST_ROW.fullmatch(line)
        if match is None:
            return (
                set(),
                "devin plugins list contains an unrecognized inventory row "
                f"at line {line_number}",
            )
        plugin_ids.add(match.group("name"))
    if saw_empty_inventory and plugin_ids:
        return set(), "devin plugins list returned a contradictory inventory"
    if saw_empty_inventory:
        return set(), None
    if not plugin_ids:
        return set(), "devin plugins list returned no parseable inventory rows"
    return plugin_ids, None


def _normalized_list_line(raw_line: str) -> str:
    line = raw_line.strip()
    if _LIST_SEPARATOR.fullmatch(line):
        return line
    line = line.strip("|│ ").lstrip("?*+!•├└ ").strip()
    return " ".join(line.replace("│", " ").replace("|", " ").split())


def _is_list_header(line: str) -> bool:
    lowered = line.lower().rstrip(":")
    if lowered == "installed plugins":
        return True
    words = set(lowered.split())
    return (
        bool(words)
        and words <= _LIST_HEADINGS
        and bool(words & {"name", "plugin", "plugins"})
    )


def _parse_info(stdout: str) -> tuple[Mapping[str, Any], str | None]:
    plain = _ANSI.sub("", stdout)
    row: dict[str, Any] = {"skills": set()}
    section = None
    for raw_line in plain.splitlines():
        stripped = raw_line.strip()
        if not stripped:
            continue
        lowered = stripped.lower()
        key, separator, value = stripped.partition(":")
        field = key.lower()
        if separator and field in {"plugin", "version", "source"}:
            row["name" if field == "plugin" else field] = value.strip()
            section = None
            continue
        header = lowered.rstrip(":")
        if header == "skills":
            section = "skills"
            continue
        if header in {"required plugins", "optional plugins", "forbidden plugins"}:
            section = None
            continue
        if section is None or lowered == "(none)":
            continue
        identity = stripped.lstrip("-*+ ").split(maxsplit=1)[0]
        if section == "skills" and _PLUGIN_ID.fullmatch(identity):
            row[section].add(identity)
    if any(not row.get(field) for field in ("name", "version", "source")):
        return {}, "devin plugins info omitted name, version, or source"
    return row, None

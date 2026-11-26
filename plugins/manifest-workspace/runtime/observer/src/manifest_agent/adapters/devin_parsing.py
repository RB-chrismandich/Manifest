"""Strict parsers for Devin's human-readable native plugin output."""

import re
from collections.abc import Mapping
from typing import Any

from manifest_agent.capabilities import McpDefinition

_ANSI = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")
_PLUGIN_ID_PATTERN = r"(?:[A-Za-z0-9][A-Za-z0-9._-]*/)?[A-Za-z0-9][A-Za-z0-9._-]*"
_SKILL_NAME_PATTERN = r"[A-Za-z0-9](?:[A-Za-z0-9._-]*[A-Za-z0-9])?"
_PLUGIN_VERSION_PATTERN = r"(?:v?\d+(?:\.\d+)+(?:[-+][0-9A-Za-z.-]+)?|unversioned)"
_LIST_ROW = re.compile(
    rf"^(?P<name>{_PLUGIN_ID_PATTERN})\s+"
    rf"(?P<version>{_PLUGIN_VERSION_PATTERN})(?:\s+.*)?$",
    re.IGNORECASE,
)
_LIST_SEPARATOR = re.compile(r"^[+|│─━═┄┈╌╍┅┉┴┬┼=*_~\s-]+$")
_FRAMED_HEADER = re.compile(r"^[─━═=-]{2,}\s*(?P<title>.+?)\s*[─━═=-]{2,}$")
_HEADER_COUNT = re.compile(r"\s*\(\d+\)\s*$")
_BULLET_PREFIX = re.compile(r"^[-*+•]\s+")
_DESCRIPTION_SEP = re.compile(r"^\s+[-\u2013\u2014]\s+")
_SLASH_SKILL = re.compile(
    rf"^(?:(?P<plugin>{_PLUGIN_ID_PATTERN}):)?(?P<skill>{_SKILL_NAME_PATTERN})$"
)
_QUALIFIED_SKILL = re.compile(
    rf"^(?P<plugin>{_PLUGIN_ID_PATTERN}):(?P<skill>{_SKILL_NAME_PATTERN})$"
)
_BARE_SKILL = re.compile(rf"^{_SKILL_NAME_PATTERN}$")
_HTTP_URL = re.compile(r"https?://[^\s)]+")
_DISABLED_TOKEN = re.compile(r"\bdisabled\b", re.IGNORECASE)
_LIST_HEADINGS = frozenset(
    {"installed", "plugin", "plugins", "name", "version", "blocked", "status"}
)
_METADATA_FIELDS = frozenset({"plugin", "version", "source", "description"})
_SKILL_HEADERS = frozenset({"skills", "available skills"})
_MCP_HEADERS = frozenset({"mcp", "mcp server", "mcp servers"})
_SURFACE_STEMS = frozenset(
    {
        "agent",
        "command",
        "guidance",
        "hook",
        "prompt",
        "rule",
        "runtime",
        "subagent",
        "tool",
    }
)
_DEPENDENCY_HEADERS = frozenset(
    {
        "dependencies",
        "forbidden",
        "forbidden plugins",
        "optional",
        "optional plugins",
        "required",
        "required plugins",
    }
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
    row: dict[str, Any] = {"skills": set(), "mcp_servers": {}}
    section: str | None = None
    skill_indent: int | None = None
    for raw_line in plain.splitlines():
        stripped = raw_line.strip()
        if not stripped or _LIST_SEPARATOR.fullmatch(stripped):
            continue
        if _consume_metadata_field(stripped, row):
            section = None
            skill_indent = None
            continue
        is_header, next_section = _classify_info_header(raw_line, stripped)
        if is_header:
            section = next_section
            skill_indent = None
            continue
        if section is None or stripped.lower() in {"(none)", "none"}:
            continue
        if section == "skills":
            skill, skill_indent = _extract_skill_entry(raw_line, stripped, skill_indent)
            if skill is not None:
                row["skills"].add(skill)
        elif section == "mcp_servers":
            _consume_mcp_entry(stripped, row["mcp_servers"])
    if any(not row.get(field) for field in ("name", "version", "source")):
        return {}, "devin plugins info omitted name, version, or source"
    return row, None


def _consume_metadata_field(stripped: str, row: dict[str, Any]) -> bool:
    key, separator, value = stripped.partition(":")
    field = key.strip().lower()
    if not separator or field not in _METADATA_FIELDS:
        return False
    if value and not value[0].isspace():
        return False
    if field in {"plugin", "version", "source"}:
        row["name" if field == "plugin" else field] = value.strip()
    return True


def _classify_info_header(raw_line: str, stripped: str) -> tuple[bool, str | None]:
    framed = _FRAMED_HEADER.fullmatch(stripped)
    candidate = framed.group("title").strip() if framed is not None else stripped
    if framed is None and (
        candidate.startswith("/") or _BULLET_PREFIX.match(candidate) is not None
    ):
        return False, None
    key, separator, value = candidate.partition(":")
    if separator:
        if value and not value[0].isspace():
            return False, None
        if value.strip().lower() in {"(none)", "none", "0", "[]"}:
            return True, None
        if value.strip():
            return not raw_line[0].isspace(), None
        title = _HEADER_COUNT.sub("", key).strip().lower()
        return True, _section_for_title(title)
    title = _HEADER_COUNT.sub("", candidate).strip().lower()
    section = _section_for_title(title)
    if (
        section is not None
        or title.rstrip("s") in _SURFACE_STEMS
        or title in _DEPENDENCY_HEADERS
        or framed is not None
    ):
        return True, section
    if not raw_line[0].isspace():
        return True, None
    return False, None


def _section_for_title(title: str) -> str | None:
    if title in _SKILL_HEADERS:
        return "skills"
    if title in _MCP_HEADERS:
        return "mcp_servers"
    return None


def _extract_skill_entry(
    raw_line: str, stripped: str, skill_indent: int | None
) -> tuple[str | None, int | None]:
    indent = len(raw_line) - len(raw_line.lstrip())
    bullet = _BULLET_PREFIX.match(stripped)
    body = stripped[bullet.end() :] if bullet is not None else stripped
    if not body:
        return None, skill_indent
    if body.startswith("/"):
        token = body[1:].split(maxsplit=1)[0].rstrip(":")
        match = _SLASH_SKILL.fullmatch(token)
        return (match.group("skill"), indent) if match else (None, skill_indent)
    first_token = body.split(maxsplit=1)[0].rstrip(":")
    if ":" in first_token:
        match = _QUALIFIED_SKILL.fullmatch(first_token)
        return (match.group("skill"), indent) if match else (None, skill_indent)
    if bullet is not None:
        if _BARE_SKILL.fullmatch(first_token):
            return first_token, indent
        return None, skill_indent
    if indent == 0 or (skill_indent is not None and indent > skill_indent):
        return None, skill_indent
    remainder = body[len(first_token) :]
    if remainder and _DESCRIPTION_SEP.match(remainder) is None:
        return None, skill_indent
    if _BARE_SKILL.fullmatch(first_token):
        return first_token, indent if skill_indent is None else skill_indent
    return None, skill_indent


def _consume_mcp_entry(stripped: str, servers: dict[str, McpDefinition]) -> None:
    bullet = _BULLET_PREFIX.match(stripped)
    body = stripped[bullet.end() :] if bullet is not None else stripped
    if not body or _DISABLED_TOKEN.search(body):
        return
    name = body.split(maxsplit=1)[0].rstrip(":")
    if not _BARE_SKILL.fullmatch(name):
        return
    url_match = _HTTP_URL.search(body)
    if url_match is not None:
        servers[name] = McpDefinition(
            name=name, transport="http", url=url_match.group(0)
        )
    else:
        servers[name] = McpDefinition(
            name=name, transport="native-existing", discovery_prefixes=(name,)
        )

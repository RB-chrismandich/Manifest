"""Strict JSON decoding for the Codex native plugin CLI."""

from __future__ import annotations

import json
import os
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit

_MARKETPLACE = "manifest"


def validate_marketplace_add_json(stdout: str) -> str | None:
    document, error = _json_object(stdout, "Codex marketplace add")
    if error is not None:
        return error
    if (
        document.get("marketplaceName") != _MARKETPLACE
        or not isinstance(document.get("installedRoot"), str)
        or not isinstance(document.get("alreadyAdded"), bool)
    ):
        return "Codex marketplace add JSON has an invalid success schema"
    return None


def validate_plugin_add_json(stdout: str, bundle: str, version: str) -> str | None:
    document, error = _json_object(stdout, "Codex plugin add")
    if error is not None:
        return error
    plugin_id = f"{bundle}@{_MARKETPLACE}"
    if (
        document.get("pluginId") != plugin_id
        or document.get("name") != bundle
        or document.get("marketplaceName") != _MARKETPLACE
        or document.get("version") != version
        or not isinstance(document.get("installedPath"), str)
    ):
        return f"Codex plugin add JSON did not confirm {plugin_id} {version}"
    return None


def validate_remove_json(argv: Sequence[str], stdout: str) -> str | None:
    document, error = _json_object(stdout, "Codex remove")
    if error is not None:
        return error
    if tuple(argv[1:4]) == ("plugin", "marketplace", "remove"):
        if (
            document.get("marketplaceName") != _MARKETPLACE
            or document.get("installedRoot") is not None
        ):
            return "Codex marketplace remove JSON has an invalid success schema"
        return None
    plugin_id = argv[3] if len(argv) > 3 else None
    if (
        document.get("pluginId") != plugin_id
        or document.get("marketplaceName") != _MARKETPLACE
    ):
        return "Codex plugin remove JSON has an invalid success schema"
    return None


def marketplace_row(stdout: str) -> tuple[Mapping[str, Any], str | None]:
    document, error = _json_object(stdout, "Codex marketplace list")
    if error is not None:
        return {}, error
    rows = document.get("marketplaces")
    if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
        return {}, "Codex marketplace list JSON has an invalid schema"
    matches = [row for row in rows if row.get("name") == _MARKETPLACE]
    if len(matches) != 1:
        return {}, "Codex marketplace list must contain exactly one manifest source"
    return matches[0], None


def plugin_rows(
    stdout: str, env: Mapping[str, str] | None = None
) -> tuple[list[Mapping[str, Any]], str | None]:
    try:
        document = json.loads(stdout)
    except json.JSONDecodeError:
        return [], "codex plugin list did not return valid JSON"
    if not isinstance(document, dict) or not isinstance(
        document.get("installed"), list
    ):
        return [], "codex plugin list JSON has an invalid installed-plugin schema"
    rows = document["installed"]
    if any(not isinstance(row, dict) for row in rows):
        return [], "codex plugin list JSON has an invalid installed-plugin schema"
    normalized: list[Mapping[str, Any]] = []
    for row in rows:
        item = dict(row)
        if not isinstance(item.get("installedPath"), str):
            installed, path_error = _runtime_cache_path(item, env)
            if path_error is not None:
                return [], path_error
            if installed is not None:
                item["installedPath"] = installed
        normalized.append(item)
    return normalized, None


def installed_plugin_path(row: Mapping[str, Any]) -> str | None:
    value = row.get("installedPath")
    return value if isinstance(value, str) and value else None


def _runtime_cache_path(
    row: Mapping[str, Any], env: Mapping[str, str] | None
) -> tuple[str | None, str | None]:
    plugin_id = row.get("pluginId")
    version = row.get("version")
    if not isinstance(plugin_id, str) or "@" not in plugin_id:
        return None, None
    identifier_name, identifier_marketplace = plugin_id.rsplit("@", 1)
    name = row.get("name", identifier_name)
    marketplace = row.get("marketplaceName", identifier_marketplace)
    components = (name, marketplace, version)
    if not all(isinstance(value, str) for value in components):
        return None, None
    if plugin_id != f"{name}@{marketplace}" or any(
        not _safe_cache_component(value) for value in components
    ):
        return None, "codex plugin list contains an unsafe installed-plugin identity"
    values = dict(os.environ)
    if env is not None:
        values.update(env)
    configured = values.get("CODEX_HOME")
    if configured is None:
        home = values.get("HOME")
        if not home:
            return None, "Codex home is unavailable for installed-plugin resolution"
        configured = str(Path(home) / ".codex")
    root = Path(configured)
    if not root.is_absolute():
        return None, "Codex home must be absolute for installed-plugin resolution"
    return str(root / "plugins" / "cache" / marketplace / name / version), None


def _safe_cache_component(value: str) -> bool:
    return (
        bool(value)
        and value not in {".", ".."}
        and "/" not in value
        and "\\" not in value
        and "\x00" not in value
    )


def normalized_git_source(value: str) -> str:
    parts = urlsplit(value)
    path = parts.path.rstrip("/")
    if path.endswith(".git"):
        path = path[:-4]
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), path, "", ""))


def _json_object(stdout: str, operation: str) -> tuple[Mapping[str, Any], str | None]:
    try:
        document = json.loads(stdout)
    except json.JSONDecodeError:
        return {}, f"{operation} did not return valid JSON"
    if not isinstance(document, dict):
        return {}, f"{operation} JSON must be an object"
    return document, None

"""Strict JSON decoding for the Codex native plugin CLI."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
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


def plugin_rows(stdout: str) -> tuple[list[Mapping[str, Any]], str | None]:
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
    return rows, None


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

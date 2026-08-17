"""Strict native marketplace and plugin inventory capture for Claude Code."""

import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from manifest_agent.codex_plugin_backup import (
    capture_plugin_backup,
    plugin_tree_sha256,
)
from manifest_agent.models import AdapterPluginState

_MARKETPLACE = "manifest"


def _marketplace_row(stdout: str) -> tuple[Mapping[str, Any], str | None]:
    try:
        document = json.loads(stdout)
    except json.JSONDecodeError:
        return {}, "claude marketplace list did not return valid JSON"
    if not isinstance(document, list) or any(
        not isinstance(row, dict) for row in document
    ):
        return {}, "claude marketplace list JSON has an invalid schema"
    matches = [row for row in document if row.get("name") == _MARKETPLACE]
    if len(matches) != 1:
        return {}, "claude marketplace list must contain exactly one manifest source"
    return matches[0], None


def _plugin_rows(stdout: str) -> tuple[list[Mapping[str, Any]], str | None]:
    try:
        document = json.loads(stdout)
    except json.JSONDecodeError:
        return [], "claude plugin list did not return valid JSON"
    if isinstance(document, dict):
        document = document.get("installed")
    if not isinstance(document, list) or any(
        not isinstance(row, dict) for row in document
    ):
        return [], "claude plugin list JSON has an invalid installed-plugin schema"
    return document, None


def _installed_manifest_ids(rows: Sequence[Mapping[str, Any]]) -> set[str]:
    return {
        identifier
        for row in rows
        if isinstance((identifier := row.get("id")), str)
        and identifier.endswith(f"@{_MARKETPLACE}")
    }


def _native_inventory(
    adapter,
    capture_backups: bool,
    identifiers: set[str] | None,
) -> tuple[AdapterPluginState, ...]:
    marketplace_command, marketplace_error = adapter._execute(
        (adapter.name, "plugin", "marketplace", "list", "--json")
    )
    if marketplace_error is not None or marketplace_command is None:
        raise ValueError("Claude marketplace state is unavailable")
    marketplace, parse_error = _marketplace_row(marketplace_command.stdout)
    if parse_error is not None:
        raise ValueError(parse_error)
    source = marketplace.get("path")
    if marketplace.get("source") != "directory" or not isinstance(source, str):
        raise ValueError("Claude marketplace identity is incomplete")
    command, error = adapter._execute((adapter.name, "plugin", "list", "--json"))
    if error is not None or command is None:
        raise ValueError("Claude plugin inventory is unavailable")
    rows, parse_error = _plugin_rows(command.stdout)
    if parse_error is not None:
        raise ValueError(parse_error)
    inventory = [
        _native_inventory_item(adapter, row, source, capture_backups)
        for row in rows
        if _selected_native_row(row, identifiers)
    ]
    return tuple(sorted(inventory, key=lambda item: item.identifier))


def _selected_native_row(row: Mapping[str, Any], identifiers: set[str] | None) -> bool:
    plugin_id = row.get("id")
    return bool(
        isinstance(plugin_id, str)
        and plugin_id.endswith("@manifest")
        and (identifiers is None or plugin_id in identifiers)
    )


def _native_inventory_item(
    adapter,
    row: Mapping[str, Any],
    source: str,
    capture_backups: bool,
) -> AdapterPluginState:
    plugin_id = row.get("id")
    version = row.get("version")
    enabled = row.get("enabled")
    installed = row.get("installPath")
    if (
        not isinstance(plugin_id, str)
        or not isinstance(version, str)
        or not isinstance(enabled, bool)
        or not isinstance(installed, str)
    ):
        raise ValueError("Claude plugin inventory lacks exact native metadata")
    root = Path(installed)
    backup = None
    if capture_backups:
        backup = capture_plugin_backup(
            {
                "pluginId": plugin_id,
                "version": version,
                "enabled": enabled,
                "source": {"path": installed},
            },
            adapter._env,
        ).to_dict()
    return AdapterPluginState(
        plugin_id,
        version,
        enabled,
        rollback_data=backup,
        installed_path=str(root.resolve(strict=True)),
        installed_sha256=plugin_tree_sha256(root),
        source_identity=f"directory:{Path(source).resolve(strict=False)}",
    )

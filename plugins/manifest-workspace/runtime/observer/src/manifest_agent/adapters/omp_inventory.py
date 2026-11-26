"""Strict OMP native metadata and filesystem observations (default user only)."""

from __future__ import annotations

import hashlib
import json
import os
import re
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from manifest_agent.codex_plugin_backup import (
    CodexPluginBackupError,
    plugin_tree_sha256,
)

OMP_MARKETPLACE = "manifest"
_PACKAGE_NAME = re.compile(
    r"^(?:@[A-Za-z0-9][A-Za-z0-9._~-]*/)?[A-Za-z0-9][A-Za-z0-9._~-]*$"
)


class OmpInventoryError(ValueError):
    """Native inventory is absent, malformed, unsafe, or inconsistent."""


def omp_native_root(env: Mapping[str, str] | None) -> Path:
    source = {**os.environ, **(env or {})}
    home = source.get("HOME", "")
    if not home or not Path(home).is_absolute():
        raise OmpInventoryError("OMP requires an absolute HOME")
    profile = source.get("OMP_PROFILE", source.get("PI_PROFILE", "")).strip()
    if profile not in {"", "default"}:
        raise OmpInventoryError("OMP named profiles are unsupported")
    if source.get("PI_CONFIG_DIR", ".omp") not in {"", ".omp"}:
        raise OmpInventoryError("OMP custom config roots are unsupported")
    if source.get("PI_CODING_AGENT_DIR"):
        raise OmpInventoryError("OMP custom agent roots are unsupported")
    if sys.platform in {"linux", "darwin"}:
        for variable in ("XDG_DATA_HOME", "XDG_CACHE_HOME"):
            value = source.get(variable)
            if value and (Path(value) / "omp").exists():
                raise OmpInventoryError(
                    f"OMP initialized {variable}/omp layout is unsupported"
                )
    root = Path(home) / ".omp"
    regular_chain(root)
    for env_file in (root / "agent/.env", root / ".env"):
        if env_file.exists() or env_file.is_symlink():
            raise OmpInventoryError(
                "OMP environment-file layout overrides are unsupported"
            )
    return root


def regular_chain(path: Path) -> None:
    if not path.is_absolute() or ".." in path.parts:
        raise OmpInventoryError(f"unsafe native path: {path}")
    for candidate in (*reversed(path.parents), path):
        if candidate.is_symlink():
            raise OmpInventoryError(f"native path traverses a symlink: {candidate}")
        if candidate.exists() and not candidate.is_dir():
            raise OmpInventoryError(
                f"native directory path is not a directory: {candidate}"
            )


def read_object(path: Path, label: str) -> dict[str, Any] | None:
    regular_chain(path.parent)
    if path.is_symlink() or (path.exists() and not path.is_file()):
        raise OmpInventoryError(f"OMP {label} is not a regular file")
    if not path.exists():
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise OmpInventoryError(f"OMP {label} is malformed") from error
    if not isinstance(value, dict):
        raise OmpInventoryError(f"OMP {label} must be an object")
    return value


def read_marketplaces(native_root: Path) -> dict[str, Mapping[str, Any]]:
    document = read_object(native_root / "marketplaces.json", "marketplace registry")
    if document is None:
        return {}
    rows = document.get("marketplaces")
    if document.get("version") != 1 or not isinstance(rows, list):
        raise OmpInventoryError("OMP marketplace registry has an unsupported schema")
    result = {}
    for row in rows:
        if (
            not isinstance(row, dict)
            or not isinstance(row.get("name"), str)
            or not row["name"]
        ):
            raise OmpInventoryError("OMP marketplace registry row is malformed")
        if row["name"] in result:
            raise OmpInventoryError("OMP marketplace registry has duplicate names")
        result[row["name"]] = row
    return result


def read_installed_plugins(native_root: Path) -> dict[str, list[Mapping[str, Any]]]:
    document = read_object(
        native_root / "plugins/installed_plugins.json", "install registry"
    )
    if document is None:
        return {}
    plugins = document.get("plugins")
    if document.get("version") != 2 or not isinstance(plugins, dict):
        raise OmpInventoryError(
            "OMP installed-plugin registry has an unsupported schema"
        )
    for key, rows in plugins.items():
        if not isinstance(key, str) or not isinstance(rows, list):
            raise OmpInventoryError("OMP install registry entry is malformed")
        if any(not isinstance(row, dict) for row in rows):
            raise OmpInventoryError("OMP install registry row is malformed")
    return plugins


def read_runtime_document(native_root: Path) -> dict[str, Any]:
    document = read_object(
        native_root / "plugins/omp-plugins.lock.json", "runtime lock"
    )
    if document is None:
        return {"plugins": {}, "settings": {}}
    plugins, settings = document.get("plugins"), document.get("settings", {})
    if not isinstance(plugins, dict) or not isinstance(settings, dict):
        raise OmpInventoryError("OMP runtime lock has an unsupported schema")
    if any(not isinstance(row, dict) for row in plugins.values()):
        raise OmpInventoryError("OMP runtime lock entry is malformed")
    return document


def plugin_cli_rows(stdout: str) -> tuple[list[Mapping[str, Any]], str | None]:
    try:
        document = json.loads(stdout)
    except json.JSONDecodeError:
        return [], "OMP plugin list output is not valid JSON"
    rows = document.get("marketplace") if isinstance(document, dict) else None
    if not isinstance(rows, list):
        return [], "OMP plugin list marketplace rows are malformed"
    identities = set()
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get("id"), str):
            return [], "OMP plugin list row is malformed"
        entries = row.get("entries")
        if not isinstance(entries, list) or any(
            not isinstance(entry, dict) for entry in entries
        ):
            return [], "OMP plugin list entries are malformed"
        key = (row["id"], row.get("scope", "user"))
        if key in identities:
            return [], "OMP plugin list contains duplicate identities"
        identities.add(key)
    return rows, None


def cache_directory_name(name: str, marketplace: str, version: str) -> str:
    if any(
        not part or "/" in part or "\\" in part or part in {".", ".."}
        for part in (name, marketplace, version)
    ):
        raise OmpInventoryError("OMP cache identity has unsafe segments")
    return f"{marketplace}___{name}___{version}"


def runtime_name(install_path: Path, fallback: str) -> str:
    package = read_object(install_path / "package.json", "plugin package metadata")
    name = package.get("name", fallback) if package is not None else fallback
    if (
        not isinstance(name, str)
        or len(name) > 214
        or not _PACKAGE_NAME.fullmatch(name)
    ):
        raise OmpInventoryError("OMP runtime package name is malformed")
    return name


def plugin_path(native_root: Path, plugin_id: str, row: Mapping[str, Any]) -> Path:
    name, separator, marketplace = plugin_id.partition("@")
    version, install_path = row.get("version"), row.get("installPath")
    if (
        not separator
        or not isinstance(version, str)
        or not isinstance(install_path, str)
    ):
        raise OmpInventoryError(f"{plugin_id}: native install identity is malformed")
    expected = (
        native_root
        / "plugins/cache/plugins"
        / cache_directory_name(name, marketplace, version)
    )
    if Path(install_path) != expected:
        raise OmpInventoryError(
            f"{plugin_id}: install path does not match its content-addressed "
            "cache name and native root"
        )
    regular_chain(expected)
    if not expected.is_dir():
        raise OmpInventoryError(f"{plugin_id}: native cache is missing")
    return expected


def cross_checked_plugin(
    *,
    plugin_id: str,
    marketplace: str,
    cli_entries: Sequence[Mapping[str, Any]],
    registry_rows: Sequence[Mapping[str, Any]],
    runtime_row: Mapping[str, Any] | None,
    native_root: Path,
) -> tuple[Mapping[str, Any] | None, str | None]:
    if any(not isinstance(row, Mapping) for row in (*cli_entries, *registry_rows)):
        return None, f"{plugin_id}: native rows are malformed"
    if any(row.get("scope") != "user" for row in (*cli_entries, *registry_rows)):
        return None, f"{plugin_id}: project/scope conflict is unsupported"
    if not cli_entries and not registry_rows:
        return (
            (None, f"{plugin_id}: runtime-only stale inventory")
            if runtime_row is not None
            else (None, None)
        )
    if len(cli_entries) != 1 or len(registry_rows) != 1:
        return None, f"{plugin_id}: ambiguous or missing user-scope native rows"
    cli, row = cli_entries[0], registry_rows[0]
    if cli != row:
        return None, f"{plugin_id}: native CLI and install registry disagree"
    try:
        path = plugin_path(native_root, plugin_id, row)
        package_name = runtime_name(path, plugin_id.partition("@")[0])
        link = native_root / "plugins/node_modules" / package_name
        regular_chain(link.parent)
        if not link.is_symlink() or link.resolve(strict=True) != path:
            raise OmpInventoryError(
                f"{plugin_id}: runtime link identity is missing or stale"
            )
    except (OmpInventoryError, OSError) as error:
        return None, str(error)
    if runtime_row is None:
        return None, f"{plugin_id}: no runtime lock entry"
    if runtime_row.get("version") != row["version"]:
        return None, f"{plugin_id}: runtime lock version is stale against install state"
    enabled = runtime_row.get("enabled")
    if not isinstance(enabled, bool) or row.get("enabled", True) != enabled:
        return None, f"{plugin_id}: runtime enabled state is malformed or inconsistent"
    return {
        "plugin_id": plugin_id,
        "name": plugin_id.partition("@")[0],
        "marketplace": marketplace,
        "version": row["version"],
        "scope": "user",
        "install_path": str(path),
        "enabled": enabled,
        "runtime_name": package_name,
    }, None


def skill_file_path(stdout: str) -> str | None:
    for line in stdout.splitlines():
        if line.startswith("[Skill file: ") and line.endswith("]"):
            return line[len("[Skill file: ") : -1]
    return None


def directory_sha256(path: Path) -> str:
    regular_chain(path)
    try:
        return plugin_tree_sha256(path)
    except (OSError, ValueError, CodexPluginBackupError) as error:
        raise OmpInventoryError(f"native tree is unreadable: {path}") from error


def document_sha256(value: object) -> str:
    canonical = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(canonical).hexdigest()

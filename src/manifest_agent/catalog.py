"""Strict loading of the canonical Manifest marketplace inventory."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from manifest_agent.models import CatalogPlugin


class CatalogError(ValueError):
    """The marketplace catalog is malformed or escapes its repository."""


def _decode_plugin(repo_root: Path, row: Any) -> CatalogPlugin:
    if not isinstance(row, dict):
        raise CatalogError("marketplace plugin entries must be objects")
    name = row.get("name")
    version = row.get("version")
    source = row.get("source")
    if not all(
        isinstance(value, str) and value.strip() for value in (name, version, source)
    ):
        raise CatalogError("marketplace plugin name, version, and source are required")
    source_path = Path(source)
    if source_path.is_absolute():
        raise CatalogError(f"marketplace source for {name} must be relative")
    resolved = (repo_root / source_path).resolve(strict=False)
    try:
        resolved.relative_to(repo_root.resolve())
    except ValueError as error:
        raise CatalogError(
            f"marketplace source for {name} escapes the repository"
        ) from error
    if resolved != (repo_root / "plugins" / name).resolve(strict=False):
        raise CatalogError(
            f"marketplace source for {name} must match its plugin directory"
        )
    if not resolved.is_dir():
        raise CatalogError(f"marketplace source for {name} does not exist")
    return CatalogPlugin(name=name, version=version, source=source)


def load_catalog(path: Path) -> tuple[CatalogPlugin, ...]:
    """Load and validate the complete marketplace in declared order."""
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise CatalogError(f"unable to read marketplace catalog: {error}") from error
    rows = document.get("plugins") if isinstance(document, dict) else None
    if not isinstance(rows, list) or not rows:
        raise CatalogError("marketplace plugins are required")
    repo_root = path.parent.parent
    plugins = tuple(_decode_plugin(repo_root, row) for row in rows)
    names = [plugin.name for plugin in plugins]
    if len(names) != len(set(names)):
        raise CatalogError("duplicate plugin name in marketplace")
    return plugins

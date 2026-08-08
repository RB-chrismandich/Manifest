"""Cursor MCP configuration persistence helpers."""

from __future__ import annotations

import json
import os
import tempfile
from collections.abc import Mapping
from pathlib import Path

from manifest_agent.capabilities import CapabilityConflict, load_mcp_catalog
from manifest_agent.models import HarnessReceipt

_OWNERSHIP_MARKER = "manifest"
_CURSOR_KEY_PREFIX = "manifest-"


def cursor_mcp_path(env: Mapping[str, str] | None) -> Path:
    """Resolve Cursor's MCP file against an injected or process home."""
    home = Path(env["HOME"]) if env and "HOME" in env else Path.home()
    return home / ".cursor" / "mcp.json"


def read_cursor_document(path: Path) -> dict:
    """Read and validate Cursor's top-level MCP configuration object."""
    if not path.exists():
        return {}
    document = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(document, dict):
        raise CapabilityConflict("Cursor MCP configuration must be a JSON object")
    return document


def write_json_atomic(path: Path, document: dict) -> None:
    """Persist Cursor configuration atomically with user-only permissions."""
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    descriptor, name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temporary = Path(name)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            descriptor = -1
            # Dict insertion order keeps unrelated nested values byte-equivalent.
            json.dump(document, stream, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        directory = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        temporary.unlink(missing_ok=True)


def remove_owned_cursor_mcp(receipt: HarnessReceipt, path: Path) -> tuple[str, ...]:
    """Remove unchanged Cursor MCP entries authenticated by a receipt."""
    owned = {
        entry.identifier
        for entry in receipt.owned_entries
        if entry.kind == "mcp"
        and entry.ownership_marker == _OWNERSHIP_MARKER
        and entry.target_path == str(path)
    }
    if not owned:
        return ()
    document = read_cursor_document(path)
    servers = document.get("mcpServers", {})
    if not isinstance(servers, dict):
        raise CapabilityConflict("Cursor mcpServers must be a JSON object")
    catalog = load_mcp_catalog()
    removed: list[str] = []
    for name in sorted(owned):
        key = f"{_CURSOR_KEY_PREFIX}{name}"
        expected = {"url": catalog[name].url} if name in catalog else None
        if key in servers and servers[key] != expected:
            raise CapabilityConflict(f"receipt-owned Cursor MCP entry {key} changed")
        if key in servers:
            del servers[key]
            removed.append(name)
    if removed:
        write_json_atomic(path, document)
    return tuple(removed)

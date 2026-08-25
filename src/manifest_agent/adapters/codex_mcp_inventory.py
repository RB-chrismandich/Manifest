"""Observe Codex MCP state without turning uncertainty into mutation authority."""

from __future__ import annotations

import json
from collections.abc import Collection, Mapping
from dataclasses import dataclass, field
from typing import Any

from manifest_agent.capabilities import McpDefinition
from manifest_agent.process import CommandRunner, redact_text

_LIST_COMMAND = ("codex", "mcp", "list", "--json")
_HTTP_TRANSPORT = "streamable_http"

NativeMcpInventory = Collection[str] | Mapping[str, McpDefinition]


@dataclass(frozen=True)
class McpInventoryObservation:
    """A successful inventory, per-name conflicts, or an unavailable observation."""

    inventory: NativeMcpInventory
    conflicts: Mapping[str, str] = field(default_factory=dict)
    error: str | None = None

    def failure_for(self, name: str) -> tuple[str, str] | None:
        """Return the non-mutating failure classification for one server."""
        if self.error is not None:
            return "observation-unavailable", self.error
        conflict = self.conflicts.get(name)
        if conflict is not None:
            return "conflicting", conflict
        return None


def read_codex_mcp_inventory(
    runner: CommandRunner, env: Mapping[str, str] | None
) -> McpInventoryObservation:
    """Return Codex's observed MCP definitions without hiding read failures."""
    try:
        command = runner.run(_LIST_COMMAND, env=env)
    except Exception as error:
        return _unavailable(
            f"Codex MCP inventory command failed ({type(error).__name__}): {error}"
        )
    if command.returncode != 0:
        return _unavailable(
            _command_error(command.returncode, command.stdout, command.stderr)
        )
    try:
        records = json.loads(command.stdout)
    except (json.JSONDecodeError, UnicodeError) as error:
        return _unavailable(f"Codex MCP inventory is invalid JSON: {error}")
    if not isinstance(records, list):
        return _unavailable("Codex MCP inventory must be a JSON array")
    try:
        return _observation(records)
    except ValueError as error:
        return _unavailable(str(error))


def merged_native_mcp_inventory(
    harness: str,
    runner: CommandRunner,
    env: Mapping[str, str] | None,
    inventory: NativeMcpInventory | None,
) -> McpInventoryObservation:
    """Use an explicit inventory verbatim; otherwise observe live Codex state once."""
    if harness == "codex" and inventory is None:
        return read_codex_mcp_inventory(runner, env)
    return McpInventoryObservation(inventory=() if inventory is None else inventory)


def _observation(records: list[Any]) -> McpInventoryObservation:
    inventory: dict[str, McpDefinition] = {}
    conflicts: dict[str, str] = {}
    for record in records:
        name, definition, conflict = _record(record)
        if name in inventory or name in conflicts:
            raise ValueError(f"Codex MCP inventory contains duplicate server {name!r}")
        if definition is not None:
            inventory[name] = definition
        else:
            assert conflict is not None
            conflicts[name] = conflict
    return McpInventoryObservation(inventory, conflicts)


def _record(record: Any) -> tuple[str, McpDefinition | None, str | None]:
    if not isinstance(record, Mapping):
        raise ValueError("Codex MCP inventory rows must be JSON objects")
    name = record.get("name")
    enabled = record.get("enabled")
    transport = record.get("transport")
    if not isinstance(name, str) or not name:
        raise ValueError("Codex MCP inventory row has an invalid name")
    if not isinstance(enabled, bool):
        raise ValueError(f"Codex MCP inventory row for {name!r} is malformed")
    if not enabled:
        return name, None, f"Codex MCP server {name!r} is disabled"
    if not isinstance(transport, Mapping):
        raise ValueError(f"Codex MCP inventory row for {name!r} is malformed")
    kind = transport.get("type")
    if kind != _HTTP_TRANSPORT:
        label = kind if isinstance(kind, str) and kind else "unknown"
        return name, None, f"Codex MCP server {name!r} uses {label!r} transport"
    url = transport.get("url")
    if not isinstance(url, str) or not url:
        return name, None, f"Codex MCP server {name!r} has an invalid HTTP URL"
    return name, McpDefinition(name=name, transport="http", url=url), None


def _unavailable(diagnostic: str) -> McpInventoryObservation:
    return McpInventoryObservation(
        inventory=(),
        error=redact_text(f"Codex MCP inventory observation unavailable: {diagnostic}"),
    )


def _command_error(returncode: int, stdout: str, stderr: str) -> str:
    details = [f"command exited {returncode}"]
    if stdout.strip():
        details.append(f"stdout: {stdout.strip()}")
    if stderr.strip():
        details.append(f"stderr: {stderr.strip()}")
    return "; ".join(details)

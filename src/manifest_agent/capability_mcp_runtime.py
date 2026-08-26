"""MCP-specific application policy for resolved capability plans."""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass, replace
from pathlib import Path
from typing import TYPE_CHECKING

from manifest_agent.adapters.codex_mcp_inventory import McpInventoryObservation
from manifest_agent.capability_cursor import (
    cursor_mcp_path,
    read_cursor_document,
    write_json_atomic,
)
from manifest_agent.models import (
    CapabilityTier,
    CommandResult,
    HarnessResult,
    ResultState,
)
from manifest_agent.ownership import OwnershipError, owned_capability_entry
from manifest_agent.process import CommandRunner

if TYPE_CHECKING:
    from manifest_agent.capabilities import CapabilityPlan, McpDefinition

_CURSOR_KEY_PREFIX = "manifest-"
_NATIVE_HTTP_COMMANDS = {
    "claude": lambda name, url: (
        "claude",
        "mcp",
        "add",
        "--scope",
        "user",
        "--transport",
        "http",
        name,
        url,
    ),
    "codex": lambda name, url: ("codex", "mcp", "add", name, "--url", url),
    "gemini": lambda name, url: (
        "gemini",
        "mcp",
        "add",
        "--scope",
        "user",
        "--transport",
        "http",
        name,
        url,
    ),
    "devin": lambda name, url: (
        "devin",
        "mcp",
        "add",
        "--scope",
        "user",
        "--transport",
        "http",
        name,
        url,
    ),
}


@dataclass(frozen=True)
class McpApplyContext:
    """Dependencies and one observed inventory shared by every selected MCP."""

    harness: str
    runner: CommandRunner
    env: Mapping[str, str] | None
    observation: McpInventoryObservation
    cursor_path: Path | None
    run: Callable[..., tuple[HarnessResult, CommandResult | None]]
    success: Callable[..., HarnessResult]
    failure: Callable[..., HarnessResult]


def apply_mcp(
    context: McpApplyContext, plan: CapabilityPlan, name: str
) -> HarnessResult:
    """Verify, reject, or install one selected MCP without re-observing state."""
    tier = plan.tier("mcp", name)
    identity = f"mcp:{name}"
    definition = plan.mcp_definitions[name]
    observation_failure = context.observation.failure_for(name)
    if observation_failure is not None:
        status, diagnostic = observation_failure
        return context.failure(
            context.harness, tier, diagnostic, identity, status=status
        )
    existing = _existing_mcp_result(context, definition, tier, identity)
    if existing is not None:
        return existing
    if definition.transport == "native-existing":
        return _native_existing_result(context, definition, tier, identity)
    if context.harness == "cursor":
        return _apply_cursor_mcp(context, definition, tier, identity)
    if context.harness == "antigravity":
        return context.failure(
            context.harness,
            tier,
            f"Antigravity imported plugin has no native declaration for MCP {name}",
            identity,
        )
    return _install_http_mcp(context, definition, tier, identity)


def _existing_mcp_result(
    context: McpApplyContext,
    definition: McpDefinition,
    tier: CapabilityTier,
    identity: str,
) -> HarnessResult | None:
    from manifest_agent.capabilities import CapabilityConflict, merge_mcp_definitions

    observed = _inventory_definition(context.observation.inventory, definition.name)
    if observed is None:
        return None
    if isinstance(observed, str) and definition.transport != "native-existing":
        return context.failure(
            context.harness,
            tier,
            f"native MCP inventory lacks transport identity for {definition.name}",
            identity,
            status="conflicting",
        )
    if not isinstance(observed, str):
        try:
            merge_mcp_definitions(definition, observed)
        except CapabilityConflict as error:
            return context.failure(
                context.harness, tier, str(error), identity, status="conflicting"
            )
    return context.success(context.harness, identity, "verified")


def _native_existing_result(
    context: McpApplyContext,
    definition: McpDefinition,
    tier: CapabilityTier,
    identity: str,
) -> HarnessResult:
    names = _native_inventory_names(context)
    if any(
        native_name.startswith(definition.discovery_prefixes) for native_name in names
    ):
        return context.success(context.harness, identity, "verified")
    return context.failure(
        context.harness,
        tier,
        f"native {definition.name.title()} setup is not present in {context.harness}",
        identity,
    )


def _apply_cursor_mcp(
    context: McpApplyContext,
    definition: McpDefinition,
    tier: CapabilityTier,
    identity: str,
) -> HarnessResult:
    from manifest_agent.capabilities import CapabilityConflict

    path = context.cursor_path or cursor_mcp_path(context.env)
    desired = {"url": definition.url}
    try:
        document = read_cursor_document(path)
        servers = document.setdefault("mcpServers", {})
        if not isinstance(servers, dict):
            raise CapabilityConflict("Cursor mcpServers must be a JSON object")
        key = f"{_CURSOR_KEY_PREFIX}{definition.name}"
        if key in servers:
            if servers[key] != desired:
                raise CapabilityConflict(f"conflicting Cursor MCP entry {key}")
            return context.success(context.harness, identity, "verified")
        owned_entry = owned_capability_entry(
            "mcp", definition.name, str(path), env=context.env
        )
        servers[key] = desired
        write_json_atomic(path, document)
        return HarnessResult(
            context.harness,
            ResultState.READY,
            (),
            {identity: "installed-by-manifest"},
            owned_entries=(owned_entry,),
        )
    except (
        CapabilityConflict,
        OwnershipError,
        OSError,
        UnicodeError,
        json.JSONDecodeError,
    ) as error:
        return context.failure(context.harness, tier, str(error), identity)


def _install_http_mcp(
    context: McpApplyContext,
    definition: McpDefinition,
    tier: CapabilityTier,
    identity: str,
) -> HarnessResult:
    command_builder = _NATIVE_HTTP_COMMANDS.get(context.harness)
    if command_builder is None or definition.url is None:
        return context.failure(
            context.harness,
            tier,
            f"unsupported MCP transport for {definition.name}",
            identity,
        )
    try:
        owned_entry = owned_capability_entry("mcp", definition.name, env=context.env)
    except OwnershipError as error:
        return context.failure(context.harness, tier, str(error), identity)
    result, command = context.run(
        context.harness,
        context.runner,
        command_builder(definition.name, definition.url),
        tier,
        identity,
        context.env,
        success="installed-by-manifest",
    )
    if result.state is not ResultState.READY:
        if command is not None and _already_registered(command):
            return context.success(context.harness, identity, "verified")
        return result
    return replace(result, owned_entries=(owned_entry,))


def _already_registered(command: CommandResult) -> bool:
    """Return whether a native MCP add refused because the server is present.

    Reached only for harnesses whose live inventory is not observed:
    merged_native_mcp_inventory reads live state for Codex alone, so every other
    harness arrives here with an EMPTY observation and re-adds a server it
    already has. Claude then exits 1 with "already exists in user config", the
    capability lands as `failed`, and write_receipt_atomic refuses the receipt --
    blocking install on exactly the machines bootstrap has already configured
    (Context7 is the one server Manifest ships registered).

    Deliberately returns a VERIFIED capability and no owned entry at the call
    site: Manifest did not create this server, and claiming ownership would let
    uninstall delete a server the user or bootstrap registered.
    """
    diagnostic = f"{command.stdout}\n{command.stderr}".lower()
    return "already" in diagnostic and any(
        word in diagnostic for word in ("added", "exists", "installed", "present")
    )


def _inventory_definition(inventory, name):
    if isinstance(inventory, Mapping):
        return inventory.get(name)
    return name if name in inventory else None


def _native_inventory_names(context: McpApplyContext) -> set[str]:
    inventory = context.observation.inventory
    names = set(inventory.keys() if isinstance(inventory, Mapping) else inventory)
    if context.harness != "cursor":
        return names
    path = context.cursor_path or cursor_mcp_path(context.env)
    try:
        servers = read_cursor_document(path).get("mcpServers", {})
    except (OSError, UnicodeError, json.JSONDecodeError):
        servers = {}
    if isinstance(servers, dict):
        names.update(name for name in servers if isinstance(name, str))
    return names

"""Harness-neutral application of a resolved capability plan."""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Collection, Mapping
from dataclasses import replace
from pathlib import Path
from typing import TYPE_CHECKING

from manifest_agent.capability_cursor import (
    cursor_mcp_path as default_cursor_mcp_path,
)
from manifest_agent.capability_cursor import (
    read_cursor_document,
    remove_owned_cursor_mcp,
    write_json_atomic,
)
from manifest_agent.models import (
    CapabilityTier,
    CommandResult,
    HarnessReceipt,
    HarnessResult,
    ResultState,
)
from manifest_agent.ownership import (
    OwnershipError,
    capability_ownership_errors,
    owned_capability_entry,
)
from manifest_agent.process import CommandRunner, redact_text

if TYPE_CHECKING:
    from manifest_agent.capabilities import (
        CapabilityPlan,
        ExecutableDefinition,
        McpDefinition,
    )

_MARKER = "manifest"
_CURSOR_KEY_PREFIX = "manifest-"
_STATE_PRIORITY = {
    ResultState.READY: 0,
    ResultState.DEGRADED: 1,
    ResultState.DRIFTED: 2,
    ResultState.BLOCKED: 3,
}
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


def apply_capability_plan(
    harness: str,
    plan: CapabilityPlan,
    *,
    runner: CommandRunner,
    which: Callable[[str], str | None],
    env: Mapping[str, str] | None = None,
    native_mcp_inventory: Collection[str] | Mapping[str, McpDefinition] = (),
    cursor_mcp_path: Path | None = None,
    configure_mcp: bool = True,
    configure_executables: bool = True,
) -> HarnessResult:
    """Apply one union through the harness-independent adapter seam."""
    results: list[HarnessResult] = []
    if configure_executables:
        results.extend(
            _apply_executable(harness, plan, name, runner, which, env)
            for name in plan.selected_executables
        )
    if configure_mcp:
        results.extend(
            _apply_mcp(
                harness,
                plan,
                name,
                runner,
                env,
                native_mcp_inventory,
                cursor_mcp_path,
            )
            for name in plan.selected_mcp
        )
    return _combine(harness, results)


def remove_owned_capabilities(
    harness: str,
    receipt: HarnessReceipt,
    *,
    runner: CommandRunner,
    env: Mapping[str, str] | None = None,
    cursor_mcp_path: Path | None = None,
) -> HarnessResult:
    """Remove only executable and Cursor MCP entries proven owned by a receipt."""
    if receipt.harness != harness:
        return _failure(
            harness,
            CapabilityTier.REQUIRED,
            f"receipt harness {receipt.harness!r} does not match {harness!r}",
        )
    ownership_errors = capability_ownership_errors(
        receipt,
        env=env,
        expected_cursor_path=(
            cursor_mcp_path or default_cursor_mcp_path(env)
            if harness == "cursor"
            else None
        ),
    )
    if ownership_errors:
        return _failure(
            harness,
            CapabilityTier.REQUIRED,
            "; ".join(ownership_errors),
        )
    results: list[HarnessResult] = []
    if any(
        entry.kind == "executable"
        and entry.identifier == "graphify"
        and entry.ownership_marker == _MARKER
        for entry in receipt.owned_entries
    ):
        results.append(
            _run(
                harness,
                runner,
                ("uv", "tool", "uninstall", "graphifyy"),
                CapabilityTier.DEFAULT,
                "executable:graphify",
                env,
                success="removed",
            )[0]
        )
    if harness == "cursor":
        results.extend(
            _remove_cursor_entries(
                receipt, cursor_mcp_path or default_cursor_mcp_path(env)
            )
        )
    return _combine(harness, results)


def _apply_executable(harness, plan, name, runner, which, env):
    tier = plan.tier("executables", name)
    identity = f"executable:{name}"
    recipe = plan.executable_definitions.get(name)
    try:
        executable = which(name)
    except Exception as error:
        return _failure(harness, tier, str(error), identity)
    if executable is not None:
        if recipe is None:
            return _success(harness, identity, "verified")
        verified = _verify_recipe(
            harness, recipe, runner, tier, identity, env, "verified"
        )
        if verified.state is ResultState.READY:
            return verified
        if "version does not match" not in " ".join(verified.errors):
            return verified
    if recipe is None:
        return _failure(harness, tier, f"executable {name} is not available", identity)
    return _install_recipe(harness, recipe, runner, which, tier, identity, env)


def _install_recipe(harness, recipe, runner, which, tier, identity, env):
    try:
        manager = which("uv")
    except Exception as error:
        return _failure(harness, tier, str(error), identity)
    if recipe.manager != "uv-tool" or manager is None:
        return _failure(harness, tier, "uv tool manager is not available", identity)
    try:
        owned_entry = owned_capability_entry("executable", recipe.executable, env=env)
    except OwnershipError as error:
        return _failure(harness, tier, str(error), identity)
    installed, _command = _run(
        harness,
        runner,
        ("uv", "tool", "install", f"{recipe.distribution}=={recipe.version}"),
        tier,
        identity,
        env,
        success="installed-by-manifest",
    )
    if installed.state is not ResultState.READY:
        return installed
    try:
        installed_executable = which(recipe.executable)
    except Exception as error:
        return _failure(harness, tier, str(error), identity)
    if installed_executable is None:
        return _failure(
            harness,
            tier,
            f"installed {recipe.executable} executable is not discoverable",
            identity,
        )
    verified = _verify_recipe(
        harness,
        recipe,
        runner,
        tier,
        identity,
        env,
        "installed-by-manifest",
    )
    if verified.state is not ResultState.READY:
        return verified
    return replace(
        verified,
        owned_entries=(owned_entry,),
    )


def _verify_recipe(
    harness,
    recipe: ExecutableDefinition,
    runner,
    tier,
    identity,
    env,
    status,
):
    result, command = _run(
        harness,
        runner,
        (recipe.executable, "--version"),
        tier,
        identity,
        env,
        success=status,
    )
    if result.state is not ResultState.READY or command is None:
        return result
    version = rf"(?<![0-9.]){re.escape(recipe.version)}(?![0-9.])"
    if re.search(version, command.stdout):
        return result
    return _failure(
        harness,
        tier,
        f"{recipe.executable} version does not match {recipe.version}",
        identity,
    )


def _apply_mcp(harness, plan, name, runner, env, inventory, cursor_path):
    tier = plan.tier("mcp", name)
    identity = f"mcp:{name}"
    definition = plan.mcp_definitions[name]
    existing = _existing_mcp_result(harness, definition, tier, identity, inventory)
    if existing is not None:
        return existing
    if definition.transport == "native-existing":
        names = _native_inventory_names(harness, inventory, cursor_path, env)
        if any(
            native_name.startswith(definition.discovery_prefixes)
            for native_name in names
        ):
            return _success(harness, identity, "verified")
        return _failure(
            harness,
            tier,
            f"native {name.title()} setup is not present in {harness}",
            identity,
        )
    if harness == "cursor":
        return _apply_cursor_mcp(
            definition,
            tier,
            cursor_path or default_cursor_mcp_path(env),
            harness,
            env,
        )
    if harness == "antigravity":
        return _failure(
            harness,
            tier,
            f"Antigravity imported plugin has no native declaration for MCP {name}",
            identity,
        )
    command_builder = _NATIVE_HTTP_COMMANDS.get(harness)
    if command_builder is None or definition.url is None:
        return _failure(
            harness, tier, f"unsupported MCP transport for {name}", identity
        )
    try:
        owned_entry = owned_capability_entry("mcp", name, env=env)
    except OwnershipError as error:
        return _failure(harness, tier, str(error), identity)
    result = _run(
        harness,
        runner,
        command_builder(name, definition.url),
        tier,
        identity,
        env,
        success="installed-by-manifest",
    )[0]
    if result.state is not ResultState.READY:
        return result
    return replace(
        result,
        owned_entries=(owned_entry,),
    )


def _existing_mcp_result(harness, definition, tier, identity, inventory):
    from manifest_agent.capabilities import CapabilityConflict, merge_mcp_definitions

    observed = _inventory_definition(inventory, definition.name)
    if observed is None:
        return None
    if isinstance(observed, str) and definition.transport != "native-existing":
        return _failure(
            harness,
            tier,
            f"native MCP inventory lacks transport identity for {definition.name}",
            identity,
        )
    if not isinstance(observed, str):
        try:
            merge_mcp_definitions(definition, observed)
        except CapabilityConflict as error:
            return _failure(harness, tier, str(error), identity)
    return _success(harness, identity, "verified")


def _apply_cursor_mcp(definition, tier, path, harness, env):
    from manifest_agent.capabilities import CapabilityConflict

    identity = f"mcp:{definition.name}"
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
            return _success(harness, identity, "verified")
        owned_entry = owned_capability_entry("mcp", definition.name, str(path), env=env)
        servers[key] = desired
        write_json_atomic(path, document)
        return HarnessResult(
            harness,
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
        return _failure(harness, tier, str(error), identity)


def _remove_cursor_entries(receipt, path):
    from manifest_agent.capabilities import CapabilityConflict

    try:
        return [
            _success("cursor", f"mcp:{name}", "removed")
            for name in remove_owned_cursor_mcp(receipt, path)
        ]
    except (CapabilityConflict, OSError, UnicodeError, json.JSONDecodeError) as error:
        return [_failure("cursor", CapabilityTier.REQUIRED, str(error))]


def _run(harness, runner, argv, tier, identity, env, *, success):
    try:
        command = runner.run(argv, env=env)
    except Exception as error:
        return _failure(
            harness, tier, f"native command failed: {error}", identity
        ), None
    if command.returncode != 0:
        return _failure(harness, tier, _command_diagnostic(command), identity), command
    return _success(harness, identity, success), command


def _command_diagnostic(command: CommandResult) -> str:
    parts = [f"native command exited {command.returncode}"]
    if command.stdout.strip():
        parts.append(f"stdout: {command.stdout.strip()}")
    if command.stderr.strip():
        parts.append(f"stderr: {command.stderr.strip()}")
    return "; ".join(parts)


def _success(harness, identity, status):
    return HarnessResult(harness, ResultState.READY, (), {identity: status})


def _failure(harness, tier, diagnostic, identity=None):
    diagnostic = redact_text(diagnostic)
    status = "missing" if tier is CapabilityTier.OPTIONAL else "failed"
    capabilities = {identity: status} if identity else {}
    if tier is CapabilityTier.REQUIRED:
        return HarnessResult(
            harness, ResultState.BLOCKED, (), capabilities, errors=(diagnostic,)
        )
    if tier is CapabilityTier.DEFAULT:
        return HarnessResult(
            harness, ResultState.DEGRADED, (), capabilities, errors=(diagnostic,)
        )
    return HarnessResult(
        harness, ResultState.READY, (), capabilities, warnings=(diagnostic,)
    )


def _combine(harness, results):
    if not results:
        return HarnessResult(harness, ResultState.READY, (), {})
    state = max((item.state for item in results), key=_STATE_PRIORITY.__getitem__)
    return HarnessResult(
        harness,
        state,
        (),
        {key: value for item in results for key, value in item.capabilities.items()},
        errors=tuple(value for item in results for value in item.errors),
        warnings=tuple(value for item in results for value in item.warnings),
        owned_entries=tuple(
            dict.fromkeys(entry for item in results for entry in item.owned_entries)
        ),
    )


def _inventory_definition(inventory, name):
    if isinstance(inventory, Mapping):
        return inventory.get(name)
    return name if name in inventory else None


def _native_inventory_names(harness, inventory, cursor_path, env):
    names = set(inventory.keys() if isinstance(inventory, Mapping) else inventory)
    if harness == "cursor":
        path = cursor_path or default_cursor_mcp_path(env)
        try:
            servers = read_cursor_document(path).get("mcpServers", {})
        except (OSError, UnicodeError, json.JSONDecodeError):
            servers = {}
        if isinstance(servers, dict):
            names.update(name for name in servers if isinstance(name, str))
    return names

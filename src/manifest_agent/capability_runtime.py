"""Harness-neutral application of a resolved capability plan."""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Collection, Mapping
from dataclasses import replace
from pathlib import Path
from typing import TYPE_CHECKING

from manifest_agent.adapters.codex_mcp_inventory import merged_native_mcp_inventory
from manifest_agent.capability_cursor import (
    cursor_mcp_path as default_cursor_mcp_path,
)
from manifest_agent.capability_cursor import (
    remove_owned_cursor_mcp,
)
from manifest_agent.capability_mcp_runtime import McpApplyContext, apply_mcp
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
_STATE_PRIORITY = {
    ResultState.READY: 0,
    ResultState.DEGRADED: 1,
    ResultState.DRIFTED: 2,
    ResultState.BLOCKED: 3,
}


def apply_capability_plan(
    harness: str,
    plan: CapabilityPlan,
    *,
    runner: CommandRunner,
    which: Callable[[str], str | None],
    env: Mapping[str, str] | None = None,
    native_mcp_inventory: Collection[str] | Mapping[str, McpDefinition] | None = None,
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
        observation = merged_native_mcp_inventory(
            harness, runner, env, native_mcp_inventory
        )
        context = McpApplyContext(
            harness,
            runner,
            env,
            observation,
            cursor_mcp_path,
            _run,
            _success,
            _failure,
        )
        results.extend(apply_mcp(context, plan, name) for name in plan.selected_mcp)
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


def _failure(harness, tier, diagnostic, identity=None, *, status=None):
    diagnostic = redact_text(diagnostic)
    if status is None:
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
        declared_degradations=tuple(
            value for item in results for value in item.declared_degradations
        ),
    )

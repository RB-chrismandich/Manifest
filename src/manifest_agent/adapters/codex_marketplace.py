"""Codex marketplace identity and plugin-state comparisons."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
from pathlib import Path
from typing import Any

from manifest_agent.adapters.base import native_command_result
from manifest_agent.adapters.codex_common import (
    COMMIT,
    MARKETPLACE,
    CodexCommandExecutor,
    blocked,
    resolved_path,
)
from manifest_agent.adapters.codex_native import (
    installed_plugin_path,
    normalized_git_source,
    validate_marketplace_add_json,
    validate_plugin_add_json,
)
from manifest_agent.codex_plugin_backup import (
    CodexPluginBackup,
    CodexPluginBackupError,
    plugin_tree_sha256,
    verify_plugin_backup,
)
from manifest_agent.models import (
    AdapterMarketplaceState,
    AdapterMutationHandle,
    AdapterPluginState,
    CapabilityTier,
    CommandResult,
    DesiredState,
    HarnessResult,
    MarketplaceSourceKind,
)


def marketplace_identity_error(
    desired: DesiredState, observed: AdapterMarketplaceState
) -> str | None:
    expected = desired_marketplace_identity(desired)
    if (
        observed.source_kind != expected.source_kind
        or observed.source != expected.source
    ):
        return (
            "manifest marketplace source mismatch: expected "
            f"{expected.source}, found {observed.source}"
        )
    if observed.immutable_ref != expected.immutable_ref:
        return (
            "manifest marketplace ref mismatch: expected "
            f"{expected.immutable_ref}, found {observed.immutable_ref}"
        )
    return None


def marketplace_state_from_row(
    adapter: CodexCommandExecutor, row: Mapping[str, Any]
) -> AdapterMarketplaceState:
    source = row.get("marketplaceSource")
    root = row.get("root")
    if not isinstance(source, Mapping) or not isinstance(root, str) or not root:
        raise ValueError("manifest marketplace lacks exact source/root identity")
    source_kind = source.get("sourceType")
    source_value = source.get("source")
    if source_kind not in {"local", "git"} or not isinstance(source_value, str):
        raise ValueError("manifest marketplace lacks exact source identity")
    immutable_ref = None
    normalized_source = resolved_path(source_value)
    if source_kind == "git":
        normalized_source = normalized_git_source(source_value)
        command, error = adapter._execute(("git", "-C", root, "rev-parse", "HEAD"))
        if error is not None or command is None or command.returncode != 0:
            raise ValueError("manifest marketplace checkout identity is unavailable")
        immutable_ref = command.stdout.strip().lower()
        if COMMIT.fullmatch(immutable_ref) is None:
            raise ValueError("manifest marketplace checkout ref is invalid")
    return AdapterMarketplaceState(
        MARKETPLACE,
        source_kind,
        normalized_source,
        immutable_ref,
        resolved_path(root),
    )


def desired_marketplace_identity(desired: DesiredState) -> AdapterMarketplaceState:
    source_kind = desired.marketplace_source.kind.value
    source = (
        resolved_path(desired.marketplace_source.source)
        if desired.marketplace_source.kind is MarketplaceSourceKind.LOCAL
        else normalized_git_source(desired.marketplace_source.source)
    )
    return AdapterMarketplaceState(
        MARKETPLACE,
        source_kind,
        source,
        desired.marketplace_source.ref,
        resolved_path(
            desired.marketplace_source.source
            if desired.marketplace_source.kind is MarketplaceSourceKind.LOCAL
            else str(desired.release_root)
        ),
    )


def row_matches_state(row: Mapping[str, Any], state: AdapterPluginState) -> bool:
    if not (
        row.get("pluginId") == state.identifier
        and row.get("version") == state.version
        and row.get("enabled") is state.enabled
    ):
        return False
    if state.installed_path is None and state.installed_sha256 is None:
        return True
    installed = installed_plugin_path(row)
    if not isinstance(installed, str):
        return False
    if state.installed_path is not None and resolved_path(installed) != resolved_path(
        state.installed_path
    ):
        return False
    if state.installed_sha256 is not None:
        try:
            return plugin_tree_sha256(Path(installed)) == state.installed_sha256
        except CodexPluginBackupError:
            return False
    return True


def inventory_matches(
    rows: Mapping[str, Mapping[str, Any]],
    expected: Mapping[str, AdapterPluginState],
) -> bool:
    return set(rows) == set(expected) and all(
        row_matches_state(rows[plugin_id], state)
        for plugin_id, state in expected.items()
    )


def local_marketplace_requires_refresh(handle: AdapterMutationHandle) -> bool:
    """Detect same-version content changes hidden by a stable local path."""
    marketplace = handle.target_marketplace
    if marketplace is None or marketplace.source_kind != "local":
        return False
    prior = {item.identifier: item for item in handle.prior_inventory}
    target = {item.identifier: item for item in handle.target_inventory}
    return any(
        prior[plugin_id].version == target[plugin_id].version
        and prior[plugin_id].installed_sha256 != target[plugin_id].installed_sha256
        for plugin_id in prior.keys() & target.keys()
    )


def backup_from_state(state: AdapterPluginState) -> CodexPluginBackup | None:
    if state.rollback_data is None:
        return None
    try:
        return CodexPluginBackup.from_dict(state.rollback_data)
    except CodexPluginBackupError:
        return None


def verified_backup_from_state(
    state: AdapterPluginState,
) -> CodexPluginBackup | None:
    backup = backup_from_state(state)
    if (
        backup is None
        or backup.plugin_id != state.identifier
        or backup.version != state.version
        or backup.enabled is not state.enabled
        or state.installed_path is None
        or resolved_path(backup.installed_path) != resolved_path(state.installed_path)
        or backup.installed_sha256 != state.installed_sha256
    ):
        return None
    try:
        verify_plugin_backup(backup)
    except CodexPluginBackupError:
        return None
    return backup


def with_retirement_phase(
    handle: AdapterMutationHandle, plugin_id: str, phase: str
) -> AdapterMutationHandle:
    return replace(
        handle,
        prior_inventory=tuple(
            replace(item, retirement_phase=phase)
            if item.identifier == plugin_id
            else item
            for item in handle.prior_inventory
        ),
    )


def row_matches_backup(row: Mapping[str, Any], backup: CodexPluginBackup) -> bool:
    installed = installed_plugin_path(row)
    if (
        row.get("pluginId") != backup.plugin_id
        or row.get("version") != backup.version
        or row.get("enabled") is not backup.enabled
        or not isinstance(installed, str)
        or resolved_path(installed) != resolved_path(backup.installed_path)
    ):
        return False
    try:
        return plugin_tree_sha256(Path(installed)) == backup.installed_sha256
    except CodexPluginBackupError:
        return False


def marketplace_add_argv(desired: DesiredState) -> tuple[str, ...]:
    argv = [
        "codex",
        "plugin",
        "marketplace",
        "add",
        desired.marketplace_source.source,
    ]
    if desired.marketplace_source.kind is MarketplaceSourceKind.GIT:
        assert desired.marketplace_source.ref is not None
        argv.extend(("--ref", desired.marketplace_source.ref))
    argv.append("--json")
    return tuple(argv)


def validate_marketplace_add(command: CommandResult) -> HarnessResult | None:
    if command.returncode != 0:
        return native_command_result("codex", command, CapabilityTier.REQUIRED)
    error = validate_marketplace_add_json(command.stdout)
    return blocked(error) if error is not None else None


def validate_plugin_add(
    command: CommandResult, bundle: str, version: str
) -> HarnessResult | None:
    if command.returncode != 0:
        return native_command_result("codex", command, CapabilityTier.REQUIRED)
    error = validate_plugin_add_json(command.stdout, bundle, version)
    return blocked(error) if error is not None else None

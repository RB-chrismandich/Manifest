"""Claude Code native marketplace adapter."""

from __future__ import annotations

import json
import shutil
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

from manifest_agent.adapters.base import (
    CapabilityAdapterMixin,
    Detection,
    NativeMcpInventory,
    collect_native_component_evidence,
    combine_results,
    native_command_result,
    normalize_native_mcp_inventory,
    verify_declared_components,
)
from manifest_agent.contracts import DOMAIN_BUNDLES
from manifest_agent.models import (
    CapabilityTier,
    CommandResult,
    DesiredState,
    HarnessReceipt,
    HarnessResult,
    MarketplaceSourceKind,
    ResultState,
)
from manifest_agent.process import CommandRunner, redact_text

_MARKETPLACE = "manifest"
_ADAPTER_VERSION = "1"
_CANONICAL_PLUGIN_IDS = tuple(f"{name}@{_MARKETPLACE}" for name in DOMAIN_BUNDLES)


class ClaudeAdapter(CapabilityAdapterMixin):
    """Install and verify the canonical Manifest bundles through Claude Code."""

    name = "claude"
    adapter_version = _ADAPTER_VERSION

    def __init__(
        self,
        runner: CommandRunner | None = None,
        *,
        which: Callable[[str], str | None] = shutil.which,
        env: Mapping[str, str] | None = None,
        native_mcp_inventory: NativeMcpInventory = (),
    ) -> None:
        self.runner = runner or CommandRunner()
        self._which = which
        self._env = env
        self._native_mcp_inventory = normalize_native_mcp_inventory(
            native_mcp_inventory
        )

    def detect(self) -> Detection:
        """Report the Claude executable and native version, including absence."""
        executable = self._which(self.name)
        if executable is None:
            return Detection(False, None, None, "claude CLI not present")
        command, error = self._execute((executable, "--version"))
        if error is not None:
            return Detection(True, executable, None, error.errors[0])
        assert command is not None
        if command.returncode != 0:
            result = native_command_result(self.name, command, CapabilityTier.REQUIRED)
            return Detection(True, executable, None, result.errors[0])
        version = (
            command.stdout.strip().splitlines()[0] if command.stdout.strip() else None
        )
        return Detection(True, executable, redact_text(version) if version else None)

    def inspect(self, desired: DesiredState) -> HarnessResult:
        """Verify marketplace identity, plugins, and declared native evidence."""
        invalid = _validate_desired(desired)
        if invalid is not None:
            return invalid
        marketplace = self._inspect_marketplace(desired)
        if marketplace.state is not ResultState.READY:
            return marketplace
        command, error = self._execute((self.name, "plugin", "list", "--json"))
        if error is not None:
            return error
        assert command is not None
        if command.returncode != 0:
            return native_command_result(self.name, command, CapabilityTier.REQUIRED)
        rows, parse_error = _plugin_rows(command.stdout)
        if parse_error is not None:
            return _blocked(parse_error)
        plugins = _verify_rows(desired, rows, require_user_scope=True)
        evidence = _component_evidence(desired, rows, self._which)
        components = verify_declared_components(self.name, desired, evidence)
        return combine_results(marketplace, plugins, components)

    def install(self, desired: DesiredState) -> HarnessResult:
        """Converge the marketplace and all canonical bundles at user scope."""
        invalid = _validate_desired(desired)
        if invalid is not None:
            return invalid

        source = _marketplace_command_source(desired)
        add_command = (
            self.name,
            "plugin",
            "marketplace",
            "add",
            source,
            "--scope",
            "user",
        )
        add_failures, add_conflicts = self._run_install_mutations([add_command])
        marketplace = self._inspect_marketplace(desired)
        if marketplace.state is not ResultState.READY or add_failures:
            return combine_results(*add_failures, *add_conflicts, marketplace)

        commands: list[Sequence[str]] = [
            (
                self.name,
                "plugin",
                "install",
                f"{bundle}@{_MARKETPLACE}",
                "--scope",
                "user",
            )
            for bundle in DOMAIN_BUNDLES
        ]
        failures, already_present = self._run_install_mutations(commands)
        capabilities = self.install_capabilities(desired)
        inspected = self.inspect(desired)
        if not _selected_plugins_match(desired, inspected):
            failures.extend(already_present)
        return combine_results(*failures, capabilities, inspected)

    def _inspect_marketplace(self, desired: DesiredState) -> HarnessResult:
        command, error = self._execute(
            (self.name, "plugin", "marketplace", "list", "--json")
        )
        if error is not None:
            return error
        assert command is not None
        if command.returncode != 0:
            return native_command_result(self.name, command, CapabilityTier.REQUIRED)
        row, parse_error = _marketplace_row(command.stdout)
        if parse_error is not None:
            return _blocked(parse_error)
        expected = _marketplace_command_source(desired)
        observed = row.get("path")
        if row.get("source") != "directory" or not isinstance(observed, str):
            return _blocked("manifest marketplace is not a native directory source")
        if _resolved_path(observed) != _resolved_path(expected):
            return _blocked(
                f"manifest marketplace source mismatch: expected {expected}, found {observed}"
            )
        return HarnessResult(
            self.name,
            ResultState.READY,
            (),
            {"marketplace:manifest": "verified"},
        )

    def uninstall(self, receipt: HarnessReceipt) -> HarnessResult:
        """Remove receipt-owned plugins and an unreferenced owned marketplace."""
        plugin_ids, id_errors = _receipt_plugin_ids(receipt)
        invalid = self.validate_uninstall_receipt(
            receipt,
            plugin_ids,
            _CANONICAL_PLUGIN_IDS,
            identity_errors=id_errors,
            marketplace_identifier=_MARKETPLACE,
        )
        if invalid is not None:
            return invalid
        capabilities = self.remove_capabilities(receipt)
        removal_commands = [
            (self.name, "plugin", "uninstall", plugin_id) for plugin_id in plugin_ids
        ]
        removal_failures = self._run_mutations(removal_commands)
        installed_ids, list_error = self._list_installed_manifest_ids()
        if list_error is not None:
            return combine_results(capabilities, *removal_failures, list_error)
        assert installed_ids is not None
        plugins = _finish_uninstall(
            self, receipt, plugin_ids, removal_failures, installed_ids
        )
        return combine_results(capabilities, plugins)

    def _list_installed_manifest_ids(
        self,
    ) -> tuple[set[str] | None, HarnessResult | None]:
        command, error = self._execute((self.name, "plugin", "list", "--json"))
        if error is not None:
            return None, error
        assert command is not None
        if command.returncode != 0:
            return None, native_command_result(
                self.name, command, CapabilityTier.REQUIRED
            )
        rows, parse_error = _plugin_rows(command.stdout)
        if parse_error is not None:
            return None, _blocked(parse_error)
        return _installed_manifest_ids(rows), None

    def _run_mutations(self, commands: Sequence[Sequence[str]]) -> list[HarnessResult]:
        failures: list[HarnessResult] = []
        for argv in commands:
            command, error = self._execute(argv)
            if error is not None:
                failures.append(error)
            elif command is not None and command.returncode != 0:
                failures.append(
                    native_command_result(self.name, command, CapabilityTier.REQUIRED)
                )
        return failures

    def _run_install_mutations(
        self, commands: Sequence[Sequence[str]]
    ) -> tuple[list[HarnessResult], list[HarnessResult]]:
        failures: list[HarnessResult] = []
        already_present: list[HarnessResult] = []
        for argv in commands:
            command, error = self._execute(argv)
            if error is not None:
                failures.append(error)
            elif command is not None and command.returncode != 0:
                result = native_command_result(
                    self.name, command, CapabilityTier.REQUIRED
                )
                target = already_present if _already_present(command) else failures
                target.append(result)
        return failures, already_present

    def _execute(
        self, argv: Sequence[str]
    ) -> tuple[CommandResult | None, HarnessResult | None]:
        try:
            return self.runner.run(argv, env=self._env), None
        # constitution: exempt C-ERR -- adapter boundary returns redacted errors.
        except Exception as error:
            diagnostic = redact_text(
                f"native command execution failed ({type(error).__name__}): {error}"
            )
            return None, _blocked(diagnostic)


def _finish_uninstall(
    adapter: ClaudeAdapter,
    receipt: HarnessReceipt,
    plugin_ids: Sequence[str],
    failures: list[HarnessResult],
    installed_ids: set[str],
) -> HarnessResult:
    owned_remaining = tuple(
        plugin_id for plugin_id in plugin_ids if plugin_id in installed_ids
    )
    unowned = sorted(installed_ids - set(plugin_ids))
    warnings: tuple[str, ...] = ()
    if unowned:
        warnings = (
            "manifest marketplace retained because an unowned plugin references it: "
            + ", ".join(unowned),
        )
    elif not owned_remaining and not failures and _owns_marketplace(receipt):
        marketplace_failure = adapter._run_mutations(
            [
                (
                    adapter.name,
                    "plugin",
                    "marketplace",
                    "remove",
                    _MARKETPLACE,
                )
            ]
        )
        failures.extend(marketplace_failure)

    result = HarnessResult(
        adapter.name,
        ResultState.BLOCKED if owned_remaining else ResultState.READY,
        owned_remaining,
        {},
        errors=tuple(
            f"receipt-owned plugin remains installed: {item}"
            for item in owned_remaining
        ),
        warnings=warnings,
    )
    return combine_results(*failures, result) if failures else result


def _validate_desired(desired: DesiredState) -> HarnessResult | None:
    names = tuple(contract.name for contract in desired.contracts)
    if names != DOMAIN_BUNDLES:
        return _blocked(
            "desired state must contain the exact canonical domain plugins"
        )
    if any(not contract.version for contract in desired.contracts):
        return _blocked("desired plugin versions must be non-empty")
    if not desired.marketplace_source.source:
        return _blocked("desired marketplace source must be non-empty")
    if (
        desired.marketplace_source.kind is MarketplaceSourceKind.GIT
        and desired.marketplace_source.ref != desired.source_commit
    ):
        return _blocked("desired marketplace ref must match the release commit")
    return None


def _marketplace_command_source(desired: DesiredState) -> str:
    if desired.marketplace_source.kind is MarketplaceSourceKind.LOCAL:
        return desired.marketplace_source.source
    return str(desired.release_root)


def _marketplace_row(
    stdout: str,
) -> tuple[Mapping[str, Any], str | None]:
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


def _verify_rows(
    desired: DesiredState,
    rows: Sequence[Mapping[str, Any]],
    *,
    require_user_scope: bool,
) -> HarnessResult:
    by_id = {row.get("id"): row for row in rows if isinstance(row.get("id"), str)}
    installed: list[str] = []
    errors: list[str] = []
    drifted = False
    for contract in desired.contracts:
        plugin_id = f"{contract.name}@{_MARKETPLACE}"
        row = by_id.get(plugin_id)
        if row is None:
            errors.append(f"missing required plugin: {plugin_id}")
            continue
        installed.append(plugin_id)
        version = row.get("version")
        if version != contract.version:
            errors.append(
                redact_text(
                    f"plugin {plugin_id} expected {contract.version}, found {version}"
                )
            )
            drifted = True
        if require_user_scope and row.get("scope") != "user":
            errors.append(f"plugin {plugin_id} is not installed at user scope")
        if row.get("enabled") is False:
            errors.append(f"plugin {plugin_id} is disabled")
    if not errors:
        state = ResultState.READY
    elif drifted and len(installed) == len(desired.contracts):
        state = ResultState.DRIFTED
    else:
        state = ResultState.BLOCKED
    return HarnessResult("claude", state, tuple(installed), {}, tuple(errors))


def _component_evidence(
    desired: DesiredState,
    rows: Sequence[Mapping[str, Any]],
    which: Callable[[str], str | None],
) -> set[str]:
    roots: dict[str, Path] = {}
    mcp_servers: dict[str, tuple[str, ...]] = {}
    by_id = {row.get("id"): row for row in rows if isinstance(row.get("id"), str)}
    for contract in desired.contracts:
        row = by_id.get(f"{contract.name}@{_MARKETPLACE}")
        if row is None:
            continue
        root_value = row.get("installPath")
        if isinstance(root_value, str):
            roots[contract.name] = Path(root_value)
        native_mcp = row.get("mcpServers")
        if isinstance(native_mcp, Mapping):
            mcp_servers[contract.name] = tuple(
                server for server in native_mcp if isinstance(server, str)
            )
    return collect_native_component_evidence(desired, roots, mcp_servers, which)


def _selected_plugins_match(desired: DesiredState, result: HarnessResult) -> bool:
    expected = {f"{contract.name}@{_MARKETPLACE}" for contract in desired.contracts}
    return set(result.installed_plugin_ids) == expected and not any(
        error.startswith(("missing required plugin:", "plugin "))
        for error in result.errors
    )


def _resolved_path(value: str) -> str:
    return str(Path(value).expanduser().resolve(strict=False))


def _receipt_plugin_ids(
    receipt: HarnessReceipt,
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    ids: list[str] = []
    errors: list[str] = []
    for identifier in receipt.plugin_ids:
        plugin_id = (
            f"{identifier}@{_MARKETPLACE}"
            if identifier in DOMAIN_BUNDLES
            else identifier
        )
        bundle, separator, marketplace = plugin_id.partition("@")
        if (
            separator != "@"
            or marketplace != _MARKETPLACE
            or bundle not in DOMAIN_BUNDLES
        ):
            errors.append(f"receipt contains non-canonical plugin ID: {identifier}")
        elif plugin_id not in ids:
            ids.append(plugin_id)
    return tuple(ids), tuple(errors)


def _installed_manifest_ids(rows: Sequence[Mapping[str, Any]]) -> set[str]:
    return {
        identifier
        for row in rows
        if isinstance((identifier := row.get("id")), str)
        and identifier.endswith(f"@{_MARKETPLACE}")
    }


def _owns_marketplace(receipt: HarnessReceipt) -> bool:
    return any(
        entry.kind == "marketplace" and entry.identifier == _MARKETPLACE
        for entry in receipt.owned_entries
    )


def _already_present(command: CommandResult) -> bool:
    diagnostic = f"{command.stdout}\n{command.stderr}".lower()
    return "already" in diagnostic and any(
        word in diagnostic for word in ("added", "exists", "installed", "present")
    )


def _blocked(error: str) -> HarnessResult:
    return HarnessResult(
        "claude", ResultState.BLOCKED, (), {}, errors=(redact_text(error),)
    )

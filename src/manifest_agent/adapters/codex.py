"""Codex native marketplace adapter."""

from __future__ import annotations

import re
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
from manifest_agent.adapters.codex_native import (
    marketplace_row,
    normalized_git_source,
    plugin_rows,
    validate_marketplace_add_json,
    validate_plugin_add_json,
    validate_remove_json,
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
_COMMIT = re.compile(r"^[0-9a-fA-F]{40}(?:[0-9a-fA-F]{24})?$")


class CodexAdapter(CapabilityAdapterMixin):
    """Install and verify the nine Manifest bundles through Codex."""

    name = "codex"
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
        """Report the Codex executable and native version, including absence."""
        executable = self._which(self.name)
        if executable is None:
            return Detection(False, None, None, "codex CLI not present")
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
        rows, parse_error = plugin_rows(command.stdout)
        if parse_error is not None:
            return _blocked(parse_error)
        plugins = _verify_rows(desired, rows)
        evidence = _component_evidence(desired, rows, self._which)
        components = verify_declared_components(self.name, desired, evidence)
        return combine_results(marketplace, plugins, components)

    def install(self, desired: DesiredState) -> HarnessResult:
        """Install an immutable marketplace snapshot and all canonical bundles."""
        invalid = _validate_desired(desired)
        if invalid is not None:
            return invalid
        add_command = _marketplace_add_argv(desired)
        add_command_result, add_execution_error = self._execute(add_command)
        add_failure = add_execution_error
        if add_command_result is not None:
            add_failure = _validate_marketplace_add(add_command_result)
        marketplace = self._inspect_marketplace(desired)
        if marketplace.state is not ResultState.READY or add_failure is not None:
            results = [result for result in (add_failure, marketplace) if result]
            return combine_results(*results)

        failures: list[HarnessResult] = []
        for contract in desired.contracts:
            argv = (
                self.name,
                "plugin",
                "add",
                f"{contract.name}@{_MARKETPLACE}",
                "--json",
            )
            command, error = self._execute(argv)
            if error is not None:
                failures.append(error)
            elif command is not None:
                failure = _validate_plugin_add(command, contract.name, contract.version)
                if failure is not None:
                    failures.append(failure)
        inspected = self.inspect(desired)
        if not failures:
            return inspected
        return combine_results(*failures, inspected)

    def _inspect_marketplace(self, desired: DesiredState) -> HarnessResult:
        command, error = self._execute(
            (self.name, "plugin", "marketplace", "list", "--json")
        )
        if error is not None:
            return error
        assert command is not None
        if command.returncode != 0:
            return native_command_result(self.name, command, CapabilityTier.REQUIRED)
        row, parse_error = marketplace_row(command.stdout)
        if parse_error is not None:
            return _blocked(parse_error)
        identity_error = _marketplace_identity_error(self, desired, row)
        if identity_error is not None:
            return _blocked(identity_error)
        return HarnessResult(
            self.name,
            ResultState.READY,
            (),
            {"marketplace:manifest": "verified"},
        )

    def uninstall(self, receipt: HarnessReceipt) -> HarnessResult:
        """Remove receipt-owned plugins and an unreferenced owned marketplace."""
        if receipt.harness != self.name:
            return _blocked(
                f"receipt harness {receipt.harness!r} does not match {self.name!r}"
            )
        plugin_ids, id_errors = _receipt_plugin_ids(receipt)
        receipt_failures = [*_error_results(id_errors)]
        removal_failures = self._run_json_mutations(
            [
                (self.name, "plugin", "remove", plugin_id, "--json")
                for plugin_id in plugin_ids
            ]
        )
        failures = receipt_failures + removal_failures
        installed_ids, list_error = self._list_installed_manifest_ids()
        if list_error is not None:
            return combine_results(*failures, list_error) if failures else list_error
        assert installed_ids is not None
        return self._finish_uninstall(receipt, plugin_ids, failures, installed_ids)

    def _finish_uninstall(
        self,
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
            failures.extend(
                self._run_json_mutations(
                    [
                        (
                            self.name,
                            "plugin",
                            "marketplace",
                            "remove",
                            _MARKETPLACE,
                            "--json",
                        )
                    ]
                )
            )

        result = HarnessResult(
            self.name,
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
        rows, parse_error = plugin_rows(command.stdout)
        if parse_error is not None:
            return None, _blocked(parse_error)
        return _installed_manifest_ids(rows), None

    def _run_json_mutations(
        self, commands: Sequence[Sequence[str]]
    ) -> list[HarnessResult]:
        failures: list[HarnessResult] = []
        for argv in commands:
            command, error = self._execute(argv)
            if error is not None:
                failures.append(error)
                continue
            assert command is not None
            if command.returncode != 0:
                failures.append(
                    native_command_result(self.name, command, CapabilityTier.REQUIRED)
                )
                continue
            json_error = validate_remove_json(argv, command.stdout)
            if json_error is not None:
                failures.append(_blocked(json_error))
        return failures

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


def _marketplace_identity_error(
    adapter: CodexAdapter, desired: DesiredState, row: Mapping[str, Any]
) -> str | None:
    native_source = row.get("marketplaceSource")
    if not isinstance(native_source, Mapping):
        return "manifest marketplace JSON is missing native source identity"
    source_type = native_source.get("sourceType")
    observed = native_source.get("source")
    if not isinstance(observed, str):
        return "manifest marketplace JSON is missing its source"
    expected = desired.marketplace_source.source
    if desired.marketplace_source.kind is MarketplaceSourceKind.LOCAL:
        if source_type != "local" or _resolved_path(observed) != _resolved_path(
            expected
        ):
            return (
                f"manifest marketplace source mismatch: expected {expected}, "
                f"found {observed}"
            )
        return None
    if source_type != "git" or normalized_git_source(observed) != normalized_git_source(
        expected
    ):
        return (
            f"manifest marketplace source mismatch: expected {expected}, "
            f"found {observed}"
        )
    root = row.get("root")
    if not isinstance(root, str):
        return "manifest Git marketplace JSON is missing its checkout root"
    command, error = adapter._execute(("git", "-C", root, "rev-parse", "HEAD"))
    if error is not None:
        return error.errors[0]
    assert command is not None
    if command.returncode != 0:
        result = native_command_result("codex", command, CapabilityTier.REQUIRED)
        return result.errors[0]
    observed_ref = command.stdout.strip().lower()
    if observed_ref != desired.marketplace_source.ref:
        return (
            "manifest marketplace ref mismatch: expected "
            f"{desired.marketplace_source.ref}, found {observed_ref}"
        )
    return None


def _validate_desired(desired: DesiredState) -> HarnessResult | None:
    names = tuple(contract.name for contract in desired.contracts)
    if names != DOMAIN_BUNDLES:
        return _blocked(
            "desired state must contain the exact nine canonical domain plugins"
        )
    if any(not contract.version for contract in desired.contracts):
        return _blocked("desired plugin versions must be non-empty")
    if not desired.marketplace_source.source:
        return _blocked("desired marketplace source must be non-empty")
    if not _COMMIT.fullmatch(desired.source_commit):
        return _blocked("Codex marketplace source commit must be immutable")
    if (
        desired.marketplace_source.kind is MarketplaceSourceKind.GIT
        and desired.marketplace_source.ref != desired.source_commit
    ):
        return _blocked("desired marketplace ref must match the release commit")
    return None


def _marketplace_add_argv(desired: DesiredState) -> tuple[str, ...]:
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


def _validate_marketplace_add(command: CommandResult) -> HarnessResult | None:
    if command.returncode != 0:
        return native_command_result("codex", command, CapabilityTier.REQUIRED)
    error = validate_marketplace_add_json(command.stdout)
    if error is not None:
        return _blocked(error)
    return None


def _validate_plugin_add(
    command: CommandResult, bundle: str, version: str
) -> HarnessResult | None:
    if command.returncode != 0:
        return native_command_result("codex", command, CapabilityTier.REQUIRED)
    error = validate_plugin_add_json(command.stdout, bundle, version)
    if error is not None:
        return _blocked(error)
    return None


def _verify_rows(
    desired: DesiredState, rows: Sequence[Mapping[str, Any]]
) -> HarnessResult:
    by_id = {
        row.get("pluginId"): row
        for row in rows
        if isinstance(row.get("pluginId"), str) and row.get("installed") is not False
    }
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
        if row.get("enabled") is False:
            errors.append(f"plugin {plugin_id} is disabled")
    if not errors:
        state = ResultState.READY
    elif drifted and len(installed) == len(desired.contracts):
        state = ResultState.DRIFTED
    else:
        state = ResultState.BLOCKED
    return HarnessResult("codex", state, tuple(installed), {}, tuple(errors))


def _component_evidence(
    desired: DesiredState,
    rows: Sequence[Mapping[str, Any]],
    which: Callable[[str], str | None],
) -> set[str]:
    roots: dict[str, Path] = {}
    mcp_servers: dict[str, tuple[str, ...]] = {}
    by_id = {
        row.get("pluginId"): row for row in rows if isinstance(row.get("pluginId"), str)
    }
    for contract in desired.contracts:
        row = by_id.get(f"{contract.name}@{_MARKETPLACE}")
        if row is None:
            continue
        source = row.get("source")
        root_value = source.get("path") if isinstance(source, Mapping) else None
        if isinstance(root_value, str):
            roots[contract.name] = Path(root_value)
        native_mcp = row.get("mcpServers")
        if isinstance(native_mcp, Mapping):
            mcp_servers[contract.name] = tuple(
                server for server in native_mcp if isinstance(server, str)
            )
    return collect_native_component_evidence(desired, roots, mcp_servers, which)


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
        if isinstance((identifier := row.get("pluginId")), str)
        and identifier.endswith(f"@{_MARKETPLACE}")
        and row.get("installed") is not False
    }


def _owns_marketplace(receipt: HarnessReceipt) -> bool:
    return any(
        entry.kind == "marketplace" and entry.identifier == _MARKETPLACE
        for entry in receipt.owned_entries
    )


def _error_results(errors: Sequence[str]) -> tuple[HarnessResult, ...]:
    return tuple(_blocked(error) for error in errors)


def _blocked(error: str) -> HarnessResult:
    return HarnessResult(
        "codex", ResultState.BLOCKED, (), {}, errors=(redact_text(error),)
    )

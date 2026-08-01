"""Claude Code native marketplace adapter."""

from __future__ import annotations

import json
import shutil
from collections.abc import Callable, Mapping, Sequence
from typing import Any

from manifest_agent.adapters.base import (
    Detection,
    combine_results,
    native_command_result,
)
from manifest_agent.contracts import DOMAIN_BUNDLES
from manifest_agent.models import (
    CapabilityTier,
    CommandResult,
    DesiredState,
    HarnessReceipt,
    HarnessResult,
    ResultState,
)
from manifest_agent.process import CommandRunner, redact_text

_MARKETPLACE = "manifest"
_ADAPTER_VERSION = "1"


class ClaudeAdapter:
    """Install and verify the nine Manifest bundles through Claude Code."""

    name = "claude"
    adapter_version = _ADAPTER_VERSION

    def __init__(
        self,
        runner: CommandRunner | None = None,
        *,
        which: Callable[[str], str | None] = shutil.which,
        env: Mapping[str, str] | None = None,
    ) -> None:
        self.runner = runner or CommandRunner()
        self._which = which
        self._env = env

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
        """Verify exact user-scope bundle IDs and selected contract versions."""
        invalid = _validate_desired(desired)
        if invalid is not None:
            return invalid
        command, error = self._execute((self.name, "plugin", "list", "--json"))
        if error is not None:
            return error
        assert command is not None
        if command.returncode != 0:
            return native_command_result(self.name, command, CapabilityTier.REQUIRED)
        rows, parse_error = _plugin_rows(command.stdout)
        if parse_error is not None:
            return _blocked(parse_error)
        return _verify_rows(desired, rows, require_user_scope=True)

    def install(self, desired: DesiredState) -> HarnessResult:
        """Converge the marketplace and all canonical bundles at user scope."""
        invalid = _validate_desired(desired)
        if invalid is not None:
            return invalid

        commands: list[Sequence[str]] = [
            (
                self.name,
                "plugin",
                "marketplace",
                "add",
                desired.source,
                "--scope",
                "user",
            )
        ]
        commands.extend(
            (
                self.name,
                "plugin",
                "install",
                f"{bundle}@{_MARKETPLACE}",
                "--scope",
                "user",
            )
            for bundle in DOMAIN_BUNDLES
        )
        failures, already_present = self._run_install_mutations(commands)
        inspected = self.inspect(desired)
        if inspected.state is not ResultState.READY:
            failures.extend(already_present)
        if not failures:
            return inspected
        return combine_results(*failures, inspected)

    def uninstall(self, receipt: HarnessReceipt) -> HarnessResult:
        """Remove receipt-owned plugins and an unreferenced owned marketplace."""
        if receipt.harness != self.name:
            return _blocked(
                f"receipt harness {receipt.harness!r} does not match {self.name!r}"
            )
        plugin_ids, id_errors = _receipt_plugin_ids(receipt)
        receipt_failures = [*_error_results(id_errors)]
        removal_commands = [
            (self.name, "plugin", "uninstall", plugin_id) for plugin_id in plugin_ids
        ]
        removal_failures = self._run_mutations(removal_commands)
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
            marketplace_failure = self._run_mutations(
                [
                    (
                        self.name,
                        "plugin",
                        "marketplace",
                        "remove",
                        _MARKETPLACE,
                    )
                ]
            )
            failures.extend(marketplace_failure)

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


def _validate_desired(desired: DesiredState) -> HarnessResult | None:
    names = tuple(contract.name for contract in desired.contracts)
    if names != DOMAIN_BUNDLES:
        return _blocked(
            "desired state must contain the exact nine canonical domain plugins"
        )
    if any(not contract.version for contract in desired.contracts):
        return _blocked("desired plugin versions must be non-empty")
    if not desired.source:
        return _blocked("desired marketplace source must be non-empty")
    return None


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


def _error_results(errors: Sequence[str]) -> tuple[HarnessResult, ...]:
    return tuple(_blocked(error) for error in errors)


def _blocked(error: str) -> HarnessResult:
    return HarnessResult(
        "claude", ResultState.BLOCKED, (), {}, errors=(redact_text(error),)
    )

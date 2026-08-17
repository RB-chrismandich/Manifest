"""Codex native marketplace adapter."""

from __future__ import annotations

import json
import shutil
from collections.abc import Callable, Mapping, Sequence
from typing import Any

from manifest_agent.adapters.base import (
    CapabilityAdapterMixin,
    Detection,
    NativeMcpInventory,
    combine_results,
    native_command_result,
    normalize_native_mcp_inventory,
    verify_declared_components,
)
from manifest_agent.adapters.codex_catalog import (
    catalog_owned_entries,
    component_evidence,
    desired_target_identity,
    installed_manifest_ids,
    validate_desired,
    verify_rows,
)
from manifest_agent.adapters.codex_common import (
    ADAPTER_VERSION,
    MARKETPLACE,
    blocked,
)
from manifest_agent.adapters.codex_install import CodexInstallMixin
from manifest_agent.adapters.codex_marketplace import (
    marketplace_identity_error,
    marketplace_state_from_row,
    with_retirement_phase,
)
from manifest_agent.adapters.codex_native import (
    marketplace_row,
    plugin_rows,
    validate_remove_json,
)
from manifest_agent.adapters.codex_reconcile import CodexReconcileMixin
from manifest_agent.adapters.codex_reconcile_observe import (
    CodexReconcileObservationMixin,
)
from manifest_agent.adapters.codex_reconcile_rollback import (
    CodexReconcileRollbackMixin,
)
from manifest_agent.adapters.codex_uninstall import CodexUninstallMixin
from manifest_agent.adapters.codex_uninstall_state import (
    checkpoint_uninstall,
    load_or_create_uninstall_saga,
    uninstall_saga_path,
)
from manifest_agent.models import (
    AdapterMarketplaceState,
    CapabilityTier,
    CommandResult,
    DesiredState,
    HarnessResult,
    ResultState,
)
from manifest_agent.process import CommandRunner, redact_text

_MARKETPLACE = MARKETPLACE
_ADAPTER_VERSION = ADAPTER_VERSION
_catalog_owned_entries = catalog_owned_entries
_desired_target_identity = desired_target_identity
_checkpoint_uninstall = checkpoint_uninstall
_load_or_create_uninstall_saga = load_or_create_uninstall_saga
_uninstall_saga_path = uninstall_saga_path
_with_retirement_phase = with_retirement_phase


class CodexAdapter(
    CodexInstallMixin,
    CodexReconcileMixin,
    CodexReconcileObservationMixin,
    CodexReconcileRollbackMixin,
    CodexUninstallMixin,
    CapabilityAdapterMixin,
):
    """Install and verify the canonical Manifest bundles through Codex."""

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
        self._last_marketplace_identity: AdapterMarketplaceState | None = None
        self._marketplace_observed = False

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
        invalid = validate_desired(desired)
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
        rows, parse_error = plugin_rows(command.stdout, self._env)
        if parse_error is not None:
            return blocked(parse_error)
        plugins = verify_rows(desired, rows)
        evidence = component_evidence(desired, rows, self._which)
        components = verify_declared_components(self.name, desired, evidence)
        return combine_results(marketplace, plugins, components)

    def install(self, desired: DesiredState) -> HarnessResult:
        """Install an immutable marketplace snapshot and all canonical bundles."""
        return self.install_with_checkpoints(desired)

    def _observed_marketplace_identity(
        self, *, allow_absent: bool = False
    ) -> AdapterMarketplaceState | None:
        command, error = self._execute(
            (self.name, "plugin", "marketplace", "list", "--json")
        )
        if error is not None:
            raise ValueError(error.errors[0])
        assert command is not None
        if command.returncode != 0:
            raise ValueError("Codex marketplace inventory command failed")
        try:
            document = json.loads(command.stdout)
        except json.JSONDecodeError as error:
            raise ValueError("Codex marketplace inventory is invalid") from error
        rows = document.get("marketplaces") if isinstance(document, Mapping) else None
        if not isinstance(rows, list) or any(
            not isinstance(row, Mapping) for row in rows
        ):
            raise ValueError("Codex marketplace inventory is invalid")
        matches = [row for row in rows if row.get("name") == MARKETPLACE]
        if not matches and allow_absent:
            self._last_marketplace_identity = None
            self._marketplace_observed = True
            return None
        if len(matches) != 1:
            raise ValueError("Codex marketplace inventory is ambiguous")
        observed = marketplace_state_from_row(self, matches[0])
        self._last_marketplace_identity = observed
        self._marketplace_observed = True
        return observed

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
            return blocked(parse_error)
        try:
            identity = marketplace_state_from_row(self, row)
        except ValueError as error:
            return blocked(str(error))
        identity_error = marketplace_identity_error(desired, identity)
        if identity_error is not None:
            return blocked(identity_error)
        self._last_marketplace_identity = identity
        self._marketplace_observed = True
        return HarnessResult(
            self.name,
            ResultState.READY,
            (),
            {"marketplace:manifest": "verified"},
        )

    def _list_installed_manifest_ids(
        self,
    ) -> tuple[set[str] | None, HarnessResult | None]:
        rows, error = self._installed_manifest_rows()
        if error is not None or rows is None:
            return None, error
        return installed_manifest_ids(rows), None

    def _installed_manifest_rows(
        self,
    ) -> tuple[list[Mapping[str, Any]] | None, HarnessResult | None]:
        command, error = self._execute((self.name, "plugin", "list", "--json"))
        if error is not None:
            return None, error
        assert command is not None
        if command.returncode != 0:
            return None, native_command_result(
                self.name, command, CapabilityTier.REQUIRED
            )
        rows, parse_error = plugin_rows(command.stdout, self._env)
        if parse_error is not None:
            return None, blocked(parse_error)
        return rows, None

    def _list_installed_manifest_rows(
        self,
    ) -> tuple[dict[str, Mapping[str, Any]] | None, HarnessResult | None]:
        rows, error = self._installed_manifest_rows()
        if error is not None or rows is None:
            return None, error
        return {
            row["pluginId"]: row
            for row in rows
            if isinstance(row.get("pluginId"), str)
            and row["pluginId"].endswith(f"@{MARKETPLACE}")
            and row.get("installed") is not False
        }, None

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
                failures.append(blocked(json_error))
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
            return None, blocked(diagnostic)

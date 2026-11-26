"""Preparation and application of durable Codex reconciliation handles."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import TYPE_CHECKING, Any

from manifest_agent.adapters.codex_catalog import (
    catalog,
    desired_target_identity,
    validate_desired,
)
from manifest_agent.adapters.codex_common import MARKETPLACE, blocked, resolved_path
from manifest_agent.adapters.codex_marketplace import (
    desired_marketplace_identity,
    row_matches_state,
)
from manifest_agent.adapters.codex_native import installed_plugin_path
from manifest_agent.codex_plugin_backup import (
    CodexPluginBackupError,
    capture_plugin_backup,
    plugin_tree_sha256,
)
from manifest_agent.models import (
    AdapterMarketplaceState,
    AdapterMutationHandle,
    AdapterPluginState,
    DesiredState,
    HarnessReceipt,
    HarnessResult,
)

RetirementCheckpoint = Callable[[AdapterMutationHandle], None]


class CodexReconcileMixin:
    """Prepare, apply, and verify the durable Codex target transaction."""

    if TYPE_CHECKING:
        name: str
        adapter_version: str
        _env: Mapping[str, str] | None
        _list_installed_manifest_rows: Callable[
            [], tuple[dict[str, Mapping[str, Any]] | None, HarnessResult | None]
        ]
        _observed_marketplace_identity: Callable[..., AdapterMarketplaceState | None]
        _observe_prepared_reconcile: Callable[
            [AdapterMutationHandle], tuple[str | None, bool, HarnessResult | None]
        ]
        _retire_prior_only_plugins: Callable[
            [AdapterMutationHandle, RetirementCheckpoint | None],
            tuple[AdapterMutationHandle, HarnessResult | None],
        ]
        inspect: Callable[[DesiredState], HarnessResult]
        install_with_checkpoints: Callable[..., HarnessResult]

    def prepare_reconcile(
        self, receipt: HarnessReceipt, prior: DesiredState, desired: DesiredState
    ) -> AdapterMutationHandle:
        """Capture exact Codex marketplace/plugins before any native mutation."""
        invalid = validate_desired(desired)
        if invalid is not None:
            raise ValueError(invalid.errors[0])
        prior_marketplace, rows = _prior_state(self, receipt, prior)
        target_inventory = _target_inventory(desired)
        prior_inventory = _prior_inventory(rows, target_inventory, self._env)
        return AdapterMutationHandle(
            1,
            self.name,
            self.adapter_version,
            desired_target_identity(desired),
            prior_inventory,
            target_inventory,
            prior_marketplace,
            desired_marketplace_identity(desired),
        )

    def apply_reconcile(
        self,
        handle: AdapterMutationHandle,
        desired: DesiredState,
        retirement_checkpoint: RetirementCheckpoint | None = None,
    ) -> HarnessResult:
        """Apply only the exact Codex target recorded in the durable handle."""
        self._validate_codex_handle(handle, desired)
        observation, marketplace_preverified, failure = (
            self._observe_prepared_reconcile(handle)
        )
        if failure is not None:
            return failure
        if observation == "target":
            return self.inspect(desired)
        _updated, retirement = self._retire_prior_only_plugins(
            handle, retirement_checkpoint
        )
        if retirement is not None:
            return retirement
        return self.install_with_checkpoints(
            desired, marketplace_preverified=marketplace_preverified
        )

    def verify_reconcile(
        self, handle: AdapterMutationHandle, desired: DesiredState
    ) -> HarnessResult:
        """Verify exact marketplace and plugin target state after application."""
        self._validate_codex_handle(handle, desired)
        observation, _marketplace_preverified, failure = (
            self._observe_prepared_reconcile(handle)
        )
        if failure is not None:
            return failure
        if observation != "target":
            return blocked("Codex reconciliation did not reach the exact target")
        return self.inspect(desired)

    def classify_reconcile_state(
        self, handle: AdapterMutationHandle, desired: DesiredState
    ) -> str:
        """Classify an interrupted prepared mutation without changing native state."""
        del desired
        observation, _marketplace_preverified, failure = (
            self._observe_prepared_reconcile(handle)
        )
        if failure is not None:
            return "other"
        return observation if observation in {"prior", "target"} else "other"

    def _validate_codex_handle(
        self, handle: AdapterMutationHandle, desired: DesiredState
    ) -> None:
        valid_identity = (
            handle.schema_version == 1
            and handle.harness == self.name
            and handle.adapter_version == self.adapter_version
            and handle.target_identity == desired_target_identity(desired)
        )
        if (
            not valid_identity
            or handle.target_inventory != _target_inventory(desired)
            or handle.target_marketplace != desired_marketplace_identity(desired)
        ):
            raise ValueError("Codex reconciliation handle does not match target")


def _prior_state(
    adapter: CodexReconcileMixin,
    receipt: HarnessReceipt,
    prior: DesiredState,
) -> tuple[AdapterMarketplaceState | None, dict[str, Mapping[str, Any]]]:
    marketplace = adapter._observed_marketplace_identity(allow_absent=True)
    rows, error = adapter._list_installed_manifest_rows()
    if error is not None or rows is None:
        raise ValueError((error or blocked("plugin inventory unavailable")).errors[0])
    authorized = set(receipt.plugin_ids)
    expected = {f"{plugin.name}@{MARKETPLACE}" for plugin in catalog(prior)}
    if (
        receipt.native_version == "prepared"
        and not receipt.plugin_ids
        and not receipt.owned_entries
    ):
        expected = set()
    if authorized != expected:
        raise ValueError("prior Codex receipt inventory does not match its release")
    if set(rows) != authorized:
        raise ValueError(
            "installed Codex plugin inventory contains missing or unrecognized "
            "Manifest plugins"
        )
    return marketplace, rows


def _target_inventory(desired: DesiredState) -> tuple[AdapterPluginState, ...]:
    try:
        return tuple(
            AdapterPluginState(
                f"{plugin.name}@{MARKETPLACE}",
                plugin.version,
                True,
                installed_sha256=plugin_tree_sha256(desired.bundle_path(plugin.name)),
            )
            for plugin in catalog(desired)
        )
    except CodexPluginBackupError as error:
        raise ValueError("desired Codex plugin inventory is not hashable") from error


def _prior_inventory(
    rows: Mapping[str, Mapping[str, Any]],
    target_inventory: Sequence[AdapterPluginState],
    env: Mapping[str, str] | None,
) -> tuple[AdapterPluginState, ...]:
    target_by_id = {item.identifier: item for item in target_inventory}
    inventory: list[AdapterPluginState] = []
    for plugin_id, row in sorted(rows.items()):
        prior_state = _prior_plugin_state(plugin_id, row)
        target = target_by_id.get(plugin_id)
        backup = None
        if target is None or not row_matches_state(row, target):
            backup = capture_plugin_backup(row, env).to_dict()
        inventory.append(
            AdapterPluginState(
                prior_state.identifier,
                prior_state.version,
                prior_state.enabled,
                backup,
                prior_state.installed_path,
                prior_state.installed_sha256,
                "backed-up" if target is None else None,
            )
        )
    return tuple(inventory)


def _prior_plugin_state(plugin_id: str, row: Mapping[str, Any]) -> AdapterPluginState:
    version = row.get("version")
    enabled = row.get("enabled")
    installed = installed_plugin_path(row)
    if (
        not isinstance(version, str)
        or not isinstance(enabled, bool)
        or not isinstance(installed, str)
    ):
        raise ValueError("installed Manifest plugin inventory is not rollback-safe")
    try:
        installed_sha256 = plugin_tree_sha256(Path(installed))
    except CodexPluginBackupError as error:
        raise ValueError(
            "installed Manifest plugin inventory is not hashable"
        ) from error
    return AdapterPluginState(
        plugin_id,
        version,
        enabled,
        installed_path=resolved_path(installed),
        installed_sha256=installed_sha256,
    )

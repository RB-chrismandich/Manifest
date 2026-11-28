"""Compensating rollback for interrupted Codex reconciliation."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from manifest_agent.adapters.base import combine_results
from manifest_agent.adapters.codex_common import MARKETPLACE, blocked
from manifest_agent.adapters.codex_marketplace import (
    backup_from_state,
    row_matches_backup,
    row_matches_state,
    validate_marketplace_add,
    verified_backup_from_state,
)
from manifest_agent.codex_plugin_backup import (
    CodexPluginBackupError,
    restore_plugin_backup,
)
from manifest_agent.models import (
    AdapterMarketplaceState,
    AdapterMutationHandle,
    AdapterPluginState,
    DesiredState,
    HarnessResult,
    ResultState,
)


@dataclass(frozen=True)
class _RollbackItem:
    plugin_id: str
    prior: AdapterPluginState | None
    target: AdapterPluginState | None
    row: Mapping[str, Any] | None


class CodexReconcileRollbackMixin:
    """Restore the exact prior Codex inventory and marketplace identity."""

    if TYPE_CHECKING:
        name: str
        adapter_version: str
        _execute: Callable[..., tuple[Any, HarnessResult | None]]
        _list_installed_manifest_rows: Callable[
            [], tuple[dict[str, Mapping[str, Any]] | None, HarnessResult | None]
        ]
        _observed_marketplace_identity: Callable[..., AdapterMarketplaceState | None]
        _run_json_mutations: Callable[[Sequence[Sequence[str]]], list[HarnessResult]]

    def rollback_reconcile(
        self, handle: AdapterMutationHandle, prior: DesiredState
    ) -> HarnessResult:
        """Compensate target-only additions and exact replaced Codex plugins."""
        del prior
        if not _valid_rollback_handle(self, handle):
            return blocked("Codex reconciliation rollback handle is invalid")
        rows, error = self._list_installed_manifest_rows()
        if error is not None or rows is None:
            return error or blocked("Codex plugin inventory is unavailable")
        prior_by_id = {item.identifier: item for item in handle.prior_inventory}
        target_by_id = {item.identifier: item for item in handle.target_inventory}
        failures: list[HarnessResult] = []
        for plugin_id in reversed(tuple(dict.fromkeys((*target_by_id, *prior_by_id)))):
            item = _RollbackItem(
                plugin_id,
                prior_by_id.get(plugin_id),
                target_by_id.get(plugin_id),
                rows.get(plugin_id),
            )
            failure = _rollback_plugin(self, item, failures)
            if failure is not None:
                return combine_results(*failures, failure) if failures else failure
        result = combine_results(*failures, self._rollback_marketplace(handle))
        if result.state not in {ResultState.READY, ResultState.DEGRADED}:
            return result
        return _verify_prior_inventory(self, prior_by_id, result)

    def _rollback_marketplace(self, handle: AdapterMutationHandle) -> HarnessResult:
        current = self._observed_marketplace_identity(allow_absent=True)
        prior = handle.prior_marketplace
        if current == prior:
            return HarnessResult(self.name, ResultState.READY, (), {})
        if current != handle.target_marketplace:
            return blocked("Codex marketplace changed after prepared reconciliation")
        failures = self._run_json_mutations(
            [
                (
                    self.name,
                    "plugin",
                    "marketplace",
                    "remove",
                    MARKETPLACE,
                    "--json",
                )
            ]
        )
        if failures:
            return combine_results(*failures)
        return _restore_prior_marketplace(self, prior)


def _valid_rollback_handle(
    adapter: CodexReconcileRollbackMixin, handle: AdapterMutationHandle
) -> bool:
    return (
        handle.schema_version == 1
        and handle.harness == adapter.name
        and handle.adapter_version == adapter.adapter_version
    )


def _rollback_plugin(
    adapter: CodexReconcileRollbackMixin,
    item: _RollbackItem,
    failures: list[HarnessResult],
) -> HarnessResult | None:
    if item.target is None:
        assert item.prior is not None
        return _restore_prior_only(item)
    if item.prior is None:
        return _remove_target_only(adapter, item, failures)
    if (
        item.row is not None
        and row_matches_state(item.row, item.prior)
        and row_matches_state(item.row, item.target)
    ) or item.prior == item.target:
        return None
    backup = backup_from_state(item.prior)
    if backup is None:
        return blocked(f"Codex rollback lacks a backup for {item.plugin_id}")
    if item.row is not None and row_matches_backup(item.row, backup):
        return None
    if item.row is not None:
        if not row_matches_state(item.row, item.target):
            return blocked(f"Codex rollback blocked because {item.plugin_id} changed")
        removal = adapter._run_json_mutations(
            [(adapter.name, "plugin", "remove", item.plugin_id, "--json")]
        )
        if removal:
            return combine_results(*removal)
    try:
        restore_plugin_backup(backup)
    except CodexPluginBackupError as error:
        return blocked(str(error))
    return None


def _restore_prior_only(item: _RollbackItem) -> HarnessResult | None:
    assert item.prior is not None
    backup = verified_backup_from_state(item.prior)
    if backup is None:
        return blocked(f"Codex rollback lacks a backup for {item.plugin_id}")
    if item.row is not None:
        if row_matches_backup(item.row, backup):
            return None
        return blocked(f"Codex rollback blocked because {item.plugin_id} changed")
    try:
        restore_plugin_backup(backup)
    except CodexPluginBackupError as error:
        return blocked(str(error))
    return None


def _remove_target_only(
    adapter: CodexReconcileRollbackMixin,
    item: _RollbackItem,
    failures: list[HarnessResult],
) -> HarnessResult | None:
    if item.row is None:
        return None
    assert item.target is not None
    if not row_matches_state(item.row, item.target):
        return blocked(f"Codex rollback blocked because {item.plugin_id} was replaced")
    failures.extend(
        adapter._run_json_mutations(
            [(adapter.name, "plugin", "remove", item.plugin_id, "--json")]
        )
    )
    return None


def _verify_prior_inventory(
    adapter: CodexReconcileRollbackMixin,
    prior: Mapping[str, AdapterPluginState],
    result: HarnessResult,
) -> HarnessResult:
    observed, error = adapter._list_installed_manifest_rows()
    if error is not None or observed is None:
        return combine_results(
            result, error or blocked("Codex rollback verification is unavailable")
        )
    if set(observed) != set(prior):
        return combine_results(
            result, blocked("Codex rollback did not restore the exact prior inventory")
        )
    for plugin_id, state in prior.items():
        backup = backup_from_state(state)
        matches = (
            row_matches_backup(observed[plugin_id], backup)
            if backup is not None
            else row_matches_state(observed[plugin_id], state)
        )
        if not matches:
            return combine_results(
                result,
                blocked(f"Codex rollback did not restore exact state for {plugin_id}"),
            )
    return result


def _restore_prior_marketplace(
    adapter: CodexReconcileRollbackMixin,
    prior: AdapterMarketplaceState | None,
) -> HarnessResult:
    if prior is None:
        observed = adapter._observed_marketplace_identity(allow_absent=True)
        return (
            HarnessResult(adapter.name, ResultState.READY, (), {})
            if observed is None
            else blocked("Codex marketplace rollback did not reach absence")
        )
    argv = [adapter.name, "plugin", "marketplace", "add", prior.source]
    if prior.source_kind == "git" and prior.immutable_ref is not None:
        argv.extend(("--ref", prior.immutable_ref))
    argv.append("--json")
    command, error = adapter._execute(tuple(argv))
    if error is not None:
        return error
    assert command is not None
    add_error = validate_marketplace_add(command)
    if add_error is not None:
        return add_error
    return (
        HarnessResult(adapter.name, ResultState.READY, (), {})
        if adapter._observed_marketplace_identity() == prior
        else blocked("Codex marketplace rollback did not restore exact identity")
    )

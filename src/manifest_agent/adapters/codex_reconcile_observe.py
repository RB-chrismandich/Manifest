"""Observation and prior-only retirement for Codex reconciliation."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from manifest_agent.adapters.base import combine_results
from manifest_agent.adapters.codex_common import blocked
from manifest_agent.adapters.codex_marketplace import (
    inventory_matches,
    local_marketplace_requires_refresh,
    row_matches_backup,
    row_matches_state,
    verified_backup_from_state,
    with_retirement_phase,
)
from manifest_agent.models import (
    AdapterMarketplaceState,
    AdapterMutationHandle,
    AdapterPluginState,
    HarnessResult,
)

RetirementCheckpoint = Callable[[AdapterMutationHandle], None]


@dataclass(frozen=True)
class _PartialObservation:
    handle: AdapterMutationHandle
    marketplace: AdapterMarketplaceState | None
    rows: Mapping[str, Mapping[str, Any]]
    prior: Mapping[str, AdapterPluginState]
    target: Mapping[str, AdapterPluginState]
    preverified: bool


class CodexReconcileObservationMixin:
    """Classify prepared native state and retire plugins absent from the target."""

    if TYPE_CHECKING:
        name: str
        _list_installed_manifest_rows: Callable[
            [], tuple[dict[str, Mapping[str, Any]] | None, HarnessResult | None]
        ]
        _observed_marketplace_identity: Callable[..., AdapterMarketplaceState | None]
        _run_json_mutations: Callable[[Sequence[Sequence[str]]], list[HarnessResult]]

    def _observe_prepared_reconcile(
        self, handle: AdapterMutationHandle
    ) -> tuple[str | None, bool, HarnessResult | None]:
        """Classify exact prior, target, authorized partial, or changed state."""
        try:
            marketplace = self._observed_marketplace_identity(allow_absent=True)
        except ValueError as error:
            return None, False, blocked(str(error))
        if marketplace not in {handle.prior_marketplace, handle.target_marketplace}:
            return (
                None,
                False,
                blocked("Codex marketplace changed after prepared reconciliation"),
            )
        rows, error = self._list_installed_manifest_rows()
        if error is not None or rows is None:
            return (
                None,
                False,
                error or blocked("Codex plugin inventory is unavailable"),
            )
        prior = {item.identifier: item for item in handle.prior_inventory}
        target = {item.identifier: item for item in handle.target_inventory}
        preverified = (
            marketplace == handle.target_marketplace
            and not local_marketplace_requires_refresh(handle)
        )
        unexpected = set(rows) - (set(prior) | set(target))
        if unexpected:
            return (
                None,
                False,
                blocked("Codex plugin inventory changed after prepared reconciliation"),
            )
        if marketplace == handle.target_marketplace and inventory_matches(rows, target):
            return "target", True, None
        if marketplace == handle.prior_marketplace and inventory_matches(rows, prior):
            return "prior", preverified, None
        return _classify_partial(
            _PartialObservation(
                handle,
                marketplace,
                rows,
                prior,
                target,
                preverified,
            )
        )

    def _retire_prior_only_plugins(
        self,
        handle: AdapterMutationHandle,
        checkpoint: RetirementCheckpoint | None,
    ) -> tuple[AdapterMutationHandle, HarnessResult | None]:
        """Remove prior-only plugins with a durable pre-removal checkpoint."""
        target_ids = {item.identifier for item in handle.target_inventory}
        current = handle
        for original in handle.prior_inventory:
            if original.identifier in target_ids:
                continue
            state = next(
                item
                for item in current.prior_inventory
                if item.identifier == original.identifier
            )
            current, failure = _retire_one(self, current, state, checkpoint)
            if failure is not None:
                return current, failure
        return current, None


def _classify_partial(
    observation: _PartialObservation,
) -> tuple[str | None, bool, HarnessResult | None]:
    expected_ids = set(observation.prior) | set(observation.target)
    if (
        observation.marketplace == observation.handle.prior_marketplace
        and observation.handle.prior_marketplace
        != observation.handle.target_marketplace
    ):
        if all(
            _prior_partial_entry(
                observation.rows.get(plugin_id),
                observation.prior.get(plugin_id),
                observation.target.get(plugin_id),
            )
            for plugin_id in expected_ids
        ):
            return "partial", False, None
        return (
            None,
            False,
            blocked(
                "Codex marketplace/plugin state is mixed after prepared reconciliation"
            ),
        )
    for plugin_id in expected_ids:
        if not _target_partial_entry(
            observation.rows.get(plugin_id),
            observation.prior.get(plugin_id),
            observation.target.get(plugin_id),
        ):
            return (
                None,
                True,
                blocked(
                    f"Codex plugin {plugin_id} changed after prepared reconciliation"
                ),
            )
    return "partial", observation.preverified, None


def _prior_partial_entry(
    row: Mapping[str, Any] | None,
    prior: AdapterPluginState | None,
    target: AdapterPluginState | None,
) -> bool:
    if prior is None and row is None:
        return True
    if prior is not None and row is not None and row_matches_state(row, prior):
        return True
    if _verified_retired_absence(row, prior, target):
        return True
    return _interrupted_rollback_absence(row, prior, target)


def _target_partial_entry(
    row: Mapping[str, Any] | None,
    prior: AdapterPluginState | None,
    target: AdapterPluginState | None,
) -> bool:
    if row is not None:
        return (prior is not None and row_matches_state(row, prior)) or (
            target is not None and row_matches_state(row, target)
        )
    if _verified_retired_absence(row, prior, target):
        return True
    return prior is None or _interrupted_rollback_absence(row, prior, target)


def _interrupted_rollback_absence(
    row: Mapping[str, Any] | None,
    prior: AdapterPluginState | None,
    target: AdapterPluginState | None,
) -> bool:
    """Is an absent plugin explained by a rollback whose restore did not finish?

    Rollback removes the installed target before restoring the prior backup, so
    a failed restore leaves the plugin absent with its prior backup still on
    disk. That is resumable -- the next pass retries the restore.

    The plugin must actually have been part of this reconciliation's diff:
    `prior != target` and a target exists. An unchanged plugin that simply
    vanished was never in a rollback, and must keep classifying as a blocking
    inconsistency rather than being waved through as in-progress. Both partial
    classifiers share this predicate so the two cannot drift apart again.
    """
    return (
        row is None
        and prior is not None
        and target is not None
        and prior != target
        and prior.rollback_data is not None
    )


def _verified_retired_absence(
    row: Mapping[str, Any] | None,
    prior: AdapterPluginState | None,
    target: AdapterPluginState | None,
) -> bool:
    return (
        row is None
        and prior is not None
        and target is None
        and prior.retirement_phase in {"removal-prepared", "removed"}
        and verified_backup_from_state(prior) is not None
    )


def _retire_one(
    adapter: CodexReconcileObservationMixin,
    handle: AdapterMutationHandle,
    state: AdapterPluginState,
    checkpoint: RetirementCheckpoint | None,
) -> tuple[AdapterMutationHandle, HarnessResult | None]:
    backup = verified_backup_from_state(state)
    if backup is None:
        return handle, blocked(
            f"Codex retirement lacks a verified backup for {state.identifier}"
        )
    rows, error = adapter._list_installed_manifest_rows()
    if error is not None or rows is None:
        return handle, error or blocked("Codex plugin inventory is unavailable")
    row = rows.get(state.identifier)
    if row is None:
        return _record_observed_absence(handle, state, checkpoint)
    if not row_matches_backup(row, backup):
        return handle, blocked(
            f"Codex retirement blocked because {state.identifier} changed"
        )
    if state.retirement_phase == "removed":
        return handle, blocked(f"Codex retired plugin {state.identifier} reappeared")
    current = _checkpoint_phase(
        handle, state.identifier, "removal-prepared", checkpoint
    )
    removal = adapter._run_json_mutations(
        [(adapter.name, "plugin", "remove", state.identifier, "--json")]
    )
    if removal:
        return current, combine_results(*removal)
    return _verify_retirement(adapter, current, state.identifier, checkpoint)


def _record_observed_absence(
    handle: AdapterMutationHandle,
    state: AdapterPluginState,
    checkpoint: RetirementCheckpoint | None,
) -> tuple[AdapterMutationHandle, HarnessResult | None]:
    if state.retirement_phase not in {"removal-prepared", "removed"}:
        return handle, blocked(
            f"Codex retirement of {state.identifier} is not checkpointed"
        )
    if state.retirement_phase == "removed":
        return handle, None
    return _checkpoint_phase(handle, state.identifier, "removed", checkpoint), None


def _verify_retirement(
    adapter: CodexReconcileObservationMixin,
    handle: AdapterMutationHandle,
    plugin_id: str,
    checkpoint: RetirementCheckpoint | None,
) -> tuple[AdapterMutationHandle, HarnessResult | None]:
    observed, error = adapter._list_installed_manifest_rows()
    if error is not None or observed is None:
        return handle, error or blocked("Codex retirement verification is unavailable")
    if plugin_id in observed:
        return handle, blocked(f"Codex retirement did not remove {plugin_id}")
    return _checkpoint_phase(handle, plugin_id, "removed", checkpoint), None


def _checkpoint_phase(
    handle: AdapterMutationHandle,
    plugin_id: str,
    phase: str,
    checkpoint: RetirementCheckpoint | None,
) -> AdapterMutationHandle:
    current = with_retirement_phase(handle, plugin_id, phase)
    if checkpoint is not None:
        checkpoint(current)
    return current

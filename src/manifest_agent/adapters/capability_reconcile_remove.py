"""Capability lifecycle responsibility mixin."""

from __future__ import annotations

from collections.abc import Callable, Sequence

from manifest_agent.models import (
    AdapterMutationHandle,
    AdapterPluginState,
    DesiredState,
    HarnessResult,
    ResultState,
)
from manifest_agent.process import redact_text


class ReconcileRemoveMixin:
    """Capability lifecycle methods grouped by one mutation responsibility."""

    def _remove_reconcile_plugins(
        self, expected_items: Sequence[AdapterPluginState], desired: DesiredState
    ) -> HarnessResult:
        if not expected_items:
            return HarnessResult(self.name, ResultState.READY, (), {})
        commands: dict[str, Callable[[str], Sequence[str]]] = {
            "claude": lambda item: (
                "claude",
                "plugin",
                "uninstall",
                item,
                "--scope",
                "user",
            ),
            "codex": lambda item: ("codex", "plugin", "remove", item, "--json"),
            "gemini": lambda item: ("gemini", "extensions", "uninstall", item),
            "antigravity": lambda item: ("agy", "plugin", "uninstall", item),
            "devin": lambda item: ("devin", "plugins", "remove", item),
        }
        if self.name == "cursor":
            return HarnessResult(
                self.name,
                ResultState.BLOCKED,
                (),
                {},
                errors=(
                    "Cursor cannot remove a target-only plugin delta through its "
                    "documented marketplace-only API",
                ),
            )
        builder = commands.get(self.name)
        if builder is None:
            return HarnessResult(
                self.name,
                ResultState.BLOCKED,
                (),
                {},
                errors=("adapter has no exact rollback removal implementation",),
            )
        failures = []
        with self._native_mutation_lock():
            for expected in expected_items:
                try:
                    error = self._conditional_native_remove(
                        expected, desired, builder(expected.identifier)
                    )
                except (OSError, ValueError) as error:
                    failures.append(redact_text(str(error)))
                    continue
                if error is not None:
                    failures.append(error)
        return HarnessResult(
            self.name,
            ResultState.BLOCKED if failures else ResultState.READY,
            (),
            {},
            errors=tuple(failures),
        )

    def _observe_exact_reconcile_inventory(
        self,
        desired: DesiredState,
        expected: Sequence[AdapterPluginState],
        handle: AdapterMutationHandle | None,
    ) -> HarnessResult | None:
        observer = getattr(self, "_native_reconcile_inventory", None)
        if observer is None:
            return HarnessResult(
                self.name,
                ResultState.BLOCKED,
                (),
                {},
                errors=("exact native reconciliation observation is unavailable",),
            )
        identifiers = {item.identifier for item in expected}
        if handle is not None:
            identifiers.update(
                item.identifier
                for item in (*handle.prior_inventory, *handle.target_inventory)
            )
        observed = tuple(
            observer(desired, capture_backups=False, identifiers=identifiers)
        )
        observed_by_id = {item.identifier: item for item in observed}
        expected_by_id = {item.identifier: item for item in expected}
        if set(observed_by_id) != set(expected_by_id) or any(
            self._reconcile_plugin_payload(observed_by_id[identifier])
            != self._reconcile_plugin_payload(item)
            for identifier, item in expected_by_id.items()
        ):
            return HarnessResult(
                self.name,
                ResultState.BLOCKED,
                (),
                {},
                errors=("native state changed at the mutation boundary",),
            )
        return None

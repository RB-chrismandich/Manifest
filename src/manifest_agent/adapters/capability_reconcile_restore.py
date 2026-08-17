"""Capability lifecycle responsibility mixin."""

from __future__ import annotations

import shutil
from collections.abc import Mapping
from pathlib import Path

from manifest_agent.adapters.capability_inventory import (
    normalize_native_mcp_inventory,
)
from manifest_agent.codex_plugin_backup import (
    CodexPluginBackup,
    plugin_tree_sha256,
    restore_plugin_backup,
)
from manifest_agent.models import (
    AdapterMutationHandle,
    AdapterPluginState,
    DesiredState,
    HarnessResult,
    ResultState,
)
from manifest_agent.process import redact_text


class ReconcileRestoreMixin:
    """Capability lifecycle methods grouped by one mutation responsibility."""

    def _restore_exact_prior_backups(
        self, handle: AdapterMutationHandle, prior: DesiredState
    ) -> HarnessResult:
        backups = tuple(
            item for item in handle.prior_inventory if item.rollback_data is not None
        )
        if not backups:
            return HarnessResult(self.name, ResultState.READY, (), {})
        current, error = self._current_prior_backups(handle, prior)
        if error is not None:
            return error
        assert current is not None
        restored_ids: list[str] = []
        for expected in backups:
            error = self._restore_prior_backup(
                expected, current.get(expected.identifier), restored_ids
            )
            if error is not None:
                return error
        return HarnessResult(self.name, ResultState.READY, tuple(restored_ids), {})

    def _current_prior_backups(self, handle, prior):
        observer = getattr(self, "_native_reconcile_inventory", None)
        if observer is None:
            error = self._restore_backup_error(
                (), "exact native reconciliation observation is unavailable"
            )
            return None, error
        managed = {
            item.identifier
            for item in (*handle.prior_inventory, *handle.target_inventory)
        }
        current = {
            item.identifier: item
            for item in observer(prior, capture_backups=False, identifiers=managed)
        }
        return current, None

    def _restore_prior_backup(
        self,
        expected: AdapterPluginState,
        observed: AdapterPluginState | None,
        restored_ids: list[str],
    ) -> HarnessResult | None:
        if observed is None:
            return self._restore_backup_error(
                restored_ids, f"native reinstall did not restore {expected.identifier}"
            )
        expected_metadata = self._reconcile_plugin_payload(expected)
        observed_metadata = self._reconcile_plugin_payload(observed)
        expected_digest = expected_metadata.pop("installed_sha256", None)
        observed_digest = observed_metadata.pop("installed_sha256", None)
        if observed_metadata != expected_metadata:
            return self._restore_backup_error(
                restored_ids,
                f"native reinstall changed rollback metadata for {expected.identifier}",
            )
        if observed_digest == expected_digest:
            restored_ids.append(expected.identifier)
            return None
        if (
            expected.installed_path is None
            or observed.installed_path != expected.installed_path
            or observed_digest is None
        ):
            return self._restore_backup_error(
                restored_ids,
                f"native reinstall changed rollback path for {expected.identifier}",
            )
        installed_path = Path(expected.installed_path)
        if installed_path.is_symlink() or not installed_path.is_dir():
            return self._restore_backup_error(
                restored_ids,
                f"native reinstall produced an unsafe rollback path for {expected.identifier}",
            )
        if plugin_tree_sha256(installed_path) != observed_digest:
            return self._restore_backup_error(
                restored_ids,
                f"native reinstall changed concurrently for {expected.identifier}",
            )
        shutil.rmtree(installed_path)
        restore_plugin_backup(CodexPluginBackup.from_dict(expected.rollback_data or {}))
        restored_ids.append(expected.identifier)
        return None

    def _restore_backup_error(self, restored_ids, message):
        return HarnessResult(
            self.name,
            ResultState.BLOCKED,
            tuple(restored_ids),
            {},
            errors=(message,),
        )

    def _restore_exact_prior_owned_files(
        self, handle: AdapterMutationHandle
    ) -> HarnessResult:
        prior = {str(item["path"]): item for item in handle.prior_owned_files}
        target = {str(item["path"]): item for item in handle.target_owned_files}
        restored: list[str] = []
        try:
            for raw_path in sorted(set(prior) | set(target)):
                path = Path(raw_path)
                expected = prior.get(raw_path, {"path": raw_path, "type": "missing"})
                expected_target = target.get(
                    raw_path, {"path": raw_path, "type": "missing"}
                )
                with self._owned_file_mutation_lock():
                    observed = self._observe_owned_file(path)
                    if self._observable_owned_file(
                        observed
                    ) != self._observable_owned_file(expected_target):
                        raise ValueError(
                            f"owned rollback target changed concurrently: {path}"
                        )
                    self._conditional_owned_file_transition(
                        path, expected_target, expected
                    )
                restored.append(raw_path)
        except (OSError, ValueError) as error:
            return HarnessResult(
                self.name,
                ResultState.BLOCKED,
                (),
                {},
                errors=(redact_text(str(error)),),
            )
        return HarnessResult(self.name, ResultState.READY, tuple(restored), {})

    def _reconcile_install_replaces_changed_plugins(self) -> bool:
        return self.name == "cursor"

    def _observe_reconcile_capability_keys(
        self, expected: Mapping[str, str]
    ) -> dict[str, str]:
        native_mcp = normalize_native_mcp_inventory(self._native_mcp_inventory)
        observed: dict[str, str] = {}
        for identity in expected:
            kind, _, name = identity.partition(":")
            if kind == "mcp":
                observed[identity] = "present" if name in native_mcp else "absent"
            elif kind == "executable":
                resolved = self._which(name)
                observed[identity] = (
                    str(Path(resolved).resolve()) if resolved else "absent"
                )
        return observed

    def _capture_current_owned_files(self, expected):
        return tuple(
            self._observe_owned_file(Path(str(item["path"]))) for item in expected
        )

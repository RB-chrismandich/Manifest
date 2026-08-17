"""Capability lifecycle responsibility mixin."""

from __future__ import annotations

import hashlib
import json

from manifest_agent.models import (
    AdapterMutationHandle,
    AdapterPluginState,
    DesiredState,
    HarnessReceipt,
    HarnessResult,
    ResultState,
)


class ReconcileLifecycleMixin:
    """Capability lifecycle methods grouped by one mutation responsibility."""

    def prepare_reconcile(
        self, receipt: HarnessReceipt, prior: DesiredState, desired: DesiredState
    ) -> AdapterMutationHandle:
        """Create a serializable handle before any release-changing mutation."""
        from manifest_agent.service_state import bundle_checksums

        payload = json.dumps(
            {
                "archive_sha256": desired.archive_sha256,
                "bundle_checksums": bundle_checksums(desired),
                "release_version": desired.release_version,
                "source_commit": desired.source_commit,
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        prior_inventory = self._capture_reconcile_inventory(receipt, prior)
        target_inventory = self._desired_reconcile_inventory(desired)
        prior_capabilities = self._reconcile_capability_state(prior)
        target_capabilities = self._expected_reconcile_capability_state(desired)
        prior_owned_files = self._capture_receipt_owned_files(receipt)
        target_owned_files = self._expected_reconcile_owned_files(receipt, desired)
        return AdapterMutationHandle(
            2,
            self.name,
            self.adapter_version,
            hashlib.sha256(payload).hexdigest(),
            prior_inventory,
            target_inventory,
            prior_cas=self._reconcile_cas(
                prior_inventory, prior_capabilities, prior_owned_files
            ),
            target_cas=self._reconcile_cas(
                target_inventory, target_capabilities, target_owned_files
            ),
            prior_capabilities=prior_capabilities,
            target_capabilities=target_capabilities,
            prior_owned_files=prior_owned_files,
            target_owned_files=target_owned_files,
        )

    def apply_reconcile(
        self, handle: AdapterMutationHandle, desired: DesiredState
    ) -> HarnessResult:
        """Apply only the target authorized by a prepared adapter handle."""
        from manifest_agent.adapters.base import combine_results

        self._validate_reconcile_handle(handle, desired)
        backup_error = self._reconcile_backup_error(handle)
        if backup_error is not None:
            return HarnessResult(
                self.name, ResultState.BLOCKED, (), {}, errors=(backup_error,)
            )
        prior_check = self._observe_reconcile_cas(handle, desired, prior=True)
        if prior_check is not None:
            return prior_check
        target_by_id = {item.identifier: item for item in handle.target_inventory}
        changed = tuple(
            item
            for item in handle.prior_inventory
            if target_by_id.get(item.identifier) is None
            or (
                not self._reconcile_install_replaces_changed_plugins()
                and self._reconcile_plugin_payload(target_by_id[item.identifier])
                != self._reconcile_plugin_payload(item)
            )
        )
        removed = self._remove_reconcile_plugins(changed, desired)
        if removed.state is ResultState.BLOCKED:
            return removed
        intermediate = self._observe_exact_reconcile_inventory(
            desired,
            tuple(item for item in handle.prior_inventory if item not in changed),
            handle,
        )
        if intermediate is not None:
            return combine_results(removed, intermediate)
        installed = self.install(desired)
        if installed.state not in {ResultState.READY, ResultState.DEGRADED}:
            # The removal already happened. Returning `installed` alone would
            # hide it, under-reporting the blast radius of a failed reconcile:
            # the plugins are gone but nothing downstream is told. Every other
            # exit path here combines, as does _restore_prior_release.
            return combine_results(removed, installed)
        target_check = self._observe_reconcile_cas(handle, desired, prior=False)
        if target_check is not None:
            return combine_results(removed, installed, target_check)
        return combine_results(removed, installed)

    def verify_reconcile(
        self, handle: AdapterMutationHandle, desired: DesiredState
    ) -> HarnessResult:
        """Verify the applied target through the adapter's production inventory."""
        self._validate_reconcile_handle(handle, desired)
        mismatch = self._observe_reconcile_cas(handle, desired, prior=False)
        return mismatch or self.inspect(desired)

    def rollback_reconcile(
        self, handle: AdapterMutationHandle, prior: DesiredState
    ) -> HarnessResult:
        """Compensate an applied participant using its prior immutable release."""
        from manifest_agent.adapters.base import combine_results

        invalid = self._rollback_handle_error(handle)
        if invalid is not None:
            return invalid
        target_mismatch = self._observe_reconcile_cas(handle, prior, prior=False)
        if target_mismatch is not None:
            return target_mismatch
        target_only = self._rollback_target_only(handle)
        removed = self._remove_reconcile_plugins(target_only, prior)
        if removed.state is ResultState.BLOCKED:
            return removed
        intermediate = self._observe_exact_reconcile_inventory(
            prior,
            tuple(item for item in handle.target_inventory if item not in target_only),
            handle,
        )
        if intermediate is not None:
            return combine_results(removed, intermediate)
        return self._restore_prior_release(handle, prior, removed)

    def _rollback_handle_error(
        self, handle: AdapterMutationHandle
    ) -> HarnessResult | None:
        invalid = (
            handle.schema_version != 2
            or handle.harness != self.name
            or handle.adapter_version != self.adapter_version
            or not handle.prior_cas
            or not handle.target_cas
        )
        if invalid:
            return HarnessResult(
                self.name,
                ResultState.BLOCKED,
                (),
                {},
                errors=("adapter reconciliation rollback handle is invalid",),
            )
        backup_error = self._reconcile_backup_error(handle)
        if backup_error is None:
            return None
        return HarnessResult(
            self.name, ResultState.BLOCKED, (), {}, errors=(backup_error,)
        )

    def _rollback_target_only(
        self, handle: AdapterMutationHandle
    ) -> tuple[AdapterPluginState, ...]:
        prior_ids = {item.identifier for item in handle.prior_inventory}
        prior_by_id = {item.identifier: item for item in handle.prior_inventory}
        return tuple(
            item
            for item in handle.target_inventory
            if item.identifier not in prior_ids
            or (
                not self._reconcile_install_replaces_changed_plugins()
                and self._reconcile_plugin_payload(item)
                != self._reconcile_plugin_payload(prior_by_id[item.identifier])
            )
        )

    def _restore_prior_release(
        self,
        handle: AdapterMutationHandle,
        prior: DesiredState,
        removed: HarnessResult,
    ) -> HarnessResult:
        from manifest_agent.adapters.base import combine_results

        restored_files = self._restore_exact_prior_owned_files(handle)
        combined = combine_results(removed, restored_files)
        if restored_files.state is ResultState.BLOCKED:
            return combined
        installed = self.install(prior)
        combined = combine_results(combined, installed)
        if installed.state not in {ResultState.READY, ResultState.DEGRADED}:
            return combined
        restored = self._restore_exact_prior_backups(handle, prior)
        combined = combine_results(combined, restored)
        if restored.state is ResultState.BLOCKED:
            return combined
        combined = combine_results(combined, self.inspect(prior))
        prior_mismatch = self._observe_reconcile_cas(handle, prior, prior=True)
        if prior_mismatch is not None:
            return combine_results(
                combined,
                prior_mismatch,
            )
        return combined

    def classify_reconcile_state(
        self, handle: AdapterMutationHandle, desired: DesiredState
    ) -> str:
        """Classify current native state as the exact prior, target, or other."""
        if (
            self._observed_reconcile_cas(handle, desired, prior=True)
            == handle.prior_cas
        ):
            return "prior"
        if (
            self._observed_reconcile_cas(handle, desired, prior=False)
            == handle.target_cas
        ):
            return "target"
        return "other"

    def _validate_reconcile_handle(
        self, handle: AdapterMutationHandle, desired: DesiredState
    ) -> None:
        from manifest_agent.service_state import bundle_checksums

        payload = json.dumps(
            {
                "archive_sha256": desired.archive_sha256,
                "bundle_checksums": bundle_checksums(desired),
                "release_version": desired.release_version,
                "source_commit": desired.source_commit,
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        expected_identity = hashlib.sha256(payload).hexdigest()
        if (
            handle.schema_version != 2
            or handle.harness != self.name
            or handle.adapter_version != self.adapter_version
            or handle.target_identity != expected_identity
            or handle.target_inventory != self._desired_reconcile_inventory(desired)
            or handle.target_capabilities
            != self._expected_reconcile_capability_state(desired)
            or handle.target_owned_files
            != self._expected_reconcile_owned_files_from_handle(handle, desired)
            or handle.target_cas
            != self._reconcile_cas(
                handle.target_inventory,
                handle.target_capabilities or {},
                handle.target_owned_files,
            )
        ):
            raise ValueError("adapter reconciliation handle does not match target")

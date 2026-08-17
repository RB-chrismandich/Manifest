"""Capability lifecycle responsibility mixin."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict
from pathlib import Path

from manifest_agent.codex_plugin_backup import (
    capture_owned_file_backup,
)
from manifest_agent.models import (
    AdapterMutationHandle,
    AdapterPluginState,
    DesiredState,
    HarnessReceipt,
    HarnessResult,
    ResultState,
)
from manifest_agent.ownership import owned_file_ownership


class ReconcileObserveMixin:
    """Capability lifecycle methods grouped by one mutation responsibility."""

    def _expected_reconcile_owned_files_from_handle(
        self, handle: AdapterMutationHandle, desired: DesiredState
    ) -> tuple[dict[str, object], ...]:
        return self._expected_reconcile_owned_files_from_prior(
            handle.prior_owned_files, desired
        )

    def _capture_receipt_owned_files(
        self, receipt: HarnessReceipt
    ) -> tuple[dict[str, object], ...]:
        captured: list[dict[str, object]] = []
        for entry in receipt.owned_entries:
            if not entry.target_path:
                continue
            if entry.kind == "owned-file":
                prior, installed, errors = owned_file_ownership(entry, env=self._env)
                if errors or prior is None or installed is None:
                    raise ValueError(
                        errors[0] if errors else "owned-file receipt is invalid"
                    )
                path = Path(entry.target_path)
                backup, mode, digest = capture_owned_file_backup(path, self._env)
                observed = {
                    "path": str(path),
                    "type": "file",
                    "mode": mode,
                    "digest": digest,
                    "restore": {"archive": backup.to_dict()},
                }
                if self._observable_owned_file(observed) != self._observable_owned_file(
                    installed
                ):
                    raise ValueError("receipt-owned file changed before reconciliation")
                captured.append(observed)
                continue
            path = Path(entry.target_path)
            try:
                backup, mode, digest = capture_owned_file_backup(path, self._env)
            except FileNotFoundError:
                captured.append({"path": str(path), "type": "missing"})
                continue
            except Exception as error:
                if not path.exists() and not path.is_symlink():
                    captured.append({"path": str(path), "type": "missing"})
                    continue
                raise ValueError(f"owned path is not backup-safe: {path}") from error
            row = {
                "path": str(path),
                "type": "file",
                "mode": mode,
                "digest": digest,
                "restore": {"archive": backup.to_dict()},
            }
            captured.append(row)
        return tuple(sorted(captured, key=lambda item: str(item["path"])))

    def _reconcile_cas(self, inventory, capabilities, owned_files) -> str:
        rows = [self._reconcile_plugin_payload(item) for item in inventory]
        observable_owned_files = tuple(
            {key: value for key, value in item.items() if key != "restore"}
            for item in owned_files
        )
        payload = json.dumps(
            {
                "capabilities": capabilities,
                "inventory": rows,
                "owned_files": observable_owned_files,
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        return hashlib.sha256(payload).hexdigest()

    def _reconcile_plugin_payload(self, item: AdapterPluginState) -> dict[str, object]:
        row = asdict(item)
        row.pop("rollback_data", None)
        row.pop("retirement_phase", None)
        row.pop("installed_path", None)
        return row

    def _observe_reconcile_cas(
        self, handle: AdapterMutationHandle, desired: DesiredState, *, prior: bool
    ) -> HarnessResult | None:
        try:
            observed = self._observed_reconcile_cas(handle, desired, prior=prior)
        except ValueError as error:
            return HarnessResult(
                self.name,
                ResultState.BLOCKED,
                (),
                {},
                errors=(str(error),),
            )
        expected = handle.prior_cas if prior else handle.target_cas
        if observed != expected:
            return HarnessResult(
                self.name,
                ResultState.BLOCKED,
                (),
                {},
                errors=(
                    "native state changed after reconciliation prepare"
                    if prior
                    else "native state does not match the exact prepared target",
                ),
            )
        return None

    def _observed_reconcile_cas(
        self,
        handle: AdapterMutationHandle,
        desired: DesiredState,
        *,
        prior: bool,
    ) -> str:
        observer = getattr(self, "_native_reconcile_inventory", None)
        if observer is None:
            raise ValueError("exact native reconciliation observation is unavailable")
        managed_identifiers = {
            item.identifier
            for item in (*handle.prior_inventory, *handle.target_inventory)
        }
        inventory = tuple(
            observer(
                desired,
                capture_backups=False,
                identifiers=managed_identifiers,
            )
        )
        expected_capabilities = (
            handle.prior_capabilities if prior else handle.target_capabilities
        ) or {}
        capability_keys = expected_capabilities
        capabilities = self._observe_reconcile_capability_keys(capability_keys)
        expected_files = (
            handle.prior_owned_files if prior else handle.target_owned_files
        )
        owned_files = self._capture_current_owned_files(expected_files)
        return self._reconcile_cas(inventory, capabilities, owned_files)

"""OMP native user-package lifecycle, independent of activation qualification."""

from __future__ import annotations

import shutil
from collections.abc import Callable, Mapping, Sequence
from dataclasses import replace
from pathlib import Path

from manifest_agent.adapters.base import CapabilityAdapterMixin, Detection
from manifest_agent.adapters.omp_identity import PLUGIN_KIND, receipt_entries
from manifest_agent.adapters.omp_inspection import OmpInspectionMixin
from manifest_agent.adapters.omp_inventory import OmpInventoryError, omp_native_root
from manifest_agent.adapters.omp_lifecycle import OmpLifecycleMixin
from manifest_agent.adapters.omp_source import OmpSourceMixin
from manifest_agent.models import (
    HarnessReceipt,
    HarnessResult,
    NativeInspection,
    ResultState,
)
from manifest_agent.ownership import (
    authenticate_omp_receipt,
    omp_receipt_ownership_errors,
    ownership_key_path,
)
from manifest_agent.process import CommandRunner, redact_text


class _OmpReceiptMixin:
    def bind_ownership_authority(self, key_path: Path) -> None:
        """Trust service-supplied authority, never a key carried by a receipt."""
        self._ownership_key_path = Path(key_path)

    def authenticate_provisional_receipt(
        self, receipt: HarnessReceipt
    ) -> HarnessReceipt:
        return authenticate_omp_receipt(receipt, key_path=self._ownership_key_path)

    def validate_provisional_receipt(self, receipt: HarnessReceipt) -> None:
        self._authenticated_entries(receipt)

    def migration_cleanup_receipt(self, receipt, prior):
        """Cleanup only creations, never inherited pre-migration ownership."""
        inherited = self._authenticated_entries(prior)
        entries = self._authenticated_entries(receipt)
        created = tuple(entry for key, entry in entries.items() if key not in inherited)
        cleanup = replace(
            receipt,
            plugin_ids=tuple(
                sorted(
                    entry.identifier for entry in created if entry.kind == PLUGIN_KIND
                )
            ),
            owned_entries=created,
        )
        return self.authenticate_provisional_receipt(cleanup)

    def inspection_desired_state(self, desired, result):
        """Authenticate only actual operation ownership for immediate verification."""
        if not result.owned_entries:
            return desired
        prior = self._prior_receipt(desired)
        self._authenticated_entries(prior)
        entries = self.merge_owned_entries(prior, result)
        receipt = self.authenticate_provisional_receipt(
            HarnessReceipt(
                self.name,
                self.adapter_version,
                result.native_version or "unknown",
                self.receipt_plugin_ids(result, prior),
                entries,
                result.capabilities,
                result.state is ResultState.READY,
                result.errors,
            )
        )
        return replace(
            desired,
            prior_harness_receipts=(
                *(
                    item
                    for item in desired.prior_harness_receipts
                    if item.harness != self.name
                ),
                receipt,
            ),
        )

    def _prior_receipt(self, desired):
        receipts = tuple(
            receipt
            for receipt in desired.prior_harness_receipts
            if receipt.harness == self.name
        )
        if len(receipts) > 1:
            raise OmpInventoryError("duplicate prior OMP receipts")
        return receipts[0] if receipts else None

    def _authenticated_entries(self, receipt):
        if receipt is None:
            return {}
        errors = omp_receipt_ownership_errors(
            receipt, key_path=self._ownership_key_path
        )
        if errors:
            raise OmpInventoryError("; ".join(errors))
        return receipt_entries(receipt)

    def merge_owned_entries(self, previous, result):
        entries = self._authenticated_entries(previous)
        for entry in result.owned_entries:
            if entry.kind != "omp-receipt-auth":
                entries[(entry.kind, entry.identifier)] = entry
        return tuple(entries.values())

    def receipt_plugin_ids(self, result, previous):
        return tuple(
            sorted(
                entry.identifier
                for entry in self.merge_owned_entries(previous, result)
                if entry.kind == PLUGIN_KIND
            )
        )


class _OmpShadowMixin:
    def shadow_install(self, desired, home):
        return self._shadow_operation("install", desired, home)

    def shadow_inspect(self, desired, home):
        return self._shadow_operation("inspect", desired, home)

    def _shadow_operation(self, operation, desired, home):
        """Keep shadow receipts and signing authority inside the isolated home."""
        import copy

        from manifest_agent.service_state import (
            build_receipt,
            with_prior_harness_receipts,
        )
        from manifest_agent.state import read_receipt, write_receipt_atomic

        home.mkdir(parents=True, exist_ok=True, mode=0o700)
        shadow = copy.copy(self)
        shadow._env = {
            **(self._env or {}),
            "HOME": str(home),
            "XDG_CONFIG_HOME": str(home / ".config"),
            "XDG_DATA_HOME": str(home / ".local/share"),
            "XDG_STATE_HOME": str(home / ".local/state"),
            "XDG_CACHE_HOME": str(home / ".cache"),
        }
        path = home / ".local/state/manifest/installation.json"
        shadow.bind_ownership_authority(path.parent / "ownership.key")
        previous = read_receipt(path)
        desired = with_prior_harness_receipts(desired, previous)
        result = getattr(shadow, operation)(desired)
        if operation == "install":
            receipt = build_receipt(
                desired,
                {self.name: result},
                {},
                {self.name: shadow},
                (self.name,),
                previous=previous,
            )
            write_receipt_atomic(path, receipt)
        return result


class OmpAdapter(
    _OmpReceiptMixin,
    _OmpShadowMixin,
    OmpSourceMixin,
    OmpLifecycleMixin,
    OmpInspectionMixin,
    CapabilityAdapterMixin,
):
    """Delegate registration to OMP; authorize only exact coordinator creations."""

    name = "omp"
    adapter_version = "1"
    preserves_partial_ownership = True

    def __init__(
        self,
        runner: CommandRunner | None = None,
        *,
        which: Callable[[str], str | None] = shutil.which,
        env: Mapping[str, str] | None = None,
        cwd: Path | None = None,
    ) -> None:
        self.runner = runner or CommandRunner()
        self._which = which
        self._env = dict(env) if env is not None else None
        self._cwd = (cwd or Path.cwd()).resolve(strict=True)
        self._ownership_key_path = ownership_key_path(env)

    def _native_root(self) -> Path:
        return omp_native_root(self._env)

    def detect(self) -> Detection:
        executable = self._which("omp")
        if executable is None:
            return Detection(False, None, None, "omp CLI not present")
        try:
            self._native_root()
            command, error = self._execute((executable, "--version"))
            if error is not None or command is None or command.returncode != 0:
                return Detection(
                    False, executable, None, "OMP native version probe failed"
                )
            text = command.stdout.strip()
            version = text.splitlines()[0] if text else None
            if version is None:
                return Detection(
                    False,
                    executable,
                    None,
                    "OMP native version probe returned no version",
                )
            return Detection(True, executable, redact_text(version))
        except (OSError, ValueError) as error:
            return Detection(False, executable, None, redact_text(str(error)))

    def _execute(self, argv: Sequence[str]):
        try:
            return self.runner.run(argv, env=self._env, cwd=self._cwd), None
        # constitution: exempt C-ERR -- native boundary returns redacted diagnostics.
        except Exception as error:
            return None, self._blocked(
                f"native command execution failed ({type(error).__name__}): {error}"
            )

    def _blocked(self, message: str) -> HarnessResult:
        diagnostic = redact_text(message)
        return HarnessResult(
            self.name,
            ResultState.BLOCKED,
            (),
            {},
            errors=(diagnostic,),
            native_inspection=NativeInspection(
                self.name, "user", None, inventory_errors=(diagnostic,)
            ),
        )

    def prepare_reconcile(self, receipt, prior, desired):
        """Reject unsafe durable compensation BEFORE any native mutation.

        Native OMP cannot re-register a retained cache without force-copying
        over it. Ordinary signed package reconcile is supported; cross-harness
        atomic compensation cannot preserve that exact cache.
        """
        self._authenticated_entries(receipt)
        self._preflight(desired, receipt)
        raise OmpInventoryError(
            "OMP durable cross-harness transaction is unsupported: native rollback "
            "would overwrite retained caches; no mutation performed"
        )

    def apply_reconcile(self, handle, desired):
        raise OmpInventoryError("OMP has no authorized durable transaction handle")

    def verify_reconcile(self, handle, desired):
        raise OmpInventoryError("OMP has no authorized durable transaction handle")

    def rollback_reconcile(self, handle, prior):
        raise OmpInventoryError("OMP has no authorized durable transaction handle")

    def classify_reconcile_state(self, handle, desired):
        raise OmpInventoryError("OMP has no authorized durable transaction handle")

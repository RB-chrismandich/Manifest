"""Capability lifecycle responsibility mixin."""

from __future__ import annotations

import fcntl
import os
from collections.abc import Sequence
from contextlib import contextmanager
from pathlib import Path

from manifest_agent.adapters.capability_inventory import (
    NativeMcpInventory,
    _inventory_mapping,
)
from manifest_agent.capabilities import (
    CapabilityConflict,
    CapabilityPlan,
    apply_capability_plan,
    remove_owned_capabilities,
    resolve_capabilities,
)
from manifest_agent.capability_cursor import cursor_mcp_path
from manifest_agent.contracts import ADDON_BUNDLES, DOMAIN_BUNDLES
from manifest_agent.models import (
    AdapterMutationHandle,
    DesiredState,
    HarnessReceipt,
    HarnessResult,
    OwnedEntry,
    ResultState,
)
from manifest_agent.ownership import capability_ownership_errors, owned_file_ownership
from manifest_agent.paths import xdg_paths
from manifest_agent.process import redact_text


def expected_uninstall_plugin_ids(plugin_ids: Sequence[str]) -> tuple[str, ...]:
    """Return the inventory an uninstall receipt must carry to be complete.

    Every domain bundle is mandatory, so a receipt missing one is incomplete
    and must not authorise removal. Addon bundles are opt-in, so only those the
    receipt actually records are expected. Passing the receipt's own IDs as the
    expected set instead would compare a value against itself and never fire.

    Adapters record plugin IDs either bare (``manifest-docs``) or
    marketplace-qualified (``manifest-docs@manifest``); the expected set is
    rebuilt in whichever form the receipt already uses so the comparison stays
    a completeness check rather than a formatting check.
    """
    suffixes = {
        identifier.partition("@")[2] for identifier in plugin_ids if "@" in identifier
    }
    suffix = f"@{suffixes.pop()}" if len(suffixes) == 1 else ""
    bundles = {identifier.partition("@")[0] for identifier in plugin_ids}
    present_addons = tuple(name for name in ADDON_BUNDLES if name in bundles)
    return tuple(f"{name}{suffix}" for name in (*DOMAIN_BUNDLES, *present_addons))


class ReceiptCapabilityMixin:
    """Capability lifecycle methods grouped by one mutation responsibility."""

    def restore_receipt_owned_file(self, entry: OwnedEntry) -> HarnessResult:
        """Restore original receipt-owned bytes under an exact current-content CAS."""
        prior, installed, errors = owned_file_ownership(entry, env=self._env)
        if errors or prior is None or installed is None or entry.target_path is None:
            return HarnessResult(
                self.name,
                ResultState.BLOCKED,
                (),
                {},
                errors=errors or ("receipt owned-file entry is invalid",),
            )
        handle = AdapterMutationHandle(
            2,
            self.name,
            self.adapter_version,
            "receipt-uninstall",
            (),
            (),
            prior_owned_files=(prior,),
            target_owned_files=(installed,),
        )
        return self._restore_exact_prior_owned_files(handle)

    def validate_receipt_owned_file(self, entry: OwnedEntry) -> HarnessResult:
        """Authenticate and compare an owned file without mutating it."""
        _prior, installed, errors = owned_file_ownership(entry, env=self._env)
        if errors or installed is None or entry.target_path is None:
            return HarnessResult(
                self.name,
                ResultState.BLOCKED,
                (),
                {},
                errors=errors or ("receipt owned-file entry is invalid",),
            )
        try:
            observed = self._observe_owned_file(Path(entry.target_path))
        except ValueError as error:
            return HarnessResult(
                self.name,
                ResultState.BLOCKED,
                (),
                {},
                errors=(redact_text(str(error)),),
            )
        if self._observable_owned_file(observed) != self._observable_owned_file(
            installed
        ):
            return HarnessResult(
                self.name,
                ResultState.BLOCKED,
                (),
                {},
                errors=("receipt-owned file changed concurrently",),
            )
        return HarnessResult(self.name, ResultState.READY, (), {})

    @contextmanager
    def _owned_file_mutation_lock(self):
        lock_path = xdg_paths(self._env).state / f"{self.name}-owned-files.lock"
        lock_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        descriptor = os.open(
            lock_path,
            os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0),
            0o600,
        )
        try:
            os.fchmod(descriptor, 0o600)
            fcntl.flock(descriptor, fcntl.LOCK_EX)
            yield
        finally:
            fcntl.flock(descriptor, fcntl.LOCK_UN)
            os.close(descriptor)

    @contextmanager
    def _native_mutation_lock(self):
        lock_path = xdg_paths(self._env).state / f"{self.name}-native-reconcile.lock"
        lock_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        descriptor = os.open(
            lock_path,
            os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0),
            0o600,
        )
        try:
            os.fchmod(descriptor, 0o600)
            fcntl.flock(descriptor, fcntl.LOCK_EX)
            yield
        finally:
            fcntl.flock(descriptor, fcntl.LOCK_UN)
            os.close(descriptor)

    def _native_mutation_boundary(self, identifier: str) -> None:
        """Test seam immediately before the native tree quarantine rename."""
        del identifier

    def install_capabilities(self, desired: DesiredState) -> HarnessResult:
        """Resolve and apply the desired union during normal adapter install."""
        try:
            plan = resolve_capabilities(
                desired.all_contracts, selected_optional=desired.selected_optional
            )
        except CapabilityConflict as error:
            return HarnessResult(
                self.name,
                ResultState.BLOCKED,
                (),
                {},
                errors=(redact_text(str(error)),),
            )
        result = self.apply_capabilities(plan)
        self._remember_capabilities(plan, result)
        return result

    def apply_capabilities(self, plan: CapabilityPlan) -> HarnessResult:
        """Apply MCP and executable capabilities without adapter duplication."""
        return apply_capability_plan(
            self.name,
            plan,
            runner=self.runner,
            which=self._which,
            env=self._env,
            native_mcp_inventory=self._native_mcp_inventory_for_apply(),
        )

    def _native_mcp_inventory_for_apply(self) -> NativeMcpInventory | None:
        """Return injected or remembered native state for capability application."""
        return self._native_mcp_inventory

    def remove_capabilities(self, receipt: HarnessReceipt) -> HarnessResult:
        """Remove only shared capabilities proven owned by the receipt."""
        return remove_owned_capabilities(
            self.name, receipt, runner=self.runner, env=self._env
        )

    def validate_uninstall_receipt(
        self,
        receipt: HarnessReceipt,
        plugin_ids: Sequence[str],
        expected_plugin_ids: Sequence[str],
        *,
        identity_errors: Sequence[str] = (),
        marketplace_identifier: str | None = None,
    ) -> HarnessResult | None:
        """Reject incomplete or forged ownership before any uninstall mutation."""
        errors: list[str] = []
        if receipt.harness != self.name:
            errors.append(
                f"receipt harness {receipt.harness!r} does not match {self.name!r}"
            )
        if receipt.adapter_version != self.adapter_version:
            errors.append("receipt adapter version does not match this adapter")
        if not receipt.native_version:
            errors.append("receipt native version must be non-empty")
        if not receipt.verified or receipt.errors:
            errors.append("receipt must represent a verified installation")
        errors.extend(identity_errors)
        if len(plugin_ids) != len(expected_plugin_ids) or set(plugin_ids) != set(
            expected_plugin_ids
        ):
            errors.append(
                "receipt must contain the complete canonical plugin inventory"
            )
        if marketplace_identifier is not None:
            marketplace_entries = tuple(
                entry for entry in receipt.owned_entries if entry.kind == "marketplace"
            )
            if len(marketplace_entries) > 1 or any(
                entry.identifier != marketplace_identifier or not entry.ownership_marker
                for entry in marketplace_entries
            ):
                errors.append("receipt contains invalid marketplace ownership")
        errors.extend(
            capability_ownership_errors(
                receipt,
                env=self._env,
                expected_cursor_path=(
                    cursor_mcp_path(self._env) if self.name == "cursor" else None
                ),
            )
        )
        if not errors:
            return None
        return HarnessResult(
            self.name,
            ResultState.BLOCKED,
            (),
            {},
            errors=tuple(redact_text(error) for error in errors),
        )

    def _remember_capabilities(
        self, plan: CapabilityPlan, result: HarnessResult
    ) -> None:
        inventory = _inventory_mapping(self._native_mcp_inventory)
        for name in plan.selected_mcp:
            if result.capabilities.get(f"mcp:{name}") in {
                "installed-by-manifest",
                "verified",
            }:
                inventory[name] = plan.mcp_definitions[name]
        self._native_mcp_inventory = inventory

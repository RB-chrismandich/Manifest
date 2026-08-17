"""Normal adapter lifecycle seam for resolved shared capabilities."""

from __future__ import annotations

from collections.abc import Callable, Mapping

from manifest_agent.adapters.capability_inventory import (
    NativeMcpInventory as NativeMcpInventory,
)
from manifest_agent.adapters.capability_inventory import (
    _inventory_mapping as _inventory_mapping,
)
from manifest_agent.adapters.capability_inventory import (
    normalize_native_mcp_inventory as normalize_native_mcp_inventory,
)
from manifest_agent.adapters.capability_native_remove import NativeRemoveMixin
from manifest_agent.adapters.capability_owned_files import OwnedFileMixin
from manifest_agent.adapters.capability_receipt import ReceiptCapabilityMixin
from manifest_agent.adapters.capability_reconcile_lifecycle import (
    ReconcileLifecycleMixin,
)
from manifest_agent.adapters.capability_reconcile_observe import ReconcileObserveMixin
from manifest_agent.adapters.capability_reconcile_remove import ReconcileRemoveMixin
from manifest_agent.adapters.capability_reconcile_restore import ReconcileRestoreMixin
from manifest_agent.adapters.capability_reconcile_state import ReconcileStateMixin
from manifest_agent.capabilities import CapabilityPlan as CapabilityPlan
from manifest_agent.capabilities import resolve_capabilities as resolve_capabilities
from manifest_agent.process import CommandRunner


class CapabilityAdapterMixin(
    ReconcileLifecycleMixin,
    ReconcileStateMixin,
    ReconcileObserveMixin,
    ReconcileRestoreMixin,
    ReconcileRemoveMixin,
    NativeRemoveMixin,
    OwnedFileMixin,
    ReceiptCapabilityMixin,
):
    """Apply and remove capabilities through each concrete adapter lifecycle."""

    name: str
    adapter_version: str
    runner: CommandRunner
    _which: Callable[[str], str | None]
    _env: Mapping[str, str] | None
    _native_mcp_inventory: NativeMcpInventory = ()


__all__ = [
    "CapabilityAdapterMixin",
    "CapabilityPlan",
    "NativeMcpInventory",
    "normalize_native_mcp_inventory",
    "resolve_capabilities",
]

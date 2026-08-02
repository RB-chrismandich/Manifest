"""Normal adapter lifecycle seam for resolved shared capabilities."""

from __future__ import annotations

from collections.abc import Callable, Collection, Mapping

from manifest_agent.capabilities import (
    CapabilityConflict,
    CapabilityPlan,
    McpDefinition,
    apply_capability_plan,
    remove_owned_capabilities,
    resolve_capabilities,
)
from manifest_agent.models import (
    DesiredState,
    HarnessReceipt,
    HarnessResult,
    ResultState,
)
from manifest_agent.process import CommandRunner, redact_text

NativeMcpInventory = Collection[str] | Mapping[str, McpDefinition]


class CapabilityAdapterMixin:
    """Apply and remove capabilities through every concrete adapter lifecycle."""

    name: str
    runner: CommandRunner
    _which: Callable[[str], str | None]
    _env: Mapping[str, str] | None
    _native_mcp_inventory: NativeMcpInventory = ()

    def install_capabilities(self, desired: DesiredState) -> HarnessResult:
        """Resolve and apply the desired union during normal adapter install."""
        try:
            plan = resolve_capabilities(
                desired.contracts, selected_optional=desired.selected_optional
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
            native_mcp_inventory=self._native_mcp_inventory,
        )

    def remove_capabilities(self, receipt: HarnessReceipt) -> HarnessResult:
        """Remove only shared capabilities proven owned by the receipt."""
        return remove_owned_capabilities(
            self.name, receipt, runner=self.runner, env=self._env
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


def normalize_native_mcp_inventory(
    inventory: NativeMcpInventory,
) -> tuple[str, ...] | Mapping[str, McpDefinition]:
    """Freeze injected native inventory without discarding transport identity."""
    if isinstance(inventory, Mapping):
        if any(
            not isinstance(name, str) or not isinstance(value, McpDefinition)
            for name, value in inventory.items()
        ):
            raise TypeError("native MCP inventory mappings require MCP definitions")
        return dict(inventory)
    if isinstance(inventory, str) or any(
        not isinstance(name, str) for name in inventory
    ):
        raise TypeError("native MCP inventory must contain string identities")
    return tuple(inventory)


def _inventory_mapping(inventory: NativeMcpInventory) -> dict[str, McpDefinition]:
    if isinstance(inventory, Mapping):
        return dict(inventory)
    return {
        name: McpDefinition(name, "native-existing", discovery_prefixes=(name,))
        for name in inventory
    }


__all__ = [
    "CapabilityAdapterMixin",
    "CapabilityPlan",
    "NativeMcpInventory",
    "normalize_native_mcp_inventory",
]

"""Native MCP inventory normalization shared by adapter lifecycle mixins."""

from collections.abc import Collection, Mapping

from manifest_agent.capabilities import McpDefinition

NativeMcpInventory = Collection[str] | Mapping[str, McpDefinition]


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

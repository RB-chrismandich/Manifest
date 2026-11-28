"""Match a harness's live MCP registrations against bundle declarations."""

from __future__ import annotations

from collections.abc import Iterable, Mapping

from manifest_agent.capabilities import (
    CapabilityConflict,
    McpDefinition,
    load_mcp_catalog,
    merge_mcp_definitions,
)
from manifest_agent.models import BundleContract, CapabilityTier


def declared_mcp(contract: BundleContract) -> tuple[str, ...]:
    """Every MCP identity this bundle declares, across all tiers."""
    return tuple(
        dict.fromkeys(
            name for tier in CapabilityTier for name in contract.capabilities.mcp[tier]
        )
    )


def matching_mcp_names(served_mcp: Mapping[str, McpDefinition]) -> frozenset[str]:
    """Native registrations whose transport matches the reviewed catalog exactly."""
    catalog = load_mcp_catalog()
    matches: set[str] = set()
    for name, observed in served_mcp.items():
        expected = catalog.get(name)
        if expected is None:
            continue
        try:
            merge_mcp_definitions(expected, observed)
        except CapabilityConflict:
            continue
        matches.add(name)
    return frozenset(matches)


def served_declared_mcp(
    contracts: Iterable[BundleContract], served_mcp: Mapping[str, McpDefinition]
) -> dict[str, tuple[str, ...]]:
    """Per bundle, the declared MCP identities the harness verifiably serves."""
    matching = matching_mcp_names(served_mcp)
    served: dict[str, tuple[str, ...]] = {}
    for contract in contracts:
        names = tuple(name for name in declared_mcp(contract) if name in matching)
        if names:
            served[contract.name] = names
    return served


__all__ = ["declared_mcp", "matching_mcp_names", "served_declared_mcp"]

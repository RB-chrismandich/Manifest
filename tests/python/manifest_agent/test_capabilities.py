"""Capability-union and executable acquisition tests."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from manifest_agent.capabilities import (
    CapabilityConflict,
    McpDefinition,
    load_executable_catalog,
    load_mcp_catalog,
    merge_mcp_definitions,
    resolve_capabilities,
)
from manifest_agent.contracts import load_domain_contracts
from manifest_agent.models import (
    BundleContract,
    CapabilityTier,
)


@pytest.fixture
def contracts() -> tuple[BundleContract, ...]:
    repo_root = Path(__file__).parents[3]
    return load_domain_contracts(repo_root / "plugins")


def test_repeated_default_mcp_is_registered_once(contracts) -> None:
    plan = resolve_capabilities(contracts, selected_optional=set())

    assert plan.default_mcp == ("context7",)
    assert plan.selected_mcp == ("context7",)


def test_optional_mcp_is_not_inferred(contracts) -> None:
    plan = resolve_capabilities(contracts, selected_optional=set())

    assert plan.optional_mcp == ("atlassian", "github", "linear", "sentry", "stitch")
    assert "github" not in plan.selected_mcp
    assert "stitch" not in plan.selected_mcp


def test_only_explicit_optional_capabilities_are_selected(contracts) -> None:
    plan = resolve_capabilities(
        contracts, selected_optional={"github", "executable:semgrep"}
    )

    assert plan.selected_mcp == ("context7", "github")
    assert "semgrep" in plan.selected_executables
    assert "stitch" not in plan.selected_mcp


def test_unknown_optional_selection_fails_closed(contracts) -> None:
    with pytest.raises(CapabilityConflict, match="unknown optional capability"):
        resolve_capabilities(contracts, selected_optional={"invented"})


def test_conflicting_tier_declarations_block(contracts) -> None:
    workspace = next(item for item in contracts if item.name == "manifest-workspace")
    changed_mcp = dict(workspace.capabilities.mcp)
    changed_mcp[CapabilityTier.REQUIRED] = ("context7",)
    changed = replace(
        workspace,
        capabilities=replace(workspace.capabilities, mcp=changed_mcp),
    )

    with pytest.raises(CapabilityConflict, match="context7"):
        resolve_capabilities(
            tuple(changed if item is workspace else item for item in contracts),
            selected_optional=set(),
        )


def test_conflicting_transport_definitions_block() -> None:
    http = McpDefinition(
        name="context7",
        transport="http",
        url="https://mcp.context7.com/mcp/oauth",
    )
    stdio = McpDefinition(name="context7", transport="stdio", command=("context7",))

    with pytest.raises(CapabilityConflict, match="context7"):
        merge_mcp_definitions(http, stdio)


def test_catalogs_are_exact_secret_free_coordinator_data() -> None:
    mcp_catalog = load_mcp_catalog()
    executable_catalog = load_executable_catalog()

    assert mcp_catalog["context7"] == McpDefinition(
        name="context7",
        transport="http",
        url="https://mcp.context7.com/mcp/oauth",
    )
    assert mcp_catalog["stitch"].transport == "native-existing"
    assert mcp_catalog["stitch"].discovery_prefixes == ("stitch", "mcp_stitch")
    assert set(mcp_catalog) == {
        "atlassian",
        "context7",
        "github",
        "linear",
        "sentry",
        "stitch",
    }
    assert executable_catalog == {}

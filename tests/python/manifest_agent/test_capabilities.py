"""Capability-union and executable acquisition tests."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from manifest_agent.capabilities import (
    CapabilityConflict,
    McpDefinition,
    apply_capability_plan,
    load_executable_catalog,
    load_mcp_catalog,
    merge_mcp_definitions,
    remove_owned_capabilities,
    resolve_capabilities,
)
from manifest_agent.contracts import load_domain_contracts
from manifest_agent.models import (
    BundleContract,
    CapabilityTier,
    CommandResult,
    HarnessReceipt,
    OwnedEntry,
    ResultState,
)
from manifest_agent.ownership import owned_capability_entry


class ExecutableRunner:
    def __init__(
        self, *, install_succeeds: bool = True, version: str = "0.9.31"
    ) -> None:
        self.calls: list[tuple[str, ...]] = []
        self.installed = False
        self.install_succeeds = install_succeeds
        self.version = version

    def run(self, argv, *, env=None):
        del env
        command = tuple(argv)
        self.calls.append(command)
        if command == ("uv", "tool", "install", "graphifyy==0.9.31"):
            self.installed = self.install_succeeds
            if self.install_succeeds:
                self.version = "0.9.31"
            return CommandResult(command, 0 if self.install_succeeds else 1, "", "")
        if command == ("graphify", "--version"):
            return CommandResult(command, 0, f"graphify {self.version}\n", "")
        if command == ("uv", "tool", "uninstall", "graphifyy"):
            return CommandResult(command, 0, "", "")
        raise AssertionError(f"unexpected command: {command}")


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
    assert executable_catalog["graphify"].as_dict() == {
        "manager": "uv-tool",
        "distribution": "graphifyy",
        "version": "0.9.31",
        "executable": "graphify",
    }
    assert not {"bash", "git", "node", "python3"} & set(executable_catalog)


def test_missing_default_graphify_uses_one_pinned_user_scope_recipe(contracts) -> None:
    plan = resolve_capabilities(contracts, selected_optional=set())
    runner = ExecutableRunner()

    def which(name: str) -> str | None:
        if name in {"bash", "git", "node", "python3", "uv"}:
            return name
        if name == "graphify" and runner.installed:
            return name
        return None

    result = apply_capability_plan(
        "claude",
        plan,
        runner=runner,
        which=which,
        configure_mcp=False,
    )

    assert result.state is ResultState.READY
    assert runner.calls == [
        ("uv", "tool", "install", "graphifyy==0.9.31"),
        ("graphify", "--version"),
    ]
    assert result.capabilities["executable:graphify"] == "installed-by-manifest"


def test_matching_preexisting_graphify_is_preserved(contracts) -> None:
    plan = resolve_capabilities(contracts, selected_optional=set())
    runner = ExecutableRunner()

    result = apply_capability_plan(
        "claude",
        plan,
        runner=runner,
        which=lambda name: name,
        configure_mcp=False,
    )

    assert result.state is ResultState.READY
    assert runner.calls == [("graphify", "--version")]
    assert result.capabilities["executable:graphify"] == "verified"


def test_mismatched_preexisting_graphify_is_reconciled_to_exact_pin(
    contracts,
) -> None:
    plan = resolve_capabilities(contracts, selected_optional=set())
    runner = ExecutableRunner(version="0.9.30")

    result = apply_capability_plan(
        "claude",
        plan,
        runner=runner,
        which=lambda name: name,
        configure_mcp=False,
    )

    assert result.state is ResultState.READY
    assert runner.calls == [
        ("graphify", "--version"),
        ("uv", "tool", "install", "graphifyy==0.9.31"),
        ("graphify", "--version"),
    ]
    assert result.capabilities["executable:graphify"] == "installed-by-manifest"
    assert [(entry.kind, entry.identifier) for entry in result.owned_entries] == [
        ("executable", "graphify")
    ]


def test_graphify_uninstall_requires_receipt_ownership() -> None:
    runner = ExecutableRunner()
    unowned = HarnessReceipt("claude", "1", "1", (), (), {}, True)
    forged = replace(
        unowned,
        owned_entries=(OwnedEntry("executable", "graphify", "manifest", None, None),),
    )
    owned = replace(
        unowned,
        owned_entries=(owned_capability_entry("executable", "graphify"),),
        capabilities={"executable:graphify": "installed-by-manifest"},
    )

    first = remove_owned_capabilities("claude", unowned, runner=runner)
    second = remove_owned_capabilities("claude", forged, runner=runner)
    third = remove_owned_capabilities("claude", owned, runner=runner)

    assert first.state is ResultState.READY
    assert second.state is ResultState.BLOCKED
    assert third.state is ResultState.READY
    assert runner.calls == [("uv", "tool", "uninstall", "graphifyy")]

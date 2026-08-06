"""Graphify is retired from current release surfaces and user installs stay safe."""

from __future__ import annotations

import json
from pathlib import Path

from manifest_agent.capabilities import remove_owned_capabilities
from manifest_agent.contracts import DOMAIN_BUNDLES, load_domain_contracts
from manifest_agent.models import CommandResult, HarnessReceipt, OwnedEntry, ResultState
from manifest_agent.ownership import owned_capability_entry


class RecordingRunner:
    def __init__(self) -> None:
        self.calls: list[tuple[str, ...]] = []

    def run(self, argv, *, env=None) -> CommandResult:
        del env
        command = tuple(argv)
        self.calls.append(command)
        return CommandResult(command, 0, "", "")


def test_graphify_is_absent_from_current_bundle_and_marketplace_surfaces() -> None:
    root = Path(__file__).parents[3]
    marketplace = json.loads(
        (root / ".claude-plugin/marketplace.json").read_text(encoding="utf-8")
    )

    assert len(DOMAIN_BUNDLES) == 8
    assert "manifest-graphify" not in DOMAIN_BUNDLES
    assert not (root / "plugins/manifest-graphify").exists()
    assert not (root / "configs/cursor/rules/graphify.mdc").exists()
    assert "manifest-graphify" not in {item["name"] for item in marketplace["plugins"]}
    assert (
        tuple(contract.name for contract in load_domain_contracts(root / "plugins"))
        == DOMAIN_BUNDLES
    )


def test_receipt_proven_legacy_graphify_is_removed_once(tmp_path: Path) -> None:
    runner = RecordingRunner()
    env = {"HOME": str(tmp_path)}
    entry = owned_capability_entry("executable", "graphify", env=env)
    receipt = HarnessReceipt(
        "claude",
        "1",
        "1",
        (),
        (entry,),
        {"executable:graphify": "installed-by-manifest"},
        True,
    )

    result = remove_owned_capabilities("claude", receipt, runner=runner, env=env)

    assert result.state is ResultState.READY
    assert runner.calls == [("uv", "tool", "uninstall", "graphifyy")]


def test_unproven_legacy_graphify_is_preserved(tmp_path: Path) -> None:
    runner = RecordingRunner()
    receipt = HarnessReceipt(
        "claude",
        "1",
        "1",
        (),
        (OwnedEntry("executable", "graphify", "manifest", None, None),),
        {"executable:graphify": "installed-by-manifest"},
        True,
    )

    result = remove_owned_capabilities(
        "claude", receipt, runner=runner, env={"HOME": str(tmp_path)}
    )

    assert result.state is ResultState.BLOCKED
    assert runner.calls == []

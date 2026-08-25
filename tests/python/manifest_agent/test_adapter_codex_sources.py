"""Codex Git-source and isolated native lifecycle tests."""

from __future__ import annotations

import os
import shutil
from dataclasses import replace
from pathlib import Path

import pytest

from manifest_agent.adapters.codex import CodexAdapter
from manifest_agent.capabilities import load_mcp_catalog
from manifest_agent.contracts import DOMAIN_BUNDLES, Capabilities, load_domain_contracts
from manifest_agent.models import (
    CapabilityTier,
    DesiredState,
    HarnessReceipt,
    MarketplaceSource,
    MarketplaceSourceKind,
    OwnedEntry,
    ResultState,
)
from manifest_agent.process import CommandRunner
from tests.python.manifest_agent._codex_adapter_test_support import (
    QueueRunner,
    command,
    installed_json,
    marketplace_add_json,
    marketplace_json,
    plugin_add_json,
)
from tests.python.manifest_agent._codex_adapter_test_support import (
    desired as desired_fixture,
)

desired = desired_fixture


def test_codex_published_release_pins_git_marketplace_ref(
    desired: DesiredState,
) -> None:
    git_root = desired.release_root / "codex-marketplace"
    published = replace(
        desired,
        source="https://example.invalid/releases/manifest-release.json",
        marketplace_source=MarketplaceSource(
            MarketplaceSourceKind.GIT,
            "https://example.invalid/Manifest.git",
            desired.source_commit,
        ),
    )
    marketplace = command(
        stdout=marketplace_json(
            published.marketplace_source.source, git_root, source_type="git"
        )
    )
    runner = QueueRunner(
        [
            command(stdout=marketplace_add_json(git_root)),
            marketplace,
            command(stdout=published.source_commit),
            command(stdout='{"installed": []}'),
            *[
                command(stdout=plugin_add_json(published, name))
                for name in DOMAIN_BUNDLES
            ],
            marketplace,
            command(stdout=published.source_commit),
            command(stdout=installed_json(published)),
        ]
    )

    result = CodexAdapter(
        runner=runner,
        which=lambda name: name,
        native_mcp_inventory={"context7": load_mcp_catalog()["context7"]},
    ).install(published)

    assert result.state is ResultState.READY
    assert runner.log[0] == [
        "codex",
        "plugin",
        "marketplace",
        "add",
        published.marketplace_source.source,
        "--ref",
        published.source_commit,
        "--json",
    ]
    assert ["git", "-C", str(git_root), "rev-parse", "HEAD"] in runner.log


def test_codex_marketplace_ref_collision_blocks_before_plugin_install(
    desired: DesiredState,
) -> None:
    git_root = desired.release_root / "codex-marketplace"
    published = replace(
        desired,
        marketplace_source=MarketplaceSource(
            MarketplaceSourceKind.GIT,
            "https://example.invalid/Manifest.git",
            desired.source_commit,
        ),
    )
    runner = QueueRunner(
        [
            command(stdout=marketplace_add_json(git_root, already_added=True)),
            command(
                stdout=marketplace_json(
                    published.marketplace_source.source,
                    git_root,
                    source_type="git",
                )
            ),
            command(stdout="b" * 40),
        ]
    )

    result = CodexAdapter(runner=runner, which=lambda name: name).install(published)

    assert result.state is ResultState.BLOCKED
    assert "marketplace ref mismatch" in " ".join(result.errors)
    assert not any(row[1:3] == ["plugin", "add"] for row in runner.log)


def _native_codex_desired_state(repository: Path) -> DesiredState:
    return DesiredState(
        release_version="0.2.0",
        source_commit="a" * 40,
        source=str(repository),
        marketplace_source=MarketplaceSource(
            MarketplaceSourceKind.LOCAL, str(repository), None
        ),
        release_root=repository,
        repository_url="https://example.invalid/Manifest",
        source_dirty=True,
        archive_sha256="b" * 64,
        contracts=tuple(
            replace(
                contract,
                capabilities=Capabilities(
                    dict.fromkeys(CapabilityTier, ()),
                    dict.fromkeys(CapabilityTier, ()),
                ),
            )
            for contract in load_domain_contracts(repository / "plugins")
        ),
        selected_optional=frozenset(),
        requested_harnesses=("codex",),
    )


@pytest.mark.native
def test_native_codex_adapter_lifecycle_uses_an_isolated_home(tmp_path: Path) -> None:
    if shutil.which("codex") is None:
        pytest.skip("codex CLI not present")
    isolated_home = tmp_path / "home"
    (isolated_home / ".codex").mkdir(parents=True)
    env = {
        "HOME": str(isolated_home),
        "CODEX_HOME": str(isolated_home / ".codex"),
        "PATH": os.environ["PATH"],
    }
    repository = Path(__file__).parents[3]
    desired_state = _native_codex_desired_state(repository)
    adapter = CodexAdapter(runner=CommandRunner(), env=env)

    result = adapter.install(desired_state)
    receipt = HarnessReceipt(
        harness="codex",
        adapter_version=adapter.adapter_version,
        native_version="native-smoke",
        plugin_ids=result.installed_plugin_ids,
        owned_entries=(OwnedEntry("marketplace", "manifest", "native-smoke"),),
        capabilities=result.capabilities,
        verified=result.state is not ResultState.BLOCKED,
    )
    removed = adapter.uninstall(receipt)

    assert len(result.installed_plugin_ids) == len(DOMAIN_BUNDLES)
    assert result.state in {
        ResultState.READY,
        ResultState.DEGRADED,
        ResultState.BLOCKED,
    }
    if result.state is ResultState.BLOCKED:
        assert result.errors
    # The receipt above is hand-built, so it carries no `codex-catalog` ownership
    # entry; only a real install writes one. Uninstall must therefore refuse it
    # in every case, and say why. This branch went unexercised while directory-
    # valued components could never be evidenced and install was permanently
    # BLOCKED — see tests/python/manifest_agent/test_component_presence.py. The
    # authenticated uninstall path is covered by test_codex_uninstall.py.
    assert removed.state is ResultState.BLOCKED
    assert any("ownership proof" in error for error in removed.errors)

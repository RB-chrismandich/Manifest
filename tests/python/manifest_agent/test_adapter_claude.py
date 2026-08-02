"""Claude Code marketplace adapter tests."""

from __future__ import annotations

import json
import os
import shutil
from collections.abc import Mapping, Sequence
from dataclasses import replace
from pathlib import Path

import pytest

from manifest_agent.adapters.claude import ClaudeAdapter
from manifest_agent.capabilities import load_mcp_catalog
from manifest_agent.contracts import (
    DOMAIN_BUNDLES,
    Capabilities,
    CompatibilityStatus,
    Components,
    Provenance,
    load_domain_contracts,
)
from manifest_agent.models import (
    BundleContract,
    CapabilityTier,
    CommandResult,
    DesiredState,
    HarnessReceipt,
    MarketplaceSource,
    MarketplaceSourceKind,
    OwnedEntry,
    ResultState,
)
from manifest_agent.process import CommandRunner


class QueueRunner(CommandRunner):
    def __init__(self, results: Sequence[CommandResult]) -> None:
        self.results = list(results)
        self.log: list[list[str]] = []

    def run(
        self,
        argv: Sequence[str],
        *,
        env: Mapping[str, str] | None = None,
    ) -> CommandResult:
        del env
        self.log.append(list(argv))
        result = self.results.pop(0)
        return CommandResult(
            tuple(argv), result.returncode, result.stdout, result.stderr
        )


def command(
    *, returncode: int = 0, stdout: str = "", stderr: str = ""
) -> CommandResult:
    return CommandResult(("fixture",), returncode, stdout, stderr)


@pytest.fixture
def desired(tmp_path: Path) -> DesiredState:
    contracts = []
    for name in DOMAIN_BUNDLES:
        skill = tmp_path / "plugins" / name / "skills" / "help" / "SKILL.md"
        skill.parent.mkdir(parents=True)
        skill.write_text("# Help\n", encoding="utf-8")
        contracts.append(
            BundleContract(
                name,
                "0.2.0",
                "fixture",
                "fixture",
                Components("skills", ("*/SKILL.md",), (), (), (), ()),
                Capabilities(
                    {
                        CapabilityTier.REQUIRED: (),
                        CapabilityTier.DEFAULT: ("context7",)
                        if name == "manifest-workspace"
                        else (),
                        CapabilityTier.OPTIONAL: (),
                    },
                    {
                        CapabilityTier.REQUIRED: ("git",),
                        CapabilityTier.DEFAULT: (),
                        CapabilityTier.OPTIONAL: (),
                    },
                ),
                {
                    "claude": CompatibilityStatus("native"),
                    "codex": CompatibilityStatus("native"),
                },
                Provenance("https://example.invalid", "MIT", "LICENSE", "test"),
            )
        )
    return DesiredState(
        release_version="0.2.0",
        source_commit="a" * 40,
        source=str(tmp_path),
        marketplace_source=MarketplaceSource(
            MarketplaceSourceKind.LOCAL, str(tmp_path), None
        ),
        release_root=tmp_path,
        repository_url="https://example.invalid/Manifest",
        source_dirty=False,
        archive_sha256="b" * 64,
        contracts=tuple(contracts),
        selected_optional=frozenset(),
        requested_harnesses=("claude",),
    )


def marketplace_json(source: Path | str) -> str:
    return json.dumps(
        [{"name": "manifest", "source": "directory", "path": str(source)}]
    )


def installed_json(
    desired: DesiredState, version: str = "0.2.0", *, extra: bool = False
) -> str:
    rows = [
        {
            "id": f"{name}@manifest",
            "version": version,
            "scope": "user",
            "enabled": True,
            "installPath": str(desired.bundle_path(name)),
            "mcpServers": {"context7": {}} if name == "manifest-workspace" else {},
        }
        for name in DOMAIN_BUNDLES
    ]
    if extra:
        rows.append(
            {
                "id": "adversarial-design-loop@manifest",
                "version": "0.1.0",
                "scope": "user",
                "enabled": True,
            }
        )
    return json.dumps(rows)


def test_detection_reports_absent_cli_explicitly() -> None:
    adapter = ClaudeAdapter(which=lambda _name: None)

    detection = adapter.detect()

    assert detection.present is False
    assert detection.executable is None
    assert detection.reason == "claude CLI not present"


def test_claude_installs_marketplace_and_nine_user_plugins(
    desired: DesiredState,
) -> None:
    marketplace = command(stdout=marketplace_json(desired.marketplace_source.source))
    runner = QueueRunner(
        [command(), marketplace]
        + [command()] * 9
        + [marketplace, command(stdout=installed_json(desired))]
    )
    adapter = ClaudeAdapter(
        runner=runner,
        which=lambda name: name,
        native_mcp_inventory={"context7": load_mcp_catalog()["context7"]},
    )

    result = adapter.install(desired)

    assert result.state is ResultState.READY
    assert runner.log[0] == [
        "claude",
        "plugin",
        "marketplace",
        "add",
        desired.marketplace_source.source,
        "--scope",
        "user",
    ]
    assert [row for row in runner.log if row[1:3] == ["plugin", "install"]] == [
        ["claude", "plugin", "install", f"{name}@manifest", "--scope", "user"]
        for name in DOMAIN_BUNDLES
    ]
    assert runner.log[-1] == ["claude", "plugin", "list", "--json"]
    assert result.installed_plugin_ids == tuple(
        f"{name}@manifest" for name in DOMAIN_BUNDLES
    )
    assert result.capabilities["manifest-workspace:skill:help"] == "verified"
    assert result.capabilities["manifest-workspace:mcp:context7"] == "verified"
    assert result.capabilities["manifest-workspace:executable:git"] == "verified"


def test_claude_published_release_uses_verified_extracted_marketplace(
    desired: DesiredState,
) -> None:
    published = replace(
        desired,
        source="https://example.invalid/releases/manifest-release.json",
        marketplace_source=MarketplaceSource(
            MarketplaceSourceKind.GIT,
            "https://example.invalid/Manifest.git",
            desired.source_commit,
        ),
    )
    marketplace = command(stdout=marketplace_json(published.release_root))
    runner = QueueRunner(
        [command(), marketplace]
        + [command()] * 9
        + [marketplace, command(stdout=installed_json(published))]
    )

    result = ClaudeAdapter(
        runner=runner,
        which=lambda name: name,
        native_mcp_inventory={"context7": load_mcp_catalog()["context7"]},
    ).install(published)

    assert result.state is ResultState.READY
    assert runner.log[0] == [
        "claude",
        "plugin",
        "marketplace",
        "add",
        str(published.release_root),
        "--scope",
        "user",
    ]


def test_already_present_is_idempotent_only_after_selected_version_inspection(
    desired: DesiredState,
) -> None:
    marketplace = command(stdout=marketplace_json(desired.marketplace_source.source))
    runner = QueueRunner(
        [command(returncode=1, stderr="already present"), marketplace]
        + [command(returncode=1, stderr="already installed")] * 9
        + [marketplace, command(stdout=installed_json(desired))]
    )

    result = ClaudeAdapter(
        runner=runner,
        which=lambda name: name,
        native_mcp_inventory={"context7": load_mcp_catalog()["context7"]},
    ).install(desired)

    assert result.state is ResultState.READY
    assert result.errors == ()
    assert runner.log[-1] == ["claude", "plugin", "list", "--json"]


def test_marketplace_collision_blocks_before_plugin_install(
    desired: DesiredState,
) -> None:
    runner = QueueRunner(
        [
            command(returncode=1, stderr="already present"),
            command(stdout=marketplace_json("/different/source")),
        ]
    )

    result = ClaudeAdapter(runner=runner, which=lambda name: name).install(desired)

    assert result.state is ResultState.BLOCKED
    assert "marketplace source mismatch" in " ".join(result.errors)
    assert not any(row[1:3] == ["plugin", "install"] for row in runner.log)


def test_inspect_reports_selected_version_drift(desired: DesiredState) -> None:
    runner = QueueRunner(
        [
            command(stdout=marketplace_json(desired.marketplace_source.source)),
            command(stdout=installed_json(desired, "0.1.0")),
        ]
    )

    result = ClaudeAdapter(runner=runner, which=lambda name: name).inspect(desired)

    assert result.state is ResultState.DRIFTED
    assert "expected 0.2.0, found 0.1.0" in result.errors[0]


def test_install_failure_is_redacted_when_inspection_cannot_confirm_state(
    desired: DesiredState,
) -> None:
    rows = json.loads(installed_json(desired))
    rows.pop()
    marketplace = command(stdout=marketplace_json(desired.marketplace_source.source))
    runner = QueueRunner(
        [command(), marketplace]
        + [command(returncode=1, stderr="--token native-secret rejected")]
        + [command()] * 8
        + [marketplace, command(stdout=json.dumps(rows))]
    )

    result = ClaudeAdapter(runner=runner, which=lambda name: name).install(desired)

    assert result.state is ResultState.BLOCKED
    assert "native-secret" not in " ".join(result.errors)
    assert "[REDACTED]" in " ".join(result.errors)


def test_non_idempotent_failure_propagates_even_when_state_is_already_ready(
    desired: DesiredState,
) -> None:
    marketplace = command(stdout=marketplace_json(desired.marketplace_source.source))
    runner = QueueRunner(
        [command(returncode=1, stderr="authentication failed"), marketplace]
    )

    result = ClaudeAdapter(runner=runner, which=lambda name: name).install(desired)

    assert result.state is ResultState.BLOCKED
    assert "authentication failed" in result.errors[0]
    assert not any(row[1:3] == ["plugin", "install"] for row in runner.log)


def test_inspect_blocks_when_required_component_evidence_is_missing(
    desired: DesiredState,
) -> None:
    runner = QueueRunner(
        [
            command(stdout=marketplace_json(desired.marketplace_source.source)),
            command(stdout=installed_json(desired)),
        ]
    )

    result = ClaudeAdapter(runner=runner, which=lambda _name: None).inspect(desired)

    assert result.state is ResultState.BLOCKED
    assert "manifest-workspace:executable:git" in " ".join(result.errors)


def test_uninstall_removes_only_receipt_plugins_and_retains_shared_marketplace() -> (
    None
):
    runner = QueueRunner(
        [
            command(),
            command(
                stdout=json.dumps(
                    [
                        {
                            "id": "adversarial-design-loop@manifest",
                            "version": "0.1.0",
                            "scope": "user",
                        }
                    ]
                )
            ),
        ]
    )
    receipt = HarnessReceipt(
        harness="claude",
        adapter_version="1",
        native_version="2",
        plugin_ids=("manifest-docs@manifest",),
        owned_entries=(OwnedEntry("marketplace", "manifest", "receipt"),),
        capabilities={},
        verified=True,
    )

    result = ClaudeAdapter(runner=runner, which=lambda name: name).uninstall(receipt)

    assert result.state is ResultState.READY
    assert runner.log == [
        ["claude", "plugin", "uninstall", "manifest-docs@manifest"],
        ["claude", "plugin", "list", "--json"],
    ]
    assert "unowned plugin" in result.warnings[0]


def test_uninstall_removes_owned_marketplace_when_no_plugins_reference_it() -> None:
    runner = QueueRunner([command(), command(stdout="[]"), command()])
    receipt = HarnessReceipt(
        harness="claude",
        adapter_version="1",
        native_version="2",
        plugin_ids=("manifest-docs",),
        owned_entries=(OwnedEntry("marketplace", "manifest", "receipt"),),
        capabilities={},
        verified=True,
    )

    result = ClaudeAdapter(runner=runner, which=lambda name: name).uninstall(receipt)

    assert result.state is ResultState.READY
    assert runner.log[-1] == [
        "claude",
        "plugin",
        "marketplace",
        "remove",
        "manifest",
    ]


@pytest.mark.native
def test_native_claude_adapter_lifecycle_uses_an_isolated_home(tmp_path: Path) -> None:
    executable = shutil.which("claude")
    if executable is None:
        pytest.skip("claude CLI not present")
    isolated_home = tmp_path / "home"
    isolated_home.mkdir()
    env = {
        "HOME": str(isolated_home),
        "CLAUDE_CONFIG_DIR": str(isolated_home / ".claude"),
        "PATH": os.environ["PATH"],
    }
    repository = Path(__file__).parents[3]
    desired = DesiredState(
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
        requested_harnesses=("claude",),
    )
    adapter = ClaudeAdapter(runner=CommandRunner(), env=env)

    result = adapter.install(desired)
    receipt = HarnessReceipt(
        harness="claude",
        adapter_version=adapter.adapter_version,
        native_version="native-smoke",
        plugin_ids=result.installed_plugin_ids,
        owned_entries=(OwnedEntry("marketplace", "manifest", "native-smoke"),),
        capabilities=result.capabilities,
        verified=result.state is not ResultState.BLOCKED,
    )
    removed = adapter.uninstall(receipt)

    assert len(result.installed_plugin_ids) == 9
    assert result.state in {ResultState.READY, ResultState.DEGRADED}
    assert removed.state is ResultState.READY

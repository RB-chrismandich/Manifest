"""Codex native marketplace adapter tests."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from pathlib import Path

import pytest

from manifest_agent.adapters.codex import CodexAdapter
from manifest_agent.capabilities import load_mcp_catalog
from manifest_agent.contracts import (
    DOMAIN_BUNDLES,
    Capabilities,
    CompatibilityStatus,
    Components,
    Provenance,
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
    *, returncode: int = 0, stdout: str = "{}", stderr: str = ""
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
        requested_harnesses=("codex",),
    )


def marketplace_json(
    source: str, root: Path | str, *, source_type: str = "local"
) -> str:
    return json.dumps(
        {
            "marketplaces": [
                {
                    "name": "manifest",
                    "root": str(root),
                    "marketplaceSource": {
                        "sourceType": source_type,
                        "source": source,
                    },
                }
            ]
        }
    )


def marketplace_add_json(root: Path | str, *, already_added: bool = False) -> str:
    return json.dumps(
        {
            "marketplaceName": "manifest",
            "installedRoot": str(root),
            "alreadyAdded": already_added,
        }
    )


def plugin_add_json(desired: DesiredState, name: str) -> str:
    return json.dumps(
        {
            "pluginId": f"{name}@manifest",
            "name": name,
            "marketplaceName": "manifest",
            "version": "0.2.0",
            "installedPath": str(desired.bundle_path(name)),
        }
    )


def plugin_remove_json(name: str) -> str:
    return json.dumps(
        {
            "pluginId": f"{name}@manifest",
            "name": name,
            "marketplaceName": "manifest",
        }
    )


def installed_json(
    desired: DesiredState, version: str = "0.2.0", *, extra: bool = False
) -> str:
    rows = [
        {
            "pluginId": f"{name}@manifest",
            "name": name,
            "marketplaceName": "manifest",
            "version": version,
            "installed": True,
            "enabled": True,
            "source": {
                "source": "local",
                "path": str(desired.bundle_path(name)),
            },
            "mcpServers": {"context7": {}} if name == "manifest-workspace" else {},
        }
        for name in DOMAIN_BUNDLES
    ]
    if extra:
        rows.append(
            {
                "pluginId": "adversarial-design-loop@manifest",
                "name": "adversarial-design-loop",
                "marketplaceName": "manifest",
                "version": "0.1.0",
                "installed": True,
                "enabled": True,
            }
        )
    return json.dumps({"installed": rows})


def test_detection_reports_absent_cli_explicitly() -> None:
    detection = CodexAdapter(which=lambda _name: None).detect()

    assert detection.present is False
    assert detection.executable is None
    assert detection.reason == "codex CLI not present"


def test_codex_local_release_omits_ref_and_installs_nine_plugins(
    desired: DesiredState,
) -> None:
    marketplace = command(
        stdout=marketplace_json(
            desired.marketplace_source.source,
            desired.marketplace_source.source,
        )
    )
    runner = QueueRunner(
        [
            command(stdout=marketplace_add_json(desired.marketplace_source.source)),
            marketplace,
            *[
                command(stdout=plugin_add_json(desired, name))
                for name in DOMAIN_BUNDLES
            ],
            marketplace,
            command(stdout=installed_json(desired)),
        ]
    )
    adapter = CodexAdapter(
        runner=runner,
        which=lambda name: name,
        native_mcp_inventory={"context7": load_mcp_catalog()["context7"]},
    )

    result = adapter.install(desired)

    assert result.state is ResultState.READY
    assert runner.log[0] == [
        "codex",
        "plugin",
        "marketplace",
        "add",
        desired.marketplace_source.source,
        "--json",
    ]
    assert [row for row in runner.log if row[1:3] == ["plugin", "add"]] == [
        ["codex", "plugin", "add", f"{name}@manifest", "--json"]
        for name in DOMAIN_BUNDLES
    ]
    assert runner.log[-1] == ["codex", "plugin", "list", "--json"]
    assert result.capabilities["manifest-workspace:skill:help"] == "verified"
    assert result.capabilities["manifest-workspace:mcp:context7"] == "verified"


def test_codex_requires_structured_mutation_output(desired: DesiredState) -> None:
    marketplace = command(
        stdout=marketplace_json(
            desired.marketplace_source.source,
            desired.marketplace_source.source,
        )
    )
    runner = QueueRunner([command(stdout="installed successfully"), marketplace])

    result = CodexAdapter(
        runner=runner,
        which=lambda name: name,
        native_mcp_inventory={"context7": load_mcp_catalog()["context7"]},
    ).install(desired)

    assert result.state is ResultState.BLOCKED
    assert "valid JSON" in " ".join(result.errors)
    assert not any(row[1:3] == ["plugin", "add"] for row in runner.log)


def test_codex_already_present_requires_selected_version_inspection(
    desired: DesiredState,
) -> None:
    marketplace = command(
        stdout=marketplace_json(
            desired.marketplace_source.source,
            desired.marketplace_source.source,
        )
    )
    runner = QueueRunner(
        [
            command(
                stdout=marketplace_add_json(
                    desired.marketplace_source.source, already_added=True
                )
            ),
            marketplace,
            *[
                command(stdout=plugin_add_json(desired, name))
                for name in DOMAIN_BUNDLES
            ],
            marketplace,
            command(stdout=installed_json(desired)),
        ]
    )

    result = CodexAdapter(
        runner=runner,
        which=lambda name: name,
        native_mcp_inventory={"context7": load_mcp_catalog()["context7"]},
    ).install(desired)

    assert result.state is ResultState.READY
    assert result.errors == ()


def test_codex_marketplace_collision_blocks_before_plugin_install(
    desired: DesiredState,
) -> None:
    runner = QueueRunner(
        [
            command(
                stdout=marketplace_add_json(
                    desired.marketplace_source.source, already_added=True
                )
            ),
            command(stdout=marketplace_json("/different/source", "/different/source")),
        ]
    )

    result = CodexAdapter(runner=runner, which=lambda name: name).install(desired)

    assert result.state is ResultState.BLOCKED
    assert "marketplace source mismatch" in " ".join(result.errors)
    assert not any(row[1:3] == ["plugin", "add"] for row in runner.log)


def test_codex_plugin_add_requires_exact_native_identity(
    desired: DesiredState,
) -> None:
    marketplace = command(
        stdout=marketplace_json(
            desired.marketplace_source.source,
            desired.marketplace_source.source,
        )
    )
    runner = QueueRunner(
        [
            command(stdout=marketplace_add_json(desired.marketplace_source.source)),
            marketplace,
            command(stdout="{}"),
            *[
                command(stdout=plugin_add_json(desired, name))
                for name in DOMAIN_BUNDLES[1:]
            ],
            marketplace,
            command(stdout=installed_json(desired)),
        ]
    )

    result = CodexAdapter(runner=runner, which=lambda name: name).install(desired)

    assert result.state is ResultState.BLOCKED
    assert "did not confirm manifest-code-quality@manifest" in result.errors[0]


def test_codex_inspect_reports_selected_version_drift(desired: DesiredState) -> None:
    runner = QueueRunner(
        [
            command(
                stdout=marketplace_json(
                    desired.marketplace_source.source,
                    desired.marketplace_source.source,
                )
            ),
            command(stdout=installed_json(desired, "0.1.0")),
        ]
    )

    result = CodexAdapter(runner=runner, which=lambda name: name).inspect(desired)

    assert result.state is ResultState.DRIFTED
    assert "expected 0.2.0, found 0.1.0" in result.errors[0]


def test_codex_inspect_blocks_when_required_component_evidence_is_missing(
    desired: DesiredState,
) -> None:
    runner = QueueRunner(
        [
            command(
                stdout=marketplace_json(
                    desired.marketplace_source.source,
                    desired.marketplace_source.source,
                )
            ),
            command(stdout=installed_json(desired)),
        ]
    )

    result = CodexAdapter(runner=runner, which=lambda _name: None).inspect(desired)

    assert result.state is ResultState.BLOCKED
    assert "manifest-workspace:executable:git" in " ".join(result.errors)


def test_codex_uninstall_retains_marketplace_for_unowned_plugin() -> None:
    runner = QueueRunner([])
    receipt = HarnessReceipt(
        harness="codex",
        adapter_version="1",
        native_version="0.146",
        plugin_ids=tuple(f"{name}@manifest" for name in DOMAIN_BUNDLES),
        owned_entries=(OwnedEntry("marketplace", "manifest", "receipt"),),
        capabilities={},
        verified=True,
    )
    # One response is reused for each native remove before the final list.
    runner.results = [
        command(stdout=plugin_remove_json(name)) for name in DOMAIN_BUNDLES
    ] + [
        command(
            stdout=json.dumps(
                {
                    "installed": [
                        {
                            "pluginId": "adversarial-design-loop@manifest",
                            "marketplaceName": "manifest",
                            "version": "0.1.0",
                            "installed": True,
                        }
                    ]
                }
            )
        )
    ]

    result = CodexAdapter(runner=runner, which=lambda name: name).uninstall(receipt)

    assert result.state is ResultState.READY
    assert all(row[-1] == "--json" for row in runner.log[:9])
    assert not any(
        row[1:4] == ["plugin", "marketplace", "remove"] for row in runner.log
    )
    assert "unowned plugin" in result.warnings[0]


def test_codex_uninstall_removes_owned_marketplace_when_unreferenced() -> None:
    runner = QueueRunner(
        [command(stdout=plugin_remove_json(name)) for name in DOMAIN_BUNDLES]
        + [
            command(stdout=json.dumps({"installed": []})),
            command(
                stdout=json.dumps(
                    {"marketplaceName": "manifest", "installedRoot": None}
                )
            ),
        ]
    )
    receipt = HarnessReceipt(
        harness="codex",
        adapter_version="1",
        native_version="0.146",
        plugin_ids=DOMAIN_BUNDLES,
        owned_entries=(OwnedEntry("marketplace", "manifest", "receipt"),),
        capabilities={},
        verified=True,
    )

    result = CodexAdapter(runner=runner, which=lambda name: name).uninstall(receipt)

    assert result.state is ResultState.READY
    assert runner.log[-1] == [
        "codex",
        "plugin",
        "marketplace",
        "remove",
        "manifest",
        "--json",
    ]

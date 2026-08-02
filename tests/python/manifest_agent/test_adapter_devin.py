"""Devin native plugin adapter tests."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from pathlib import Path

import pytest

from manifest_agent.adapters.devin import DevinAdapter
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
        skill_name = f"skill-{name}"
        skill = tmp_path / "plugins" / name / "skills" / skill_name / "SKILL.md"
        skill.parent.mkdir(parents=True)
        skill.write_text("# Skill\n", encoding="utf-8")
        (tmp_path / "plugins" / name / "plugin.json").write_text(
            json.dumps(
                {
                    "name": name,
                    "version": "0.2.0",
                    "skills": [f"skills/{skill_name}"],
                    "harnesses": {
                        "antigravity": {
                            "mode": "imported",
                            "skills": [f"skills/{skill_name}"],
                        },
                        "devin": {
                            "mode": "native",
                            "skills": [f"skills/{skill_name}"],
                        },
                    },
                }
            ),
            encoding="utf-8",
        )
        contracts.append(
            BundleContract(
                name,
                "0.2.0",
                "fixture",
                "fixture",
                Components("skills", ("*/SKILL.md",), (), (), (), ()),
                Capabilities(
                    dict.fromkeys(CapabilityTier, ()),
                    dict.fromkeys(CapabilityTier, ()),
                ),
                {"devin": CompatibilityStatus("native")},
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
        repository_url="https://example.invalid/Manifest.git",
        source_dirty=False,
        archive_sha256="b" * 64,
        contracts=tuple(contracts),
        selected_optional=frozenset(),
        requested_harnesses=("devin",),
    )


def list_text(names: Sequence[str] = DOMAIN_BUNDLES) -> str:
    if not names:
        return "No plugins installed.\n"
    return "Installed plugins\n" + "\n".join(f"{name} 0.2.0" for name in names)


def info_text(
    desired: DesiredState,
    name: str,
    *,
    version: str = "0.2.0",
    source: str | None = None,
    include_skill: bool = True,
) -> str:
    skill = f"skill-{name}"
    skills = f"  - {skill}\n" if include_skill else "  (none)\n"
    return (
        f"Plugin: {name}\n"
        f"  version: {version}\n"
        f"  source: {source or desired.bundle_path(name)}\n"
        "Skills\n"
        f"{skills}"
        "Required plugins\n"
        "  (none)\n"
        "Optional plugins\n"
        "  (none)\n"
        "Forbidden plugins\n"
        "  (none)\n"
    )


def install_results(
    desired: DesiredState,
    *,
    drifted: str | None = None,
    missing_skill: str | None = None,
) -> list[CommandResult]:
    return (
        [command()] * 9
        + [command(stdout=list_text())]
        + [
            command(
                stdout=info_text(
                    desired,
                    name,
                    version="0.1.0" if name == drifted else "0.2.0",
                    include_skill=name != missing_skill,
                )
            )
            for name in DOMAIN_BUNDLES
        ]
    )


def test_detection_reports_absent_cli_explicitly() -> None:
    detection = DevinAdapter(which=lambda _name: None).detect()

    assert detection.present is False
    assert detection.executable is None
    assert detection.reason == "devin CLI not present"


def test_devin_installs_and_verifies_local_bundle_views(
    desired: DesiredState,
) -> None:
    runner = QueueRunner(install_results(desired))

    result = DevinAdapter(runner=runner, which=lambda name: name).install(desired)

    assert result.state is ResultState.READY
    assert runner.log[:9] == [
        ["devin", "plugins", "install", str(desired.bundle_path(name)), "--yes"]
        for name in DOMAIN_BUNDLES
    ]
    assert runner.log[9] == ["devin", "plugins", "list"]
    assert runner.log[10:] == [
        ["devin", "plugins", "info", name] for name in DOMAIN_BUNDLES
    ]
    assert all(".claude" not in part for row in runner.log for part in row)
    assert result.installed_plugin_ids == DOMAIN_BUNDLES
    assert result.capabilities["manifest-workspace:skill:skill-manifest-workspace"] == (
        "verified"
    )


def test_devin_info_version_mismatch_is_drifted(desired: DesiredState) -> None:
    runner = QueueRunner(
        [command(stdout=list_text())]
        + [
            command(
                stdout=info_text(
                    desired,
                    name,
                    version="0.1.0" if name == DOMAIN_BUNDLES[-1] else "0.2.0",
                )
            )
            for name in DOMAIN_BUNDLES
        ]
    )

    result = DevinAdapter(runner=runner).inspect(desired)

    assert result.state is ResultState.DRIFTED
    assert "expected 0.2.0, found 0.1.0" in " ".join(result.errors)


def test_devin_info_requires_native_skill_evidence(desired: DesiredState) -> None:
    missing = DOMAIN_BUNDLES[-1]
    runner = QueueRunner(
        [command(stdout=list_text())]
        + [
            command(stdout=info_text(desired, name, include_skill=name != missing))
            for name in DOMAIN_BUNDLES
        ]
    )

    result = DevinAdapter(runner=runner).inspect(desired)

    assert result.state is ResultState.BLOCKED
    assert f"skill-{missing}" in " ".join(result.errors)


def test_devin_info_requires_exact_acquired_local_source(desired: DesiredState) -> None:
    runner = QueueRunner(
        [command(stdout=list_text())]
        + [
            command(
                stdout=info_text(
                    desired,
                    name,
                    source="/tmp/unverified-copy"
                    if name == DOMAIN_BUNDLES[0]
                    else None,
                )
            )
            for name in DOMAIN_BUNDLES
        ]
    )

    result = DevinAdapter(runner=runner).inspect(desired)

    assert result.state is ResultState.BLOCKED
    assert "source mismatch" in " ".join(result.errors)


def test_devin_rejects_invalid_generic_view_before_mutation(
    desired: DesiredState,
) -> None:
    view = desired.bundle_path(DOMAIN_BUNDLES[0]) / "plugin.json"
    document = json.loads(view.read_text(encoding="utf-8"))
    document["harnesses"]["devin"]["mode"] = "imported"
    view.write_text(json.dumps(document), encoding="utf-8")
    runner = QueueRunner([])

    result = DevinAdapter(runner=runner).install(desired)

    assert result.state is ResultState.BLOCKED
    assert "generic plugin view" in " ".join(result.errors)
    assert runner.log == []


def test_devin_native_errors_are_redacted_and_aggregated(
    desired: DesiredState,
) -> None:
    installs = [command()] * 9
    installs[1] = command(returncode=1, stderr="--token devin-native-secret rejected")
    installs[6] = command(returncode=1, stderr="second install failed")
    runner = QueueRunner(installs + install_results(desired)[9:])

    result = DevinAdapter(runner=runner, which=lambda name: name).install(desired)

    assert result.state is ResultState.BLOCKED
    assert len(result.errors) == 2
    assert "devin-native-secret" not in " ".join(result.errors)
    assert "[REDACTED]" in " ".join(result.errors)


def test_devin_uninstall_prunes_only_after_owned_removal_and_preserves_unowned() -> (
    None
):
    unowned = "other-team-plugin"
    runner = QueueRunner(
        [command(stdout=list_text((*DOMAIN_BUNDLES, unowned)))]
        + [command()] * 9
        + [command(stdout=list_text((unowned,)))]
        + [command()]
        + [command(stdout=list_text((unowned,)))]
    )
    receipt = HarnessReceipt(
        harness="devin",
        adapter_version="1",
        native_version="3000.2.17",
        plugin_ids=DOMAIN_BUNDLES,
        owned_entries=(),
        capabilities={},
        verified=True,
    )

    result = DevinAdapter(runner=runner).uninstall(receipt)

    assert result.state is ResultState.READY
    assert runner.log[0] == ["devin", "plugins", "list"]
    assert runner.log[1:10] == [
        ["devin", "plugins", "remove", name] for name in DOMAIN_BUNDLES
    ]
    assert runner.log[-3:] == [
        ["devin", "plugins", "list"],
        ["devin", "plugins", "prune"],
        ["devin", "plugins", "list"],
    ]


def test_devin_uninstall_skips_prune_after_any_owned_remove_failure() -> None:
    removals = [command()] * 9
    removals[3] = command(returncode=1, stderr="remove failed")
    runner = QueueRunner(
        [
            command(stdout=list_text()),
            *removals,
            command(stdout=list_text((DOMAIN_BUNDLES[3],))),
        ]
    )
    receipt = HarnessReceipt("devin", "1", "3000.2.17", DOMAIN_BUNDLES, (), {}, True)

    result = DevinAdapter(runner=runner).uninstall(receipt)

    assert result.state is ResultState.BLOCKED
    assert not any(row[1:] == ["plugins", "prune"] for row in runner.log)


def test_devin_uninstall_refuses_prune_when_unowned_preservation_is_unverified() -> (
    None
):
    unowned = "other-team-plugin"
    runner = QueueRunner(
        [command(stdout=list_text((*DOMAIN_BUNDLES, unowned)))]
        + [command()] * 9
        + [command(stdout=list_text())]
    )
    receipt = HarnessReceipt("devin", "1", "3000.2.17", DOMAIN_BUNDLES, (), {}, True)

    result = DevinAdapter(runner=runner).uninstall(receipt)

    assert result.state is ResultState.BLOCKED
    assert "unowned plugin disappeared" in " ".join(result.errors)
    assert not any(row[1:] == ["plugins", "prune"] for row in runner.log)


def test_devin_uninstall_blocks_unparsed_inventory_before_removal() -> None:
    stdout = list_text() + "\n@other/private 1.0\n"
    runner = QueueRunner([command(stdout=stdout)])
    receipt = HarnessReceipt("devin", "1", "3000.2.17", DOMAIN_BUNDLES, (), {}, True)

    result = DevinAdapter(runner=runner).uninstall(receipt)

    assert result.state is ResultState.BLOCKED
    assert "unrecognized inventory row" in " ".join(result.errors)
    assert runner.log == [["devin", "plugins", "list"]]
    assert not any(row[1:] == ["plugins", "prune"] for row in runner.log)


def test_devin_uninstall_parses_documented_table_inventory_variants() -> None:
    before = (
        "\x1b[1mInstalled plugins\x1b[0m\n"
        "Name │ Version │ Blocked\n"
        "manifest-docs │ v0.2.0-beta.1 │ no\n"
        "other-team/private │ unversioned │ required\n"
    )
    after = (
        "Installed plugins\n"
        "Name | Version | Blocked\n"
        "other-team/private | unversioned | required\n"
    )
    runner = QueueRunner([command(stdout=before), command(), command(stdout=after)])
    receipt = HarnessReceipt(
        "devin", "1", "3000.2.17", ("manifest-docs",), (), {}, True
    )

    result = DevinAdapter(runner=runner).uninstall(receipt)

    assert result.state is ResultState.READY
    assert runner.log == [
        ["devin", "plugins", "list"],
        ["devin", "plugins", "remove", "manifest-docs"],
        ["devin", "plugins", "list"],
    ]


def test_devin_uninstall_removes_only_canonical_receipt_ids() -> None:
    runner = QueueRunner([])
    receipt = HarnessReceipt(
        "devin",
        "1",
        "3000.2.17",
        ("manifest-docs", "unrelated-plugin"),
        (),
        {},
        True,
    )

    result = DevinAdapter(runner=runner).uninstall(receipt)

    assert result.state is ResultState.BLOCKED
    assert runner.log == []
    assert "non-canonical" in " ".join(result.errors)

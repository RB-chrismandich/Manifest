"""Devin native plugin adapter tests."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from pathlib import Path

import pytest

from manifest_agent.adapters.devin import DevinAdapter
from manifest_agent.codex_plugin_backup import capture_owned_file_backup
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
from manifest_agent.ownership import owned_file_entry
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
    generated_rule = tmp_path / "plugins/manifest-i-have-adhd/devin/global-rule.md"
    generated_rule.parent.mkdir(parents=True)
    generated_rule.write_text("# Generated ADHD rule\n", encoding="utf-8")
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
        [command()] * len(DOMAIN_BUNDLES)
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


def owned_rule_receipt(
    desired: DesiredState, home: Path, *, prior: bytes | None = None
) -> OwnedEntry:
    target = home / ".codeium/windsurf/memories/global_rules.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    source = desired.bundle_path("manifest-i-have-adhd") / "devin/global-rule.md"
    source_backup, _mode, source_digest = capture_owned_file_backup(
        source, {"HOME": str(home)}
    )
    if prior is None:
        prior_row = {"path": str(target), "type": "missing"}
    else:
        target.write_bytes(prior)
        prior_backup, prior_mode, prior_digest = capture_owned_file_backup(
            target, {"HOME": str(home)}
        )
        prior_row = {
            "path": str(target),
            "type": "file",
            "mode": prior_mode,
            "digest": prior_digest,
            "restore": {"archive": prior_backup.to_dict()},
        }
    target.write_bytes(source.read_bytes())
    target.chmod(0o600)
    installed = {
        "path": str(target),
        "type": "file",
        "mode": 0o600,
        "digest": source_digest,
        "restore": {"archive": source_backup.to_dict()},
    }
    return owned_file_entry(
        "devin-global-rules",
        target,
        prior_row,
        installed,
        env={"HOME": str(home)},
    )


def uninstall_receipt(
    desired: DesiredState, home: Path, *, prior=None
) -> HarnessReceipt:
    return HarnessReceipt(
        "devin",
        "1",
        "3000.2.17",
        DOMAIN_BUNDLES,
        (owned_rule_receipt(desired, home, prior=prior),),
        {},
        True,
    )


def test_devin_uninstall_prunes_only_after_owned_removal_and_preserves_unowned(
    desired: DesiredState,
) -> None:
    unowned = "other-team-plugin"
    runner = QueueRunner(
        [command(stdout=list_text((*DOMAIN_BUNDLES, unowned)))]
        + [command()] * len(DOMAIN_BUNDLES)
        + [command(stdout=list_text((unowned,)))]
        + [command()]
        + [command(stdout=list_text((unowned,)))]
    )
    home = desired.release_root / "uninstall-prune-home"
    receipt = uninstall_receipt(desired, home)

    result = DevinAdapter(runner=runner, env={"HOME": str(home)}).uninstall(receipt)

    assert result.state is ResultState.READY
    assert runner.log[0] == ["devin", "plugins", "list"]
    assert runner.log[1 : len(DOMAIN_BUNDLES) + 1] == [
        ["devin", "plugins", "remove", name] for name in DOMAIN_BUNDLES
    ]
    assert runner.log[-3:] == [
        ["devin", "plugins", "list"],
        ["devin", "plugins", "prune"],
        ["devin", "plugins", "list"],
    ]
    assert not (home / ".codeium/windsurf/memories/global_rules.md").exists()


def test_devin_uninstall_accepts_legacy_receipt_without_global_rule(
    desired: DesiredState,
) -> None:
    runner = QueueRunner(
        [command(stdout=list_text())]
        + [command()] * len(DOMAIN_BUNDLES)
        + [command(stdout=list_text(())), command(), command(stdout=list_text(()))]
    )
    home = desired.release_root / "legacy-uninstall-home"
    receipt = HarnessReceipt("devin", "1", "3000.2.17", DOMAIN_BUNDLES, (), {}, True)

    result = DevinAdapter(runner=runner, env={"HOME": str(home)}).uninstall(receipt)

    assert result.state is ResultState.READY
    assert runner.log[-2] == ["devin", "plugins", "prune"]
    assert not (home / ".codeium/windsurf/memories/global_rules.md").exists()


@pytest.mark.parametrize("prior", (b"", b"original user rule\n"))
def test_devin_uninstall_restores_exact_prior_regular_file(
    desired: DesiredState, prior: bytes
) -> None:
    home = desired.release_root / f"restore-{len(prior)}"
    receipt = uninstall_receipt(desired, home, prior=prior)
    runner = QueueRunner(
        [command(stdout=list_text())]
        + [command()] * len(DOMAIN_BUNDLES)
        + [command(stdout=list_text(())), command(), command(stdout=list_text(()))]
    )

    result = DevinAdapter(runner=runner, env={"HOME": str(home)}).uninstall(receipt)

    assert result.state is ResultState.READY
    target = home / ".codeium/windsurf/memories/global_rules.md"
    assert target.read_bytes() == prior


def test_devin_uninstall_blocks_current_rule_drift_before_plugin_mutation(
    desired: DesiredState,
) -> None:
    home = desired.release_root / "drift-home"
    receipt = uninstall_receipt(desired, home)
    target = home / ".codeium/windsurf/memories/global_rules.md"
    target.write_text("concurrent user change\n", encoding="utf-8")
    runner = QueueRunner([])

    result = DevinAdapter(runner=runner, env={"HOME": str(home)}).uninstall(receipt)

    assert result.state is ResultState.BLOCKED
    assert target.read_text(encoding="utf-8") == "concurrent user change\n"
    assert runner.log == []


def test_devin_uninstall_blocks_corrupt_prior_archive_before_plugin_mutation(
    desired: DesiredState,
) -> None:
    home = desired.release_root / "corrupt-home"
    receipt = uninstall_receipt(desired, home, prior=b"prior\n")
    entry = receipt.owned_entries[0]
    document = json.loads(entry.previous_checksum or "")
    archive = Path(document["prior"]["restore"]["archive"]["archive_path"])
    archive.write_bytes(b"corrupt")
    runner = QueueRunner([])

    result = DevinAdapter(runner=runner, env={"HOME": str(home)}).uninstall(receipt)

    assert result.state is ResultState.BLOCKED
    assert runner.log == []


def test_devin_uninstall_blocks_tampered_ownership_before_plugin_mutation(
    desired: DesiredState,
) -> None:
    home = desired.release_root / "tamper-home"
    receipt = uninstall_receipt(desired, home)
    entry = receipt.owned_entries[0]
    tampered = OwnedEntry(
        entry.kind,
        entry.identifier,
        entry.ownership_marker,
        entry.target_path,
        (entry.previous_checksum or "").replace('"mode":384', '"mode":420'),
    )
    receipt = HarnessReceipt(
        receipt.harness,
        receipt.adapter_version,
        receipt.native_version,
        receipt.plugin_ids,
        (tampered,),
        receipt.capabilities,
        receipt.verified,
    )
    runner = QueueRunner([])

    result = DevinAdapter(runner=runner, env={"HOME": str(home)}).uninstall(receipt)

    assert result.state is ResultState.BLOCKED
    assert runner.log == []


def test_devin_uninstall_skips_prune_after_any_owned_remove_failure(
    desired: DesiredState,
) -> None:
    removals = [command()] * len(DOMAIN_BUNDLES)
    removals[3] = command(returncode=1, stderr="remove failed")
    runner = QueueRunner(
        [
            command(stdout=list_text()),
            *removals,
            command(stdout=list_text((DOMAIN_BUNDLES[3],))),
        ]
    )
    home = desired.release_root / "uninstall-failure-home"
    receipt = uninstall_receipt(desired, home)

    result = DevinAdapter(runner=runner, env={"HOME": str(home)}).uninstall(receipt)

    assert result.state is ResultState.BLOCKED
    assert not any(row[1:] == ["plugins", "prune"] for row in runner.log)


def test_devin_uninstall_refuses_prune_when_unowned_preservation_is_unverified(
    desired: DesiredState,
) -> None:
    unowned = "other-team-plugin"
    runner = QueueRunner(
        [command(stdout=list_text((*DOMAIN_BUNDLES, unowned)))]
        + [command()] * len(DOMAIN_BUNDLES)
        + [command(stdout=list_text())]
    )
    home = desired.release_root / "uninstall-unowned-home"
    receipt = uninstall_receipt(desired, home)

    result = DevinAdapter(runner=runner, env={"HOME": str(home)}).uninstall(receipt)

    assert result.state is ResultState.BLOCKED
    assert "unowned plugin disappeared" in " ".join(result.errors)
    assert not any(row[1:] == ["plugins", "prune"] for row in runner.log)


def test_devin_uninstall_blocks_unparsed_inventory_before_removal(
    desired: DesiredState,
) -> None:
    stdout = list_text() + "\n@other/private 1.0\n"
    runner = QueueRunner([command(stdout=stdout)])
    home = desired.release_root / "uninstall-unparsed-home"
    receipt = uninstall_receipt(desired, home)

    result = DevinAdapter(runner=runner, env={"HOME": str(home)}).uninstall(receipt)

    assert result.state is ResultState.BLOCKED
    assert "unrecognized inventory row" in " ".join(result.errors)
    assert runner.log == [["devin", "plugins", "list"]]
    assert not any(row[1:] == ["plugins", "prune"] for row in runner.log)


def test_devin_uninstall_parses_documented_table_inventory_variants(
    desired: DesiredState,
) -> None:
    before = (
        "\x1b[1mInstalled plugins\x1b[0m\n"
        "Name │ Version │ Blocked\n"
        + "".join(f"{name} │ v0.2.0-beta.1 │ no\n" for name in DOMAIN_BUNDLES)
        + "other-team/private │ unversioned │ required\n"
    )
    after = (
        "Installed plugins\n"
        "Name | Version | Blocked\n"
        "other-team/private | unversioned | required\n"
    )
    runner = QueueRunner(
        [command(stdout=before)]
        + [command() for _name in DOMAIN_BUNDLES]
        + [command(stdout=after), command(), command(stdout=after)]
    )
    home = desired.release_root / "uninstall-table-home"
    receipt = uninstall_receipt(desired, home)

    result = DevinAdapter(runner=runner, env={"HOME": str(home)}).uninstall(receipt)

    assert result.state is ResultState.READY
    assert runner.log[0] == ["devin", "plugins", "list"]
    assert runner.log[1 : len(DOMAIN_BUNDLES) + 1] == [
        ["devin", "plugins", "remove", name] for name in DOMAIN_BUNDLES
    ]
    assert runner.log[-3:] == [
        ["devin", "plugins", "list"],
        ["devin", "plugins", "prune"],
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

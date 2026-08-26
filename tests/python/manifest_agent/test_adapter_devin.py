"""Devin native plugin adapter tests."""

from __future__ import annotations

import json
import shutil
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


def _bundle_contract(name: str) -> BundleContract:
    return BundleContract(
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


def _write_domain_bundle(tmp_path: Path, name: str) -> None:
    skill_name = f"skill-{name}"
    skill = tmp_path / "plugins" / name / "skills" / skill_name / "SKILL.md"
    skill.parent.mkdir(parents=True)
    skill.write_text("# Skill\n", encoding="utf-8")
    # Both locations, as generate_plugin_views emits them: the bundle-root
    # generic view and the copy `devin plugins install` actually reads.
    devin_manifest = tmp_path / "plugins" / name / ".devin-plugin/plugin.json"
    devin_manifest.parent.mkdir(parents=True, exist_ok=True)
    payload = {
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
    for manifest in (tmp_path / "plugins" / name / "plugin.json", devin_manifest):
        manifest.write_text(json.dumps(payload), encoding="utf-8")


@pytest.fixture
def desired(tmp_path: Path) -> DesiredState:
    contracts = []
    for name in DOMAIN_BUNDLES:
        _write_domain_bundle(tmp_path, name)
        contracts.append(_bundle_contract(name))
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


def test_detection_reports_absent_cli_explicitly() -> None:
    detection = DevinAdapter(which=lambda _name: None).detect()

    assert detection.present is False
    assert detection.executable is None
    assert detection.reason == "devin CLI not present"


def test_devin_installs_and_verifies_local_bundle_views(
    desired: DesiredState,
) -> None:
    runner = QueueRunner(install_results(desired))
    home = desired.release_root / "home"

    result = DevinAdapter(
        runner=runner, which=lambda name: name, env={"HOME": str(home)}
    ).install(desired)

    assert result.state is ResultState.READY
    assert runner.log[: len(DOMAIN_BUNDLES)] == [
        ["devin", "plugins", "install", str(desired.bundle_path(name)), "--yes"]
        for name in DOMAIN_BUNDLES
    ]
    assert runner.log[len(DOMAIN_BUNDLES)] == ["devin", "plugins", "list"]
    assert runner.log[len(DOMAIN_BUNDLES) + 1 :] == [
        ["devin", "plugins", "info", name] for name in DOMAIN_BUNDLES
    ]
    assert all(".claude" not in part for row in runner.log for part in row)
    assert result.installed_plugin_ids == DOMAIN_BUNDLES
    assert result.capabilities["manifest-workspace:skill:skill-manifest-workspace"] == (
        "verified"
    )
    target = home / ".codeium/windsurf/memories/global_rules.md"
    source = desired.bundle_path("manifest-i-have-adhd") / "devin/global-rule.md"
    assert target.read_bytes() == source.read_bytes()


def test_devin_rule_collision_blocks_before_any_native_command(
    desired: DesiredState,
) -> None:
    home = desired.release_root / "collision-home"
    target = home / ".codeium/windsurf/memories/global_rules.md"
    target.parent.mkdir(parents=True)
    target.write_text("user-owned rule\n", encoding="utf-8")
    runner = QueueRunner([])

    result = DevinAdapter(runner=runner, env={"HOME": str(home)}).install(desired)

    assert result.state is ResultState.BLOCKED
    assert "unowned user content" in " ".join(result.errors)
    assert runner.log == []
    assert target.read_text(encoding="utf-8") == "user-owned rule\n"


def test_devin_rule_install_preserves_edit_at_final_transition_boundary(
    desired: DesiredState, monkeypatch: pytest.MonkeyPatch
) -> None:
    home = desired.release_root / "rule-race-home"
    target = home / ".codeium/windsurf/memories/global_rules.md"
    target.parent.mkdir(parents=True)
    target.write_bytes(b"")
    runner = QueueRunner(install_results(desired))
    adapter = DevinAdapter(runner=runner, env={"HOME": str(home)})

    def concurrent_edit(path: Path) -> None:
        path.write_text("concurrent user rule\n", encoding="utf-8")

    monkeypatch.setattr(adapter, "_owned_file_transition_boundary", concurrent_edit)

    result = adapter.install(desired)

    assert result.state is ResultState.BLOCKED
    assert target.read_text(encoding="utf-8") == "concurrent user rule\n"


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
    # The manifest `devin plugins install` reads, which is what the adapter
    # validates -- corrupting the bundle-root sibling proves nothing about it.
    view = desired.bundle_path(DOMAIN_BUNDLES[0]) / ".devin-plugin/plugin.json"
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
    installs = [command()] * len(DOMAIN_BUNDLES)
    installs[1] = command(returncode=1, stderr="--token devin-native-secret rejected")
    installs[6] = command(returncode=1, stderr="second install failed")
    runner = QueueRunner(installs + install_results(desired)[len(DOMAIN_BUNDLES) :])
    home = desired.release_root / "home"

    result = DevinAdapter(
        runner=runner, which=lambda name: name, env={"HOME": str(home)}
    ).install(desired)

    assert result.state is ResultState.BLOCKED
    assert len(result.errors) == 2
    assert "devin-native-secret" not in " ".join(result.errors)
    assert "[REDACTED]" in " ".join(result.errors)
    target = home / ".codeium/windsurf/memories/global_rules.md"
    source = desired.bundle_path("manifest-i-have-adhd") / "devin/global-rule.md"
    assert target.read_bytes() == source.read_bytes()


def test_devin_installs_domain_bundles_when_the_addon_is_not_shipped(
    desired: DesiredState,
) -> None:
    """Release 0.3.0 ships the eight domain bundles without the ADHD addon.
    install() prepared its global rule before the install loop and returned on
    failure, so Devin ended with ZERO plugins installed."""
    shutil.rmtree(desired.bundle_path("manifest-i-have-adhd"))
    runner = QueueRunner(install_results(desired))
    home = desired.release_root / "home"

    result = DevinAdapter(
        runner=runner, which=lambda name: name, env={"HOME": str(home)}
    ).install(desired)

    assert result.state is ResultState.READY
    assert result.installed_plugin_ids == DOMAIN_BUNDLES
    assert runner.log[: len(DOMAIN_BUNDLES)] == [
        ["devin", "plugins", "install", str(desired.bundle_path(name)), "--yes"]
        for name in DOMAIN_BUNDLES
    ]
    assert not (home / ".codeium/windsurf/memories/global_rules.md").exists()


def test_devin_still_blocks_when_a_shipped_addon_lacks_its_rule(
    desired: DesiredState,
) -> None:
    """A bundle directory that exists without a usable rule is corrupt, not
    absent, and must keep blocking before any native command runs."""
    (desired.bundle_path("manifest-i-have-adhd") / "devin/global-rule.md").unlink()
    runner = QueueRunner([])

    result = DevinAdapter(
        runner=runner,
        which=lambda name: name,
        env={"HOME": str(desired.release_root / "home")},
    ).install(desired)

    assert result.state is ResultState.BLOCKED
    assert "global rule is missing" in " ".join(result.errors)
    assert runner.log == []

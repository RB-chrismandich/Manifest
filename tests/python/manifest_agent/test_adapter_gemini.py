"""Gemini CLI extension adapter tests."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from pathlib import Path

import pytest

from manifest_agent.adapters.gemini import GeminiAdapter
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
        skill = tmp_path / "plugins" / name / "skills" / f"skill-{name}" / "SKILL.md"
        skill.parent.mkdir(parents=True)
        skill.write_text("# Skill\n", encoding="utf-8")
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
                {"gemini": CompatibilityStatus("native")},
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
        requested_harnesses=("gemini",),
    )


def extensions_json(desired: DesiredState, version: str = "0.2.0") -> str:
    return json.dumps(
        [
            {
                "name": name,
                "version": version,
                "path": f"/native/extensions/{name}",
            }
            for name in DOMAIN_BUNDLES
        ]
    )


def skills_text(*, missing: str | None = None) -> str:
    rows = ["Discovered Agent Skills:", ""]
    for name in DOMAIN_BUNDLES:
        skill = f"skill-{name}"
        if skill == missing:
            continue
        rows.extend(
            [
                f"{skill} [Enabled]",
                "  Description: fixture",
                f"  Location:    /native/extensions/{name}/skills/{skill}/SKILL.md",
                "",
            ]
        )
    return "\n".join(rows)


def test_detection_reports_absent_cli_explicitly() -> None:
    detection = GeminiAdapter(which=lambda _name: None).detect()

    assert detection.present is False
    assert detection.executable is None
    assert detection.reason == "gemini CLI not present"


def test_gemini_installs_each_bundle_from_verified_release(
    desired: DesiredState,
) -> None:
    runner = QueueRunner(
        [command()] * 9
        + [command(stdout=extensions_json(desired)), command(stdout=skills_text())]
    )
    adapter = GeminiAdapter(runner=runner, which=lambda name: name)

    result = adapter.install(desired)

    assert result.state is ResultState.READY
    assert [row[:3] for row in runner.log[:9]] == [
        ["gemini", "extensions", "install"]
    ] * 9
    assert [row[3] for row in runner.log[:9]] == [
        str(desired.bundle_path(name)) for name in DOMAIN_BUNDLES
    ]
    assert all(
        "--consent" in row and "--skip-settings" in row for row in runner.log[:9]
    )
    assert all("--auto-update" not in row for row in runner.log)
    assert runner.log[-2:] == [
        ["gemini", "extensions", "list", "--output-format", "json"],
        ["gemini", "skills", "list", "--all"],
    ]
    assert result.installed_plugin_ids == DOMAIN_BUNDLES


def test_gemini_inspect_requires_selected_versions(desired: DesiredState) -> None:
    runner = QueueRunner(
        [
            command(stdout=extensions_json(desired, "0.1.0")),
            command(stdout=skills_text()),
        ]
    )

    result = GeminiAdapter(runner=runner, which=lambda name: name).inspect(desired)

    assert result.state is ResultState.DRIFTED
    assert "expected 0.2.0, found 0.1.0" in " ".join(result.errors)


def test_gemini_inspect_requires_every_declared_skill(desired: DesiredState) -> None:
    missing = f"skill-{DOMAIN_BUNDLES[-1]}"
    runner = QueueRunner(
        [
            command(stdout=extensions_json(desired)),
            command(stdout=skills_text(missing=missing)),
        ]
    )

    result = GeminiAdapter(runner=runner, which=lambda name: name).inspect(desired)

    assert result.state is ResultState.BLOCKED
    assert missing in " ".join(result.errors)


def test_gemini_rejects_noncanonical_inventory_before_mutation(
    desired: DesiredState,
) -> None:
    runner = QueueRunner([])
    invalid = DesiredState(**{**desired.__dict__, "contracts": desired.contracts[:-1]})

    result = GeminiAdapter(runner=runner).install(invalid)

    assert result.state is ResultState.BLOCKED
    assert runner.log == []


def test_gemini_uninstall_removes_only_canonical_receipt_ids() -> None:
    runner = QueueRunner([command()])
    receipt = HarnessReceipt(
        harness="gemini",
        adapter_version="1",
        native_version="0.52.0",
        plugin_ids=("manifest-docs", "not-manifest"),
        owned_entries=(),
        capabilities={},
        verified=True,
    )

    result = GeminiAdapter(runner=runner, which=lambda name: name).uninstall(receipt)

    assert result.state is ResultState.BLOCKED
    assert runner.log == [["gemini", "extensions", "uninstall", "manifest-docs"]]
    assert "non-canonical" in " ".join(result.errors)


def test_gemini_native_errors_are_redacted_and_aggregated(
    desired: DesiredState,
) -> None:
    runner = QueueRunner(
        [command(returncode=1, stderr="--token native-secret rejected")]
        + [command()] * 8
        + [command(stdout="[]"), command(stdout="No skills discovered.")]
    )

    result = GeminiAdapter(runner=runner, which=lambda name: name).install(desired)

    assert result.state is ResultState.BLOCKED
    assert "native-secret" not in " ".join(result.errors)
    assert "[REDACTED]" in " ".join(result.errors)

"""Antigravity native plugin adapter tests."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from pathlib import Path

import pytest

from manifest_agent.adapters.antigravity import AntigravityAdapter
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
                {"antigravity": CompatibilityStatus("imported")},
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
        requested_harnesses=("antigravity",),
    )


def inventory_json(*, source: str = "manifest", missing: str | None = None) -> str:
    return json.dumps(
        {
            "imports": [
                {
                    "name": name,
                    "source": source,
                    "components": ["skills"],
                }
                for name in DOMAIN_BUNDLES
                if name != missing
            ]
        }
    )


def test_detection_reports_absent_cli_explicitly() -> None:
    detection = AntigravityAdapter(which=lambda _name: None).detect()

    assert detection.present is False
    assert detection.executable is None
    assert detection.reason == "agy CLI not present"


def test_antigravity_validates_all_bundles_before_link_and_install(
    desired: DesiredState,
) -> None:
    runner = QueueRunner(
        [command()] * 9
        + [command()]
        + [command()] * 9
        + [command(stdout=inventory_json())]
    )

    result = AntigravityAdapter(runner=runner, which=lambda name: name).install(desired)

    assert result.state is ResultState.READY
    assert runner.log[:9] == [
        ["agy", "plugin", "validate", str(desired.bundle_path(name))]
        for name in DOMAIN_BUNDLES
    ]
    assert runner.log[9] == [
        "agy",
        "plugin",
        "link",
        "manifest",
        str(desired.release_root),
    ]
    assert runner.log[10:19] == [
        ["agy", "plugin", "install", f"{name}@manifest"] for name in DOMAIN_BUNDLES
    ]
    assert runner.log[-1] == ["agy", "plugin", "list"]
    assert result.installed_plugin_ids == DOMAIN_BUNDLES
    assert result.capabilities["manifest-workspace:skill:skill-manifest-workspace"] == (
        "verified"
    )


def test_antigravity_validation_failure_blocks_every_mutation(
    desired: DesiredState,
) -> None:
    validations = [command()] * 9
    validations[2] = command(
        returncode=1, stderr="--token antigravity-native-secret rejected"
    )
    validations[7] = command(returncode=1, stderr="second validation failed")
    runner = QueueRunner(validations)

    result = AntigravityAdapter(runner=runner).install(desired)

    assert result.state is ResultState.BLOCKED
    assert len(runner.log) == 9
    assert all(row[1:3] == ["plugin", "validate"] for row in runner.log)
    assert "antigravity-native-secret" not in " ".join(result.errors)
    assert "[REDACTED]" in " ".join(result.errors)
    assert len(result.errors) == 2


def test_antigravity_requires_exact_manifest_source_inventory(
    desired: DesiredState,
) -> None:
    runner = QueueRunner([command(stdout=inventory_json(source="other"))])

    result = AntigravityAdapter(runner=runner).inspect(desired)

    assert result.state is ResultState.BLOCKED
    assert "expected source manifest" in " ".join(result.errors)


def test_antigravity_redacts_untrusted_inventory_source(
    desired: DesiredState,
) -> None:
    runner = QueueRunner(
        [command(stdout=inventory_json(source="--token exposed-credential"))]
    )

    result = AntigravityAdapter(runner=runner).inspect(desired)

    assert result.state is ResultState.BLOCKED
    assert "exposed-credential" not in " ".join(result.errors)
    assert "[REDACTED]" in " ".join(result.errors)


def test_antigravity_rejects_noncanonical_inventory_before_native_validation(
    desired: DesiredState,
) -> None:
    runner = QueueRunner([])
    invalid = DesiredState(**{**desired.__dict__, "contracts": desired.contracts[:-1]})

    result = AntigravityAdapter(runner=runner).install(invalid)

    assert result.state is ResultState.BLOCKED
    assert runner.log == []


def test_antigravity_rejects_mismatched_generic_view_before_mutation(
    desired: DesiredState,
) -> None:
    view = desired.bundle_path(DOMAIN_BUNDLES[0]) / "plugin.json"
    document = json.loads(view.read_text(encoding="utf-8"))
    document["version"] = "0.1.0"
    view.write_text(json.dumps(document), encoding="utf-8")
    runner = QueueRunner([])

    result = AntigravityAdapter(runner=runner).install(desired)

    assert result.state is ResultState.BLOCKED
    assert "generic plugin view" in " ".join(result.errors)
    assert runner.log == []


def test_antigravity_uninstall_removes_only_canonical_receipt_ids() -> None:
    runner = QueueRunner([command()])
    receipt = HarnessReceipt(
        harness="antigravity",
        adapter_version="1",
        native_version="1.0.0",
        plugin_ids=("manifest-docs", "unrelated-plugin"),
        owned_entries=(),
        capabilities={},
        verified=True,
    )

    result = AntigravityAdapter(runner=runner).uninstall(receipt)

    assert result.state is ResultState.BLOCKED
    assert runner.log == [["agy", "plugin", "uninstall", "manifest-docs"]]
    assert "non-canonical" in " ".join(result.errors)

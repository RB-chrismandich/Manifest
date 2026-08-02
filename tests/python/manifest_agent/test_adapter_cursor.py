"""Cursor native marketplace adapter tests."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from pathlib import Path

import pytest

from manifest_agent.adapters.cursor import CursorAdapter
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


class ProbeFailureRunner(QueueRunner):
    def __init__(self, marketplace: CommandResult, error: Exception) -> None:
        super().__init__([marketplace])
        self.error = error

    def run(
        self,
        argv: Sequence[str],
        *,
        env: Mapping[str, str] | None = None,
    ) -> CommandResult:
        if self.results:
            return super().run(argv, env=env)
        self.log.append(list(argv))
        raise self.error


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
                {"cursor": CompatibilityStatus("native")},
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
        requested_harnesses=("cursor",),
    )


def marketplace_json(
    desired: DesiredState,
    *,
    git_url: str | None = None,
    git_ref: str | None = None,
) -> str:
    return json.dumps(
        [
            {
                "name": "manifest",
                "gitUrl": git_url or desired.repository_url,
                "gitRef": git_ref or desired.source_commit,
                "scope": "user",
                "lastIndexedAt": 1782629316510,
            }
        ]
    )


def plugin_help() -> str:
    return """Usage: agent plugin [options] [command]

Manage plugins and plugin marketplaces

Commands:
  marketplace  Manage plugin marketplaces
"""


def test_detection_reports_absent_cli_explicitly() -> None:
    detection = CursorAdapter(which=lambda _name: None).detect()

    assert detection.present is False
    assert detection.executable is None
    assert detection.reason == "cursor-agent CLI not present"


def test_cursor_indexes_immutable_marketplace_ref(
    desired: DesiredState, tmp_path: Path
) -> None:
    runner = QueueRunner(
        [
            command(),
            command(stdout=marketplace_json(desired)),
            command(stdout=plugin_help()),
        ]
    )
    adapter = CursorAdapter(
        runner=runner, which=lambda name: name, env={"HOME": str(tmp_path)}
    )

    result = adapter.install(desired)

    assert runner.log[0] == [
        "cursor-agent",
        "plugin",
        "marketplace",
        "add",
        desired.repository_url,
        "--git-ref",
        desired.source_commit,
    ]
    assert runner.log[1] == [
        "cursor-agent",
        "plugin",
        "marketplace",
        "list",
        "--format",
        "json",
    ]
    assert result.state is ResultState.DEGRADED
    assert runner.log[2] == ["cursor-agent", "plugin", "--help"]
    assert result.installed_plugin_ids == ()
    assert result.capabilities["marketplace:manifest"] == "verified"
    assert result.capabilities["plugins.inventory"] == "unsupported"
    assert result.capabilities["plugins.activation"] == "unsupported"
    assert "no documented user-scope plugin inventory" in " ".join(result.errors)


def test_cursor_dirty_local_source_is_blocked_before_indexing(
    desired: DesiredState,
) -> None:
    dirty = DesiredState(**{**desired.__dict__, "source_dirty": True})
    runner = QueueRunner([])

    result = CursorAdapter(runner=runner).install(dirty)

    assert result.state is ResultState.BLOCKED
    assert "dirty" in " ".join(result.errors)
    assert runner.log == []


def test_cursor_inspect_requires_exact_marketplace_identity(
    desired: DesiredState,
) -> None:
    runner = QueueRunner(
        [
            command(
                stdout=marketplace_json(desired, git_url="https://other.invalid/repo")
            )
        ]
    )

    result = CursorAdapter(runner=runner, which=lambda name: name).inspect(desired)

    assert result.state is ResultState.BLOCKED
    assert "source mismatch" in " ".join(result.errors)


def test_cursor_real_marketplace_schema_degrades_when_inventory_api_is_absent(
    desired: DesiredState,
) -> None:
    runner = QueueRunner(
        [command(stdout=marketplace_json(desired)), command(stdout=plugin_help())]
    )

    result = CursorAdapter(runner=runner, which=lambda name: name).inspect(desired)

    assert result.state is ResultState.DEGRADED
    assert result.capabilities["plugins.inventory"] == "unsupported"
    assert result.capabilities["plugins.activation"] == "unsupported"


def test_cursor_nonzero_inventory_discovery_is_redacted_blocked(
    desired: DesiredState,
) -> None:
    runner = QueueRunner(
        [
            command(stdout=marketplace_json(desired)),
            command(returncode=2, stderr="--token native-secret rejected"),
        ]
    )

    result = CursorAdapter(runner=runner, which=lambda name: name).inspect(desired)

    assert result.state is ResultState.BLOCKED
    assert "native-secret" not in " ".join(result.errors)
    assert "[REDACTED]" in " ".join(result.errors)


@pytest.mark.parametrize(
    "error",
    [FileNotFoundError("cursor-agent missing"), PermissionError("permission denied")],
)
def test_cursor_inventory_probe_execution_failure_is_blocked(
    desired: DesiredState,
    error: Exception,
) -> None:
    runner = ProbeFailureRunner(command(stdout=marketplace_json(desired)), error)

    result = CursorAdapter(runner=runner, which=lambda name: name).inspect(desired)

    assert result.state is ResultState.BLOCKED
    assert runner.log[-1] == ["cursor-agent", "plugin", "--help"]


def test_cursor_malformed_inventory_probe_is_blocked(desired: DesiredState) -> None:
    runner = QueueRunner(
        [command(stdout=marketplace_json(desired)), command(stdout="not help output")]
    )

    result = CursorAdapter(runner=runner, which=lambda name: name).inspect(desired)

    assert result.state is ResultState.BLOCKED
    assert "valid command inventory" in " ".join(result.errors)


def test_cursor_rejects_noncanonical_inventory_before_mutation(
    desired: DesiredState,
) -> None:
    invalid = DesiredState(**{**desired.__dict__, "contracts": desired.contracts[:-1]})
    runner = QueueRunner([])

    result = CursorAdapter(runner=runner).install(invalid)

    assert result.state is ResultState.BLOCKED
    assert runner.log == []


def test_cursor_uninstall_removes_only_receipt_owned_marketplace_url(
    desired: DesiredState,
) -> None:
    runner = QueueRunner([command()])
    receipt = HarnessReceipt(
        harness="cursor",
        adapter_version="1",
        native_version="2026.07.23",
        plugin_ids=DOMAIN_BUNDLES,
        owned_entries=(
            OwnedEntry("marketplace", desired.repository_url, "manifest"),
            OwnedEntry("cache", "unrelated", "other"),
        ),
        capabilities={},
        verified=True,
    )

    result = CursorAdapter(
        runner=runner,
        which=lambda name: name,
        repository_url=desired.repository_url,
    ).uninstall(receipt)

    assert result.state is ResultState.READY
    assert runner.log == [
        [
            "cursor-agent",
            "plugin",
            "marketplace",
            "remove",
            desired.repository_url,
        ]
    ]


def test_cursor_uninstall_without_owned_marketplace_is_non_mutating() -> None:
    runner = QueueRunner([])
    receipt = HarnessReceipt(
        harness="cursor",
        adapter_version="1",
        native_version="2026.07.23",
        plugin_ids=DOMAIN_BUNDLES,
        owned_entries=(),
        capabilities={},
        verified=True,
    )

    result = CursorAdapter(runner=runner).uninstall(receipt)

    assert result.state is ResultState.BLOCKED
    assert "owned marketplace" in " ".join(result.errors)
    assert runner.log == []


@pytest.mark.parametrize(
    ("identifier", "marker"),
    [
        ("https://other.invalid/repo", "manifest"),
        ("ssh://git@other.invalid/repo", "manifest"),
        ("https://example.invalid/Manifest.git", "receipt"),
        ("https://example.invalid/Manifest.git?ref=main", "manifest"),
        ("https://example.invalid/Manifest.git#forged", "manifest"),
    ],
)
def test_cursor_uninstall_rejects_forged_marketplace_receipt_without_invocation(
    desired: DesiredState,
    identifier: str,
    marker: str,
) -> None:
    runner = QueueRunner([])
    receipt = HarnessReceipt(
        harness="cursor",
        adapter_version="1",
        native_version="2026.07.23",
        plugin_ids=DOMAIN_BUNDLES,
        owned_entries=(OwnedEntry("marketplace", identifier, marker),),
        capabilities={},
        verified=True,
    )

    result = CursorAdapter(
        runner=runner, repository_url=desired.repository_url
    ).uninstall(receipt)

    assert result.state is ResultState.BLOCKED
    assert runner.log == []


def test_cursor_native_errors_are_redacted(desired: DesiredState) -> None:
    runner = QueueRunner(
        [command(returncode=1, stderr="Authorization: Bearer native-secret")]
    )

    result = CursorAdapter(runner=runner, which=lambda name: name).install(desired)

    assert result.state is ResultState.BLOCKED
    assert "native-secret" not in " ".join(result.errors)
    assert "[REDACTED]" in " ".join(result.errors)

"""Harness-native MCP configuration tests."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from pathlib import Path

import pytest

from manifest_agent.adapters.antigravity import AntigravityAdapter
from manifest_agent.adapters.claude import ClaudeAdapter
from manifest_agent.adapters.codex import CodexAdapter
from manifest_agent.adapters.cursor import CursorAdapter
from manifest_agent.adapters.devin import DevinAdapter
from manifest_agent.adapters.gemini import GeminiAdapter
from manifest_agent.capabilities import CapabilityPlan, McpDefinition, load_mcp_catalog
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


class RecordingRunner:
    def __init__(self, results: Sequence[CommandResult] = ()) -> None:
        self.results = list(results)
        self.calls: list[tuple[str, ...]] = []

    def run(
        self,
        argv: Sequence[str],
        *,
        env: Mapping[str, str] | None = None,
    ) -> CommandResult:
        del env
        command = tuple(argv)
        self.calls.append(command)
        if self.results:
            result = self.results.pop(0)
            return CommandResult(
                command, result.returncode, result.stdout, result.stderr
            )
        return CommandResult(command, 0, "", "")


def _plan(*, optional: tuple[str, ...] = (), selected: frozenset[str] = frozenset()):
    catalog = load_mcp_catalog()
    names = ("context7", *optional)
    return CapabilityPlan(
        required_mcp=(),
        default_mcp=("context7",),
        optional_mcp=optional,
        required_executables=(),
        default_executables=(),
        optional_executables=(),
        selected_optional=selected,
        mcp_definitions={name: catalog[name] for name in names},
        executable_definitions={},
    )


def _antigravity_plan(tier: CapabilityTier) -> CapabilityPlan:
    values = {
        CapabilityTier.REQUIRED: (),
        CapabilityTier.DEFAULT: (),
        CapabilityTier.OPTIONAL: (),
    }
    values[tier] = ("context7",)
    selected = (
        frozenset({"context7"}) if tier is CapabilityTier.OPTIONAL else frozenset()
    )
    return CapabilityPlan(
        required_mcp=values[CapabilityTier.REQUIRED],
        default_mcp=values[CapabilityTier.DEFAULT],
        optional_mcp=values[CapabilityTier.OPTIONAL],
        required_executables=(),
        default_executables=(),
        optional_executables=(),
        selected_optional=selected,
        mcp_definitions={"context7": load_mcp_catalog()["context7"]},
        executable_definitions={},
    )


def _cursor_desired(tmp_path: Path) -> DesiredState:
    contracts = []
    for name in DOMAIN_BUNDLES:
        mcp = dict.fromkeys(CapabilityTier, ())
        if name == "manifest-workspace":
            mcp = {**mcp, CapabilityTier.DEFAULT: ("context7",)}
        contracts.append(
            BundleContract(
                name,
                "0.2.0",
                "fixture",
                "fixture",
                Components("skills", (), (), (), (), ()),
                Capabilities(mcp, dict.fromkeys(CapabilityTier, ())),
                {"cursor": CompatibilityStatus("generated")},
                Provenance("https://example.invalid", "MIT", "LICENSE", "test"),
            )
        )
    return DesiredState(
        release_version="0.2.0",
        source_commit="a" * 40,
        source=str(tmp_path),
        marketplace_source=MarketplaceSource(
            MarketplaceSourceKind.GIT,
            "https://example.invalid/Manifest.git",
            "a" * 40,
        ),
        release_root=tmp_path,
        repository_url="https://example.invalid/Manifest.git",
        source_dirty=False,
        archive_sha256="b" * 64,
        contracts=tuple(contracts),
        selected_optional=frozenset(),
        requested_harnesses=("cursor",),
    )


@pytest.mark.parametrize(
    ("adapter_type", "expected"),
    [
        (
            ClaudeAdapter,
            (
                "claude",
                "mcp",
                "add",
                "--scope",
                "user",
                "--transport",
                "http",
                "context7",
                "https://mcp.context7.com/mcp/oauth",
            ),
        ),
        (
            CodexAdapter,
            (
                "codex",
                "mcp",
                "add",
                "context7",
                "--url",
                "https://mcp.context7.com/mcp/oauth",
            ),
        ),
        (
            GeminiAdapter,
            (
                "gemini",
                "mcp",
                "add",
                "--scope",
                "user",
                "--transport",
                "http",
                "context7",
                "https://mcp.context7.com/mcp/oauth",
            ),
        ),
        (
            DevinAdapter,
            (
                "devin",
                "mcp",
                "add",
                "--scope",
                "user",
                "--transport",
                "http",
                "context7",
                "https://mcp.context7.com/mcp/oauth",
            ),
        ),
    ],
)
def test_documented_native_mcp_commands_are_exact(
    adapter_type, expected, tmp_path: Path
) -> None:
    runner = RecordingRunner()
    adapter = adapter_type(
        runner=runner, which=lambda name: name, env={"HOME": str(tmp_path)}
    )

    result = adapter.apply_capabilities(_plan())

    assert result.state is ResultState.READY
    assert runner.calls == [expected]
    assert result.capabilities["mcp:context7"] == "installed-by-manifest"


def test_native_mcp_failure_is_redacted_and_tier_truthful(tmp_path: Path) -> None:
    runner = RecordingRunner(
        [CommandResult(("fixture",), 1, "", "--token native-secret rejected")]
    )

    result = ClaudeAdapter(
        runner=runner,
        which=lambda name: name,
        env={"HOME": str(tmp_path)},
    ).apply_capabilities(_plan())

    assert result.state is ResultState.DEGRADED
    assert result.capabilities["mcp:context7"] == "failed"
    assert "native-secret" not in " ".join(result.errors)
    assert "[REDACTED]" in " ".join(result.errors)


def test_existing_http_mcp_requires_exact_transport_identity() -> None:
    runner = RecordingRunner()

    result = ClaudeAdapter(
        runner=runner,
        which=lambda name: name,
        native_mcp_inventory=("context7",),
    ).apply_capabilities(_plan())

    assert result.state is ResultState.DEGRADED
    assert runner.calls == []
    assert "transport identity" in " ".join(result.errors)


def test_matching_http_transport_inventory_is_preserved() -> None:
    runner = RecordingRunner()
    context7 = McpDefinition("context7", "http", "https://mcp.context7.com/mcp/oauth")

    result = ClaudeAdapter(
        runner=runner,
        which=lambda name: name,
        native_mcp_inventory={"context7": context7},
    ).apply_capabilities(_plan())

    assert result.state is ResultState.READY
    assert result.capabilities["mcp:context7"] == "verified"
    assert runner.calls == []


def test_cursor_atomic_merge_and_receipt_owned_removal_preserve_unrelated_values(
    tmp_path: Path,
) -> None:
    path = tmp_path / ".cursor" / "mcp.json"
    path.parent.mkdir(parents=True)
    unrelated = {
        "command": "foreign-server",
        "args": ["--flag", {"nested": [1, True, None]}],
        "env": {"FOREIGN_SETTING": "unchanged"},
    }
    path.write_text(
        json.dumps({"mcpServers": {"foreign": unrelated}, "other": [3, 2, 1]}),
        encoding="utf-8",
    )
    adapter = CursorAdapter(
        runner=RecordingRunner(),
        which=lambda name: name,
        env={"HOME": str(tmp_path)},
    )

    installed = adapter.apply_capabilities(_plan())
    after_install = json.loads(path.read_text(encoding="utf-8"))
    receipt = HarnessReceipt(
        "cursor",
        "1",
        "1",
        (),
        installed.owned_entries,
        installed.capabilities,
        True,
    )
    removed = adapter.remove_capabilities(receipt)
    after_remove = json.loads(path.read_text(encoding="utf-8"))

    assert installed.state is ResultState.READY
    assert installed.capabilities["mcp:context7"] == "installed-by-manifest"
    assert after_install["mcpServers"]["manifest-context7"] == {
        "url": "https://mcp.context7.com/mcp/oauth"
    }
    assert json.dumps(after_install["mcpServers"]["foreign"]) == json.dumps(unrelated)
    assert removed.state is ResultState.READY
    assert "manifest-context7" not in after_remove["mcpServers"]
    assert json.dumps(after_remove["mcpServers"]["foreign"]) == json.dumps(unrelated)
    assert after_remove["other"] == [3, 2, 1]
    assert not list(path.parent.glob("*.tmp"))


def test_cursor_preserves_matching_preexisting_manifest_entry(tmp_path: Path) -> None:
    path = tmp_path / ".cursor" / "mcp.json"
    path.parent.mkdir(parents=True)
    path.write_text(
        json.dumps(
            {
                "mcpServers": {
                    "manifest-context7": {"url": "https://mcp.context7.com/mcp/oauth"}
                }
            }
        ),
        encoding="utf-8",
    )

    result = CursorAdapter(env={"HOME": str(tmp_path)}).apply_capabilities(_plan())

    assert result.state is ResultState.READY
    assert result.capabilities["mcp:context7"] == "verified"


def test_cursor_conflicting_manifest_entry_is_not_overwritten(tmp_path: Path) -> None:
    path = tmp_path / ".cursor" / "mcp.json"
    path.parent.mkdir(parents=True)
    original = {"url": "https://user.example/mcp"}
    path.write_text(
        json.dumps({"mcpServers": {"manifest-context7": original}}),
        encoding="utf-8",
    )

    result = CursorAdapter(env={"HOME": str(tmp_path)}).apply_capabilities(_plan())

    assert result.state is ResultState.DEGRADED
    assert (
        json.loads(path.read_text(encoding="utf-8"))["mcpServers"]["manifest-context7"]
        == original
    )


def test_antigravity_reports_exact_default_mcp_as_degraded_when_not_declared() -> None:
    result = AntigravityAdapter(
        runner=RecordingRunner(),
        which=lambda name: name,
        native_mcp_inventory=(),
    ).apply_capabilities(_plan())

    assert result.state is ResultState.DEGRADED
    assert result.capabilities["mcp:context7"] == "failed"
    assert "context7" in " ".join(result.errors)


@pytest.mark.parametrize(
    ("tier", "state", "field"),
    [
        (CapabilityTier.REQUIRED, ResultState.BLOCKED, "errors"),
        (CapabilityTier.DEFAULT, ResultState.DEGRADED, "errors"),
        (CapabilityTier.OPTIONAL, ResultState.READY, "warnings"),
    ],
)
def test_antigravity_unsupported_http_mcp_uses_normal_tier_policy(
    tier: CapabilityTier, state: ResultState, field: str
) -> None:
    result = AntigravityAdapter(
        native_mcp_inventory=(), which=lambda name: name
    ).apply_capabilities(_antigravity_plan(tier))

    assert result.state is state
    assert result.capabilities["mcp:context7"] == (
        "missing" if tier is CapabilityTier.OPTIONAL else "failed"
    )
    assert "context7" in " ".join(getattr(result, field))


def test_normal_cursor_lifecycle_applies_and_removes_owned_mcp(tmp_path: Path) -> None:
    desired = _cursor_desired(tmp_path)
    marketplace = json.dumps(
        [
            {
                "name": "manifest",
                "gitUrl": desired.repository_url,
                "gitRef": desired.source_commit,
                "scope": "user",
            }
        ]
    )
    runner = RecordingRunner(
        [
            CommandResult(("fixture",), 0, "", ""),
            CommandResult(("fixture",), 0, marketplace, ""),
            CommandResult(("fixture",), 0, "Commands:\n  marketplace\n", ""),
            CommandResult(("fixture",), 0, "", ""),
        ]
    )
    adapter = CursorAdapter(
        runner=runner,
        which=lambda name: name,
        env={"HOME": str(tmp_path)},
        repository_url=desired.repository_url,
    )

    installed = adapter.install(desired)
    path = tmp_path / ".cursor" / "mcp.json"
    receipt = HarnessReceipt(
        "cursor",
        "1",
        "1",
        DOMAIN_BUNDLES,
        (
            *installed.owned_entries,
            OwnedEntry("marketplace", desired.repository_url, "manifest", None, None),
        ),
        installed.capabilities,
        True,
    )
    removed = adapter.uninstall(receipt)

    assert json.loads(path.read_text(encoding="utf-8"))["mcpServers"] == {}
    assert installed.capabilities["mcp:context7"] == "installed-by-manifest"
    assert [(entry.kind, entry.identifier) for entry in installed.owned_entries] == [
        ("mcp", "context7")
    ]
    assert removed.state is ResultState.READY
    assert runner.calls[-1] == (
        "cursor-agent",
        "plugin",
        "marketplace",
        "remove",
        desired.repository_url,
    )


def test_native_existing_is_only_checked_when_explicitly_selected() -> None:
    unselected = AntigravityAdapter(
        native_mcp_inventory=(), which=lambda name: name
    ).apply_capabilities(_plan(optional=("stitch",)))
    selected = AntigravityAdapter(
        native_mcp_inventory=("mcp_stitch_native",), which=lambda name: name
    ).apply_capabilities(_plan(optional=("stitch",), selected=frozenset({"stitch"})))

    assert "mcp:stitch" not in unselected.capabilities
    assert selected.state is ResultState.DEGRADED  # Context7 remains unsupported.
    assert selected.capabilities["mcp:stitch"] == "verified"


def test_absent_selected_native_existing_warns_without_inventing_transport() -> None:
    runner = RecordingRunner()
    result = ClaudeAdapter(
        runner=runner,
        which=lambda name: name,
        native_mcp_inventory=(),
    ).apply_capabilities(_plan(optional=("stitch",), selected=frozenset({"stitch"})))

    assert runner.calls == [
        (
            "claude",
            "mcp",
            "add",
            "--scope",
            "user",
            "--transport",
            "http",
            "context7",
            "https://mcp.context7.com/mcp/oauth",
        )
    ]
    assert result.state is ResultState.READY
    assert result.capabilities["mcp:stitch"] == "missing"
    assert "native Stitch setup" in " ".join(result.warnings)

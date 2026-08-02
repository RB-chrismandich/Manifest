"""Destructive uninstall preflight regression tests."""

from __future__ import annotations

import hashlib
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
from manifest_agent.capabilities import (
    CapabilityPlan,
    load_executable_catalog,
    load_mcp_catalog,
)
from manifest_agent.contracts import DOMAIN_BUNDLES
from manifest_agent.models import (
    CommandResult,
    HarnessReceipt,
    OwnedEntry,
    ResultState,
)
from tests.python.manifest_agent.test_mcp_configuration import RecordingRunner


class GraphifyLifecycleRunner(RecordingRunner):
    """Model Graphify installation while accepting fake native removals."""

    def __init__(self, *, installed: bool = False) -> None:
        super().__init__()
        self.installed = installed

    def run(
        self,
        argv: Sequence[str],
        *,
        env: Mapping[str, str] | None = None,
    ) -> CommandResult:
        del env
        command = tuple(argv)
        self.calls.append(command)
        if command == ("uv", "tool", "install", "graphifyy==0.9.31"):
            self.installed = True
        if command == ("graphify", "--version"):
            return CommandResult(command, 0, "graphify 0.9.31\n", "")
        return CommandResult(command, 0, "", "")


def _graphify_plan() -> CapabilityPlan:
    recipe = load_executable_catalog()["graphify"]
    return CapabilityPlan(
        required_mcp=(),
        default_mcp=(),
        optional_mcp=(),
        required_executables=(),
        default_executables=("graphify",),
        optional_executables=(),
        selected_optional=frozenset(),
        mcp_definitions={},
        executable_definitions={"graphify": recipe},
    )


def _public_receipt_checksum(
    kind: str, identifier: str, target_path: str | None
) -> str:
    payload = json.dumps(
        {
            "capability": f"{kind}:{identifier}",
            "identifier": identifier,
            "kind": kind,
            "ownership_marker": "manifest",
            "status": "installed-by-manifest",
            "target_path": target_path,
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return hashlib.sha256(payload).hexdigest()


def test_cursor_incomplete_receipt_cannot_remove_owned_mcp(tmp_path: Path) -> None:
    repository_url = "https://example.invalid/Manifest.git"
    path = tmp_path / ".cursor" / "mcp.json"
    path.parent.mkdir(parents=True)
    original = {
        "mcpServers": {
            "manifest-context7": {"url": load_mcp_catalog()["context7"].url},
            "unrelated": {"command": "other"},
        }
    }
    path.write_text(json.dumps(original), encoding="utf-8")
    runner = RecordingRunner()
    receipt = HarnessReceipt(
        "cursor",
        "1",
        "1",
        DOMAIN_BUNDLES[:-1],
        (
            OwnedEntry("mcp", "context7", "manifest", str(path), None),
            OwnedEntry("marketplace", repository_url, "manifest", None, None),
        ),
        {"mcp:context7": "installed-by-manifest"},
        True,
    )

    result = CursorAdapter(
        runner=runner,
        env={"HOME": str(tmp_path)},
        repository_url=repository_url,
    ).uninstall(receipt)

    assert result.state is ResultState.BLOCKED
    assert runner.calls == []
    assert json.loads(path.read_text(encoding="utf-8")) == original


@pytest.mark.parametrize(
    ("adapter_type", "harness"),
    [
        (AntigravityAdapter, "antigravity"),
        (ClaudeAdapter, "claude"),
        (CodexAdapter, "codex"),
        (DevinAdapter, "devin"),
        (GeminiAdapter, "gemini"),
    ],
)
def test_incomplete_receipt_cannot_remove_owned_graphify(
    adapter_type, harness: str
) -> None:
    runner = RecordingRunner()
    receipt = HarnessReceipt(
        harness,
        "1",
        "1",
        DOMAIN_BUNDLES[:-1],
        (OwnedEntry("executable", "graphify", "manifest", None, None),),
        {"executable:graphify": "installed-by-manifest"},
        True,
    )

    result = adapter_type(runner=runner, which=lambda name: name).uninstall(receipt)

    assert result.state is ResultState.BLOCKED
    assert runner.calls == []


@pytest.mark.parametrize(
    ("adapter_type", "harness"),
    [(ClaudeAdapter, "claude"), (CodexAdapter, "codex")],
)
def test_invalid_marketplace_ownership_blocks_graphify_removal(
    adapter_type, harness: str
) -> None:
    runner = RecordingRunner()
    receipt = HarnessReceipt(
        harness,
        "1",
        "1",
        DOMAIN_BUNDLES,
        (
            OwnedEntry("marketplace", "not-manifest", "receipt", None, None),
            OwnedEntry("executable", "graphify", "manifest", None, None),
        ),
        {"executable:graphify": "installed-by-manifest"},
        True,
    )

    result = adapter_type(runner=runner, which=lambda name: name).uninstall(receipt)

    assert result.state is ResultState.BLOCKED
    assert runner.calls == []


def test_gemini_forged_graphify_ownership_is_non_mutating() -> None:
    runner = GraphifyLifecycleRunner(installed=True)
    receipt = HarnessReceipt(
        "gemini",
        "1",
        "1",
        DOMAIN_BUNDLES,
        (
            OwnedEntry(
                "executable",
                "graphify",
                "manifest",
                None,
                _public_receipt_checksum("executable", "graphify", None),
            ),
        ),
        {"executable:graphify": "installed-by-manifest"},
        True,
    )

    result = GeminiAdapter(
        runner=runner, which=lambda name: name if name in {"uv", "graphify"} else None
    ).uninstall(receipt)

    assert result.state is ResultState.BLOCKED
    assert runner.calls == []


def test_cursor_forged_mcp_ownership_is_non_mutating(tmp_path: Path) -> None:
    repository_url = "https://example.invalid/Manifest.git"
    path = tmp_path / ".cursor" / "mcp.json"
    path.parent.mkdir(parents=True)
    original = {
        "mcpServers": {"manifest-context7": {"url": load_mcp_catalog()["context7"].url}}
    }
    path.write_text(json.dumps(original), encoding="utf-8")
    runner = RecordingRunner()
    forged_mcp = OwnedEntry(
        "mcp",
        "context7",
        "manifest",
        str(path),
        _public_receipt_checksum("mcp", "context7", str(path)),
    )
    receipt = HarnessReceipt(
        "cursor",
        "1",
        "1",
        DOMAIN_BUNDLES,
        (
            forged_mcp,
            OwnedEntry("marketplace", repository_url, "manifest", None, None),
        ),
        {"mcp:context7": "installed-by-manifest"},
        True,
    )

    result = CursorAdapter(
        runner=runner,
        env={"HOME": str(tmp_path)},
        repository_url=repository_url,
    ).uninstall(receipt)

    assert result.state is ResultState.BLOCKED
    assert runner.calls == []
    assert json.loads(path.read_text(encoding="utf-8")) == original


def test_genuine_graphify_installation_receipt_can_remove_owned_tool(
    tmp_path: Path,
) -> None:
    runner = GraphifyLifecycleRunner()
    env = {"HOME": str(tmp_path)}
    adapter = GeminiAdapter(
        runner=runner,
        which=lambda name: name if name == "uv" or runner.installed else None,
        env=env,
    )
    installed = adapter.apply_capabilities(_graphify_plan())
    receipt = HarnessReceipt(
        "gemini",
        "1",
        "1",
        DOMAIN_BUNDLES,
        installed.owned_entries,
        installed.capabilities,
        True,
    )

    key_path = tmp_path / ".local" / "state" / "manifest" / "ownership.key"
    restarted = GeminiAdapter(
        runner=runner,
        which=lambda name: name if name == "uv" or runner.installed else None,
        env=env,
    )
    removed = restarted.uninstall(receipt)

    assert removed.state is ResultState.READY
    assert key_path.stat().st_mode & 0o777 == 0o600
    secret = key_path.read_bytes()
    assert len(secret) == 32
    assert installed.owned_entries[0].previous_checksum != secret.hex()
    assert ("uv", "tool", "uninstall", "graphifyy") in runner.calls


@pytest.mark.parametrize("damage", ["missing", "corrupt"])
def test_missing_or_corrupt_ownership_secret_fails_closed(
    tmp_path: Path, damage: str
) -> None:
    runner = GraphifyLifecycleRunner()
    env = {"HOME": str(tmp_path)}
    adapter = GeminiAdapter(
        runner=runner,
        which=lambda name: name if name == "uv" or runner.installed else None,
        env=env,
    )
    installed = adapter.apply_capabilities(_graphify_plan())
    receipt = HarnessReceipt(
        "gemini",
        "1",
        "1",
        DOMAIN_BUNDLES,
        installed.owned_entries,
        installed.capabilities,
        True,
    )
    key_path = tmp_path / ".local" / "state" / "manifest" / "ownership.key"
    if damage == "missing":
        key_path.unlink()
    else:
        key_path.write_bytes(b"corrupt")
    calls_before = tuple(runner.calls)

    removed = GeminiAdapter(runner=runner, env=env).uninstall(receipt)

    assert removed.state is ResultState.BLOCKED
    assert tuple(runner.calls) == calls_before
    if damage == "missing":
        assert not key_path.exists()
    else:
        assert key_path.read_bytes() == b"corrupt"


def test_matching_preexisting_graphify_is_not_owned_or_removed() -> None:
    runner = GraphifyLifecycleRunner(installed=True)
    adapter = GeminiAdapter(
        runner=runner,
        which=lambda name: name if name in {"uv", "graphify"} else None,
    )
    inspected = adapter.apply_capabilities(_graphify_plan())
    receipt = HarnessReceipt(
        "gemini",
        "1",
        "1",
        DOMAIN_BUNDLES,
        inspected.owned_entries,
        inspected.capabilities,
        True,
    )

    removed = adapter.uninstall(receipt)

    assert removed.state is ResultState.READY
    assert inspected.capabilities["executable:graphify"] == "verified"
    assert inspected.owned_entries == ()
    assert ("uv", "tool", "uninstall", "graphifyy") not in runner.calls

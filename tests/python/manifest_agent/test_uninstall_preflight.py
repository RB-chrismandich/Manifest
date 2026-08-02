"""Destructive uninstall preflight regression tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from manifest_agent.adapters.antigravity import AntigravityAdapter
from manifest_agent.adapters.claude import ClaudeAdapter
from manifest_agent.adapters.codex import CodexAdapter
from manifest_agent.adapters.cursor import CursorAdapter
from manifest_agent.adapters.devin import DevinAdapter
from manifest_agent.adapters.gemini import GeminiAdapter
from manifest_agent.capabilities import load_mcp_catalog
from manifest_agent.contracts import DOMAIN_BUNDLES
from manifest_agent.models import HarnessReceipt, OwnedEntry, ResultState
from tests.python.manifest_agent.test_mcp_configuration import RecordingRunner


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

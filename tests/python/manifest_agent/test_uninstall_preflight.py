"""Destructive uninstall preflight regression tests."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from manifest_agent.adapters.cursor import CursorAdapter
from manifest_agent.capabilities import load_mcp_catalog
from manifest_agent.contracts import DOMAIN_BUNDLES
from manifest_agent.models import HarnessReceipt, OwnedEntry, ResultState
from tests.python.manifest_agent.test_mcp_configuration import RecordingRunner


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

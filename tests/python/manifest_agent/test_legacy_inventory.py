"""The legacy inventory is complete, machine-readable, and conservative."""

from __future__ import annotations

from pathlib import Path

import pytest

from manifest_agent.migration import load_legacy_inventory, scan_legacy_state
from manifest_agent.paths import xdg_paths


@pytest.fixture
def legacy_inventory():
    return load_legacy_inventory()


def test_every_bootstrap_output_class_has_a_disposition(legacy_inventory):
    assert set(legacy_inventory.categories) == {
        "skills",
        "agents",
        "guidance",
        "hooks",
        "permissions",
        "mcp",
        "scripts",
        "optional_tools",
        "configuration",
        "diagnostics",
        "updates",
        "uninstall",
    }


def test_destructive_entries_require_ownership_proof(legacy_inventory):
    for entry in legacy_inventory.entries:
        if entry.action in {"disable", "remove"}:
            assert entry.ownership_proof.type in {
                "symlink-target",
                "deploy-stamp",
                "generated-hash",
                "exact-marker",
            }


def test_inventory_covers_known_legacy_home_outputs(legacy_inventory):
    identifiers = {entry.id for entry in legacy_inventory.entries}
    assert {
        "claude-agent-outputs-link",
        "cursor-hooks",
        "cursor-agents",
        "cursor-scripts-link",
        "cursor-rule-manifest",
        "gemini-scripts-link",
        "codex-scripts-link",
    } <= identifiers


def test_placeholder_generated_hash_is_rejected(tmp_path: Path):
    inventory = tmp_path / "inventory.yml"
    inventory.write_text(
        "categories: [skills, agents, guidance, hooks, permissions, mcp, scripts, optional_tools, configuration, diagnostics, updates, uninstall]\n"
        "entries:\n  - id: bad\n    category: scripts\n    path: ~/.local/bin/bad\n"
        "    harnesses: [claude]\n    classification: bundle-owned\n    destination: domain-bundle-runtime\n"
        "    ownership_proof: {type: generated-hash, value: placeholder}\n"
        "    action: remove\n    recovery: restore-file\n    parity_test: test\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="exact SHA-256"):
        load_legacy_inventory(inventory)


def test_unknown_files_are_always_user_owned(tmp_path: Path, monkeypatch):
    home = tmp_path / "home"
    custom = home / ".claude" / "custom.txt"
    custom.parent.mkdir(parents=True)
    custom.write_text("do not touch", encoding="utf-8")
    monkeypatch.setenv("HOME", str(home))

    result = scan_legacy_state(xdg_paths(), home=home)

    assert result.entry("~/.claude/custom.txt").classification == "user-owned"


def test_renderer_rejects_shared_runtime_destinations(tmp_path: Path):
    inventory = tmp_path / "inventory.yml"
    inventory.write_text(
        "categories: [skills]\nentries:\n"
        "  - id: bad\n    category: skills\n    path: ~/.claude/skills\n"
        "    harnesses: [claude]\n"
        "    classification: bundle-owned\n    destination: manifest-core/runtime\n"
        "    ownership_proof: {type: exact-marker, value: manifest}\n"
        "    action: disable\n    recovery: restore\n    parity_test: test\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="forbidden destination"):
        load_legacy_inventory(inventory)

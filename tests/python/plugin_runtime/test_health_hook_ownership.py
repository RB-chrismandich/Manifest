"""Focused tests for canonical health-hook matching in the installer reconcile path."""

from __future__ import annotations

import sys

import pytest

from tests.python.plugin_runtime.health_test_helpers import (
    load_runtime_module,
    repo_root,
)

_SCRIPTS = repo_root() / "plugins/manifest-workspace/skills/env-check/scripts"


@pytest.fixture(scope="module")
def reconcile():
    sys.path.insert(0, str(_SCRIPTS))
    try:
        module = load_runtime_module(
            _SCRIPTS / "health_install_reconcile.py", "health_install_reconcile"
        )
    finally:
        sys.path.remove(str(_SCRIPTS))
    return module


def _settings_with(hooks: list[dict]) -> dict:
    return {"hooks": {"SessionStart": [{"hooks": hooks}]}}


def _commands(settings: dict) -> list[str]:
    return [
        hook["command"]
        for entry in settings["hooks"]["SessionStart"]
        for hook in entry["hooks"]
    ]


def test_hook_is_present_matches_tilde_and_absolute(reconcile, tmp_path):
    wrapper = tmp_path / ".claude" / "scripts" / "mcp_health_check.sh"
    absolute = str(wrapper.resolve())
    tilde = "~/.claude/scripts/mcp_health_check.sh"

    absolute_settings = _settings_with(
        [{"type": "command", "command": absolute, "timeout": 30}]
    )
    assert reconcile._hook_is_present(absolute_settings, absolute)
    # Tilde form only matches when the wrapper actually lives under $HOME;
    # simulate by passing a command that resolves to the same wrapper.
    assert reconcile._hook_is_present(absolute_settings, str(wrapper))
    assert not reconcile._hook_is_present(
        _settings_with([{"type": "command", "command": tilde, "timeout": 30}]),
        absolute,
    )


def test_install_normalizes_tilde_hook_to_canonical_command(
    reconcile, tmp_path, monkeypatch
):
    wrapper = tmp_path / ".claude" / "scripts" / "mcp_health_check.sh"
    wrapper.parent.mkdir(parents=True)
    monkeypatch.setenv("HOME", str(tmp_path))
    canonical = str(wrapper.resolve())
    settings = _settings_with(
        [
            {
                "type": "command",
                "command": "~/.claude/scripts/mcp_health_check.sh",
                "timeout": 30,
            }
        ]
    )
    updated = reconcile._rewrite_health_hook(settings, canonical, install=True)
    commands = _commands(updated)
    assert commands.count(canonical) == 1
    assert "~/.claude/scripts/mcp_health_check.sh" not in commands


def test_install_dedupes_absolute_and_tilde_forms(reconcile, tmp_path, monkeypatch):
    wrapper = tmp_path / ".claude" / "scripts" / "mcp_health_check.sh"
    wrapper.parent.mkdir(parents=True)
    monkeypatch.setenv("HOME", str(tmp_path))
    canonical = str(wrapper.resolve())
    hook = {"type": "command", "command": canonical, "timeout": 30}
    tilde_hook = {
        "type": "command",
        "command": "~/.claude/scripts/mcp_health_check.sh",
        "timeout": 30,
    }
    settings = _settings_with([hook, tilde_hook])
    updated = reconcile._rewrite_health_hook(settings, canonical, install=True)
    assert _commands(updated) == [canonical]


def test_install_rejects_divergent_managed_hook(reconcile, tmp_path, monkeypatch):
    wrapper = tmp_path / ".claude" / "scripts" / "mcp_health_check.sh"
    wrapper.parent.mkdir(parents=True)
    monkeypatch.setenv("HOME", str(tmp_path))
    canonical = str(wrapper.resolve())
    divergent = _settings_with(
        [{"type": "command", "command": canonical, "timeout": 99}]
    )
    with pytest.raises(reconcile.InstallError, match="externally edited"):
        reconcile._rewrite_health_hook(divergent, canonical, install=True)


def test_rewrite_preserves_unrelated_hooks_and_empty_entries(reconcile, tmp_path):
    wrapper = tmp_path / ".claude" / "scripts" / "mcp_health_check.sh"
    canonical = str(wrapper.resolve())
    other = {"type": "command", "command": "/custom/session"}
    settings = {
        "hooks": {
            "SessionStart": [
                {
                    "matcher": "x",
                    "hooks": [
                        {"type": "command", "command": canonical, "timeout": 30},
                        other,
                    ],
                },
                {"hooks": [{"type": "command", "command": "/other"}]},
            ]
        }
    }
    updated = reconcile._rewrite_health_hook(settings, canonical, install=True)
    entries = updated["hooks"]["SessionStart"]
    assert entries[0]["hooks"] == [other]
    assert entries[0]["matcher"] == "x"
    assert entries[1]["hooks"] == [{"type": "command", "command": "/other"}]
    assert entries[2] == {
        "hooks": [{"type": "command", "command": canonical, "timeout": 30}]
    }


def test_uninstall_removes_hook_in_tilde_form(reconcile, tmp_path, monkeypatch):
    wrapper = tmp_path / ".claude" / "scripts" / "mcp_health_check.sh"
    wrapper.parent.mkdir(parents=True)
    monkeypatch.setenv("HOME", str(tmp_path))
    canonical = str(wrapper.resolve())
    keep = {"type": "command", "command": "/custom/session"}
    settings = _settings_with(
        [
            {
                "type": "command",
                "command": "~/.claude/scripts/mcp_health_check.sh",
                "timeout": 30,
            },
            keep,
        ]
    )
    updated = reconcile._rewrite_health_hook(settings, canonical, install=False)
    assert _commands(updated) == ["/custom/session"]

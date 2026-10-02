"""Focused tests for canonical health-hook matching and wrapper ownership."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pytest

from tests.python.plugin_runtime.health_test_helpers import (
    isolated_env,
    load_runtime_module,
    run_script,
)
from tests.python.plugin_runtime.health_test_helpers import (
    repo_root as _repo_root,
)
from tests.python.plugin_runtime.test_health_installer import (
    _copy_health_source,
    _install,
    _installer,
    _no_installation,
    _seed_claude_settings,
    _session_start_commands,
    _write_health_tool_fakes,
)

_SCRIPTS = _repo_root() / "plugins/manifest-workspace/skills/env-check/scripts"


@pytest.fixture
def repo_root() -> Path:
    return _repo_root()


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


@pytest.fixture(scope="module")
def scheduler_module():
    sys.path.insert(0, str(_SCRIPTS))
    try:
        module = load_runtime_module(
            _SCRIPTS / "health_install_scheduler.py", "health_install_scheduler"
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


def test_health_installer_adopts_an_identical_bootstrap_wrapper(
    repo_root: Path, tmp_path: Path
) -> None:
    """A routine bootstrap redeploy leaves an identical wrapper the installer
    must adopt, not reject — plus the legacy hook bootstrap registered."""
    source_root = _copy_health_source(repo_root, tmp_path / "source")
    env = isolated_env(tmp_path)
    _write_health_tool_fakes(tmp_path, env)
    settings_path = _seed_claude_settings(env)
    wrapper_path = Path(env["HOME"]) / ".claude/scripts/mcp_health_check.sh"
    wrapper_path.parent.mkdir(parents=True, exist_ok=True)
    wrapper_path.write_bytes(
        (source_root / "configs/claude/scripts/mcp_health_check.sh").read_bytes()
    )
    settings = json.loads(settings_path.read_text(encoding="utf-8"))
    settings["hooks"]["SessionStart"][0]["hooks"].append(
        {
            "type": "command",
            "command": "~/.claude/scripts/mcp_health_check.sh",
            "timeout": 30,
        }
    )
    settings_path.write_text(json.dumps(settings), encoding="utf-8")

    _install(source_root, env, tmp_path)

    receipt_path = Path(env["XDG_STATE_HOME"]) / "manifest/health/installation.json"
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    assert (
        receipt["claude_wrapper"]["destination_sha256"]
        == hashlib.sha256(wrapper_path.read_bytes()).hexdigest()
    )
    commands = _session_start_commands(
        json.loads(settings_path.read_text(encoding="utf-8"))
    )
    assert commands.count(str(wrapper_path)) == 1
    assert commands.count("/custom/session") == 1
    assert "~/.claude/scripts/mcp_health_check.sh" not in commands


def test_health_installer_refuses_a_divergent_unowned_wrapper(
    repo_root: Path, tmp_path: Path
) -> None:
    """Only identical content is adopted; a divergent wrapper still refuses."""
    source_root = _copy_health_source(repo_root, tmp_path / "source")
    env = isolated_env(tmp_path)
    _write_health_tool_fakes(tmp_path, env)
    wrapper_path = Path(env["HOME"]) / ".claude/scripts/mcp_health_check.sh"
    wrapper_path.parent.mkdir(parents=True, exist_ok=True)
    wrapper_path.write_text("# operator-local wrapper\n", encoding="utf-8")

    result = run_script(
        _installer(source_root),
        "--source-root",
        str(source_root),
        "--install",
        env=env,
        cwd=tmp_path,
    )

    assert result.returncode == 1
    assert wrapper_path.read_text(encoding="utf-8") == "# operator-local wrapper\n"
    _no_installation(env)


def test_systemd_execstart_escapes_percent_specifiers(
    scheduler_module, tmp_path: Path
) -> None:
    """%% expansion applies to ExecStart even inside quotes, so managed paths
    containing % must be escaped there — while Environment= values, which are
    not specifier-expanded, must stay literal."""
    import health_install_files as files

    environment = isolated_env(tmp_path)
    percent_home = tmp_path / "data 100%"
    percent_home.mkdir()
    environment["XDG_DATA_HOME"] = str(percent_home)
    paths = files._paths(environment)

    _timer, service = scheduler_module._systemd_unit_payloads(
        paths, sys.executable, environment
    )

    text = service.decode("utf-8")
    exec_line = next(
        line for line in text.splitlines() if line.startswith("ExecStart=")
    )
    assert "100%%" in exec_line
    env_lines = [
        line for line in text.splitlines() if line.startswith("Environment=")
    ]
    assert any("100%" in line and "100%%" not in line for line in env_lines)

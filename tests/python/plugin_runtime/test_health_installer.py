"""Isolation tests for the install_health_reporting.py installer."""

from __future__ import annotations

import hashlib
import json
import os
import plistlib
import shutil
import stat
import sys
from pathlib import Path

import pytest

from tests.python.plugin_runtime.health_test_helpers import (
    isolated_env,
    run_script,
)
from tests.python.plugin_runtime.health_test_helpers import (
    repo_root as _repo_root,
)


@pytest.fixture
def repo_root() -> Path:
    """The repository root that ships the installer under test."""
    return _repo_root()


def _copy_health_source(repo_root: Path, destination: Path) -> Path:
    relative_sources = (
        "plugins/manifest-workspace/skills/env-check/scripts/env_check.py",
        "plugins/manifest-workspace/skills/env-check/scripts/mcp_health.py",
        "plugins/manifest-workspace/skills/env-check/scripts/health_report.py",
        "plugins/manifest-workspace/skills/env-check/scripts/health_report_collect.py",
        "plugins/manifest-workspace/skills/env-check/scripts/health_report_common.py",
        "plugins/manifest-workspace/skills/env-check/scripts/health_report_inspect.py",
        "configs/claude/scripts/hook_smoke_support.py",
        "plugins/manifest-workspace/skills/env-check/scripts/health_report_sanitize.py",
        "plugins/manifest-workspace/skills/env-check/scripts/health_install_files.py",
        "plugins/manifest-workspace/skills/env-check/scripts/health_install_reconcile.py",
        "plugins/manifest-workspace/skills/env-check/scripts/mcp_health_expectations.py",
        "plugins/manifest-workspace/skills/env-check/scripts/mcp_health_report.py",
        "plugins/manifest-workspace/skills/env-check/scripts/mcp_health_runtime.py",
        "plugins/manifest-workspace/skills/env-check/scripts/install_health_reporting.py",
        "configs/claude/scripts/hook_smoke.py",
        "configs/claude/scripts/mcp_health_check.sh",
        "configs/omp/extensions/manifest-health.ts",
        "plugins/manifest-delegate/hooks/hooks.json",
        "plugins/manifest-delegate/scripts/delegate.py",
        "plugins/manifest-delegate/scripts/stop_gate_hook.py",
        "plugins/manifest-delegate/scripts/stop_gate_hook.sh",
    )
    for relative in relative_sources:
        source = repo_root / relative
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    return destination


def _write_health_tool_fakes(tmp_path: Path, env: dict[str, str]) -> Path:
    binary_dir = tmp_path / "health-bin"
    binary_dir.mkdir()
    log = tmp_path / "native-commands.log"
    for name in ("omp", "claude", "manifest", "launchctl", "plutil"):
        executable = binary_dir / name
        executable.write_text(
            "#!/bin/sh\n"
            f'printf "%s\\n" "{name} $*" >> "$MANIFEST_TEST_COMMAND_LOG"\n'
            "exit 0\n",
            encoding="utf-8",
        )
        executable.chmod(0o755)
    env["PATH"] = f"{binary_dir}:{env['PATH']}"
    env["MANIFEST_TEST_COMMAND_LOG"] = str(log)
    env["OMP_AGENT_DIR"] = str(tmp_path / "omp-agent")
    return log


def _session_start_commands(settings: dict) -> list[str]:
    return [
        hook["command"]
        for matcher in settings.get("hooks", {}).get("SessionStart", [])
        if isinstance(matcher, dict)
        for hook in matcher.get("hooks", [])
        if isinstance(hook, dict) and isinstance(hook.get("command"), str)
    ]


def _installer(source_root: Path) -> Path:
    return (
        source_root
        / "plugins/manifest-workspace/skills/env-check/scripts"
        / "install_health_reporting.py"
    )


def _install(source_root: Path, env: dict[str, str], cwd: Path) -> None:
    result = run_script(
        _installer(source_root),
        "--source-root",
        str(source_root),
        "--install",
        env=env,
        cwd=cwd,
    )
    assert result.returncode == 0, result.stderr


def _no_installation(env: dict[str, str]) -> None:
    assert not (Path(env["XDG_DATA_HOME"]) / "manifest/health").exists()
    assert not (
        Path(env["XDG_STATE_HOME"]) / "manifest/health/installation.json"
    ).exists()


def _seed_claude_settings(env: dict[str, str]) -> Path:
    settings_path = Path(env["HOME"]) / ".claude/settings.json"
    settings_path.parent.mkdir(parents=True)
    settings_path.write_text(
        json.dumps(
            {
                "hooks": {
                    "SessionStart": [
                        {"hooks": [{"type": "command", "command": "/custom/session"}]}
                    ]
                }
            }
        ),
        encoding="utf-8",
    )
    return settings_path


def _assert_installation_manifest(source_root: Path, env: dict[str, str]) -> Path:
    installation_path = (
        Path(env["XDG_STATE_HOME"]) / "manifest/health/installation.json"
    )
    installation = json.loads(installation_path.read_text(encoding="utf-8"))
    assert stat.S_IMODE(installation_path.stat().st_mode) == 0o600
    assert Path(installation["source_root"]) == source_root.resolve()
    assert set(installation["executables"]) == {
        "python",
        "omp",
        "claude",
        "coordinator",
    }
    assert installation["installed_at"].endswith("Z")
    assert set(installation["files"]) == {
        "env_check.py",
        "health_report.py",
        "health_report_collect.py",
        "health_report_common.py",
        "health_report_inspect.py",
        "health_report_sanitize.py",
        "health_install_files.py",
        "health_install_reconcile.py",
        "hook_smoke.py",
        "hook_smoke_support.py",
        "mcp_health.py",
        "mcp_health_expectations.py",
        "mcp_health_report.py",
        "mcp_health_runtime.py",
    }
    for executable in installation["executables"].values():
        assert Path(executable).is_absolute()
    runtime_root = Path(env["XDG_DATA_HOME"]) / "manifest/health"
    assert {path.name for path in runtime_root.iterdir()} == set(installation["files"])
    for name, row in installation["files"].items():
        destination = runtime_root / name
        digest = hashlib.sha256(destination.read_bytes()).hexdigest()
        assert row["destination"] == str(destination.resolve())
        assert row["source_sha256"] == digest
        assert row["destination_sha256"] == digest
        assert stat.S_IMODE(destination.stat().st_mode) == 0o600
    _assert_owned_destinations(installation, env)
    return runtime_root


def _assert_owned_destinations(installation: dict, env: dict[str, str]) -> None:
    assert (Path(env["XDG_DATA_HOME"]) / "manifest/health/health_report.py").is_file()
    assert (
        Path(env["OMP_AGENT_DIR"]) / "extensions/manifest-health.ts"
    ).read_bytes() == (
        Path(installation["source_root"]) / "configs/omp/extensions/manifest-health.ts"
    ).read_bytes()
    assert (
        stat.S_IMODE(
            (Path(env["OMP_AGENT_DIR"]) / "extensions/manifest-health.ts")
            .stat()
            .st_mode
        )
        == 0o600
    )
    for key, destination in (
        ("omp_extension", Path(env["OMP_AGENT_DIR"]) / "extensions/manifest-health.ts"),
        (
            "claude_wrapper",
            Path(env["HOME"]) / ".claude/scripts/mcp_health_check.sh",
        ),
        (
            "launchd_plist",
            Path(env["HOME"]) / "Library/LaunchAgents/com.manifest.health-report.plist",
        ),
    ):
        row = installation[key]
        digest = hashlib.sha256(destination.read_bytes()).hexdigest()
        assert row["destination"] == str(destination.resolve())
        assert row["source_sha256"] == digest
        assert row["destination_sha256"] == digest


def _assert_launchd_plist(env: dict[str, str], runtime_root: Path) -> None:
    plist_path = (
        Path(env["HOME"]) / "Library/LaunchAgents/com.manifest.health-report.plist"
    )
    with plist_path.open("rb") as handle:
        plist = plistlib.load(handle)
    assert plist["ProgramArguments"] == [
        str(Path(sys.executable).resolve()),
        str((runtime_root / "health_report.py").resolve()),
        "--json",
        "--harness",
        "claude",
        "--harness",
        "omp",
        "--out-dir",
        str((Path(env["XDG_STATE_HOME"]) / "manifest/reports").resolve()),
    ]
    assert plist["StartCalendarInterval"] == {"Weekday": 1, "Hour": 9, "Minute": 0}
    assert plist["RunAtLoad"] is False
    assert plist["ProcessType"] == "Background"
    assert plist["ManifestManagedBy"] == "manifest-health-reporting"
    assert plist["EnvironmentVariables"] == {
        "HOME": str(Path(env["HOME"]).resolve()),
        "PATH": env["PATH"],
        "XDG_CONFIG_HOME": str(Path(env["XDG_CONFIG_HOME"]).resolve()),
        "XDG_DATA_HOME": str(Path(env["XDG_DATA_HOME"]).resolve()),
        "XDG_STATE_HOME": str(Path(env["XDG_STATE_HOME"]).resolve()),
    }
    assert stat.S_IMODE(plist_path.stat().st_mode) == 0o600


def _assert_uninstalled(env: dict[str, str], settings_path: Path) -> None:
    assert not (
        Path(env["XDG_STATE_HOME"]) / "manifest/health/installation.json"
    ).exists()
    assert not (Path(env["OMP_AGENT_DIR"]) / "extensions/manifest-health.ts").exists()
    assert not (Path(env["HOME"]) / ".claude/scripts/mcp_health_check.sh").exists()
    assert not (
        Path(env["HOME"]) / "Library/LaunchAgents/com.manifest.health-report.plist"
    ).exists()
    remaining = json.loads(settings_path.read_text(encoding="utf-8"))
    assert _session_start_commands(remaining) == ["/custom/session"]


def test_health_installer_is_owned_idempotent_updatable_and_uninstallable(
    repo_root: Path, tmp_path: Path
) -> None:
    """Install twice, mutate a source file, reinstall, then uninstall twice."""
    source_root = _copy_health_source(repo_root, tmp_path / "source")
    env = isolated_env(tmp_path)
    command_log = _write_health_tool_fakes(tmp_path, env)
    settings_path = _seed_claude_settings(env)

    _install(source_root, env, tmp_path)
    _install(source_root, env, tmp_path)

    runtime_root = _assert_installation_manifest(source_root, env)
    _assert_launchd_plist(env, runtime_root)
    wrapper_path = Path(env["HOME"]) / ".claude/scripts/mcp_health_check.sh"
    assert stat.S_IMODE(wrapper_path.stat().st_mode) == 0o700
    assert stat.S_IMODE(settings_path.stat().st_mode) == 0o600
    settings = json.loads(settings_path.read_text(encoding="utf-8"))
    commands = _session_start_commands(settings)
    assert commands.count("/custom/session") == 1
    assert commands.count(str(wrapper_path)) == 1

    source_health = (
        source_root
        / "plugins/manifest-workspace/skills/env-check/scripts/mcp_health.py"
    )
    source_health.write_text(
        source_health.read_text(encoding="utf-8") + "\n", encoding="utf-8"
    )
    _install(source_root, env, tmp_path)
    assert hashlib.sha256(
        (runtime_root / "mcp_health.py").read_bytes()
    ).hexdigest() == (hashlib.sha256(source_health.read_bytes()).hexdigest())

    for _ in range(2):
        removed = run_script(
            _installer(source_root),
            "--source-root",
            str(source_root),
            "--uninstall",
            env=env,
            cwd=tmp_path,
        )
        assert removed.returncode == 0, removed.stderr
    _assert_uninstalled(env, settings_path)

    log_lines = command_log.read_text(encoding="utf-8").splitlines()
    assert any("bootstrap gui/" in line for line in log_lines)
    assert any("kickstart -k gui/" in line for line in log_lines)
    assert any("plutil -lint " in line for line in log_lines)
    assert sum("kickstart -k gui/" in line for line in log_lines) == 3


def test_health_installer_refuses_unowned_or_edited_destinations(
    repo_root: Path, tmp_path: Path
) -> None:
    """A pre-existing operator file is never overwritten or claimed."""
    source_root = _copy_health_source(repo_root, tmp_path / "source")
    env = isolated_env(tmp_path)
    _write_health_tool_fakes(tmp_path, env)
    extension = Path(env["OMP_AGENT_DIR"]) / "extensions/manifest-health.ts"
    extension.parent.mkdir(parents=True)
    extension.write_text("user-owned\n", encoding="utf-8")

    result = run_script(
        _installer(source_root),
        "--source-root",
        str(source_root),
        "--install",
        env=env,
        cwd=tmp_path,
    )

    assert result.returncode == 1
    assert extension.read_text(encoding="utf-8") == "user-owned\n"
    assert not (
        Path(env["XDG_STATE_HOME"]) / "manifest/health/installation.json"
    ).exists()


def test_health_installer_preserves_an_unowned_launchd_job(
    repo_root: Path, tmp_path: Path
) -> None:
    """An existing operator-owned LaunchAgent with the same label is untouched."""
    source_root = _copy_health_source(repo_root, tmp_path / "source")
    env = isolated_env(tmp_path)
    _write_health_tool_fakes(tmp_path, env)
    plist_path = (
        Path(env["HOME"]) / "Library/LaunchAgents/com.manifest.health-report.plist"
    )
    plist_path.parent.mkdir(parents=True)
    original = plistlib.dumps(
        {
            "Label": "com.manifest.health-report",
            "ProgramArguments": ["/user/owned/reporter"],
        }
    )
    plist_path.write_bytes(original)

    result = run_script(
        _installer(source_root),
        "--source-root",
        str(source_root),
        "--install",
        env=env,
        cwd=tmp_path,
    )

    assert result.returncode == 1
    assert plist_path.read_bytes() == original
    _no_installation(env)


def test_health_installer_requires_one_explicit_action(
    repo_root: Path, tmp_path: Path
) -> None:
    """Zero or conflicting actions are a usage error, not a partial install."""
    source_root = _copy_health_source(repo_root, tmp_path / "source")
    env = isolated_env(tmp_path)
    installer = _installer(source_root)

    missing = run_script(
        installer,
        "--source-root",
        str(source_root),
        env=env,
        cwd=tmp_path,
    )
    conflicting = run_script(
        installer,
        "--source-root",
        str(source_root),
        "--install",
        "--uninstall",
        env=env,
        cwd=tmp_path,
    )

    assert missing.returncode == 2
    assert conflicting.returncode == 2
    _no_installation(env)


def test_health_installer_refuses_to_uninstall_edited_owned_files(
    repo_root: Path, tmp_path: Path
) -> None:
    """Uninstall refuses to delete files that drifted from the recorded digest."""
    source_root = _copy_health_source(repo_root, tmp_path / "source")
    env = isolated_env(tmp_path)
    _write_health_tool_fakes(tmp_path, env)
    _install(source_root, env, tmp_path)
    extension = Path(env["OMP_AGENT_DIR"]) / "extensions/manifest-health.ts"
    extension.write_text("externally edited\n", encoding="utf-8")

    removed = run_script(
        _installer(source_root),
        "--source-root",
        str(source_root),
        "--uninstall",
        env=env,
        cwd=tmp_path,
    )

    assert removed.returncode == 1
    assert extension.read_text(encoding="utf-8") == "externally edited\n"
    assert (Path(env["XDG_STATE_HOME"]) / "manifest/health/installation.json").is_file()
    assert (Path(env["HOME"]) / ".claude/scripts/mcp_health_check.sh").is_file()
    assert (
        Path(env["HOME"]) / "Library/LaunchAgents/com.manifest.health-report.plist"
    ).is_file()


def _stateful_launchctl(env: dict[str, str]) -> None:
    launchctl = Path(env["PATH"].split(os.pathsep, 1)[0]) / "launchctl"
    launchctl.write_text(
        "#!/bin/sh\n"
        'printf "%s\\n" "launchctl $*" >> "$MANIFEST_TEST_COMMAND_LOG"\n'
        'case "$1" in\n'
        "  bootstrap)\n"
        '    test ! -e "$MANIFEST_TEST_LAUNCHD_STATE" || exit 36\n'
        '    printf "manifest\\n" > "$MANIFEST_TEST_LAUNCHD_STATE"\n'
        "    ;;\n"
        "  bootout)\n"
        '    rm -f "$MANIFEST_TEST_LAUNCHD_STATE"\n'
        "    ;;\n"
        "esac\n"
        "exit 0\n",
        encoding="utf-8",
    )
    launchctl.chmod(0o755)


def test_health_installer_does_not_bootout_an_unowned_loaded_label_after_failed_bootstrap(
    repo_root: Path, tmp_path: Path
) -> None:
    """A failed bootstrap against an unowned label never escalates to bootout."""
    source_root = _copy_health_source(repo_root, tmp_path / "source")
    env = isolated_env(tmp_path)
    command_log = _write_health_tool_fakes(tmp_path, env)
    launchd_state = tmp_path / "launchd-state"
    launchd_state.write_text("unowned\n", encoding="utf-8")
    env["MANIFEST_TEST_LAUNCHD_STATE"] = str(launchd_state)
    _stateful_launchctl(env)

    result = run_script(
        _installer(source_root),
        "--source-root",
        str(source_root),
        "--install",
        env=env,
        cwd=tmp_path,
    )

    log_lines = command_log.read_text(encoding="utf-8").splitlines()
    assert result.returncode == 1
    assert "launchd bootstrap failed" in result.stderr
    assert any(line.startswith("launchctl bootstrap gui/") for line in log_lines)
    assert launchd_state.is_file()
    assert launchd_state.read_text(encoding="utf-8") == "unowned\n"
    assert not any(line.startswith("launchctl bootout ") for line in log_lines)

"""Contract tests for platform health-report schedulers."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from tests.python.plugin_runtime.health_test_helpers import isolated_env, repo_root

_SCRIPTS = repo_root() / "plugins/manifest-workspace/skills/env-check/scripts"
sys.path.insert(0, str(_SCRIPTS))

import health_install_files as files
import health_install_scheduler as schedulers
import install_health_reporting as installer


def _write_fake_tools(tmp_path: Path, environment: dict[str, str]) -> Path:
    binary_dir = tmp_path / "bin"
    binary_dir.mkdir()
    log_path = tmp_path / "commands.log"
    for name in (
        "omp",
        "claude",
        "manifest",
        "launchctl",
        "plutil",
        "systemctl",
        "systemd-run",
    ):
        executable = binary_dir / name
        executable.write_text(
            "#!/bin/sh\n"
            'printf \'%s %s\\n\' "$(basename "$0")" "$*" >> "$MANIFEST_TEST_COMMAND_LOG"\n'
            'if [ "$(basename "$0")" = systemd-run ]; then\n'
            '  exit "${MANIFEST_TEST_SYSTEMD_RUN_STATUS:-0}"\n'
            "fi\n"
            'if [ "$(basename "$0")" = launchctl ] && [ "$1" = bootout ]; then\n'
            '  exit "${MANIFEST_TEST_BOOTOUT_STATUS:-0}"\n'
            "fi\n"
            "exit 0\n",
            encoding="utf-8",
        )
        executable.chmod(0o755)
    environment["PATH"] = f"{binary_dir}:{environment.get('PATH', '')}"
    environment["MANIFEST_TEST_COMMAND_LOG"] = str(log_path)
    return log_path


def test_launchd_payload_preserves_resolved_omp_root(tmp_path: Path) -> None:
    environment = isolated_env(tmp_path)
    environment["OMP_AGENT_DIR"] = str(tmp_path / "custom-omp")

    payload = files._plist_payload(
        files._paths(environment), sys.executable, environment
    )

    assert b"<key>OMP_AGENT_DIR</key>" in payload
    assert str((tmp_path / "custom-omp").resolve()).encode() in payload


def test_paths_use_active_claude_config_root(tmp_path: Path) -> None:
    environment = isolated_env(tmp_path)
    environment["CLAUDE_CONFIG_DIR"] = str(tmp_path / "claude-profile")

    paths = files._paths(environment)

    assert paths.settings == (tmp_path / "claude-profile/settings.json").resolve()
    assert (
        paths.wrapper
        == (tmp_path / "claude-profile/scripts/mcp_health_check.sh").resolve()
    )


def test_linux_scheduler_uses_systemd_user_timer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    environment = isolated_env(tmp_path)
    monkeypatch.setattr(schedulers.sys, "platform", "linux")
    monkeypatch.setattr(schedulers, "_resolve_executable", lambda name: f"/bin/{name}")

    scheduler = schedulers._resolve_scheduler(
        files._paths(environment), environment, sys.executable
    )
    argv = scheduler.systemd_argv(
        files._paths(environment), sys.executable, environment
    )

    assert scheduler.kind == "systemd"
    assert argv[:3] == ["/bin/systemd-run", "--user", "--unit=manifest-health-report"]
    assert any(argument.startswith("--on-calendar=") for argument in argv)
    assert f"--setenv=OMP_AGENT_DIR={files._paths(environment).agent_root}" in argv


def test_unsupported_platform_refuses_scheduler() -> None:
    with pytest.raises(
        files.InstallError, match="unsupported scheduler platform: win32"
    ):
        schedulers._scheduler_kind("win32")


def test_launchd_bootout_failure_is_fatal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    environment = isolated_env(tmp_path)
    scheduler = schedulers._Scheduler(
        kind="launchd",
        domain="gui/1",
        service="gui/1/com.manifest.health-report",
        unit="",
        launchctl="/bin/launchctl",
        plutil="",
        systemd_run="",
        systemctl="",
        payload=b"",
    )
    monkeypatch.setattr(
        schedulers,
        "_run_quiet",
        lambda *_args, **_kwargs: subprocess.CompletedProcess([], 1),
    )

    with pytest.raises(files.InstallError, match="launchd bootout failed"):
        schedulers._stop_scheduler_job(scheduler, environment)


def test_systemd_state_probe_failure_is_fatal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    environment = isolated_env(tmp_path)
    scheduler = schedulers._Scheduler(
        kind="systemd",
        domain="",
        service="",
        unit="manifest-health-report",
        launchctl="",
        plutil="",
        systemd_run="",
        systemctl="/bin/systemctl",
        payload=b"",
    )
    monkeypatch.setattr(
        schedulers,
        "_run_quiet",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("unavailable")),
    )

    with pytest.raises(
        files.InstallError, match="systemd unit state could not be verified"
    ):
        schedulers._stop_scheduler_job(scheduler, environment)


def test_linux_install_arms_recorded_systemd_timer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    environment = isolated_env(tmp_path)
    command_log = _write_fake_tools(tmp_path, environment)
    monkeypatch.setenv("PATH", environment["PATH"])
    monkeypatch.setattr(schedulers.sys, "platform", "linux")

    installer.install(repo_root(), environment)

    receipt = json.loads(
        (
            Path(environment["XDG_STATE_HOME"]) / "manifest/health/installation.json"
        ).read_text(encoding="utf-8")
    )
    assert receipt["scheduler"]["kind"] == "systemd"
    assert "systemd-run --user --unit=manifest-health-report" in command_log.read_text(
        encoding="utf-8"
    )


def test_uninstall_preserves_owned_files_when_launchd_bootout_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    environment = isolated_env(tmp_path)
    _write_fake_tools(tmp_path, environment)
    monkeypatch.setattr(schedulers.sys, "platform", "darwin")
    monkeypatch.setenv("PATH", environment["PATH"])

    installer.install(repo_root(), environment)
    receipt = Path(environment["XDG_STATE_HOME"]) / "manifest/health/installation.json"
    wrapper = Path(environment["HOME"]) / ".claude/scripts/mcp_health_check.sh"
    environment["MANIFEST_TEST_BOOTOUT_STATUS"] = "1"

    with pytest.raises(files.InstallError, match="launchd bootout failed"):
        installer.uninstall(repo_root(), environment)

    assert receipt.is_file()
    assert wrapper.is_file()


def test_failed_systemd_creation_does_not_stop_an_unowned_unit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    environment = isolated_env(tmp_path)
    command_log = _write_fake_tools(tmp_path, environment)
    environment["MANIFEST_TEST_SYSTEMD_RUN_STATUS"] = "36"
    monkeypatch.setenv("PATH", environment["PATH"])
    monkeypatch.setattr(schedulers.sys, "platform", "linux")
    paths = files._paths(environment)
    scheduler = schedulers._resolve_scheduler(paths, environment, sys.executable)

    with pytest.raises(files.InstallError, match="systemd timer creation failed"):
        schedulers._activate_scheduler_job(
            scheduler, None, paths, sys.executable, b"{}", environment
        )

    log_lines = command_log.read_text(encoding="utf-8").splitlines()
    assert any(line.startswith("systemd-run --user") for line in log_lines)
    assert not any(line.startswith("systemctl --user stop") for line in log_lines)

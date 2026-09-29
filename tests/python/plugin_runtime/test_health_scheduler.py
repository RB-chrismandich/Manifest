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
    systemctl = binary_dir / "systemctl"
    systemctl.write_text(
        "#!/bin/sh\n"
        'printf \'%s %s\\n\' "systemctl" "$*" >> "$MANIFEST_TEST_COMMAND_LOG"\n'
        'verb=""\n'
        'for arg in "$@"; do\n'
        '  case "$arg" in -*) ;; *) verb="$arg"; break;; esac\n'
        "done\n"
        'case "$verb" in\n'
        "  is-active)\n"
        '    if [ "${MANIFEST_TEST_SYSTEMD_ACTIVE:-}" = "1" ]; then\n'
        '      printf "active\\nactive\\n"; exit 0\n'
        "    fi\n"
        '    printf "inactive\\ninactive\\n"; exit 3;;\n'
        '  show-environment) exit "${MANIFEST_TEST_SHOW_ENV_STATUS:-0}";;\n'
        '  daemon-reload) exit "${MANIFEST_TEST_DAEMON_RELOAD_STATUS:-0}";;\n'
        '  enable) exit "${MANIFEST_TEST_ENABLE_STATUS:-0}";;\n'
        '  disable) exit "${MANIFEST_TEST_DISABLE_STATUS:-0}";;\n'
        '  stop) exit "${MANIFEST_TEST_STOP_STATUS:-0}";;\n'
        "  reset-failed) exit 0;;\n"
        "  *) exit 0;;\n"
        "esac\n",
        encoding="utf-8",
    )
    systemctl.chmod(0o755)
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
    environment["CLAUDE_CONFIG_DIR"] = str(tmp_path / "claude-profile")
    monkeypatch.setattr(schedulers.sys, "platform", "linux")
    monkeypatch.setattr(schedulers, "_resolve_executable", lambda name: f"/bin/{name}")
    monkeypatch.setattr(
        schedulers,
        "_run_quiet",
        lambda *_args, **_kwargs: subprocess.CompletedProcess([], 0),
    )

    paths = files._paths(environment)
    scheduler = schedulers._resolve_scheduler(paths, environment, sys.executable)

    assert scheduler.kind == "systemd"
    assert scheduler.persistent
    assert b"OnCalendar=" in scheduler.timer_payload
    assert b"Persistent=true" in scheduler.timer_payload
    assert b"WantedBy=timers.target" in scheduler.timer_payload
    assert (
        f'Environment="CLAUDE_CONFIG_DIR={paths.claude_root}"'.encode()
        in scheduler.service_payload
    )
    assert files.SYSTEMD_UNIT_MARKER.encode() in scheduler.timer_payload
    argv = scheduler.systemd_argv(paths, sys.executable, environment)

    assert argv[:3] == ["/bin/systemd-run", "--user", "--unit=manifest-health-report"]
    assert any(argument.startswith("--on-calendar=") for argument in argv)
    assert f"--setenv=OMP_AGENT_DIR={paths.agent_root}" in argv
    assert f"--setenv=CLAUDE_CONFIG_DIR={paths.claude_root}" in argv



def test_report_environment_omits_empty_claude_config_override(tmp_path: Path) -> None:
    environment = isolated_env(tmp_path)
    environment["CLAUDE_CONFIG_DIR"] = ""

    report_environment = schedulers._report_environment(
        files._paths(environment), environment
    )

    assert "CLAUDE_CONFIG_DIR" not in report_environment

def test_linux_without_user_manager_installs_unscheduled(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    environment = isolated_env(tmp_path)
    monkeypatch.setattr(schedulers.sys, "platform", "linux")
    monkeypatch.setattr(schedulers, "_resolve_executable", lambda name: f"/bin/{name}")

    def refuse_probe(*_args, **_kwargs):
        raise OSError("Failed to connect to bus")

    monkeypatch.setattr(schedulers, "_run_quiet", refuse_probe)

    scheduler = schedulers._resolve_scheduler(
        files._paths(environment), environment, sys.executable
    )

    assert scheduler.kind == "none"
    assert scheduler.metadata() == {
        "kind": "none",
        "managed_by": files.OWNERSHIP_MARKER,
    }
    # An unscheduled install is fully removable: stop is a no-op.
    schedulers._stop_scheduler_job(scheduler, environment)


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



def test_systemd_disable_failure_is_fatal(
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
        persistent=True,
    )
    monkeypatch.setattr(
        schedulers,
        "_run_required",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            files.InstallError("systemd timer disable failed")
        ),
    )

    with pytest.raises(files.InstallError, match="systemd timer disable failed"):
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

    def fail_probe(argv, *_args, **_kwargs):
        if "is-active" in argv:
            raise OSError("unavailable")
        return subprocess.CompletedProcess(argv, 0)

    monkeypatch.setattr(schedulers, "_run_quiet", fail_probe)

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

    paths = files._paths(environment)
    receipt = json.loads(paths.receipt.read_text(encoding="utf-8"))
    assert receipt["scheduler"]["kind"] == "systemd"
    assert receipt["systemd_timer"]["destination"] == str(paths.systemd_timer)
    assert receipt["systemd_service"]["destination"] == str(paths.systemd_service)
    assert paths.systemd_timer.is_file()
    assert paths.systemd_service.is_file()
    log = command_log.read_text(encoding="utf-8")
    assert "systemctl --user daemon-reload" in log
    assert "systemctl --user enable --now manifest-health-report.timer" in log
    assert "systemd-run --user" not in log


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


def test_failed_systemd_enable_cleans_up_partially_armed_timer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    environment = isolated_env(tmp_path)
    command_log = _write_fake_tools(tmp_path, environment)
    environment["MANIFEST_TEST_ENABLE_STATUS"] = "36"
    monkeypatch.setenv("PATH", environment["PATH"])
    monkeypatch.setattr(schedulers.sys, "platform", "linux")
    paths = files._paths(environment)
    scheduler = schedulers._resolve_scheduler(paths, environment, sys.executable)

    with pytest.raises(files.InstallError, match="systemd timer enable failed"):
        schedulers._activate_scheduler_job(scheduler, None, paths, b"{}", environment)

    log_lines = command_log.read_text(encoding="utf-8").splitlines()
    assert any(line.startswith("systemctl --user enable --now") for line in log_lines)
    assert any(line.startswith("systemctl --user disable") for line in log_lines)
    assert any(line.startswith("systemctl --user stop") for line in log_lines)


def test_linux_install_without_user_manager_records_unscheduled(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    environment = isolated_env(tmp_path)
    command_log = _write_fake_tools(tmp_path, environment)
    environment["MANIFEST_TEST_SHOW_ENV_STATUS"] = "1"
    monkeypatch.setenv("PATH", environment["PATH"])
    monkeypatch.setattr(schedulers.sys, "platform", "linux")

    installer.install(repo_root(), environment)

    paths = files._paths(environment)
    receipt = json.loads(paths.receipt.read_text(encoding="utf-8"))
    assert receipt["scheduler"]["kind"] == "none"
    assert "systemd_timer" not in receipt
    assert not paths.systemd_timer.exists()
    assert paths.wrapper.is_file()
    log = command_log.read_text(encoding="utf-8")
    assert "systemctl --user enable" not in log
    assert "systemd-run" not in log


def test_failed_systemd_teardown_prevents_transaction_rollback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    environment = isolated_env(tmp_path)
    _write_fake_tools(tmp_path, environment)
    environment["MANIFEST_TEST_ENABLE_STATUS"] = "36"
    monkeypatch.setenv("PATH", environment["PATH"])
    monkeypatch.setattr(schedulers.sys, "platform", "linux")
    monkeypatch.setattr(
        schedulers,
        "_stop_scheduler_job",
        lambda *_args: (_ for _ in ()).throw(files.InstallError("still active")),
    )
    paths = files._paths(environment)

    with pytest.raises(schedulers.SchedulerTeardownError):
        installer.install(repo_root(), environment)

    assert paths.receipt.is_file()
    assert paths.systemd_timer.is_file()
    assert paths.systemd_service.is_file()


def test_reinstall_after_manager_returns_replaces_unscheduled(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    environment = isolated_env(tmp_path)
    _write_fake_tools(tmp_path, environment)
    environment["MANIFEST_TEST_SHOW_ENV_STATUS"] = "1"
    monkeypatch.setenv("PATH", environment["PATH"])
    monkeypatch.setattr(schedulers.sys, "platform", "linux")
    installer.install(repo_root(), environment)

    environment["MANIFEST_TEST_SHOW_ENV_STATUS"] = "0"
    installer.install(repo_root(), environment)

    paths = files._paths(environment)
    receipt = json.loads(paths.receipt.read_text(encoding="utf-8"))
    assert receipt["scheduler"]["kind"] == "systemd"
    assert paths.systemd_timer.is_file()


def _installed_linux(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[dict[str, str], files.InstallPaths]:
    environment = isolated_env(tmp_path)
    _write_fake_tools(tmp_path, environment)
    monkeypatch.setenv("PATH", environment["PATH"])
    monkeypatch.setattr(schedulers.sys, "platform", "linux")
    installer.install(repo_root(), environment)
    return environment, files._paths(environment)


def test_uninstall_keeps_files_when_systemd_unit_stays_active(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    environment, paths = _installed_linux(tmp_path, monkeypatch)
    environment["MANIFEST_TEST_SYSTEMD_ACTIVE"] = "1"

    with pytest.raises(files.InstallError, match="systemd unit stop failed"):
        installer.uninstall(repo_root(), environment)

    assert paths.receipt.is_file()
    assert paths.systemd_timer.is_file()
    assert paths.wrapper.is_file()


def test_uninstall_with_failed_stop_and_inactive_units_proceeds(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    environment, paths = _installed_linux(tmp_path, monkeypatch)
    environment["MANIFEST_TEST_STOP_STATUS"] = "1"

    installer.uninstall(repo_root(), environment)

    assert not paths.receipt.exists()
    assert not paths.systemd_timer.exists()
    assert not paths.systemd_service.exists()
    assert not paths.wrapper.exists()

"""Contract tests for platform health-report schedulers."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from tests.python.plugin_runtime.health_test_helpers import isolated_env, repo_root

_SCRIPTS = repo_root() / "plugins/manifest-workspace/skills/env-check/scripts"
sys.path.insert(0, str(_SCRIPTS))

import health_install_files as files
import health_install_scheduler as schedulers


def test_launchd_payload_preserves_resolved_omp_root(tmp_path: Path) -> None:
    environment = isolated_env(tmp_path)
    environment["OMP_AGENT_DIR"] = str(tmp_path / "custom-omp")

    payload = files._plist_payload(
        files._paths(environment), sys.executable, environment
    )

    assert b"<key>OMP_AGENT_DIR</key>" in payload
    assert str((tmp_path / "custom-omp").resolve()).encode() in payload


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

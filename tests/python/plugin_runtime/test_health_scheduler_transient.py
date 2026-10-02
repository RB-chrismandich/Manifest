"""Teardown of legacy transient systemd schedulers (systemd-run timers)."""

from __future__ import annotations

import subprocess
import sys

import pytest

from tests.python.plugin_runtime.health_test_helpers import isolated_env, repo_root

_SCRIPTS = repo_root() / "plugins/manifest-workspace/skills/env-check/scripts"
sys.path.insert(0, str(_SCRIPTS))

import health_install_files as files
import health_install_scheduler as schedulers


def _transient_scheduler() -> schedulers._Scheduler:
    return schedulers._Scheduler(
        kind="systemd",
        domain="",
        service="",
        unit="manifest-health-report",
        launchctl="",
        plutil="",
        systemd_run="/bin/systemd-run",
        systemctl="/bin/systemctl",
        payload=b"",
    )


def _fake_systemctl(load_states: bytes):
    def run(argv, *_args, **_kwargs):
        if "stop" in argv:
            return subprocess.CompletedProcess(argv, 5, b"", b"Unit not loaded.")
        if "show" in argv:
            return subprocess.CompletedProcess(argv, 0, load_states, b"")
        if "is-active" in argv:
            return subprocess.CompletedProcess(argv, 3, b"inactive\ninactive\n", b"")
        return subprocess.CompletedProcess(argv, 0, b"", b"")

    return run


def test_vanished_transient_units_count_as_stopped(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """After a reboot the transient units are gone; teardown must not abort."""
    monkeypatch.setattr(
        schedulers, "_run_quiet", _fake_systemctl(b"not-found\nnot-found\n")
    )

    schedulers._stop_scheduler_job(_transient_scheduler(), isolated_env(tmp_path))


@pytest.mark.parametrize(
    "load_states", [b"loaded\nnot-found\n", b"loaded\nloaded\n", b""]
)
def test_failed_stop_of_loaded_units_stays_fatal(
    tmp_path, monkeypatch: pytest.MonkeyPatch, load_states: bytes
) -> None:
    """Only a confirmed not-loaded answer excuses a failed stop."""
    monkeypatch.setattr(schedulers, "_run_quiet", _fake_systemctl(load_states))

    with pytest.raises(files.InstallError, match="systemd unit stop failed"):
        schedulers._stop_scheduler_job(_transient_scheduler(), isolated_env(tmp_path))

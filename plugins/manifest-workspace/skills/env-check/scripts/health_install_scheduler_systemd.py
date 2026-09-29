#!/usr/bin/env python3
"""Persistent systemd user-timer activation for the health installer.

Extracted from `health_install_scheduler._activate_scheduler_job`. This module
imports `health_install_scheduler` for its process helpers, which the caller
imports lazily inside the systemd branch so module loading stays
one-directional.
"""

from __future__ import annotations

import subprocess
from collections.abc import Mapping
from typing import TYPE_CHECKING

import health_install_scheduler as _scheduler
from health_install_files import InstallError

if TYPE_CHECKING:
    from health_install_scheduler import _Scheduler


def _activate_persistent_systemd(
    scheduler: _Scheduler, environment: Mapping[str, str]
) -> None:
    """Reload the user manager, then enable and start the persistent timer.

    A timer left half-enabled after `daemon-reload` must be stopped and
    verified inactive before the surrounding transaction can roll back.
    """
    started = False
    try:
        _scheduler._run_required(
            [scheduler.systemctl, "--user", "daemon-reload"],
            environment,
            "systemd daemon reload",
        )
        started = True
        _scheduler._run_required(
            [
                scheduler.systemctl,
                "--user",
                "enable",
                "--now",
                f"{scheduler.unit}.timer",
            ],
            environment,
            "systemd timer enable",
            timeout=30.0,
        )
    # constitution: exempt C-ERR — rollback must preserve KeyboardInterrupt.
    except BaseException:
        if started:
            try:
                _scheduler._stop_scheduler_job(scheduler, environment)
            except InstallError as error:
                raise _scheduler.SchedulerTeardownError(
                    "systemd teardown could not be verified"
                ) from error
        raise


def _stop_scheduler_job(scheduler: _Scheduler, environment: Mapping[str, str]) -> None:
    """Stop the recorded scheduler and verify both systemd units are inactive."""
    if scheduler.kind == "launchd":
        _scheduler._run_required(
            [scheduler.launchctl, "bootout", scheduler.service],
            environment,
            "launchd bootout",
        )
        return
    if scheduler.kind == "none":
        return
    timer, service = f"{scheduler.unit}.timer", f"{scheduler.unit}.service"
    _scheduler._run_best_effort(
        [scheduler.systemctl, "--user", "reset-failed", timer, service], environment
    )
    if scheduler.persistent:
        _scheduler._run_required(
            [scheduler.systemctl, "--user", "disable", timer],
            environment,
            "systemd timer disable",
        )
    try:
        stopped = _scheduler._run_quiet(
            [scheduler.systemctl, "--user", "stop", timer, service], environment, 10.0
        )
        if stopped.returncode != 0:
            raise InstallError("systemd unit stop failed")
    except (OSError, subprocess.SubprocessError) as error:
        raise InstallError("systemd unit stop failed") from error
    try:
        probe = _scheduler._run_quiet(
            [scheduler.systemctl, "--user", "is-active", timer, service],
            environment,
            10.0,
        )
    except (OSError, subprocess.SubprocessError) as error:
        raise InstallError("systemd unit state could not be verified") from error
    states = probe.stdout.decode("utf-8", "replace").split() if probe.stdout else []
    if probe.returncode == 0:
        raise InstallError("systemd unit stop failed")
    if not _scheduler._verified_inactive(states):
        raise InstallError("systemd unit state could not be verified")


def _scheduler_reactivate(
    scheduler: _Scheduler,
    paths: _scheduler.InstallPaths,
    python: str,
    environment: Mapping[str, str],
) -> None:
    """Best-effort re-arm of a previously running scheduler after rollback."""
    if scheduler.kind == "launchd":
        if _scheduler._path_present(paths.plist):
            _scheduler._run_best_effort(
                [scheduler.launchctl, "bootstrap", scheduler.domain, str(paths.plist)],
                environment,
            )
        return
    if scheduler.kind == "none":
        return
    if _scheduler._path_present(paths.systemd_timer) and _scheduler._path_present(
        paths.systemd_service
    ):
        _scheduler._run_best_effort(
            [scheduler.systemctl, "--user", "daemon-reload"], environment
        )
        _scheduler._run_best_effort(
            [
                scheduler.systemctl,
                "--user",
                "enable",
                "--now",
                f"{scheduler.unit}.timer",
            ],
            environment,
        )
        return
    if scheduler.systemd_run:
        _scheduler._run_best_effort(
            scheduler.systemd_argv(paths, python, environment), environment
        )

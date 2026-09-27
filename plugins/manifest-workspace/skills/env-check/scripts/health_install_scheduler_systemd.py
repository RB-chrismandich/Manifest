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
from contextlib import suppress
from typing import TYPE_CHECKING

import health_install_scheduler as _scheduler
from health_install_files import InstallError

if TYPE_CHECKING:
    from health_install_scheduler import _Scheduler


def _activate_persistent_systemd(
    scheduler: _Scheduler, environment: Mapping[str, str]
) -> None:
    """Reload the user manager, then enable and start the persistent timer.

    A timer left half-enabled after `daemon-reload` is stopped best-effort so
    the surrounding transaction can roll the install back; a failure before
    that point leaves nothing armed.
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
            with suppress(OSError, subprocess.SubprocessError, InstallError):
                _scheduler._stop_scheduler_job(scheduler, environment)
        raise

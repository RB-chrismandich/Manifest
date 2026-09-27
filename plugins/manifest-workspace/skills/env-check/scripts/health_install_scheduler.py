#!/usr/bin/env python3
"""Platform scheduler abstraction and process helpers for the health installer.

Owns the launchd/systemd job identity recorded in the installation receipt:
resolution for the current platform, reconstruction from a recorded receipt,
stop/reactivate for replacement and rollback, and activation during apply.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from collections.abc import Mapping, Sequence
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path

from health_install_files import (
    LAUNCHD_LABEL,
    OWNERSHIP_MARKER,
    InstallError,
    InstallPaths,
    _atomic_write,
    _path_present,
    _plist_payload,
)

SYSTEMD_UNIT_NAME = "manifest-health-report"
SYSTEMD_ON_CALENDAR = "Mon *-*-* 09:00:00"


def _resolve_executable(name: str) -> str:
    candidate = shutil.which(name)
    if not candidate:
        raise InstallError(f"required executable is unavailable: {name}")
    resolved = Path(candidate).resolve(strict=False)
    if not resolved.is_file() or not os.access(resolved, os.X_OK):
        raise InstallError(f"required executable is not runnable: {name}")
    return str(resolved)


def _run_quiet(
    argv: Sequence[str],
    environment: Mapping[str, str],
    timeout: float,
) -> subprocess.CompletedProcess:
    return subprocess.run(
        list(argv),
        env=dict(environment),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        timeout=timeout,
        check=False,
        start_new_session=True,
    )


def _run_required(
    argv: Sequence[str],
    environment: Mapping[str, str],
    description: str,
    timeout: float = 10.0,
) -> None:
    try:
        result = _run_quiet(argv, environment, timeout)
    except (OSError, subprocess.SubprocessError) as error:
        raise InstallError(f"{description} could not be executed") from error
    if result.returncode != 0:
        raise InstallError(f"{description} failed")


def _run_best_effort(
    argv: Sequence[str], environment: Mapping[str, str], timeout: float = 10.0
) -> None:
    with suppress(OSError, subprocess.SubprocessError):
        _run_quiet(argv, environment, timeout)


def _scheduler_kind(platform: object) -> str:
    return "launchd" if platform == "darwin" else "systemd"


def _receipt_scheduler_kind(receipt: dict | None) -> str:
    """Read the recorded scheduler kind; receipts without one predate systemd."""
    if isinstance(receipt, dict):
        scheduler = receipt.get("scheduler")
        if isinstance(scheduler, dict) and scheduler.get("kind") == "systemd":
            return "systemd"
    return "launchd"


def _systemd_environment(
    paths: InstallPaths, environment: Mapping[str, str]
) -> dict[str, str]:
    return {
        "HOME": str(paths.home),
        "OMP_AGENT_DIR": str(paths.agent_root),
        "PATH": environment.get("PATH") or os.defpath,
        "XDG_CONFIG_HOME": str(paths.config_home),
        "XDG_DATA_HOME": str(paths.data_home),
        "XDG_STATE_HOME": str(paths.state_home),
    }


@dataclass(frozen=True)
class _Scheduler:
    """The platform job scheduler that owns the weekly health report."""

    kind: str
    domain: str
    service: str
    unit: str
    launchctl: str
    plutil: str
    systemd_run: str
    systemctl: str
    payload: bytes

    def systemd_argv(
        self,
        paths: InstallPaths,
        python: str,
        environment: Mapping[str, str],
    ) -> list[str]:
        report = (paths.runtime_root / "health_report.py").resolve(strict=False)
        environment_pairs = _systemd_environment(paths, environment)
        return [
            self.systemd_run,
            "--user",
            f"--unit={self.unit}",
            f"--description={OWNERSHIP_MARKER} weekly health report",
            "--timer-property=AccuracySec=1min",
            f"--on-calendar={SYSTEMD_ON_CALENDAR}",
            *(
                f"--setenv={key}={value}"
                for key, value in sorted(environment_pairs.items())
            ),
            python,
            str(report),
            "--json",
            "--harness",
            "claude",
            "--harness",
            "omp",
            "--out-dir",
            str(paths.report_root.resolve(strict=False)),
        ]

    def metadata(self) -> dict[str, object]:
        """Deterministic scheduler identity recorded for replace/uninstall."""
        if self.kind == "launchd":
            return {
                "kind": "launchd",
                "managed_by": OWNERSHIP_MARKER,
                "label": LAUNCHD_LABEL,
                "domain": self.domain,
            }
        return {
            "kind": "systemd",
            "managed_by": OWNERSHIP_MARKER,
            "unit": self.unit,
            "timer": f"{self.unit}.timer",
            "service": f"{self.unit}.service",
            "on_calendar": SYSTEMD_ON_CALENDAR,
        }


def _resolve_scheduler(
    paths: InstallPaths, environment: Mapping[str, str], python: str
) -> _Scheduler:
    kind = _scheduler_kind(sys.platform)
    if kind == "launchd":
        return _Scheduler(
            kind=kind,
            domain=f"gui/{os.getuid()}",
            service=f"gui/{os.getuid()}/{LAUNCHD_LABEL}",
            unit="",
            launchctl=_resolve_executable("launchctl"),
            plutil=_resolve_executable("plutil"),
            systemd_run="",
            systemctl="",
            payload=_plist_payload(paths, python, environment),
        )
    return _Scheduler(
        kind=kind,
        domain="",
        service="",
        unit=SYSTEMD_UNIT_NAME,
        launchctl="",
        plutil="",
        systemd_run=_resolve_executable("systemd-run"),
        systemctl=_resolve_executable("systemctl"),
        payload=b"",
    )


def _recorded_scheduler(receipt: dict, environment: Mapping[str, str]) -> _Scheduler:
    """Rebuild the scheduler recorded in the receipt for stop/replacement."""
    if _receipt_scheduler_kind(receipt) == "launchd":
        domain = f"gui/{os.getuid()}"
        return _Scheduler(
            kind="launchd",
            domain=domain,
            service=f"{domain}/{LAUNCHD_LABEL}",
            unit="",
            launchctl=_resolve_executable("launchctl"),
            plutil="",
            systemd_run="",
            systemctl="",
            payload=b"",
        )
    return _Scheduler(
        kind="systemd",
        domain="",
        service="",
        unit=SYSTEMD_UNIT_NAME,
        launchctl="",
        plutil="",
        systemd_run=_resolve_executable("systemd-run"),
        systemctl=_resolve_executable("systemctl"),
        payload=b"",
    )


def _stop_scheduler_job(scheduler: _Scheduler, environment: Mapping[str, str]) -> None:
    """Stop the recorded job; any failure aborts before deletion proceeds."""
    if scheduler.kind == "launchd":
        _run_required(
            [scheduler.launchctl, "bootout", scheduler.service],
            environment,
            "launchd bootout",
        )
        return
    timer = f"{scheduler.unit}.timer"
    service = f"{scheduler.unit}.service"
    _run_best_effort(
        [scheduler.systemctl, "--user", "reset-failed", timer, service], environment
    )
    _run_best_effort(
        [scheduler.systemctl, "--user", "stop", timer, service], environment
    )
    try:
        active = _run_quiet(
            [scheduler.systemctl, "--user", "is-active", timer, service],
            environment,
            10.0,
        )
    except (OSError, subprocess.SubprocessError):
        return
    if active.returncode == 0:
        raise InstallError("systemd unit stop failed")


def _scheduler_reactivate(
    scheduler: _Scheduler,
    paths: InstallPaths,
    python: str,
    environment: Mapping[str, str],
) -> None:
    """Best-effort re-arm of a previously running job after a failure."""
    if scheduler.kind == "launchd":
        if _path_present(paths.plist):
            _run_best_effort(
                [scheduler.launchctl, "bootstrap", scheduler.domain, str(paths.plist)],
                environment,
            )
        return
    _run_best_effort(scheduler.systemd_argv(paths, python, environment), environment)


def _activate_scheduler_job(
    scheduler: _Scheduler,
    prior: _Scheduler | None,
    paths: InstallPaths,
    python: str,
    receipt_payload: bytes,
    environment: Mapping[str, str],
) -> None:
    """Stop the prior job, persist scheduler artifacts, then arm the new job.

    The receipt lands before the job is armed so a post-activate failure rolls
    back with the new scheduler identity recorded; a partially armed job is
    stopped best-effort inside this helper.
    """
    if prior is not None:
        _stop_scheduler_job(prior, environment)
    if scheduler.kind == "launchd":
        _atomic_write(paths.plist, scheduler.payload, 0o600)
        _run_required(
            [scheduler.plutil, "-lint", str(paths.plist)],
            environment,
            "launchd plist lint",
        )
    _atomic_write(paths.receipt, receipt_payload, 0o600)
    scheduler_started = False
    try:
        if scheduler.kind == "launchd":
            _run_required(
                [scheduler.launchctl, "bootstrap", scheduler.domain, str(paths.plist)],
                environment,
                "launchd bootstrap",
            )
            scheduler_started = True
            _run_required(
                [scheduler.launchctl, "kickstart", "-k", scheduler.service],
                environment,
                "launchd kickstart",
            )
        else:
            _run_required(
                scheduler.systemd_argv(paths, python, environment),
                environment,
                "systemd timer creation",
                timeout=30.0,
            )
            scheduler_started = True
    except BaseException:
        if scheduler_started:
            with suppress(OSError, subprocess.SubprocessError, InstallError):
                _stop_scheduler_job(scheduler, environment)
        raise

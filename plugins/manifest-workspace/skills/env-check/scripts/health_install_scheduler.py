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
    SYSTEMD_UNIT_MARKER,
    SYSTEMD_UNIT_NAME,
    InstallError,
    InstallPaths,
    _atomic_write,
    _path_present,
    _plist_payload,
)

SYSTEMD_ON_CALENDAR = "Mon *-*-* 09:00:00"
_INACTIVE_UNIT_STATES = frozenset({"inactive", "failed"})


def _resolve_executable(name: str) -> str:
    candidate = shutil.which(name)
    if candidate is None:
        raise InstallError(f"required executable not found on PATH: {name}")
    resolved = Path(candidate).resolve(strict=False)
    if not resolved.is_file() or not os.access(resolved, os.X_OK):
        raise InstallError(f"required executable is not runnable: {name}")
    return str(resolved)


def _find_executable(name: str) -> str:
    try:
        return _resolve_executable(name)
    except InstallError:
        return ""


def _run_quiet(
    argv: Sequence[str], environment: Mapping[str, str], timeout: float = 10.0
) -> subprocess.CompletedProcess:
    return subprocess.run(
        list(argv),
        env=dict(environment),
        capture_output=True,
        check=False,
        timeout=timeout,
    )


def _run_required(
    argv: Sequence[str],
    environment: Mapping[str, str],
    description: str,
    timeout: float = 10.0,
) -> None:
    try:
        completed = _run_quiet(argv, environment, timeout)
    except (OSError, subprocess.SubprocessError) as error:
        raise InstallError(f"{description} failed") from error
    if completed.returncode != 0:
        raise InstallError(f"{description} failed")


def _run_best_effort(
    argv: Sequence[str], environment: Mapping[str, str], timeout: float = 10.0
) -> None:
    with suppress(OSError, subprocess.SubprocessError):
        _run_quiet(argv, environment, timeout)


def _scheduler_kind(platform: object) -> str:
    if platform == "darwin":
        return "launchd"
    if platform == "linux":
        return "systemd"
    raise InstallError(f"unsupported scheduler platform: {platform}")


def _receipt_scheduler_kind(receipt: dict | None) -> str:
    """Read the recorded scheduler kind; receipts without one predate systemd."""
    if isinstance(receipt, dict):
        scheduler = receipt.get("scheduler")
        if isinstance(scheduler, dict) and scheduler.get("kind") in (
            "none",
            "systemd",
        ):
            return scheduler["kind"]
    return "launchd"


def _report_environment(
    paths: InstallPaths, environment: Mapping[str, str]
) -> dict[str, str]:
    """Environment shared by the launchd and systemd scheduled reports."""
    report_environment = {
        "HOME": str(paths.home),
        "OMP_AGENT_DIR": str(paths.agent_root),
        "PATH": environment.get("PATH") or os.defpath,
        "XDG_CONFIG_HOME": str(paths.config_home),
        "XDG_DATA_HOME": str(paths.data_home),
        "XDG_STATE_HOME": str(paths.state_home),
    }
    if environment.get("CLAUDE_CONFIG_DIR"):
        report_environment["CLAUDE_CONFIG_DIR"] = str(paths.claude_root)
    return report_environment


def _report_argv(paths: InstallPaths, python: str) -> list[str]:
    report = (paths.runtime_root / "health_report.py").resolve(strict=False)
    return [
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


def _systemd_quote(value: str) -> str:
    """Quote one systemd directive value; unit files parse \\ and " escapes."""
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _systemd_unit_payloads(
    paths: InstallPaths, python: str, environment: Mapping[str, str]
) -> tuple[bytes, bytes]:
    """(timer, service) payloads carrying the ownership marker comment."""
    environment_lines = [
        f"Environment={_systemd_quote(f'{key}={value}')}"
        for key, value in sorted(_report_environment(paths, environment).items())
    ]
    service = "\n".join(
        [
            SYSTEMD_UNIT_MARKER,
            "[Unit]",
            f"Description={OWNERSHIP_MARKER} weekly health report",
            "",
            "[Service]",
            "Type=oneshot",
            *environment_lines,
            "ExecStart="
            + " ".join(_systemd_quote(arg) for arg in _report_argv(paths, python)),
            "",
        ]
    ).encode("utf-8")
    timer = "\n".join(
        [
            SYSTEMD_UNIT_MARKER,
            "[Unit]",
            f"Description={OWNERSHIP_MARKER} weekly health report timer",
            "",
            "[Timer]",
            f"OnCalendar={SYSTEMD_ON_CALENDAR}",
            "AccuracySec=1min",
            "Persistent=true",
            f"Unit={SYSTEMD_UNIT_NAME}.service",
            "",
            "[Install]",
            "WantedBy=timers.target",
            "",
        ]
    ).encode("utf-8")
    return timer, service


def _systemd_manager_usable(systemctl: str, environment: Mapping[str, str]) -> bool:
    """Probe the systemd user manager; an unreachable bus means no manager."""
    if not systemctl:
        return False
    try:
        completed = _run_quiet(
            [systemctl, "--user", "show-environment"], environment, 10.0
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return completed.returncode == 0


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
    timer_payload: bytes = b""
    service_payload: bytes = b""
    persistent: bool = False

    def systemd_argv(
        self,
        paths: InstallPaths,
        python: str,
        environment: Mapping[str, str],
    ) -> list[str]:
        """Transient systemd-run argv retained to re-arm legacy receipts."""
        environment_pairs = _report_environment(paths, environment)
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
            *_report_argv(paths, python),
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
        if self.kind == "none":
            return {"kind": "none", "managed_by": OWNERSHIP_MARKER}
        return {
            "kind": "systemd",
            "managed_by": OWNERSHIP_MARKER,
            "unit": self.unit,
            "timer": f"{self.unit}.timer",
            "service": f"{self.unit}.service",
            "on_calendar": SYSTEMD_ON_CALENDAR,
        }


def _unscheduled_scheduler(systemctl: str) -> _Scheduler:
    """Return the receipt representation for hosts without a usable scheduler."""
    return _Scheduler(
        kind="none",
        domain="",
        service="",
        unit="",
        launchctl="",
        plutil="",
        systemd_run="",
        systemctl=systemctl,
        payload=b"",
    )


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
    systemctl = _find_executable("systemctl")
    if not _systemd_manager_usable(systemctl, environment):
        # Linux hosts without a usable systemd user manager (containers, WSL,
        # headless sessions) install the runtime without a scheduled job rather
        # than failing midway through the transaction.
        return _unscheduled_scheduler(systemctl)
    timer_payload, service_payload = _systemd_unit_payloads(paths, python, environment)
    return _Scheduler(
        kind=kind,
        domain="",
        service="",
        unit=SYSTEMD_UNIT_NAME,
        launchctl="",
        plutil="",
        systemd_run=_find_executable("systemd-run"),
        systemctl=systemctl,
        payload=b"",
        timer_payload=timer_payload,
        service_payload=service_payload,
        persistent=True,
    )


def _recorded_scheduler(receipt: dict, environment: Mapping[str, str]) -> _Scheduler:
    """Rebuild the scheduler recorded in the receipt for stop/replacement."""
    recorded = _receipt_scheduler_kind(receipt)
    if recorded == "none":
        return _unscheduled_scheduler(_find_executable("systemctl"))
    if recorded == "launchd":
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
        systemd_run=_find_executable("systemd-run"),
        systemctl=_resolve_executable("systemctl"),
        payload=b"",
        # Receipt rows exist only for persistent unit installations; older
        # receipts armed a transient systemd-run timer instead.
        persistent=isinstance(receipt, dict)
        and receipt.get("systemd_timer") is not None,
    )


def _verified_inactive(states: object) -> bool:
    if not isinstance(states, list) or len(states) != 2:
        return False
    return all(state in _INACTIVE_UNIT_STATES for state in states)


def _stop_scheduler_job(scheduler: _Scheduler, environment: Mapping[str, str]) -> None:
    """Stop the recorded job; any failure aborts before deletion proceeds."""
    if scheduler.kind == "launchd":
        _run_required(
            [scheduler.launchctl, "bootout", scheduler.service],
            environment,
            "launchd bootout",
        )
        return
    if scheduler.kind == "none":
        return
    timer = f"{scheduler.unit}.timer"
    service = f"{scheduler.unit}.service"
    _run_best_effort(
        [scheduler.systemctl, "--user", "reset-failed", timer, service], environment
    )
    if scheduler.persistent:
        _run_required(
            [scheduler.systemctl, "--user", "disable", timer],
            environment,
            "systemd timer disable",
        )
    try:
        _run_quiet(
            [scheduler.systemctl, "--user", "stop", timer, service],
            environment,
            10.0,
        )
    except (OSError, subprocess.SubprocessError) as error:
        raise InstallError("systemd unit stop failed") from error
    try:
        probe = _run_quiet(
            [scheduler.systemctl, "--user", "is-active", timer, service],
            environment,
            10.0,
        )
    except (OSError, subprocess.SubprocessError) as error:
        raise InstallError("systemd unit state could not be verified") from error
    states = probe.stdout.decode("utf-8", "replace").split() if probe.stdout else []
    if probe.returncode == 0:
        # At least one unit is still active; never delete an armed job.
        raise InstallError("systemd unit stop failed")
    if not _verified_inactive(states):
        # A nonzero is-active status is only proof of inactivity when every
        # unit reports inactive/failed; a bus error or unknown state is fatal.
        raise InstallError("systemd unit state could not be verified")
    # A failed stop with a verified-inactive outcome (for example units already
    # unloaded after a reboot) leaves nothing armed, so deletion is safe.


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
    if scheduler.kind == "none":
        return
    if _path_present(paths.systemd_timer) and _path_present(paths.systemd_service):
        _run_best_effort([scheduler.systemctl, "--user", "daemon-reload"], environment)
        _run_best_effort(
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
        _run_best_effort(
            scheduler.systemd_argv(paths, python, environment), environment
        )


def _activate_scheduler_job(
    scheduler: _Scheduler,
    prior: _Scheduler | None,
    paths: InstallPaths,
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
        if prior.kind == "systemd" and prior.persistent and scheduler.kind != "systemd":
            # The new scheduler does not own unit files; drop the recorded ones
            # so a disabled-but-present unit cannot linger (snapshots restore
            # them if the transaction rolls back).
            for unit_path in (paths.systemd_timer, paths.systemd_service):
                if _path_present(unit_path):
                    unit_path.unlink()
            _run_best_effort([prior.systemctl, "--user", "daemon-reload"], environment)
    if scheduler.kind == "launchd":
        _atomic_write(paths.plist, scheduler.payload, 0o600)
        _run_required(
            [scheduler.plutil, "-lint", str(paths.plist)],
            environment,
            "launchd plist lint",
        )
    elif scheduler.kind == "systemd":
        _atomic_write(paths.systemd_timer, scheduler.timer_payload, 0o600)
        _atomic_write(paths.systemd_service, scheduler.service_payload, 0o600)
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
        elif scheduler.kind == "systemd":
            # Deferred import: the sibling imports this module for its helpers.
            import health_install_scheduler_systemd as systemd_activation

            systemd_activation._activate_persistent_systemd(scheduler, environment)
    # constitution: exempt C-ERR — rollback must preserve KeyboardInterrupt.
    except BaseException:
        if scheduler_started:
            with suppress(OSError, subprocess.SubprocessError, InstallError):
                _stop_scheduler_job(scheduler, environment)
        raise

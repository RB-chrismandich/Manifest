#!/usr/bin/env python3
"""Payload manifests and installation-receipt validation for the installer.

Owns the source-inventory contracts: which bundle files ship into the managed
runtime, which hook sources are hashed, and whether a recorded receipt can be
trusted to describe an owned installation before it is replaced or removed.
"""

from __future__ import annotations

import os
from pathlib import Path

from health_install_files import (
    LAUNCHD_LABEL,
    OWNERSHIP_MARKER,
    RETIRED_RUNTIME_SOURCES,
    SESSION_TIMEOUT_SECONDS,
    InstallError,
    InstallPaths,
    _digest,
    _is_digest,
    _path_present,
    _read_regular,
    _valid_row,
)
from health_install_scheduler import SYSTEMD_UNIT_NAME

# Receipts recorded before the scheduler modules were split out do not carry
# either split runtime-file row.
_SPLIT_RUNTIME_EXEMPT = {
    "health_install_scheduler.py",
    "health_install_scheduler_systemd.py",
}

RUNTIME_SOURCES = {
    "env_check.py": Path(
        "plugins",
        "manifest-workspace",
        "skills",
        "env-check",
        "scripts",
        "env_check.py",
    ),
    "health_report.py": Path(
        "plugins",
        "manifest-workspace",
        "skills",
        "env-check",
        "scripts",
        "health_report.py",
    ),
    "health_report_collect.py": Path(
        "plugins",
        "manifest-workspace",
        "skills",
        "env-check",
        "scripts",
        "health_report_collect.py",
    ),
    "health_report_common.py": Path(
        "plugins",
        "manifest-workspace",
        "skills",
        "env-check",
        "scripts",
        "health_report_common.py",
    ),
    "health_report_inspect.py": Path(
        "plugins",
        "manifest-workspace",
        "skills",
        "env-check",
        "scripts",
        "health_report_inspect.py",
    ),
    "health_report_sanitize.py": Path(
        "plugins",
        "manifest-workspace",
        "skills",
        "env-check",
        "scripts",
        "health_report_sanitize.py",
    ),
    "health_install_files.py": Path(
        "plugins",
        "manifest-workspace",
        "skills",
        "env-check",
        "scripts",
        "health_install_files.py",
    ),
    "health_install_reconcile.py": Path(
        "plugins",
        "manifest-workspace",
        "skills",
        "env-check",
        "scripts",
        "health_install_reconcile.py",
    ),
    "health_install_scheduler.py": Path(
        "plugins",
        "manifest-workspace",
        "skills",
        "env-check",
        "scripts",
        "health_install_scheduler.py",
    ),
    "health_install_scheduler_systemd.py": Path(
        "plugins",
        "manifest-workspace",
        "skills",
        "env-check",
        "scripts",
        "health_install_scheduler_systemd.py",
    ),
    "mcp_health_expectations.py": Path(
        "plugins",
        "manifest-workspace",
        "skills",
        "env-check",
        "scripts",
        "mcp_health_expectations.py",
    ),
    "mcp_health_report.py": Path(
        "plugins",
        "manifest-workspace",
        "skills",
        "env-check",
        "scripts",
        "mcp_health_report.py",
    ),
    "mcp_health_runtime.py": Path(
        "plugins",
        "manifest-workspace",
        "skills",
        "env-check",
        "scripts",
        "mcp_health_runtime.py",
    ),
    "hook_smoke.py": Path("configs", "claude", "scripts", "hook_smoke.py"),
    "hook_smoke_support.py": Path(
        "configs", "claude", "scripts", "hook_smoke_support.py"
    ),
    "mcp_health.py": Path(
        "plugins",
        "manifest-workspace",
        "skills",
        "env-check",
        "scripts",
        "mcp_health.py",
    ),
}
OMP_EXTENSION_SOURCE = Path("configs", "omp", "extensions", "manifest-health.ts")
CLAUDE_WRAPPER_SOURCE = Path("configs", "claude", "scripts", "mcp_health_check.sh")
HOOK_HASH_SOURCES = {
    "delegate.py": Path("plugins", "manifest-delegate", "scripts", "delegate.py"),
    "hooks.json": Path("plugins", "manifest-delegate", "hooks", "hooks.json"),
    "stop_gate_hook.py": Path(
        "plugins", "manifest-delegate", "scripts", "stop_gate_hook.py"
    ),
    "stop_gate_hook.sh": Path(
        "plugins", "manifest-delegate", "scripts", "stop_gate_hook.sh"
    ),
}


def _validate_receipt(receipt: dict, paths: InstallPaths) -> None:
    source_root = receipt.get("source_root")
    if not isinstance(source_root, str) or not Path(source_root).is_absolute():
        raise InstallError("health installation manifest has an invalid source root")
    executables = receipt.get("executables")
    if not isinstance(executables, dict) or set(executables) != {
        "python",
        "omp",
        "claude",
        "coordinator",
    }:
        raise InstallError("health installation manifest has invalid executables")
    if any(
        not isinstance(value, str) or not Path(value).is_absolute()
        for value in executables.values()
    ):
        raise InstallError("health installation manifest has non-absolute executables")
    _validate_receipt_files(receipt.get("files"), paths.runtime_root)
    for key, destination in (
        ("omp_extension", paths.extension),
        ("claude_wrapper", paths.wrapper),
    ):
        if not _valid_row(receipt.get(key), destination):
            raise InstallError(f"health installation manifest has an invalid {key} row")
    _validate_receipt_scheduler(receipt, paths)
    expected_hook = {
        "command": str(paths.wrapper.resolve(strict=False)),
        "timeout": SESSION_TIMEOUT_SECONDS,
    }
    if receipt.get("claude_hook") != expected_hook:
        raise InstallError(
            "health installation manifest has an invalid Claude hook row"
        )
    hashes = receipt.get("hook_hashes")
    if (
        not isinstance(hashes, dict)
        or set(hashes) != set(HOOK_HASH_SOURCES)
        or any(not _is_digest(value) for value in hashes.values())
    ):
        raise InstallError("health installation manifest has invalid hook hashes")


def _validate_receipt_scheduler(receipt: dict, paths: InstallPaths) -> None:
    """Validate the recorded scheduler identity used to stop the job."""
    scheduler = receipt.get("scheduler")
    if scheduler is None:
        # Receipts written before the scheduler block are launchd-era.
        if not _valid_row(receipt.get("launchd_plist"), paths.plist):
            raise InstallError(
                "health installation manifest has an invalid launchd_plist row"
            )
        return
    if not isinstance(scheduler, dict) or scheduler.get("kind") not in (
        "launchd",
        "none",
        "systemd",
    ):
        raise InstallError("health installation manifest has an invalid scheduler")
    if scheduler.get("managed_by") != OWNERSHIP_MARKER:
        raise InstallError(
            "health installation manifest has an invalid scheduler marker"
        )
    if scheduler.get("kind") == "launchd":
        if (
            scheduler.get("label") != LAUNCHD_LABEL
            or scheduler.get("domain") != f"gui/{os.getuid()}"
        ):
            raise InstallError(
                "health installation manifest has an invalid launchd identity"
            )
        if not _valid_row(receipt.get("launchd_plist"), paths.plist):
            raise InstallError(
                "health installation manifest has an invalid launchd_plist row"
            )
        return
    if scheduler.get("kind") == "none":
        _validate_unscheduled_receipt(receipt, scheduler)
        return
    if (
        scheduler.get("unit") != SYSTEMD_UNIT_NAME
        or scheduler.get("timer") != f"{SYSTEMD_UNIT_NAME}.timer"
        or scheduler.get("service") != f"{SYSTEMD_UNIT_NAME}.service"
    ):
        raise InstallError(
            "health installation manifest has an invalid systemd identity"
        )
    # Unit rows exist only for persistent installations; older receipts armed a
    # transient systemd-run timer, so rows are valid only when both recorded.
    unit_rows = (
        ("systemd_timer", paths.systemd_timer),
        ("systemd_service", paths.systemd_service),
    )
    if any(receipt.get(key) is not None for key, _path in unit_rows):
        for key, destination in unit_rows:
            if not _valid_row(receipt.get(key), destination):
                raise InstallError(
                    "health installation manifest has an invalid systemd unit row"
                )


def _validate_unscheduled_receipt(receipt: dict, scheduler: dict) -> None:
    """Reject a `none` receipt that still records scheduler identity or files.

    An unscheduled install owns no scheduler artifacts; any leftover row means
    the job may still run against runtime files uninstall would delete.
    """
    artifact_rows = ("launchd_plist", "systemd_timer", "systemd_service")
    identity_keys = set(scheduler) - {"kind", "managed_by"}
    if identity_keys or any(receipt.get(key) is not None for key in artifact_rows):
        raise InstallError(
            "health installation manifest records scheduler artifacts "
            "for an unscheduled install"
        )


def _validate_receipt_files(files: object, runtime_root: Path) -> None:
    if not isinstance(files, dict):
        raise InstallError(
            "health installation manifest has an invalid runtime inventory"
        )
    file_keys = set(files)
    retired_keys = file_keys & RETIRED_RUNTIME_SOURCES
    runtime_keys = file_keys - RETIRED_RUNTIME_SOURCES
    missing_runtime_keys = set(RUNTIME_SOURCES) - runtime_keys
    valid_keys = (
        retired_keys in (set(), RETIRED_RUNTIME_SOURCES)
        and runtime_keys <= set(RUNTIME_SOURCES)
        and missing_runtime_keys <= _SPLIT_RUNTIME_EXEMPT
    )
    if not valid_keys:
        raise InstallError(
            "health installation manifest has an invalid runtime inventory"
        )
    for name in RUNTIME_SOURCES:
        if name in _SPLIT_RUNTIME_EXEMPT and name not in files:
            # Pre-split receipts carry no row for the split runtime file.
            continue
        if not _valid_row(files.get(name), runtime_root / name):
            raise InstallError(
                "health installation manifest has an invalid runtime row"
            )
    for name in RETIRED_RUNTIME_SOURCES:
        if name in files:
            dest = runtime_root / name
            if _path_present(dest) and not _valid_row(files.get(name), dest):
                raise InstallError(
                    f"health installation manifest has an invalid runtime row for {name}"
                )


def _hook_hashes(source_root: Path) -> dict[str, str]:
    return {
        name: _digest(_read_regular(source_root / relative, f"hook source {name}"))
        for name, relative in HOOK_HASH_SOURCES.items()
    }

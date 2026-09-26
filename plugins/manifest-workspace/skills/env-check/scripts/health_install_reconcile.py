#!/usr/bin/env python3
"""Settings-hook reconciliation and install staging for the health installer."""

from __future__ import annotations

import copy
import os
import shutil
import subprocess
import sys
from collections.abc import Mapping, Sequence
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from health_install_files import (
    LAUNCHD_LABEL,
    SCHEMA_VERSION,
    SESSION_TIMEOUT_SECONDS,
    FileSnapshot,
    InstallError,
    InstallPaths,
    _assert_destination_owned,
    _atomic_write,
    _digest,
    _json_bytes,
    _owned_row,
    _path_present,
    _read_regular,
    _restore_snapshots,
)


def _managed_hook(command: str) -> dict[str, object]:
    return {"type": "command", "command": command, "timeout": SESSION_TIMEOUT_SECONDS}


def _session_entries(settings: dict) -> tuple[dict, list]:
    hooks = settings.setdefault("hooks", {})
    if not isinstance(hooks, dict):
        raise InstallError("Claude settings hooks value is not an object")
    entries = hooks.setdefault("SessionStart", [])
    if not isinstance(entries, list):
        raise InstallError("Claude SessionStart hooks value is not a list")
    return hooks, entries


def _uninstalled_entries(updated: dict) -> tuple[dict, list] | None:
    hooks_value = updated.get("hooks")
    if hooks_value is None:
        return None
    if not isinstance(hooks_value, dict):
        raise InstallError("Claude settings hooks value is not an object")
    entries_value = hooks_value.get("SessionStart")
    if entries_value is None:
        return None
    if not isinstance(entries_value, list):
        raise InstallError("Claude SessionStart hooks value is not a list")
    return hooks_value, entries_value


def _rewrite_health_hook(settings: dict, command: str, *, install: bool) -> dict:
    updated = copy.deepcopy(settings)
    if install:
        hooks, entries = _session_entries(updated)
    else:
        uninstalled = _uninstalled_entries(updated)
        if uninstalled is None:
            return updated
        hooks, entries = uninstalled
    desired = _managed_hook(command)
    rewritten: list[object] = []
    for entry in entries:
        if not isinstance(entry, dict) or not isinstance(entry.get("hooks"), list):
            rewritten.append(entry)
            continue
        retained: list[object] = []
        removed = False
        for hook in entry["hooks"]:
            if isinstance(hook, dict) and hook.get("command") == command:
                if hook != desired:
                    raise InstallError(
                        "Claude health hook registration was externally edited"
                    )
                removed = True
                continue
            retained.append(hook)
        if retained:
            item = copy.deepcopy(entry)
            item["hooks"] = retained
            rewritten.append(item)
        elif not removed:
            rewritten.append(entry)
    if install:
        rewritten.append({"hooks": [desired]})
    hooks["SessionStart"] = rewritten
    return updated


def _hook_is_present(settings: dict, command: str) -> bool:
    hooks = settings.get("hooks")
    if not isinstance(hooks, dict):
        return False
    entries = hooks.get("SessionStart")
    if not isinstance(entries, list):
        return False
    return any(
        isinstance(entry, dict)
        and isinstance(entry.get("hooks"), list)
        and any(
            isinstance(hook, dict) and hook.get("command") == command
            for hook in entry["hooks"]
        )
        for entry in entries
    )


def _resolve_executable(name: str) -> str:
    candidate = shutil.which(name)
    if not candidate:
        raise InstallError(f"required executable is unavailable: {name}")
    resolved = Path(candidate).resolve(strict=False)
    if not resolved.is_file() or not os.access(resolved, os.X_OK):
        raise InstallError(f"required executable is not runnable: {name}")
    return str(resolved)


def _executables() -> dict[str, str]:
    python = Path(sys.executable).resolve(strict=False)
    if not python.is_file() or not os.access(python, os.X_OK):
        raise InstallError("the current Python interpreter is not executable")
    return {
        "python": str(python),
        "omp": _resolve_executable("omp"),
        "claude": _resolve_executable("claude"),
        "coordinator": _resolve_executable("manifest"),
    }


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


def _smoke_runtime(
    runtime_root: Path,
    runtime_names: Sequence[str],
    python: str,
    environment: Mapping[str, str],
) -> None:
    smoke_environment = dict(environment)
    smoke_environment["PYTHONDONTWRITEBYTECODE"] = "1"
    for name in sorted(runtime_names):
        _run_required(
            [python, "-B", str(runtime_root / name), "--help"],
            smoke_environment,
            f"installed runtime smoke for {name}",
            timeout=5.0,
        )


def _managed_paths(paths: InstallPaths, runtime_names: Sequence[str]) -> list[Path]:
    return [
        *(paths.runtime_root / name for name in sorted(runtime_names)),
        paths.extension,
        paths.wrapper,
        paths.plist,
    ]


def _assert_no_unowned_install(
    paths: InstallPaths, settings: dict, runtime_names: Sequence[str]
) -> None:
    for path in _managed_paths(paths, runtime_names):
        if _path_present(path):
            raise InstallError(f"no ownership manifest exists for managed path: {path}")
    command = str(paths.wrapper.resolve(strict=False))
    if _hook_is_present(settings, command):
        raise InstallError("no ownership manifest exists for the Claude health hook")


def _install_omp_extension(
    source: Path, agent_root: Path, ownership: Mapping[str, object]
) -> None:
    destination = agent_root.resolve(strict=False) / "extensions" / "manifest-health.ts"
    row = ownership.get("omp_extension") if ownership else None
    _assert_destination_owned(destination, row, "OMP extension")
    payload = _read_regular(source, "OMP extension source")
    _atomic_write(destination, payload, 0o600)


@dataclass(frozen=True)
class _InstallPlan:
    source_root: Path
    paths: InstallPaths
    receipt: dict | None
    runtime: Mapping[str, tuple[Path, bytes]]
    extension_source: Path
    extension_payload: bytes
    wrapper_source: Path
    wrapper_payload: bytes
    plist_payload: bytes
    executables: Mapping[str, str]
    hook_hashes: Mapping[str, str]
    launchctl: str
    plutil: str
    settings_target: Path
    updated_settings: dict
    snapshots: Sequence[FileSnapshot]
    job_was_replaced: bool


def _build_receipt(plan: _InstallPlan) -> dict[str, object]:
    installed_at = (
        datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "installed_at": installed_at,
        "source_root": str(plan.source_root),
        "executables": dict(plan.executables),
        "files": {
            name: _owned_row(str(source), plan.paths.runtime_root / name, payload)
            for name, (source, payload) in sorted(plan.runtime.items())
        },
        "omp_extension": _owned_row(
            str(plan.extension_source), plan.paths.extension, plan.extension_payload
        ),
        "claude_wrapper": _owned_row(
            str(plan.wrapper_source), plan.paths.wrapper, plan.wrapper_payload
        ),
        "launchd_plist": _owned_row(
            f"generated:{LAUNCHD_LABEL}", plan.paths.plist, plan.plist_payload
        ),
        "claude_hook": {
            "command": str(plan.paths.wrapper.resolve(strict=False)),
            "timeout": SESSION_TIMEOUT_SECONDS,
        },
        "hook_hashes": dict(sorted(plan.hook_hashes.items())),
    }


def _apply_install(plan: _InstallPlan, environment: Mapping[str, str]) -> None:
    domain = f"gui/{os.getuid()}"
    service = f"{domain}/{LAUNCHD_LABEL}"
    job_was_bootstrapped = False
    try:
        for name, (_source, payload) in plan.runtime.items():
            _atomic_write(plan.paths.runtime_root / name, payload, 0o600)
        _smoke_runtime(
            plan.paths.runtime_root,
            plan.runtime.keys(),
            plan.executables["python"],
            environment,
        )

        _install_omp_extension(
            plan.extension_source, plan.paths.agent_root, plan.receipt or {}
        )
        if _digest(plan.paths.extension.read_bytes()) != _digest(
            plan.extension_payload
        ):
            raise InstallError("OMP extension source changed during installation")
        _atomic_write(plan.paths.wrapper, plan.wrapper_payload, 0o700)
        _atomic_write(plan.settings_target, _json_bytes(plan.updated_settings), 0o600)

        if plan.job_was_replaced:
            _run_best_effort([plan.launchctl, "bootout", service], environment)
        _atomic_write(plan.paths.plist, plan.plist_payload, 0o600)
        _run_required(
            [plan.plutil, "-lint", str(plan.paths.plist)],
            environment,
            "launchd plist lint",
        )

        _atomic_write(plan.paths.receipt, _json_bytes(_build_receipt(plan)), 0o600)
        _run_required(
            [plan.launchctl, "bootstrap", domain, str(plan.paths.plist)],
            environment,
            "launchd bootstrap",
        )
        job_was_bootstrapped = True
        _run_required(
            [plan.launchctl, "kickstart", "-k", service],
            environment,
            "launchd kickstart",
        )
    except BaseException:
        if job_was_bootstrapped:
            _run_best_effort([plan.launchctl, "bootout", service], environment)
        _restore_snapshots(plan.snapshots)
        if plan.job_was_replaced and _path_present(plan.paths.plist):
            _run_best_effort(
                [plan.launchctl, "bootstrap", domain, str(plan.paths.plist)],
                environment,
            )
        raise

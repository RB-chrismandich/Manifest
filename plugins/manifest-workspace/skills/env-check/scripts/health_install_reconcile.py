#!/usr/bin/env python3
"""Settings-hook reconciliation and install staging for the health installer."""

from __future__ import annotations

import copy
import os
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from health_install_files import (
    LAUNCHD_LABEL,
    RETIRED_RUNTIME_SOURCES,
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
from health_install_scheduler import (
    SYSTEMD_UNIT_NAME,
    _activate_scheduler_job,
    _recorded_scheduler,
    _resolve_executable,
    _run_required,
    _Scheduler,
    _scheduler_reactivate,
)


def _managed_hook(command: str) -> dict[str, object]:
    return {"type": "command", "command": command, "timeout": SESSION_TIMEOUT_SECONDS}


def _hook_targets_wrapper(hook: object, wrapper: Path) -> bool:
    """Match health-hook commands in either absolute or shipped tilde form."""
    if not isinstance(hook, dict):
        return False
    command = hook.get("command")
    if not isinstance(command, str):
        return False
    try:
        candidate = Path(command).expanduser().resolve(strict=False)
    except (OSError, RuntimeError, ValueError):
        return False
    return candidate == wrapper


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


def _split_wrapper_hooks(
    hooks: list, canonical: Path, command: str, desired: dict
) -> tuple[list, bool]:
    retained: list[object] = []
    removed = False
    for hook in hooks:
        if not _hook_targets_wrapper(hook, canonical):
            retained.append(hook)
            continue
        if hook != desired:
            equivalent = dict(hook)
            equivalent["command"] = command
            if equivalent != desired:
                raise InstallError(
                    "Claude health hook registration was externally edited"
                )
        removed = True
    return retained, removed


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
    canonical = Path(command).expanduser().resolve(strict=False)
    rewritten: list[object] = []
    for entry in entries:
        if not isinstance(entry, dict) or not isinstance(entry.get("hooks"), list):
            rewritten.append(entry)
            continue
        retained, removed = _split_wrapper_hooks(
            entry["hooks"], canonical, command, desired
        )
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
    canonical = Path(command).expanduser().resolve(strict=False)
    return any(
        isinstance(entry, dict)
        and isinstance(entry.get("hooks"), list)
        and any(_hook_targets_wrapper(hook, canonical) for hook in entry["hooks"])
        for entry in entries
    )


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


def _managed_paths(
    paths: InstallPaths,
    runtime_names: Sequence[str],
    scheduler_kind: str = "launchd",
) -> list[Path]:
    managed = [
        *(paths.runtime_root / name for name in sorted(runtime_names)),
        paths.extension,
        paths.wrapper,
    ]
    if scheduler_kind == "launchd":
        managed.append(paths.plist)
    elif scheduler_kind == "systemd":
        managed.extend((paths.systemd_timer, paths.systemd_service))
    return managed


def _assert_no_unowned_install(
    paths: InstallPaths,
    settings: dict,
    runtime_names: Sequence[str],
    scheduler_kind: str = "launchd",
) -> None:
    for path in _managed_paths(paths, runtime_names, scheduler_kind):
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
    scheduler: _Scheduler
    executables: Mapping[str, str]
    hook_hashes: Mapping[str, str]
    settings_target: Path
    updated_settings: dict
    snapshots: Sequence[FileSnapshot]
    job_was_replaced: bool


def _build_receipt(plan: _InstallPlan) -> dict[str, object]:
    installed_at = (
        datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    )
    receipt: dict[str, object] = {
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
        "scheduler": plan.scheduler.metadata(),
        "claude_hook": {
            "command": str(plan.paths.wrapper.resolve(strict=False)),
            "timeout": SESSION_TIMEOUT_SECONDS,
        },
        "hook_hashes": dict(sorted(plan.hook_hashes.items())),
    }
    if plan.scheduler.kind == "launchd":
        receipt["launchd_plist"] = _owned_row(
            f"generated:{LAUNCHD_LABEL}", plan.paths.plist, plan.scheduler.payload
        )
    elif plan.scheduler.kind == "systemd":
        receipt["systemd_timer"] = _owned_row(
            f"generated:{SYSTEMD_UNIT_NAME}.timer",
            plan.paths.systemd_timer,
            plan.scheduler.timer_payload,
        )
        receipt["systemd_service"] = _owned_row(
            f"generated:{SYSTEMD_UNIT_NAME}.service",
            plan.paths.systemd_service,
            plan.scheduler.service_payload,
        )
    return receipt


def _apply_install(plan: _InstallPlan, environment: Mapping[str, str]) -> None:
    scheduler = plan.scheduler
    prior: _Scheduler | None = None
    if plan.job_was_replaced:
        prior = _recorded_scheduler(plan.receipt or {}, environment)
        if prior.kind != scheduler.kind and not {prior.kind, scheduler.kind} <= {
            "systemd",
            "none",
        }:
            raise InstallError(
                f"recorded {prior.kind} scheduler cannot be managed on this platform"
            )
    try:
        for name, (_source, payload) in plan.runtime.items():
            _atomic_write(plan.paths.runtime_root / name, payload, 0o600)
        _cleanup_retired_runtime(plan)
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

        _activate_scheduler_job(
            scheduler,
            prior,
            plan.paths,
            plan.executables["python"],
            _json_bytes(_build_receipt(plan)),
            environment,
        )
    # BaseException is deliberate: rollback must run even on KeyboardInterrupt.
    except BaseException:
        try:
            _restore_snapshots(plan.snapshots)
        finally:
            if prior is not None:
                _scheduler_reactivate(
                    prior,
                    plan.paths,
                    plan.executables["python"],
                    environment,
                )
        raise


def _cleanup_retired_runtime(plan: _InstallPlan) -> None:
    receipt_files = (
        (plan.receipt or {}).get("files", {}) if isinstance(plan.receipt, dict) else {}
    )
    for name in RETIRED_RUNTIME_SOURCES:
        retired_path = plan.paths.runtime_root / name
        if _path_present(retired_path):
            row = receipt_files.get(name) if isinstance(receipt_files, dict) else None
            _assert_destination_owned(retired_path, row, f"retired runtime file {name}")
            retired_path.unlink()

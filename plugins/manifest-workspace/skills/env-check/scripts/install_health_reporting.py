#!/usr/bin/env python3
"""Explicitly install or remove Manifest's local harness health reporting."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import plistlib
import shutil
import stat
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping, Sequence

SCHEMA_VERSION = 1
LAUNCHD_LABEL = "com.manifest.health-report"
PLIST_NAME = f"{LAUNCHD_LABEL}.plist"
OWNERSHIP_MARKER = "manifest-health-reporting"
SESSION_TIMEOUT_SECONDS = 30
SHA256_LENGTH = 64

RUNTIME_SOURCES = {
    "env_check.py": Path(
        "plugins", "manifest-workspace", "skills", "env-check", "scripts", "env_check.py"
    ),
    "health_report.py": Path(
        "plugins",
        "manifest-workspace",
        "skills",
        "env-check",
        "scripts",
        "health_report.py",
    ),
    "hook_smoke.py": Path("configs", "claude", "scripts", "hook_smoke.py"),
    "mcp_health.py": Path(
        "plugins", "manifest-workspace", "skills", "env-check", "scripts", "mcp_health.py"
    ),
    "plugin_reconcile.py": Path(
        "plugins",
        "manifest-workspace",
        "skills",
        "deploy-reconcile",
        "scripts",
        "plugin_reconcile.py",
    ),
}
OMP_EXTENSION_SOURCE = Path("configs", "omp", "extensions", "manifest-health.ts")
CLAUDE_WRAPPER_SOURCE = Path(
    "configs", "claude", "scripts", "mcp_health_check.sh"
)
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


class InstallError(RuntimeError):
    """A safe, operator-actionable installer refusal."""


@dataclass(frozen=True)
class InstallPaths:
    home: Path
    state_home: Path
    data_home: Path
    config_home: Path
    runtime_root: Path
    state_root: Path
    report_root: Path
    agent_root: Path
    extension: Path
    wrapper: Path
    settings: Path
    plist: Path
    receipt: Path


@dataclass(frozen=True)
class FileSnapshot:
    path: Path
    existed: bool
    payload: bytes | None
    mode: int | None


def _resolved_path(value: str | os.PathLike[str]) -> Path:
    return Path(value).expanduser().resolve(strict=False)


def _paths(environment: Mapping[str, str]) -> InstallPaths:
    home = _resolved_path(environment.get("HOME") or Path.home())
    state_home = _resolved_path(
        environment.get("XDG_STATE_HOME") or home / ".local" / "state"
    )
    data_home = _resolved_path(
        environment.get("XDG_DATA_HOME") or home / ".local" / "share"
    )
    config_home = _resolved_path(
        environment.get("XDG_CONFIG_HOME") or home / ".config"
    )
    runtime_root = data_home / "manifest" / "health"
    state_root = state_home / "manifest" / "health"
    agent_root = _resolved_path(environment.get("OMP_AGENT_DIR") or home / ".omp" / "agent")
    return InstallPaths(
        home=home,
        state_home=state_home,
        data_home=data_home,
        config_home=config_home,
        runtime_root=runtime_root,
        state_root=state_root,
        report_root=state_home / "manifest" / "reports",
        agent_root=agent_root,
        extension=agent_root / "extensions" / "manifest-health.ts",
        wrapper=home / ".claude" / "scripts" / "mcp_health_check.sh",
        settings=home / ".claude" / "settings.json",
        plist=home / "Library" / "LaunchAgents" / PLIST_NAME,
        receipt=state_root / "installation.json",
    )


def _path_present(path: Path) -> bool:
    return path.exists() or path.is_symlink()


def _regular_file(path: Path) -> bool:
    try:
        return stat.S_ISREG(path.lstat().st_mode) and not path.is_symlink()
    except OSError:
        return False


def _read_regular(path: Path, description: str) -> bytes:
    if not _regular_file(path):
        raise InstallError(f"{description} is missing or is not a regular file: {path}")
    try:
        return path.read_bytes()
    except OSError as error:
        raise InstallError(f"could not read {description}: {path}") from error


def _digest(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _file_digest(path: Path) -> str | None:
    if not _regular_file(path):
        return None
    try:
        return _digest(path.read_bytes())
    except OSError:
        return None


def _is_digest(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == SHA256_LENGTH
        and all(character in "0123456789abcdef" for character in value)
    )


def _atomic_write(path: Path, payload: bytes, mode: int) -> None:
    temporary: str | None = None
    try:
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        descriptor, temporary = tempfile.mkstemp(
            prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
        )
        os.fchmod(descriptor, mode)
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        temporary = None
        os.chmod(path, mode)
    except OSError as error:
        raise InstallError(f"could not atomically write managed file: {path}") from error
    finally:
        if temporary is not None:
            try:
                os.unlink(temporary)
            except OSError:
                pass


def _json_bytes(document: Mapping[str, object]) -> bytes:
    return (
        json.dumps(document, indent=2, ensure_ascii=False, sort_keys=True) + "\n"
    ).encode("utf-8")


def _snapshot(path: Path) -> FileSnapshot:
    if not _path_present(path):
        return FileSnapshot(path, False, None, None)
    if not _regular_file(path):
        raise InstallError(f"managed destination is not a regular file: {path}")
    try:
        file_stat = path.stat()
        return FileSnapshot(
            path,
            True,
            path.read_bytes(),
            stat.S_IMODE(file_stat.st_mode),
        )
    except OSError as error:
        raise InstallError(f"could not snapshot managed destination: {path}") from error


def _restore_snapshots(snapshots: Sequence[FileSnapshot]) -> None:
    for snapshot in reversed(snapshots):
        try:
            if snapshot.existed:
                assert snapshot.payload is not None and snapshot.mode is not None
                _atomic_write(snapshot.path, snapshot.payload, snapshot.mode)
            elif _path_present(snapshot.path):
                snapshot.path.unlink()
        except (AssertionError, InstallError, OSError):
            pass


def _settings_target(path: Path) -> Path:
    if not path.is_symlink():
        return path
    try:
        target = path.resolve(strict=True)
    except OSError as error:
        raise InstallError(f"Claude settings symlink is broken: {path}") from error
    if not _regular_file(target):
        raise InstallError(f"Claude settings target is not a regular file: {target}")
    return target


def _read_json_object(path: Path, description: str) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise InstallError(f"{description} is unreadable or malformed: {path}") from error
    if not isinstance(value, dict):
        raise InstallError(f"{description} must be a JSON object: {path}")
    return value


def _read_settings(path: Path) -> tuple[Path, dict]:
    target = _settings_target(path)
    if not _path_present(target):
        return target, {}
    if not _regular_file(target):
        raise InstallError(f"Claude settings are not a regular file: {target}")
    return target, _read_json_object(target, "Claude settings")


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


def _rewrite_health_hook(settings: dict, command: str, *, install: bool) -> dict:
    updated = copy.deepcopy(settings)
    if install:
        hooks, entries = _session_entries(updated)
    else:
        hooks_value = updated.get("hooks")
        if hooks_value is None:
            return updated
        if not isinstance(hooks_value, dict):
            raise InstallError("Claude settings hooks value is not an object")
        entries_value = hooks_value.get("SessionStart")
        if entries_value is None:
            return updated
        if not isinstance(entries_value, list):
            raise InstallError("Claude SessionStart hooks value is not a list")
        hooks, entries = hooks_value, entries_value
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
                    raise InstallError("Claude health hook registration was externally edited")
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


def _owned_row(source: str, destination: Path, payload: bytes) -> dict[str, str]:
    digest = _digest(payload)
    return {
        "source": source,
        "destination": str(destination.resolve(strict=False)),
        "source_sha256": digest,
        "destination_sha256": digest,
    }


def _valid_row(row: object, destination: Path) -> bool:
    if not isinstance(row, dict):
        return False
    if not all(
        isinstance(row.get(key), str)
        for key in ("source", "destination", "source_sha256", "destination_sha256")
    ):
        return False
    if (
        not _is_digest(row["source_sha256"])
        or not _is_digest(row["destination_sha256"])
        or row["source_sha256"] != row["destination_sha256"]
    ):
        return False
    try:
        recorded = Path(row["destination"]).expanduser().resolve(strict=False)
    except OSError:
        return False
    return recorded == destination.resolve(strict=False)


def _assert_destination_owned(
    destination: Path, row: object, description: str
) -> None:
    if not _path_present(destination):
        return
    if not _valid_row(row, destination):
        raise InstallError(f"refusing to replace unowned {description}: {destination}")
    assert isinstance(row, dict)
    observed = _file_digest(destination)
    if observed is None or observed != row["destination_sha256"]:
        raise InstallError(f"refusing to replace externally edited {description}: {destination}")


def _load_receipt(path: Path) -> dict | None:
    if not _path_present(path):
        return None
    if not _regular_file(path):
        raise InstallError(f"health installation manifest is not a regular file: {path}")
    receipt = _read_json_object(path, "health installation manifest")
    if receipt.get("schema_version") != SCHEMA_VERSION:
        raise InstallError("health installation manifest has an unsupported schema")
    return receipt


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
    files = receipt.get("files")
    if not isinstance(files, dict) or set(files) != set(RUNTIME_SOURCES):
        raise InstallError("health installation manifest has an invalid runtime inventory")
    for name in RUNTIME_SOURCES:
        if not _valid_row(files.get(name), paths.runtime_root / name):
            raise InstallError("health installation manifest has an invalid runtime row")
    for key, destination in (
        ("omp_extension", paths.extension),
        ("claude_wrapper", paths.wrapper),
        ("launchd_plist", paths.plist),
    ):
        if not _valid_row(receipt.get(key), destination):
            raise InstallError(f"health installation manifest has an invalid {key} row")
    expected_hook = {
        "command": str(paths.wrapper.resolve(strict=False)),
        "timeout": SESSION_TIMEOUT_SECONDS,
    }
    if receipt.get("claude_hook") != expected_hook:
        raise InstallError("health installation manifest has an invalid Claude hook row")
    hashes = receipt.get("hook_hashes")
    if (
        not isinstance(hashes, dict)
        or set(hashes) != set(HOOK_HASH_SOURCES)
        or any(not _is_digest(value) for value in hashes.values())
    ):
        raise InstallError("health installation manifest has invalid hook hashes")


def _source_payloads(source_root: Path) -> tuple[dict[str, tuple[Path, bytes]], bytes, bytes]:
    runtime: dict[str, tuple[Path, bytes]] = {}
    for name, relative in RUNTIME_SOURCES.items():
        source = source_root / relative
        payload = _read_regular(source, f"runtime source {name}")
        try:
            compile(payload, str(source), "exec")
        except (SyntaxError, ValueError, TypeError) as error:
            raise InstallError(f"runtime source does not compile: {source}") from error
        runtime[name] = (source, payload)
    extension = _read_regular(source_root / OMP_EXTENSION_SOURCE, "OMP extension source")
    wrapper = _read_regular(source_root / CLAUDE_WRAPPER_SOURCE, "Claude wrapper source")
    return runtime, extension, wrapper


def _hook_hashes(source_root: Path) -> dict[str, str]:
    return {
        name: _digest(_read_regular(source_root / relative, f"hook source {name}"))
        for name, relative in HOOK_HASH_SOURCES.items()
    }


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


def _run_required(
    argv: Sequence[str], environment: Mapping[str, str], description: str, timeout: float = 10.0
) -> None:
    try:
        result = subprocess.run(
            list(argv),
            env=dict(environment),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=timeout,
            check=False,
            start_new_session=True,
        )
    except (OSError, subprocess.SubprocessError) as error:
        raise InstallError(f"{description} could not be executed") from error
    if result.returncode != 0:
        raise InstallError(f"{description} failed")


def _run_best_effort(
    argv: Sequence[str], environment: Mapping[str, str], timeout: float = 10.0
) -> None:
    try:
        subprocess.run(
            list(argv),
            env=dict(environment),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=timeout,
            check=False,
            start_new_session=True,
        )
    except (OSError, subprocess.SubprocessError):
        pass


def _smoke_runtime(
    runtime_root: Path, python: str, environment: Mapping[str, str]
) -> None:
    smoke_environment = dict(environment)
    smoke_environment["PYTHONDONTWRITEBYTECODE"] = "1"
    for name in sorted(RUNTIME_SOURCES):
        _run_required(
            [python, "-B", str(runtime_root / name), "--help"],
            smoke_environment,
            f"installed runtime smoke for {name}",
            timeout=5.0,
        )


def _plist_payload(
    paths: InstallPaths,
    python: str,
    environment: Mapping[str, str],
) -> bytes:
    document = {
        "Label": LAUNCHD_LABEL,
        "ManifestManagedBy": OWNERSHIP_MARKER,
        "ProgramArguments": [
            python,
            str((paths.runtime_root / "health_report.py").resolve(strict=False)),
            "--json",
            "--harness",
            "claude",
            "--harness",
            "omp",
            "--out-dir",
            str(paths.report_root.resolve(strict=False)),
        ],
        "EnvironmentVariables": {
            "HOME": str(paths.home),
            "PATH": environment.get("PATH") or os.defpath,
            "XDG_CONFIG_HOME": str(paths.config_home),
            "XDG_DATA_HOME": str(paths.data_home),
            "XDG_STATE_HOME": str(paths.state_home),
        },
        "ProcessType": "Background",
        "RunAtLoad": False,
        "StartCalendarInterval": {"Weekday": 1, "Hour": 9, "Minute": 0},
    }
    return plistlib.dumps(document, fmt=plistlib.FMT_XML, sort_keys=True)


def _assert_plist_owned(path: Path, row: object) -> None:
    _assert_destination_owned(path, row, "launchd plist")
    if not _path_present(path):
        return
    try:
        document = plistlib.loads(path.read_bytes())
    except (OSError, plistlib.InvalidFileException) as error:
        raise InstallError("owned launchd plist is malformed") from error
    if (
        not isinstance(document, dict)
        or document.get("Label") != LAUNCHD_LABEL
        or document.get("ManifestManagedBy") != OWNERSHIP_MARKER
    ):
        raise InstallError("launchd plist does not carry the Manifest ownership marker")


def install_omp_extension(
    source_root: Path, agent_root: Path, ownership: dict
) -> None:
    """Atomically install the owned OMP startup extension."""
    source = source_root.resolve(strict=False) / OMP_EXTENSION_SOURCE
    destination = agent_root.resolve(strict=False) / "extensions" / "manifest-health.ts"
    row = ownership.get("omp_extension") if ownership else None
    _assert_destination_owned(destination, row, "OMP extension")
    payload = _read_regular(source, "OMP extension source")
    _atomic_write(destination, payload, 0o600)


def _preflight_destinations(receipt: dict | None, paths: InstallPaths) -> None:
    files = receipt.get("files", {}) if receipt else {}
    for name in RUNTIME_SOURCES:
        _assert_destination_owned(
            paths.runtime_root / name,
            files.get(name) if isinstance(files, dict) else None,
            f"runtime file {name}",
        )
    _assert_destination_owned(
        paths.extension,
        receipt.get("omp_extension") if receipt else None,
        "OMP extension",
    )
    _assert_destination_owned(
        paths.wrapper,
        receipt.get("claude_wrapper") if receipt else None,
        "Claude wrapper",
    )
    _assert_plist_owned(
        paths.plist,
        receipt.get("launchd_plist") if receipt else None,
    )


def _managed_paths(paths: InstallPaths) -> list[Path]:
    return [
        *(paths.runtime_root / name for name in sorted(RUNTIME_SOURCES)),
        paths.extension,
        paths.wrapper,
        paths.plist,
    ]


def _build_receipt(
    source_root: Path,
    paths: InstallPaths,
    runtime: Mapping[str, tuple[Path, bytes]],
    extension_payload: bytes,
    wrapper_payload: bytes,
    plist_payload: bytes,
    executables: Mapping[str, str],
    hook_hashes: Mapping[str, str],
) -> dict[str, object]:
    installed_at = (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "installed_at": installed_at,
        "source_root": str(source_root),
        "executables": dict(executables),
        "files": {
            name: _owned_row(str(source), paths.runtime_root / name, payload)
            for name, (source, payload) in sorted(runtime.items())
        },
        "omp_extension": _owned_row(
            str(source_root / OMP_EXTENSION_SOURCE), paths.extension, extension_payload
        ),
        "claude_wrapper": _owned_row(
            str(source_root / CLAUDE_WRAPPER_SOURCE), paths.wrapper, wrapper_payload
        ),
        "launchd_plist": _owned_row(
            f"generated:{LAUNCHD_LABEL}", paths.plist, plist_payload
        ),
        "claude_hook": {
            "command": str(paths.wrapper.resolve(strict=False)),
            "timeout": SESSION_TIMEOUT_SECONDS,
        },
        "hook_hashes": dict(sorted(hook_hashes.items())),
    }


def install(source_root: Path, environment: Mapping[str, str]) -> None:
    source_root = source_root.expanduser().resolve(strict=False)
    if not source_root.is_dir():
        raise InstallError(f"source root is not a directory: {source_root}")
    paths = _paths(environment)
    receipt = _load_receipt(paths.receipt)
    if receipt is not None:
        _validate_receipt(receipt, paths)

    runtime, extension_payload, wrapper_payload = _source_payloads(source_root)
    hook_hashes = _hook_hashes(source_root)
    executables = _executables()
    launchctl = _resolve_executable("launchctl")
    plutil = _resolve_executable("plutil")
    plist_payload = _plist_payload(paths, executables["python"], environment)
    settings_target, settings = _read_settings(paths.settings)
    hook_command = str(paths.wrapper.resolve(strict=False))
    updated_settings = _rewrite_health_hook(settings, hook_command, install=True)

    _preflight_destinations(receipt, paths)
    snapshots = [_snapshot(path) for path in _managed_paths(paths)]
    snapshots.extend((_snapshot(settings_target), _snapshot(paths.receipt)))
    job_was_replaced = _path_present(paths.plist)
    job_was_bootstrapped = False
    domain = f"gui/{os.getuid()}"
    service = f"{domain}/{LAUNCHD_LABEL}"

    try:
        for name, (_source, payload) in runtime.items():
            _atomic_write(paths.runtime_root / name, payload, 0o600)
        _smoke_runtime(paths.runtime_root, executables["python"], environment)

        install_omp_extension(source_root, paths.agent_root, receipt or {})
        if _digest(paths.extension.read_bytes()) != _digest(extension_payload):
            raise InstallError("OMP extension source changed during installation")
        _atomic_write(paths.wrapper, wrapper_payload, 0o700)
        _atomic_write(settings_target, _json_bytes(updated_settings), 0o600)

        if job_was_replaced:
            _run_best_effort([launchctl, "bootout", service], environment)
        _atomic_write(paths.plist, plist_payload, 0o600)
        _run_required([plutil, "-lint", str(paths.plist)], environment, "launchd plist lint")

        document = _build_receipt(
            source_root,
            paths,
            runtime,
            extension_payload,
            wrapper_payload,
            plist_payload,
            executables,
            hook_hashes,
        )
        _atomic_write(paths.receipt, _json_bytes(document), 0o600)
        _run_required(
            [launchctl, "bootstrap", domain, str(paths.plist)],
            environment,
            "launchd bootstrap",
        )
        job_was_bootstrapped = True
        _run_required(
            [launchctl, "kickstart", "-k", service],
            environment,
            "launchd kickstart",
        )
    except BaseException:
        if job_was_bootstrapped:
            _run_best_effort([launchctl, "bootout", service], environment)
        _restore_snapshots(snapshots)
        if job_was_replaced and _path_present(paths.plist):
            _run_best_effort(
                [launchctl, "bootstrap", domain, str(paths.plist)], environment
            )
        raise


def _assert_no_unowned_install(paths: InstallPaths, settings: dict) -> None:
    for path in _managed_paths(paths):
        if _path_present(path):
            raise InstallError(f"no ownership manifest exists for managed path: {path}")
    command = str(paths.wrapper.resolve(strict=False))
    if _hook_is_present(settings, command):
        raise InstallError("no ownership manifest exists for the Claude health hook")


def _remove_empty_directory(path: Path) -> None:
    try:
        path.rmdir()
    except OSError:
        pass


def uninstall(source_root: Path, environment: Mapping[str, str]) -> None:
    del source_root
    paths = _paths(environment)
    receipt = _load_receipt(paths.receipt)
    settings_target, settings = _read_settings(paths.settings)
    if receipt is None:
        _assert_no_unowned_install(paths, settings)
        return
    _validate_receipt(receipt, paths)
    _preflight_destinations(receipt, paths)
    hook_command = str(paths.wrapper.resolve(strict=False))
    updated_settings = _rewrite_health_hook(settings, hook_command, install=False)

    snapshots = [_snapshot(path) for path in _managed_paths(paths)]
    snapshots.extend((_snapshot(settings_target), _snapshot(paths.receipt)))
    launchctl = _resolve_executable("launchctl")
    domain = f"gui/{os.getuid()}"
    service = f"{domain}/{LAUNCHD_LABEL}"
    had_plist = _path_present(paths.plist)

    try:
        if had_plist:
            _run_best_effort([launchctl, "bootout", service], environment)
        if updated_settings != settings:
            _atomic_write(settings_target, _json_bytes(updated_settings), 0o600)
        for path in _managed_paths(paths):
            if _path_present(path):
                path.unlink()
        if _path_present(paths.receipt):
            paths.receipt.unlink()
    except BaseException:
        _restore_snapshots(snapshots)
        if had_plist and _path_present(paths.plist):
            _run_best_effort(
                [launchctl, "bootstrap", domain, str(paths.plist)], environment
            )
        raise

    _remove_empty_directory(paths.runtime_root)
    _remove_empty_directory(paths.state_root)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", required=True, type=Path)
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--install", action="store_true")
    action.add_argument("--uninstall", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    environment = dict(os.environ)
    try:
        if args.install:
            install(args.source_root, environment)
            print("health reporting installed")
        else:
            uninstall(args.source_root, environment)
            print("health reporting uninstalled")
    except (OSError, ValueError, RuntimeError) as error:
        print(f"health reporting installer: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

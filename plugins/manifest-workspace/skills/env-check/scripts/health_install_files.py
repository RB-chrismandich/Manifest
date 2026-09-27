#!/usr/bin/env python3
"""File, snapshot, receipt, and plist primitives for the health installer."""

from __future__ import annotations

import hashlib
import json
import os
import plistlib
import stat
import tempfile
from collections.abc import Mapping, Sequence
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path

SCHEMA_VERSION = 1
LAUNCHD_LABEL = "com.manifest.health-report"
PLIST_NAME = f"{LAUNCHD_LABEL}.plist"
OWNERSHIP_MARKER = "manifest-health-reporting"
SESSION_TIMEOUT_SECONDS = 30
SHA256_LENGTH = 64


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
    config_home = _resolved_path(environment.get("XDG_CONFIG_HOME") or home / ".config")
    runtime_root = data_home / "manifest" / "health"
    state_root = state_home / "manifest" / "health"
    agent_root = _resolved_path(
        environment.get("OMP_AGENT_DIR") or home / ".omp" / "agent"
    )
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
        raise InstallError(
            f"could not atomically write managed file: {path}"
        ) from error
    finally:
        if temporary is not None:
            with suppress(OSError):
                os.unlink(temporary)


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
        with suppress(AssertionError, InstallError, OSError):
            if snapshot.existed:
                assert snapshot.payload is not None and snapshot.mode is not None
                _atomic_write(snapshot.path, snapshot.payload, snapshot.mode)
            elif _path_present(snapshot.path):
                snapshot.path.unlink()


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
        raise InstallError(
            f"{description} is unreadable or malformed: {path}"
        ) from error
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


def _assert_destination_owned(destination: Path, row: object, description: str) -> None:
    if not _path_present(destination):
        return
    if not _valid_row(row, destination):
        raise InstallError(f"refusing to replace unowned {description}: {destination}")
    assert isinstance(row, dict)
    observed = _file_digest(destination)
    if observed is None or observed != row["destination_sha256"]:
        raise InstallError(
            f"refusing to replace externally edited {description}: {destination}"
        )


def _load_receipt(path: Path) -> dict | None:
    if not _path_present(path):
        return None
    if not _regular_file(path):
        raise InstallError(
            f"health installation manifest is not a regular file: {path}"
        )
    receipt = _read_json_object(path, "health installation manifest")
    if receipt.get("schema_version") != SCHEMA_VERSION:
        raise InstallError("health installation manifest has an unsupported schema")
    return receipt


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


def _remove_empty_directory(path: Path) -> None:
    with suppress(OSError):
        path.rmdir()

#!/usr/bin/env python3
"""Explicitly install or remove Manifest's local harness health reporting."""

from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Mapping
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))

from health_install_files import (  # noqa: E402
    LAUNCHD_LABEL,
    OWNERSHIP_MARKER,
    PLIST_NAME,
    RETIRED_RUNTIME_SOURCES,
    SCHEMA_VERSION,
    SESSION_TIMEOUT_SECONDS,
    SHA256_LENGTH,
    FileSnapshot,
    InstallError,
    InstallPaths,
    _assert_destination_owned,
    _assert_plist_owned,
    _assert_systemd_unit_owned,
    _atomic_write,
    _installation_lock,
    _json_bytes,
    _load_receipt,
    _path_present,
    _paths,
    _read_regular,
    _read_settings,
    _remove_empty_directory,
    _restore_snapshots,
    _snapshot,
)
from health_install_receipts import (  # noqa: E402
    CLAUDE_WRAPPER_SOURCE,
    OMP_EXTENSION_SOURCE,
    RUNTIME_SOURCES,
    _hook_hashes,
    _validate_receipt,
)
from health_install_reconcile import (  # noqa: E402
    _apply_install,
    _assert_no_unowned_install,
    _executables,
    _install_omp_extension,
    _InstallPlan,
    _managed_paths,
    _rewrite_health_hook,
)
from health_install_scheduler import (  # noqa: E402
    _receipt_scheduler_kind,
    _recorded_scheduler,
    _resolve_scheduler,
    _run_best_effort,
    _scheduler_kind,
    _scheduler_reactivate,
    _stop_scheduler_job,
)

__all__ = [
    "LAUNCHD_LABEL",
    "OWNERSHIP_MARKER",
    "PLIST_NAME",
    "RUNTIME_SOURCES",
    "SCHEMA_VERSION",
    "SESSION_TIMEOUT_SECONDS",
    "SHA256_LENGTH",
    "FileSnapshot",
    "InstallError",
    "InstallPaths",
    "build_parser",
    "install",
    "install_omp_extension",
    "main",
    "uninstall",
]


def _source_payloads(
    source_root: Path,
) -> tuple[dict[str, tuple[Path, bytes]], bytes, bytes]:
    runtime: dict[str, tuple[Path, bytes]] = {}
    for name, relative in RUNTIME_SOURCES.items():
        source = source_root / relative
        payload = _read_regular(source, f"runtime source {name}")
        try:
            compile(payload, str(source), "exec")
        except (SyntaxError, ValueError, TypeError) as error:
            raise InstallError(f"runtime source does not compile: {source}") from error
        runtime[name] = (source, payload)
    extension = _read_regular(
        source_root / OMP_EXTENSION_SOURCE, "OMP extension source"
    )
    wrapper = _read_regular(
        source_root / CLAUDE_WRAPPER_SOURCE, "Claude wrapper source"
    )
    return runtime, extension, wrapper


def _preflight_destinations(
    receipt: dict | None,
    paths: InstallPaths,
    runtime: Mapping[str, tuple[Path, bytes]] | None = None,
    extension_payload: bytes | None = None,
    wrapper_payload: bytes | None = None,
    scheduler_kind: str = "launchd",
) -> None:
    files = receipt.get("files", {}) if receipt else {}
    payloads = runtime if isinstance(runtime, Mapping) else {}
    for name in RUNTIME_SOURCES:
        payload = payloads[name][1] if name in payloads else None
        _assert_destination_owned(
            paths.runtime_root / name,
            files.get(name) if isinstance(files, dict) else None,
            f"runtime file {name}",
            payload,
        )
    if isinstance(files, dict):
        for name in RETIRED_RUNTIME_SOURCES:
            _assert_destination_owned(
                paths.runtime_root / name,
                files.get(name),
                f"retired runtime file {name}",
            )
    _assert_destination_owned(
        paths.extension,
        receipt.get("omp_extension") if receipt else None,
        "OMP extension",
        extension_payload,
    )
    _assert_destination_owned(
        paths.wrapper,
        receipt.get("claude_wrapper") if receipt else None,
        "Claude wrapper",
        wrapper_payload,
    )
    if scheduler_kind == "launchd":
        _assert_plist_owned(
            paths.plist,
            receipt.get("launchd_plist") if receipt else None,
        )
    elif scheduler_kind == "systemd":
        for key, destination, description in (
            ("systemd_timer", paths.systemd_timer, "systemd timer unit"),
            ("systemd_service", paths.systemd_service, "systemd service unit"),
        ):
            _assert_systemd_unit_owned(
                destination,
                receipt.get(key) if receipt else None,
                description,
            )


def install_omp_extension(source_root: Path, agent_root: Path, ownership: dict) -> None:
    """Atomically install the owned OMP startup extension."""
    source = source_root.resolve(strict=False) / OMP_EXTENSION_SOURCE
    _install_omp_extension(source, agent_root, ownership)


def _prepare_install(source_root: Path, environment: Mapping[str, str]) -> _InstallPlan:
    paths = _paths(environment)
    receipt = _load_receipt(paths.receipt)
    if receipt is not None:
        _validate_receipt(receipt, paths)

    runtime, extension_payload, wrapper_payload = _source_payloads(source_root)
    executables = _executables()
    scheduler = _resolve_scheduler(paths, environment, executables["python"])
    settings_target, settings = _read_settings(paths.settings)
    hook_command = str(paths.wrapper.resolve(strict=False))
    updated_settings = _rewrite_health_hook(settings, hook_command, install=True)

    _preflight_destinations(
        receipt,
        paths,
        runtime,
        extension_payload,
        wrapper_payload,
        scheduler.kind,
    )
    managed_names = set(RUNTIME_SOURCES)
    if receipt and isinstance(receipt.get("files"), dict):
        managed_names.update(
            name for name in receipt["files"] if name in RETIRED_RUNTIME_SOURCES
        )
    snapshots = [
        _snapshot(path)
        for path in _managed_paths(paths, sorted(managed_names), scheduler.kind)
    ]
    if receipt is not None and _receipt_scheduler_kind(receipt) == "systemd":
        # Stale unit files from the recorded install may be removed when the
        # scheduler kind changes; keep them rollback-able.
        snapshots.extend(
            (_snapshot(paths.systemd_timer), _snapshot(paths.systemd_service))
        )
    snapshots.extend((_snapshot(settings_target), _snapshot(paths.receipt)))
    return _InstallPlan(
        source_root=source_root,
        paths=paths,
        receipt=receipt,
        runtime=runtime,
        extension_source=source_root / OMP_EXTENSION_SOURCE,
        extension_payload=extension_payload,
        wrapper_source=source_root / CLAUDE_WRAPPER_SOURCE,
        wrapper_payload=wrapper_payload,
        scheduler=scheduler,
        executables=executables,
        hook_hashes=_hook_hashes(source_root),
        settings_target=settings_target,
        updated_settings=updated_settings,
        snapshots=snapshots,
        job_was_replaced=receipt is not None,
    )


def install(source_root: Path, environment: Mapping[str, str]) -> None:
    source_root = source_root.expanduser().resolve(strict=False)
    if not source_root.is_dir():
        raise InstallError(f"source root is not a directory: {source_root}")
    with _installation_lock(_paths(environment)):
        _apply_install(_prepare_install(source_root, environment), environment)


def _retired_runtime_names(receipt: dict) -> list[str]:
    files = receipt.get("files")
    if not isinstance(files, dict):
        return []
    return sorted(name for name in files if name in RETIRED_RUNTIME_SOURCES)


def _uninstall(environment: Mapping[str, str]) -> None:
    paths = _paths(environment)
    receipt = _load_receipt(paths.receipt)
    settings_target, settings = _read_settings(paths.settings)
    retired_names = _retired_runtime_names(receipt) if receipt else []
    if receipt is None:
        _assert_no_unowned_install(
            paths,
            settings,
            [*RUNTIME_SOURCES, *RETIRED_RUNTIME_SOURCES],
            _scheduler_kind(sys.platform),
        )
        return
    _validate_receipt(receipt, paths)
    recorded_kind = _receipt_scheduler_kind(receipt)
    _preflight_destinations(receipt, paths, scheduler_kind=recorded_kind)
    hook_command = str(paths.wrapper.resolve(strict=False))
    updated_settings = _rewrite_health_hook(settings, hook_command, install=False)

    managed = _managed_paths(paths, [*RUNTIME_SOURCES, *retired_names], recorded_kind)
    snapshots = [_snapshot(path) for path in managed]
    snapshots.extend((_snapshot(settings_target), _snapshot(paths.receipt)))
    recorded = _recorded_scheduler(receipt, environment)

    try:
        _stop_scheduler_job(recorded, environment)
        if updated_settings != settings:
            _atomic_write(settings_target, _json_bytes(updated_settings), 0o600)
        for path in managed:
            if _path_present(path):
                path.unlink()
        if _path_present(paths.receipt):
            paths.receipt.unlink()
        if recorded.kind == "systemd":
            # Forget the removed unit definitions; failures only leave a stale
            # in-memory copy of units whose files and enablement are gone.
            _run_best_effort(
                [recorded.systemctl, "--user", "daemon-reload"], environment
            )
    except BaseException:
        try:
            _restore_snapshots(snapshots)
        finally:
            _scheduler_reactivate(
                recorded,
                paths,
                str(Path(sys.executable).resolve(strict=False)),
                environment,
            )
        raise

    _remove_empty_directory(paths.runtime_root)
    _remove_empty_directory(paths.state_root)
    _remove_empty_directory(paths.systemd_timer.parent)
    _remove_empty_directory(paths.systemd_timer.parent.parent)


def uninstall(source_root: Path, environment: Mapping[str, str]) -> None:
    del source_root
    with _installation_lock(_paths(environment)):
        _uninstall(environment)


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
        cause: BaseException | None = error.__context__ or error.__cause__
        while cause is not None:
            print(f"health reporting installer: caused by: {cause}", file=sys.stderr)
            cause = cause.__context__ or cause.__cause__
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

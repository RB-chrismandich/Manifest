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
    SCHEMA_VERSION,
    SESSION_TIMEOUT_SECONDS,
    SHA256_LENGTH,
    FileSnapshot,
    InstallError,
    InstallPaths,
    _assert_destination_owned,
    _assert_plist_owned,
    _atomic_write,
    _digest,
    _is_digest,
    _json_bytes,
    _load_receipt,
    _path_present,
    _paths,
    _plist_payload,
    _read_regular,
    _read_settings,
    _remove_empty_directory,
    _restore_snapshots,
    _snapshot,
    _valid_row,
)
from health_install_reconcile import (  # noqa: E402
    _apply_install,
    _assert_no_unowned_install,
    _executables,
    _install_omp_extension,
    _InstallPlan,
    _managed_paths,
    _resolve_executable,
    _rewrite_health_hook,
    _run_best_effort,
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
    files = receipt.get("files")
    if not isinstance(files, dict) or set(files) != set(RUNTIME_SOURCES):
        raise InstallError(
            "health installation manifest has an invalid runtime inventory"
        )
    for name in RUNTIME_SOURCES:
        if not _valid_row(files.get(name), paths.runtime_root / name):
            raise InstallError(
                "health installation manifest has an invalid runtime row"
            )
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


def _hook_hashes(source_root: Path) -> dict[str, str]:
    return {
        name: _digest(_read_regular(source_root / relative, f"hook source {name}"))
        for name, relative in HOOK_HASH_SOURCES.items()
    }


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
    settings_target, settings = _read_settings(paths.settings)
    hook_command = str(paths.wrapper.resolve(strict=False))
    updated_settings = _rewrite_health_hook(settings, hook_command, install=True)

    _preflight_destinations(receipt, paths)
    snapshots = [_snapshot(path) for path in _managed_paths(paths, RUNTIME_SOURCES)]
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
        plist_payload=_plist_payload(paths, executables["python"], environment),
        executables=executables,
        hook_hashes=_hook_hashes(source_root),
        launchctl=_resolve_executable("launchctl"),
        plutil=_resolve_executable("plutil"),
        settings_target=settings_target,
        updated_settings=updated_settings,
        snapshots=snapshots,
        job_was_replaced=_path_present(paths.plist),
    )


def install(source_root: Path, environment: Mapping[str, str]) -> None:
    source_root = source_root.expanduser().resolve(strict=False)
    if not source_root.is_dir():
        raise InstallError(f"source root is not a directory: {source_root}")
    _apply_install(_prepare_install(source_root, environment), environment)


def uninstall(source_root: Path, environment: Mapping[str, str]) -> None:
    del source_root
    paths = _paths(environment)
    receipt = _load_receipt(paths.receipt)
    settings_target, settings = _read_settings(paths.settings)
    if receipt is None:
        _assert_no_unowned_install(paths, settings, RUNTIME_SOURCES)
        return
    _validate_receipt(receipt, paths)
    _preflight_destinations(receipt, paths)
    hook_command = str(paths.wrapper.resolve(strict=False))
    updated_settings = _rewrite_health_hook(settings, hook_command, install=False)

    snapshots = [_snapshot(path) for path in _managed_paths(paths, RUNTIME_SOURCES)]
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
        for path in _managed_paths(paths, RUNTIME_SOURCES):
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

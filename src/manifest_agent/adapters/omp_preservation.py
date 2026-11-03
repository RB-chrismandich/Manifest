"""Descriptor-held native cache quarantine that ALWAYS preserves the real tree."""

from __future__ import annotations

import json
import os
import secrets
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

from manifest_agent.adapters.capability_fs import (
    _exchange_directory_entries,
    _rename_directory_if_absent,
)
from manifest_agent.adapters.omp_inventory import OmpInventoryError, directory_sha256
from manifest_agent.models import CommandResult

_FLAGS = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW


def open_directory(path: Path) -> int:
    """Open every parent without following any link, not just the last parent."""
    if not path.is_absolute() or ".." in path.parts:
        raise OmpInventoryError("native preservation path is unsafe")
    descriptor = os.open(path.anchor, _FLAGS)
    try:
        for segment in path.parts[1:]:
            child = os.open(segment, _FLAGS, dir_fd=descriptor)
            os.close(descriptor)
            descriptor = child
        return descriptor
    except BaseException:
        os.close(descriptor)
        raise


def preserve_native_tree(
    identity: Mapping[str, Any],
    argv: Sequence[str],
    *,
    authorize: Callable[[], None],
    execute: Callable[[Sequence[str]], tuple[CommandResult | None, Any]],
    boundary: Callable[[str], None],
    identifier: str,
) -> CommandResult:
    """Exchange/CAS before execution; never expose the authenticated real cache.

    A concurrently occupied restoration path leaves the full recovery tree
    intact and surfaces its location. No failure path deletes the quarantine.
    """
    path = Path(identity["path"])
    parent = open_directory(path.parent)
    name = f".{path.name}.manifest-preserve-{secrets.token_hex(16)}"
    recovery = path.parent / name
    placeholder = -1
    moved = False
    command = None
    execution_error = None
    restore_error = None
    try:
        os.mkdir(name, 0o700, dir_fd=parent)
        placeholder = os.open(name, _FLAGS, dir_fd=parent)
        if "runtime_name" in identity:
            descriptor = os.open(
                "package.json",
                os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                0o600,
                dir_fd=placeholder,
            )
            with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                json.dump({"name": identity["runtime_name"]}, stream)
                stream.flush()
                os.fsync(stream.fileno())
        boundary(identifier)
        authorize()
        current_parent = open_directory(path.parent)
        try:
            original, current = os.fstat(parent), os.fstat(current_parent)
            if (original.st_dev, original.st_ino) != (current.st_dev, current.st_ino):
                raise OmpInventoryError(
                    "native cache parent changed at mutation boundary"
                )
        finally:
            os.close(current_parent)
        _exchange_directory_entries(parent, path.name, parent, name)
        moved = True
        if directory_sha256(recovery) != identity["tree_sha256"]:
            raise OmpInventoryError(
                "native cache changed at final preservation boundary"
            )
        command, error = execute(argv)
        if error is not None:
            execution_error = "; ".join(error.errors)
    finally:
        if moved:
            try:
                _restore(parent, path.name, name, placeholder)
                moved = False
            except (OSError, ValueError) as error:
                restore_error = (
                    "native cache restoration failed; recovery retained at "
                    f"{recovery}: {error}"
                )
        if placeholder >= 0:
            if not moved and not _clean_placeholder(
                parent, name, placeholder, identity.get("runtime_name")
            ):
                restore_error = (
                    "native cache restored; unexpected placeholder retained at "
                    f"{recovery}"
                )
            os.close(placeholder)
        os.close(parent)
        if restore_error is not None:
            raise OmpInventoryError(restore_error)
    if execution_error is not None:
        raise OmpInventoryError(execution_error)
    if command is None:
        raise OmpInventoryError("native mutation returned no command result")
    if command.returncode != 0:
        raise OmpInventoryError(
            f"native mutation exited {command.returncode}: "
            f"{command.stderr or command.stdout}"
        )
    return command


def _restore(parent: int, installed: str, recovery: str, placeholder: int) -> None:
    try:
        current = os.stat(installed, dir_fd=parent, follow_symlinks=False)
    except FileNotFoundError:
        _rename_directory_if_absent(parent, recovery, installed)
        os.fsync(parent)
        return
    expected = os.fstat(placeholder)
    if (current.st_dev, current.st_ino) != (expected.st_dev, expected.st_ino):
        raise OmpInventoryError("restoration path changed concurrently")
    _exchange_directory_entries(parent, installed, parent, recovery)
    os.fsync(parent)


def _clean_placeholder(
    parent: int, name: str, placeholder: int, runtime_name: str | None
) -> bool:
    """Remove only our exact placeholder; preserve any unexpected new content."""
    try:
        current = os.stat(name, dir_fd=parent, follow_symlinks=False)
    except FileNotFoundError:
        return True
    except OSError:
        return False
    expected = os.fstat(placeholder)
    if (current.st_dev, current.st_ino) != (expected.st_dev, expected.st_ino):
        return False
    try:
        children = os.listdir(placeholder)
        if children == ["package.json"] and runtime_name is not None:
            # Only our exact descriptor-read metadata can be cleaned.
            descriptor = os.open(
                "package.json", os.O_RDONLY | os.O_NOFOLLOW, dir_fd=placeholder
            )
            with os.fdopen(descriptor, "r", encoding="utf-8") as stream:
                value = json.load(stream)
            if value == {"name": runtime_name}:
                os.unlink("package.json", dir_fd=placeholder)
        os.rmdir(name, dir_fd=parent)
    except (OSError, ValueError):
        return False
    return True

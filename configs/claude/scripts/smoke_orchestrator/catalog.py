"""Catalog location, load, atomic write, and per-app file locking (T007).

Per-app YAML files under ``smoke-catalog/<app>.yaml`` keep concurrent appends
from different apps fully isolated; within an app, a flock serializes writers
and an atomic replace prevents a partial/corrupt catalog (FR-015).
"""

from __future__ import annotations

import contextlib
import fcntl
import os
import re
import stat
import uuid
from collections.abc import Iterator
from pathlib import Path

import yaml

from .validation import ValidationError

_DIRECTORY = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
_SLUG = re.compile(r"[a-z0-9][a-z0-9-]*", re.ASCII)


class _IndentedDumper(yaml.SafeDumper):
    """SafeDumper that indents sequence items under their parent key.

    PyYAML emits sequences indentless by default (``key:\\n- item``), which the
    repo's yamllint (``indentation: {indent-sequences: true}``) rejects — so a
    plain ``safe_dump`` catalog fails CI lint. Overriding ``increase_indent`` to
    never be indentless produces the ``key:\\n  - item`` form yamllint expects.
    """

    def increase_indent(self, flow: bool = False, indentless: bool = False):
        return super().increase_indent(flow, indentless=False)


def dump_catalog(data: dict) -> str:
    """Serialize a catalog to yamllint-compliant YAML (indent-sequences)."""
    return yaml.dump(
        data,
        Dumper=_IndentedDumper,
        sort_keys=False,
        default_flow_style=False,
        allow_unicode=True,
        indent=2,
    )


def catalog_path(catalog_dir: str | os.PathLike, app: str) -> Path:
    """Build a single catalog basename for every app-based operation."""
    if not isinstance(app, str) or not _SLUG.fullmatch(app):
        raise ValidationError([f"app is not a slug: {app!r}"])
    return Path(catalog_dir) / f"{app}.yaml"


def new_catalog(app: str) -> dict:
    return {"version": 1, "app": app, "tests": []}


@contextlib.contextmanager
def _open_root(path: Path, *, create: bool) -> Iterator[int]:
    """Preserve configured parent aliases; pin the root without following it."""
    try:
        root = path.parent.resolve() / path.name
    except (
        RuntimeError
    ) as exc:  # pathlib reports symlink loops this way on Python <3.13
        raise OSError("Cannot resolve catalog parent") from exc
    directory = os.open(root.anchor, _DIRECTORY)
    try:
        for part in root.parts[1:]:
            try:
                child = os.open(part, _DIRECTORY, dir_fd=directory)
            except FileNotFoundError:
                if not create:
                    raise
                with contextlib.suppress(FileExistsError):
                    os.mkdir(part, dir_fd=directory)
                child = os.open(part, _DIRECTORY, dir_fd=directory)
            os.close(directory)
            directory = child
        yield directory
    finally:
        os.close(directory)


def _regular(info: os.stat_result) -> None:
    if not stat.S_ISREG(info.st_mode):
        raise OSError("Catalog entry must be a regular file")


def _load(directory: int, name: str, app: str) -> dict:
    try:
        descriptor = os.open(
            name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory
        )
    except FileNotFoundError:
        return new_catalog(app)
    with os.fdopen(descriptor, "r", encoding="utf-8") as source:
        _regular(os.fstat(source.fileno()))
        data = yaml.safe_load(source)
    return new_catalog(app) if data is None else data


def load_catalog(path: Path, app: str) -> dict:
    """Read a regular catalog under a pinned root, or return a fresh catalog."""
    catalog_path(path.parent, app)
    try:
        with _open_root(path.parent, create=False) as directory:
            return _load(directory, path.name, app)
    except FileNotFoundError:
        return new_catalog(app)


class LockedCatalog:
    """Keep all transaction I/O relative to the directory owning the held lock."""

    def __init__(self, directory: int, name: str, lock: int) -> None:
        self.directory = directory
        self.name = name
        self.lock = lock

    def check_lock(self) -> None:
        """Reject unsafe inodes and lock-entry replacement observed while waiting."""
        info = os.fstat(self.lock)
        _regular(info)
        if info.st_uid != os.geteuid() or info.st_nlink != 1:
            raise OSError("Catalog lock must be caller-owned with one link")
        entry = os.stat(
            self.name + ".lock", dir_fd=self.directory, follow_symlinks=False
        )
        if (entry.st_dev, entry.st_ino) != (info.st_dev, info.st_ino):
            raise OSError("Catalog lock entry changed")

    def load(self, app: str) -> dict:
        """Read through the same directory descriptor used for locking."""
        return _load(self.directory, self.name, app)

    def write(self, data: dict) -> None:
        """Atomically replace an entry, never write through a shared target inode."""
        text = dump_catalog(data)
        temporary = f".catalog-{uuid.uuid4().hex}.tmp"
        descriptor = os.open(
            temporary,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
            0o600,
            dir_fd=self.directory,
        )
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as target:
                target.write(text)
                target.flush()
                os.fsync(target.fileno())
            self.check_lock()
            with contextlib.suppress(FileNotFoundError):
                _regular(
                    os.stat(self.name, dir_fd=self.directory, follow_symlinks=False)
                )
            os.replace(
                temporary,
                self.name,
                src_dir_fd=self.directory,
                dst_dir_fd=self.directory,
            )
        finally:
            with contextlib.suppress(FileNotFoundError):
                os.unlink(temporary, dir_fd=self.directory)


@contextlib.contextmanager
def file_lock(path: Path) -> Iterator[LockedCatalog]:
    """Hold a nontruncating no-follow sidecar and pin its directory until unlock."""
    if path.suffix != ".yaml":
        raise ValidationError(["catalog must have a .yaml suffix"])
    catalog_path(path.parent, path.stem)
    with _open_root(path.parent, create=True) as directory:
        descriptor = os.open(
            path.name + ".lock",
            os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW | os.O_NONBLOCK,
            0o600,
            dir_fd=directory,
        )
        try:
            locked = LockedCatalog(directory, path.name, descriptor)
            locked.check_lock()
            fcntl.flock(descriptor, fcntl.LOCK_EX)
            try:
                locked.check_lock()
                yield locked
            finally:
                fcntl.flock(descriptor, fcntl.LOCK_UN)
        finally:
            os.close(descriptor)


def atomic_write(path: Path, data: dict) -> None:
    """Lock and atomically replace a catalog for callers outside a transaction."""
    with file_lock(path) as locked:
        locked.write(data)

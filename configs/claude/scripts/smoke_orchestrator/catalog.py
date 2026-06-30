"""Catalog location, load, atomic write, and per-app file locking (T007).

Per-app YAML files under ``smoke-catalog/<app>.yaml`` keep concurrent appends
from different apps fully isolated; within an app, a flock serializes writers
and an atomic replace prevents a partial/corrupt catalog (FR-015).
"""

from __future__ import annotations

import contextlib
import fcntl
import os
import tempfile
from collections.abc import Iterator
from pathlib import Path

import yaml


def catalog_path(catalog_dir: str | os.PathLike, app: str) -> Path:
    return Path(catalog_dir) / f"{app}.yaml"


def new_catalog(app: str) -> dict:
    return {"version": 1, "app": app, "tests": []}


def load_catalog(path: Path, app: str) -> dict:
    """Load a catalog, or return a fresh one if the file does not exist."""
    if not path.exists():
        return new_catalog(app)
    with path.open("r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    if data is None:
        return new_catalog(app)
    return data


def atomic_write(path: Path, data: dict) -> None:
    """Write YAML via a temp file + os.replace so readers never see a partial file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    text = yaml.safe_dump(
        data, sort_keys=False, default_flow_style=False, allow_unicode=True
    )
    fd, tmp = tempfile.mkstemp(
        dir=str(path.parent), prefix=f".{path.name}.", suffix=".tmp"
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


@contextlib.contextmanager
def file_lock(path: Path) -> Iterator[None]:
    """Advisory exclusive lock on a per-app ``.lock`` sidecar (FR-015)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = path.with_suffix(path.suffix + ".lock")
    with open(lock_path, "w") as lock_fh:
        fcntl.flock(lock_fh, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lock_fh, fcntl.LOCK_UN)

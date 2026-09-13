"""Descriptor-relative, no-follow readers for checkout trust anchors."""

from __future__ import annotations

import os
import stat
from pathlib import Path


def _relative(repo_root: Path, path: Path) -> tuple[Path, tuple[str, ...]]:
    root = repo_root.absolute()
    candidate = path.absolute()
    try:
        relative = candidate.relative_to(root)
    except ValueError as error:
        raise ValueError("trust anchor escapes repository root") from error
    if not relative.parts or any(part in {"", ".", ".."} for part in relative.parts):
        raise ValueError("unsafe trust anchor path")
    return root, relative.parts


def read_trust_anchor(repo_root: Path, path: Path) -> bytes:
    """Read a checkout-owned regular file from one no-follow descriptor chain."""
    root, parts = _relative(repo_root, path)
    try:
        root_fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    except OSError as error:
        raise ValueError("unsafe repository root") from error
    current_fd = root_fd
    try:
        for component in parts[:-1]:
            next_fd = os.open(
                component,
                os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                dir_fd=current_fd,
            )
            os.close(current_fd)
            current_fd = next_fd
        fd = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW, dir_fd=current_fd)
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode):
            os.close(fd)
            raise ValueError("trust anchor is not a regular file")
        with os.fdopen(fd, "rb") as stream:
            return stream.read()
    except OSError as error:
        raise ValueError("unsafe trust anchor path") from error
    finally:
        os.close(current_fd)

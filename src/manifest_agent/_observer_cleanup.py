"""Deletion authority is a signed inventory, never a directory's current contents."""

from __future__ import annotations

import errno
import hashlib
import os
import stat
from pathlib import Path


def _identity(info) -> list[int]:
    return [info.st_dev, info.st_ino]


def _snapshot(info) -> tuple:
    # Reading may legitimately update atime; changes to data or identity may not.
    return (
        info.st_dev,
        info.st_ino,
        info.st_mode,
        info.st_nlink,
        info.st_uid,
        info.st_gid,
        info.st_size,
        info.st_mtime_ns,
        info.st_ctime_ns,
    )


def _unchanged(parent: int, name: str, info) -> None:
    if _snapshot(os.stat(name, dir_fd=parent, follow_symlinks=False)) != _snapshot(
        info
    ):
        raise ValueError("observer retirement surviving files changed; preserved")


def _remove_entry(parent: int, name: str, relative: str, files: dict) -> None:
    row = files.get(relative)
    if row is None:
        raise ValueError("observer retirement has unowned contents; preserved")
    info = os.stat(name, dir_fd=parent, follow_symlinks=False)
    actual = {"mode": stat.S_IMODE(info.st_mode)}
    if stat.S_ISDIR(info.st_mode):
        actual["kind"] = "directory"
        if actual != row:
            raise ValueError("observer retirement surviving files changed; preserved")
        _remove_directory(parent, name, relative, files, _identity(info))
        return
    if stat.S_ISLNK(info.st_mode):
        actual.update(kind="symlink", target=os.readlink(name, dir_fd=parent))
    elif stat.S_ISREG(info.st_mode) and info.st_nlink == 1:
        descriptor = os.open(name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=parent)
        with os.fdopen(descriptor, "rb") as stream:
            if _snapshot(os.fstat(stream.fileno())) != _snapshot(info):
                raise ValueError("observer retirement file was replaced; preserved")
            checksum = hashlib.sha256()
            while chunk := stream.read(1024 * 1024):
                checksum.update(chunk)
            if _snapshot(os.fstat(stream.fileno())) != _snapshot(info):
                raise ValueError(
                    "observer retirement file changed while reading; preserved"
                )
        actual.update(kind="file", sha256=checksum.hexdigest())
    else:
        raise ValueError("observer retirement contains an unsafe file; preserved")
    if actual != row:
        raise ValueError("observer retirement surviving files changed; preserved")
    _unchanged(parent, name, info)
    os.unlink(name, dir_fd=parent)


def _remove_directory(parent, name, relative, files, inode) -> None:
    descriptor = os.open(
        name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent
    )
    try:
        info = os.fstat(descriptor)
        if _identity(info) != inode:
            raise ValueError("observer retirement directory was replaced; preserved")
        row = files.get(relative)
        if row is not None and row != {
            "kind": "directory",
            "mode": stat.S_IMODE(info.st_mode),
        }:
            raise ValueError("observer retirement surviving files changed; preserved")
        for child in sorted(os.listdir(descriptor)):
            child_relative = child if relative == "." else f"{relative}/{child}"
            _remove_entry(descriptor, child, child_relative, files)
        # Child deletion changes directory timestamps; bind the final name to
        # the held directory, but never recurse over a new enumeration.
        final = os.stat(name, dir_fd=parent, follow_symlinks=False)
        if _identity(final) != inode or not stat.S_ISDIR(final.st_mode):
            raise ValueError("observer retirement directory was replaced; preserved")
        if stat.S_IMODE(final.st_mode) != stat.S_IMODE(info.st_mode):
            raise ValueError("observer retirement directory mode changed; preserved")
        try:
            os.rmdir(name, dir_fd=parent)
        except OSError as error:
            if error.errno in (errno.ENOTEMPTY, errno.EEXIST):
                raise ValueError(
                    "observer retirement gained unowned contents; preserved"
                ) from error
            raise
    finally:
        os.close(descriptor)


def _remove_tree_at(parent: int, name: str, *, expected_inode, files: dict) -> None:
    """Remove only matching authorized survivors, using nonrecursive rmdir.

    Descriptor-relative checks narrow replacement windows; portable unlink is
    not atomic compare-and-unlink against arbitrary concurrent same-UID writers.
    """
    if not name or Path(name).name != name or name in (".", ".."):
        raise ValueError("unsafe observer retirement name")
    _remove_directory(parent, name, ".", files, expected_inode)

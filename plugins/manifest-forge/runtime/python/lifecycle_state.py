#!/usr/bin/env python3
"""Read and atomically write Forge lifecycle tracks through verified dir FDs."""

from __future__ import annotations

import errno
import os
import re
import secrets
import stat
import sys
from collections.abc import Iterator
from contextlib import contextmanager, suppress
from pathlib import Path
from typing import BinaryIO

MISSING_TRACK = 2
UNSAFE_STATE = 64
UNSAFE_TRACK = 65
INVALID_TRACK_ID = 66
IO_ERROR = 74

_DIR_FLAGS = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
_FILE_FLAGS = os.O_NOFOLLOW | os.O_CLOEXEC
_TRACK_ID = re.compile(r"^[A-Za-z0-9_.-]+$")


class StateFailure(Exception):
    """Carry a stable exit code back to the lifecycle shell boundary."""

    def __init__(self, exit_code: int) -> None:
        super().__init__(exit_code)
        self.exit_code = exit_code


def _validate_track_id(track_id: str) -> str:
    if (
        not track_id
        or track_id.startswith(".")
        or ".." in track_id
        or _TRACK_ID.fullmatch(track_id) is None
    ):
        raise StateFailure(INVALID_TRACK_ID)
    return f"{track_id}.json"


def _open_root(configured_root: str, *, create: bool) -> int:
    root = Path(configured_root)
    if not root.is_absolute():
        raise StateFailure(UNSAFE_STATE)
    if create:
        try:
            root.mkdir(mode=0o700, parents=True, exist_ok=True)
        except OSError as exc:
            raise StateFailure(UNSAFE_STATE) from exc
    try:
        return os.open(root, _DIR_FLAGS)
    except FileNotFoundError as exc:
        raise StateFailure(MISSING_TRACK) from exc
    except OSError as exc:
        raise StateFailure(UNSAFE_STATE) from exc


def _open_child_dir(parent_fd: int, name: str, *, create: bool) -> int:
    created = False
    if create:
        try:
            os.mkdir(name, mode=0o700, dir_fd=parent_fd)
            created = True
        except FileExistsError:
            created = False
        except OSError as exc:
            raise StateFailure(UNSAFE_STATE) from exc
    try:
        child_fd = os.open(name, _DIR_FLAGS, dir_fd=parent_fd)
    except FileNotFoundError as exc:
        raise StateFailure(MISSING_TRACK) from exc
    except OSError as exc:
        raise StateFailure(UNSAFE_STATE) from exc
    if not stat.S_ISDIR(os.fstat(child_fd).st_mode):
        os.close(child_fd)
        raise StateFailure(UNSAFE_STATE)
    if created:
        os.fchmod(child_fd, 0o700)
    return child_fd


@contextmanager
def _open_state_dir(configured_root: str, *, create: bool) -> Iterator[int]:
    fds: list[int] = []
    try:
        current_fd = _open_root(configured_root, create=create)
        fds.append(current_fd)
        for component in ("manifest", "forge", "lifecycle"):
            current_fd = _open_child_dir(current_fd, component, create=create)
            fds.append(current_fd)
        yield current_fd
    finally:
        for fd in reversed(fds):
            os.close(fd)


def _open_track(state_fd: int, track_name: str) -> BinaryIO:
    try:
        track_fd = os.open(track_name, os.O_RDONLY | _FILE_FLAGS, dir_fd=state_fd)
    except FileNotFoundError as exc:
        raise StateFailure(MISSING_TRACK) from exc
    except OSError as exc:
        code = UNSAFE_TRACK if exc.errno in (errno.ELOOP, errno.ENOTDIR) else IO_ERROR
        raise StateFailure(code) from exc
    if not stat.S_ISREG(os.fstat(track_fd).st_mode):
        os.close(track_fd)
        raise StateFailure(UNSAFE_TRACK)
    return os.fdopen(track_fd, "rb")


def _reject_unsafe_target(state_fd: int, track_name: str) -> None:
    try:
        target = os.stat(track_name, dir_fd=state_fd, follow_symlinks=False)
    except FileNotFoundError:
        return
    except OSError as exc:
        raise StateFailure(IO_ERROR) from exc
    if not stat.S_ISREG(target.st_mode):
        raise StateFailure(UNSAFE_TRACK)


def _write_all(fd: int, payload: bytes) -> None:
    remaining = memoryview(payload)
    while remaining:
        written = os.write(fd, remaining)
        if written == 0:
            raise StateFailure(IO_ERROR)
        remaining = remaining[written:]


def _write_atomic(state_fd: int, track_name: str, payload: bytes) -> None:
    _reject_unsafe_target(state_fd, track_name)
    temp_name = f".track.{secrets.token_hex(16)}"
    temp_fd = -1
    try:
        temp_fd = os.open(
            temp_name,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | _FILE_FLAGS,
            0o600,
            dir_fd=state_fd,
        )
        _write_all(temp_fd, payload)
        os.fsync(temp_fd)
        os.close(temp_fd)
        temp_fd = -1
        _reject_unsafe_target(state_fd, track_name)
        os.replace(
            temp_name,
            track_name,
            src_dir_fd=state_fd,
            dst_dir_fd=state_fd,
        )
        os.fsync(state_fd)
    except StateFailure:
        raise
    except OSError as exc:
        raise StateFailure(IO_ERROR) from exc
    finally:
        if temp_fd >= 0:
            os.close(temp_fd)
        with suppress(FileNotFoundError):
            os.unlink(temp_name, dir_fd=state_fd)


def read_track(configured_root: str, track_id: str) -> bytes:
    """Read one regular track file without reopening its ancestor paths."""
    track_name = _validate_track_id(track_id)
    with (
        _open_state_dir(configured_root, create=False) as state_fd,
        _open_track(state_fd, track_name) as stream,
    ):
        return stream.read()


def write_track(configured_root: str, track_id: str, payload: bytes) -> None:
    """Atomically replace one track inside a descriptor-bound state directory."""
    track_name = _validate_track_id(track_id)
    with _open_state_dir(configured_root, create=True) as state_fd:
        _write_atomic(state_fd, track_name, payload)


def main(argv: list[str]) -> int:
    """Dispatch the narrow lifecycle track read/write interface."""
    if len(argv) != 3 or argv[0] not in ("read", "write"):
        print(
            "usage: lifecycle_state.py read|write <xdg-state-root> <track-id>",
            file=sys.stderr,
        )
        return 1
    command, configured_root, track_id = argv
    try:
        if command == "read":
            sys.stdout.buffer.write(read_track(configured_root, track_id))
        else:
            write_track(configured_root, track_id, sys.stdin.buffer.read())
    except StateFailure as exc:
        return exc.exit_code
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

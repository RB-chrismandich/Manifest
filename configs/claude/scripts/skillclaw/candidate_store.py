"""Contain generated skill writes beneath a caller-selected candidate root."""

import os
import re
import stat
import uuid
from contextlib import contextmanager, suppress
from pathlib import Path

_SLUG = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*", re.ASCII)
_DIRECTORY = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW


def validate_candidates(candidates: list[dict]) -> list[tuple[str, bytes]]:
    """Validate the entire batch before any filesystem side effects."""
    prepared = []
    for candidate in candidates:
        name = candidate.get("name")
        content = candidate.get("content")
        if not isinstance(name, str) or len(name) > 255 or not _SLUG.fullmatch(name):
            raise RuntimeError("Invalid SkillClaw candidate name")
        if not isinstance(content, str):
            raise RuntimeError("Invalid SkillClaw candidate content")
        try:
            prepared.append((name, content.encode("utf-8")))
        except UnicodeError as exc:
            raise RuntimeError("Invalid SkillClaw candidate encoding") from exc
    return prepared


@contextmanager
def _open_root(root: Path, *, create: bool):
    """Walk canonical trusted ancestors without following links at use time."""
    fd = os.open(root.anchor, _DIRECTORY)
    try:
        for part in root.parts[1:]:
            try:
                child = os.open(part, _DIRECTORY, dir_fd=fd)
            except FileNotFoundError:
                if not create:
                    yield None
                    return
                os.mkdir(part, dir_fd=fd)
                child = os.open(part, _DIRECTORY, dir_fd=fd)
            os.close(fd)
            fd = child
        yield fd
    finally:
        os.close(fd)


def _check_target(directory: int) -> int | None:
    try:
        target = os.stat("SKILL.md", dir_fd=directory, follow_symlinks=False)
    except FileNotFoundError:
        return
    if not stat.S_ISREG(target.st_mode):
        raise RuntimeError("SkillClaw candidate target must be a regular file")
    return stat.S_IMODE(target.st_mode)


def _preflight(root: int, names: list[str]) -> None:
    for name in names:
        try:
            directory = os.open(name, _DIRECTORY, dir_fd=root)
        except FileNotFoundError:
            continue
        try:
            _check_target(directory)
        finally:
            os.close(directory)


def _write(root: int, name: str, content: bytes) -> None:
    with suppress(FileExistsError):
        os.mkdir(name, dir_fd=root)
    directory = os.open(name, _DIRECTORY, dir_fd=root)
    temporary = f".skillclaw-{uuid.uuid4().hex}"
    try:
        mode = _check_target(directory)
        fd = os.open(
            temporary,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
            0o666,
            dir_fd=directory,
        )
        with os.fdopen(fd, "wb") as output:
            output.write(content)
            if mode is not None:
                os.fchmod(output.fileno(), mode)
        _check_target(directory)
        # Replace the directory entry, never truncate a potentially shared inode.
        os.replace(temporary, "SKILL.md", src_dir_fd=directory, dst_dir_fd=directory)
    finally:
        with suppress(FileNotFoundError):
            os.unlink(temporary, dir_fd=directory)
        os.close(directory)


def write_candidates(candidates: list[dict], evolved_dir: Path) -> list[str]:
    """Reject unsafe batches, then create or atomically replace regular skills."""
    prepared = validate_candidates(candidates)
    if not prepared:
        return []
    try:
        requested = Path(evolved_dir).expanduser()
        # Parent aliases are trusted configuration; the output root is protected.
        root = requested.parent.resolve() / requested.name
        names = [name for name, _ in prepared]
        with _open_root(root, create=False) as descriptor:
            if descriptor is not None:
                _preflight(descriptor, names)
                for name, content in prepared:
                    _write(descriptor, name, content)
                return names
        with _open_root(root, create=True) as descriptor:
            assert descriptor is not None
            _preflight(descriptor, names)
            for name, content in prepared:
                _write(descriptor, name, content)
        return names
    except OSError as exc:
        raise RuntimeError(f"Cannot safely write SkillClaw candidates: {exc}") from exc

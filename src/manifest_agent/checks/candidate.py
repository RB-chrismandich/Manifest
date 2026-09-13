"""Candidate-local copies with content-derived stable identity."""

from __future__ import annotations

import hashlib
import os
import shutil
import stat
from pathlib import Path

from .models import Candidate


class CandidateBlockedError(RuntimeError):
    """The requested candidate cannot be safely materialized."""


def _entries(root: Path) -> list[Path]:
    entries: list[Path] = []
    resolved_root = root.resolve()
    ignored = {".git", "__pycache__", ".venv", "node_modules", ".pytest_cache"}
    for directory, directories, files in os.walk(root, followlinks=False):
        directory_path = Path(directory)
        directories[:] = sorted(name for name in directories if name not in ignored)
        for name in sorted([*directories, *files]):
            path = directory_path / name
            relative = path.relative_to(root)
            if relative.parts[0] in ignored:
                continue
            mode = path.lstat().st_mode
            if stat.S_ISLNK(mode):
                target = path.readlink()
                if target.is_absolute():
                    raise CandidateBlockedError(
                        f"candidate source contains absolute symlink: {relative}"
                    )
                try:
                    resolved_target = (path.parent / target).resolve(strict=True)
                except OSError as error:
                    raise CandidateBlockedError(
                        f"candidate source contains dangling symlink: {relative}"
                    ) from error
                if not resolved_target.is_relative_to(resolved_root):
                    raise CandidateBlockedError(
                        f"candidate source symlink escapes root: {relative}"
                    )
                target_mode = resolved_target.lstat().st_mode
                if not (stat.S_ISDIR(target_mode) or stat.S_ISREG(target_mode)):
                    raise CandidateBlockedError(
                        f"candidate source symlink targets special file: {relative}"
                    )
                entries.append(path)
                continue
            if not (stat.S_ISDIR(mode) or stat.S_ISREG(mode)):
                raise CandidateBlockedError(
                    f"candidate source contains special file: {relative}"
                )
            entries.append(path)
    return entries


def _update_field(digest, value: bytes) -> None:
    digest.update(len(value).to_bytes(8, "big"))
    digest.update(value)


def _update_record(digest, fields: tuple[bytes, ...]) -> None:
    _update_field(digest, len(fields).to_bytes(4, "big"))
    for field in fields:
        _update_field(digest, field)


def candidate_digest(root: Path) -> str:
    digest = hashlib.sha256()
    for path in _entries(root):
        relative = path.relative_to(root).as_posix().encode()
        mode = path.lstat().st_mode
        metadata = (
            stat.S_IFMT(mode).to_bytes(4, "big"),
            stat.S_IMODE(mode).to_bytes(4, "big"),
        )
        if stat.S_ISLNK(mode):
            fields = (b"symlink", relative, *metadata, os.fsencode(path.readlink()))
        elif stat.S_ISREG(mode):
            fields = (b"file", relative, *metadata, path.read_bytes())
        elif stat.S_ISDIR(mode):
            fields = (b"directory", relative, *metadata)
        else:
            raise CandidateBlockedError(
                f"candidate source contains special file: {relative}"
            )
        _update_record(digest, fields)
    return digest.hexdigest()


def materialize_candidate(
    source: Path,
    destination: Path,
    *,
    head_sha: str | None = None,
    tree_sha: str | None = None,
    base_sha: str | None = None,
) -> Candidate:
    if destination.exists():
        raise CandidateBlockedError(f"candidate destination exists: {destination}")
    if not source.is_dir():
        raise CandidateBlockedError(f"source is unavailable: {source}")
    _entries(source)
    shutil.copytree(
        source,
        destination,
        symlinks=True,
        ignore=shutil.ignore_patterns(
            ".git", "__pycache__", ".venv", "node_modules", ".pytest_cache"
        ),
    )
    digest = candidate_digest(destination)
    return Candidate(
        destination, digest, head_sha or digest, tree_sha or digest, base_sha or digest
    )

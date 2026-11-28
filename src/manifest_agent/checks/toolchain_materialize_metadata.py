"""Local project metadata hashing for toolchain environment bundles."""

from __future__ import annotations

import hashlib
import os
import stat
from pathlib import Path


class MaterializationError(ValueError):
    """A python-env/node-env materialization step failed or was blocked."""


_PYTHON_PROJECT_METADATA = {
    "project-env": (
        "pyproject.toml",
        "configs/claude/scripts/manifest_model_policy/pyproject.toml",
    ),
    "config-env": (
        "pyproject.toml",
        "uv.lock",
        "configs/pyproject.toml",
        "configs/uv.lock",
        "configs/claude/pyproject.toml",
        "configs/claude/scripts/manifest_model_policy/pyproject.toml",
    ),
    "python-env": (
        "pyproject.toml",
        "uv.lock",
        "config/pyproject.toml",
        "config/uv.lock",
        "config/toolchain/pyproject.toml",
    ),
}


def python_project_metadata_digest(repo_root: Path, bundle: str) -> str:
    """Hash every local project file that can select uv/Hatch build behavior."""
    relative_paths = _PYTHON_PROJECT_METADATA.get(bundle)
    if relative_paths is None:
        raise MaterializationError(f"unknown python environment bundle: {bundle}")
    root = repo_root.resolve(strict=True)
    hasher = hashlib.sha256()
    for relative in relative_paths:
        candidate = root / relative
        cursor = root
        for component in Path(relative).parts:
            cursor /= component
            if cursor.is_symlink():
                raise MaterializationError(f"unsafe project metadata: {relative}")
        content = None
        if candidate.exists():
            path = candidate.resolve(strict=True)
            if not path.is_relative_to(root):
                raise MaterializationError(f"unsafe project metadata: {relative}")
            nofollow = getattr(os, "O_NOFOLLOW", 0)
            try:
                with open(
                    path,
                    "rb",
                    opener=lambda name, flags, nofollow=nofollow: os.open(
                        name, flags | nofollow
                    ),
                ) as stream:
                    if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
                        raise MaterializationError(
                            f"unsafe project metadata: {relative}"
                        )
                    content = stream.read()
            except OSError as error:
                raise MaterializationError(
                    f"unreadable project metadata: {relative}: {error}"
                ) from error
        name = relative.encode()
        hasher.update(len(name).to_bytes(8, "big"))
        hasher.update(name)
        if content is None:
            hasher.update(b"M")
            continue
        hasher.update(b"F")
        hasher.update(len(content).to_bytes(8, "big"))
        hasher.update(content)
    return hasher.hexdigest()

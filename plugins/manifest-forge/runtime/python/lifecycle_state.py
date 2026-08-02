#!/usr/bin/env python3
"""Validate that Forge lifecycle state remains in its fixed XDG directory."""

from __future__ import annotations

import os
import stat
import sys
from pathlib import Path


def validate_state_path(configured_root: str, configured_target: str) -> None:
    """Reject non-absolute, redirected, or symlinked lifecycle state paths."""
    raw_root = Path(configured_root)
    if not raw_root.is_absolute():
        raise ValueError("XDG state root must be absolute")

    root = Path(os.path.abspath(raw_root))
    target = Path(os.path.abspath(configured_target))
    if target != root / "manifest" / "forge" / "lifecycle":
        raise ValueError("lifecycle state target is outside its fixed XDG location")

    canonical_root = root.resolve(strict=False)
    components = (root, root / "manifest", root / "manifest" / "forge", target)
    for path in components:
        try:
            mode = path.lstat().st_mode
        except FileNotFoundError:
            continue
        except OSError as exc:
            raise ValueError(f"cannot inspect state component {path}") from exc
        if stat.S_ISLNK(mode) or not stat.S_ISDIR(mode):
            raise ValueError(f"unsafe state component {path}")
        try:
            path.resolve(strict=True).relative_to(canonical_root)
        except (OSError, ValueError) as exc:
            raise ValueError(f"state component escapes XDG root: {path}") from exc


def main(argv: list[str]) -> int:
    """Validate one XDG root and its fixed lifecycle state target."""
    if len(argv) != 2:
        print("usage: lifecycle_state.py <xdg-state-root> <state-dir>", file=sys.stderr)
        return 1
    try:
        validate_state_path(argv[0], argv[1])
    except ValueError:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

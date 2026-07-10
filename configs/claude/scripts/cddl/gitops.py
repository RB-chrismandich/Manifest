"""Git safety mechanics (FR-011; research D9).

Pre-flight refuses the default branch and dirty trees (unless overridden);
success stages exactly the loop-written paths. The loop never commits, pushes,
merges, or reverts — staging is the sole success signal.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from . import AbortError, PreflightError


def _git(repo_root, *args) -> tuple[int, str, str]:
    proc = subprocess.run(
        ["git", "-C", str(repo_root), *args],
        capture_output=True,
        text=True,
        check=False,
    )
    return proc.returncode, proc.stdout, proc.stderr


def repo_root_of(path: str | Path) -> Path:
    # A file target (e.g. a superpowers design doc, US3) resolves via its
    # parent — `git -C` requires a directory.
    workdir = Path(path)
    if not workdir.is_dir():
        workdir = workdir.parent
    rc, out, _err = _git(workdir, "rev-parse", "--show-toplevel")
    if rc != 0:
        raise PreflightError(f"not inside a git repository: {path}")
    return Path(out.strip()).resolve()


def current_branch(repo_root) -> str:
    rc, out, err = _git(repo_root, "rev-parse", "--abbrev-ref", "HEAD")
    if rc != 0:
        raise PreflightError(f"cannot determine current branch: {err.strip()}")
    return out.strip()


def default_branch(repo_root) -> str:
    rc, out, _ = _git(repo_root, "symbolic-ref", "--short", "refs/remotes/origin/HEAD")
    if rc == 0 and out.strip():
        return out.strip().split("/", 1)[-1]
    for candidate in ("main", "master"):
        rc, _, _ = _git(repo_root, "show-ref", "--verify", f"refs/heads/{candidate}")
        if rc == 0:
            return candidate
    return "main"


def is_dirty(repo_root) -> bool:
    rc, out, err = _git(repo_root, "status", "--porcelain")
    if rc != 0:
        raise PreflightError(f"git status failed: {err.strip()}")
    return bool(out.strip())


def preflight(repo_root, allow_dirty: bool) -> str:
    """Refuse default-branch or dirty-tree runs; return the current branch."""
    branch = current_branch(repo_root)
    default = default_branch(repo_root)
    if branch == default:
        raise PreflightError(
            f"on default branch '{default}' — the loop only writes to a "
            "feature branch; create/switch to one first (FR-011)"
        )
    if not allow_dirty and is_dirty(repo_root):
        raise PreflightError(
            "dirty working tree — commit/stash your changes, or rerun with "
            "--allow-dirty (the loop stages only its own written paths)"
        )
    return branch


def stage(repo_root, paths: list[str]) -> None:
    """Stage exactly the given paths (staged = critic-approved, FR-011).

    A path the loop created and later deleted within the run (never tracked)
    matches nothing — `git add` would die on its pathspec — and has nothing
    to stage; such phantoms are skipped.
    """
    stageable = []
    for path in paths:
        exists = (Path(repo_root) / path).exists()
        _rc, tracked, _ = _git(repo_root, "ls-files", "--", path)
        if exists or tracked.strip():
            stageable.append(path)
    if not stageable:
        return
    rc, _, err = _git(repo_root, "add", "--", *stageable)
    if rc != 0:
        raise AbortError(f"staging approved changes failed: {err.strip()}")

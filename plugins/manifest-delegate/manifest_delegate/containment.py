"""Cgroup-v2 ownership for backend descendants.

A cgroup membership survives ``setsid``.  The marker is durable so a worker
crash cannot turn a contained launch into an unreapable orphan.
"""

from __future__ import annotations

import os

from . import constants

CGROUP_ROOT_ENV = "MANIFEST_CGROUP_ROOT"
_DEFAULT_CGROUP_ROOT = "/sys/fs/cgroup"
CGROUP_DIR_FILENAME = "backend.cgroup"
STATE_CONTAINED = "contained"
STATE_DEGRADED = "degraded"
STATE_CLEANED = "cleaned"


def cgroup_root() -> str:
    """Resolve the delegated root at use time, not import time."""
    return os.environ.get(CGROUP_ROOT_ENV, _DEFAULT_CGROUP_ROOT)


def probe(root: str | None = None) -> tuple[bool, str]:
    """Verify every prerequisite required for the success description."""
    root = root or cgroup_root()
    if not os.path.isfile(os.path.join(root, "cgroup.controllers")):
        return False, "cgroup v2 unified hierarchy not mounted"
    for required in ("cgroup.procs", "cgroup.kill"):
        candidate = os.path.join(root, required)
        if not os.path.isfile(candidate) or not os.access(candidate, os.W_OK):
            return False, f"{root}/{required} is not writable"
    return True, "cgroup v2 with cgroup.kill"


def create(job_dir, root: str | None = None) -> tuple[str | None, str, str]:
    """Create and durably record one cgroup for a pre-existing job directory."""
    root = root or cgroup_root()
    available, reason = probe(root)
    if not available:
        return None, STATE_DEGRADED, reason
    path = os.path.join(root, f"manifest-delegate-{os.path.basename(job_dir)}")
    try:
        os.makedirs(path, exist_ok=True)
        if not os.path.isfile(os.path.join(path, "cgroup.kill")):
            os.rmdir(path)
            return None, STATE_DEGRADED, "kernel lacks cgroup.kill"
        with open(
            os.path.join(job_dir, CGROUP_DIR_FILENAME), "w", encoding="utf-8"
        ) as marker:
            marker.write(path)
    except OSError as exc:
        return None, STATE_DEGRADED, f"cgroup setup failed: {exc}"
    return path, STATE_CONTAINED, reason


def read_path(job_dir) -> str | None:
    try:
        with open(
            os.path.join(job_dir, CGROUP_DIR_FILENAME), encoding="utf-8"
        ) as marker:
            path = marker.read().strip()
    except OSError:
        return None
    return path or None


def is_contained(record) -> bool:
    """Whether the durable job record requires cgroup containment."""
    return (record.get("containment") or {}).get("state") == STATE_CONTAINED


def join(path: str) -> None:
    """Move the post-fork child before it starts a new session."""
    with open(os.path.join(path, "cgroup.procs"), "w", encoding="utf-8") as members:
        members.write(str(os.getpid()))


def join_hook(job_dir):
    """Return a pre-exec hook which deliberately propagates join errors."""
    path = read_path(job_dir)
    marker = os.path.join(job_dir, CGROUP_DIR_FILENAME)
    if path is None:
        if os.path.lexists(marker):
            raise OSError("corrupt containment marker")
        return None

    def _join():
        join(path)

    return _join


def reap(job_dir, required: bool = False) -> bool | None:
    """Reap descendants; a required but unreadable marker is a failed reap."""
    marker = os.path.join(job_dir, CGROUP_DIR_FILENAME)
    path = read_path(job_dir)
    if path is None:
        if required or os.path.lexists(marker):
            constants.err(f"job dir {job_dir}: contained cgroup marker is unavailable")
            return False
        return None
    try:
        with open(
            os.path.join(path, "cgroup.kill"), "w", encoding="utf-8"
        ) as kill_file:
            kill_file.write("1")
    except OSError as exc:
        constants.err(f"job dir {job_dir}: failed to reap cgroup {path}: {exc}")
        return False
    return True


def cleanup(job_dir, required: bool = False, on_cgroup_removed=None) -> bool:
    """Remove containment only after cgroup removal; retain failed state."""
    marker = os.path.join(job_dir, CGROUP_DIR_FILENAME)
    path = read_path(job_dir)
    if path is None:
        if required or os.path.lexists(marker):
            constants.err(f"job dir {job_dir}: contained cgroup marker is unavailable")
            return False
        return True
    if not os.path.exists(path):
        try:
            if on_cgroup_removed is not None:
                on_cgroup_removed()
            os.unlink(marker)
        except OSError as exc:
            constants.err(
                f"job dir {job_dir}: failed to remove containment marker: {exc}"
            )
            return False
        return True
    if reap(job_dir, required=required) is False:
        return False
    try:
        os.rmdir(path)
    except FileNotFoundError:
        constants.err(f"job dir {job_dir}: cgroup {path} disappeared before cleanup")
    except OSError as exc:
        constants.err(f"job dir {job_dir}: failed to remove cgroup {path}: {exc}")
        return False
    try:
        if on_cgroup_removed is not None:
            on_cgroup_removed()
        os.unlink(marker)
    except OSError as exc:
        constants.err(f"job dir {job_dir}: failed to remove containment marker: {exc}")
        return False
    return True

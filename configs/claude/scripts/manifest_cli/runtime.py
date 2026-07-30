"""Facts about the deployed home runtime, shared by the router and doctor.

Every path here has one resolution rule so the wrapper, the shims, the router and
doctor cannot disagree about where the runtime lives: ``MANIFEST_HOME`` wins,
otherwise ``~/.claude``.
"""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

WRAPPER_NAME = "manifest"


def runtime_root() -> Path:
    """Deployed runtime root (``~/.claude`` unless MANIFEST_HOME overrides it)."""
    override = os.environ.get("MANIFEST_HOME")
    if override:
        return Path(override)
    return Path.home() / ".claude"


def state_root() -> Path:
    """Shared state root (``~/.manifest``); outlives a deleted runtime root."""
    override = os.environ.get("MANIFEST_STATE_ROOT")
    if override:
        return Path(override)
    return Path.home() / ".manifest"


def venv_dir(root: Path | None = None) -> Path:
    return (root or runtime_root()) / ".venv"


def wrapper_path() -> Path:
    """Installed CLI entry point (``~/.local/bin/manifest``)."""
    return Path.home() / ".local" / "bin" / WRAPPER_NAME


def deployed_wrapper_source(root: Path | None = None) -> Path:
    """The wrapper as deployed into the runtime tree — the drift comparison base."""
    return (root or runtime_root()) / "scripts" / "manifest-cli.sh"


def read_stamp(path: Path) -> dict[str, str]:
    """Parse a ``key=value`` stamp file; unreadable or malformed lines are skipped."""
    values: dict[str, str] = {}
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return values
    for line in text.splitlines():
        key, sep, value = line.partition("=")
        if sep and key:
            values[key.strip()] = value.strip()
    return values


def install_stamp(root: Path | None = None) -> dict[str, str]:
    """Merged install provenance: runtime.env (survives a deleted root) wins."""
    root = root or runtime_root()
    merged = read_stamp(root / "config" / "deploy_stamp")
    merged.update(read_stamp(state_root() / "runtime.env"))
    return merged


def runtime_version() -> str:
    from importlib.metadata import PackageNotFoundError, version

    try:
        return version("manifest-runtime")
    except PackageNotFoundError:
        return "0.0.0+unknown"


def uv_path() -> str | None:
    """uv is needed to re-sync the runtime, never to run it."""
    found = shutil.which("uv")
    if found:
        return found
    fallback = Path.home() / ".local" / "bin" / "uv"
    return str(fallback) if fallback.is_file() else None


def version_line() -> str:
    """One line carrying every fact needed to spot a drifted install."""
    root = runtime_root()
    stamp = install_stamp(root)
    head = stamp.get("head_sha", "")
    deploy = head[:7] if head else "unstamped"
    if stamp.get("dirty") == "true":
        deploy += "-dirty"
    py = ".".join(str(part) for part in sys.version_info[:3])
    return (
        f"manifest-runtime {runtime_version()} (python {py}) — "
        f"root {root}, deploy {deploy}"
    )

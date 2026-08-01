"""XDG locations owned by the ephemeral Manifest coordinator."""

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class XdgPaths:
    """Coordinator-owned XDG directories, never a harness home directory."""

    config: Path
    data: Path
    state: Path
    cache: Path


def xdg_paths() -> XdgPaths:
    """Resolve coordinator state paths according to the XDG Base Directory spec."""
    home = Path.home()
    return XdgPaths(
        config=Path(os.environ.get("XDG_CONFIG_HOME", home / ".config")) / "manifest",
        data=Path(os.environ.get("XDG_DATA_HOME", home / ".local/share")) / "manifest",
        state=Path(os.environ.get("XDG_STATE_HOME", home / ".local/state"))
        / "manifest",
        cache=Path(os.environ.get("XDG_CACHE_HOME", home / ".cache")) / "manifest",
    )

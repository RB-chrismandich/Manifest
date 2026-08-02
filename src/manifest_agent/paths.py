"""XDG locations owned by the ephemeral Manifest coordinator."""

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class XdgPaths:
    """Coordinator-owned XDG directories, never a harness home directory."""

    config: Path
    data: Path
    state: Path
    cache: Path


def xdg_paths(env: Mapping[str, str] | None = None) -> XdgPaths:
    """Resolve coordinator state paths according to the XDG Base Directory spec."""
    source = os.environ if env is None else env
    home = Path(source["HOME"]) if "HOME" in source else Path.home()
    return XdgPaths(
        config=Path(source.get("XDG_CONFIG_HOME", home / ".config")) / "manifest",
        data=Path(source.get("XDG_DATA_HOME", home / ".local/share")) / "manifest",
        state=Path(source.get("XDG_STATE_HOME", home / ".local/state")) / "manifest",
        cache=Path(source.get("XDG_CACHE_HOME", home / ".cache")) / "manifest",
    )

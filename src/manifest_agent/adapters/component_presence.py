"""Whether a declared bundle component is present in an installed plugin root."""

from pathlib import Path


def component_is_installed(path: Path) -> bool:
    """Whether a declared component path is present in an installed plugin root.

    A component may declare either a single file (`runtime/catalog.py`) or a
    whole directory (`skills/parallel-agent/scripts`); roughly half of the
    components declared across `plugins/*/plugin.json` are directories. Testing
    only `is_file()` silently denied evidence to every directory-valued
    component and pinned the harness at BLOCKED with no reachable repair —
    no state change could satisfy a check that could never pass.

    An empty directory is not evidence: the component declares content that must
    be installed, and a directory created incidentally does not satisfy it.
    """
    if path.is_file():
        return True
    return path.is_dir() and any(path.iterdir())

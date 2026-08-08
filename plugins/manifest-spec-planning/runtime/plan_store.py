#!/usr/bin/env python3
"""Resolve the portable plan store without depending on an assistant home."""

from __future__ import annotations

import argparse
import os
import re
import sys
from collections.abc import Mapping
from pathlib import Path

_OVERRIDE = re.compile(r"^plan_root\s*:\s*([^#\n]+?)\s*$")


def _xdg_data(env: Mapping[str, str]) -> Path:
    configured = env.get("XDG_DATA_HOME")
    if configured:
        return Path(configured).expanduser()
    home = env.get("HOME")
    if not home:
        raise ValueError("HOME or XDG_DATA_HOME is required")
    return Path(home).expanduser() / ".local/share"


def _project_override(project_root: Path) -> Path | None:
    config = project_root / ".manifest/plans.yml"
    if not config.is_file():
        return None
    matches = [
        match.group(1).strip().strip("'\"")
        for line in config.read_text(encoding="utf-8").splitlines()
        if (match := _OVERRIDE.fullmatch(line.strip()))
    ]
    if len(matches) != 1:
        raise ValueError(".manifest/plans.yml must contain one plan_root entry")
    relative = Path(matches[0])
    if relative.is_absolute():
        raise ValueError("project plan_root must be relative")
    resolved = (project_root / relative).resolve()
    try:
        resolved.relative_to(project_root.resolve())
    except ValueError as error:
        raise ValueError("project plan_root must remain inside the project") from error
    return resolved


def resolve_plan_root(
    *,
    env: Mapping[str, str] | None = None,
    project_root: str | Path | None = None,
) -> Path:
    """Return the explicit local root or the XDG data-backed default."""
    environment = os.environ if env is None else env
    project = Path.cwd() if project_root is None else Path(project_root)
    override = _project_override(project.resolve())
    return override or _xdg_data(environment) / "manifest/plans"


def ensure_plan_root(path: Path) -> Path:
    """Create the plan root and lifecycle children after explicit invocation."""
    path.mkdir(parents=True, exist_ok=True)
    for child in (".archive", ".abandoned"):
        (path / child).mkdir(exist_ok=True)
    return path


def main(argv: list[str] | None = None) -> int:
    """Print a validated plan root and create lifecycle directories on request."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, default=Path.cwd())
    parser.add_argument("--create", action="store_true")
    args = parser.parse_args(argv)
    try:
        root = resolve_plan_root(project_root=args.project_root)
        if args.create:
            ensure_plan_root(root)
    except (OSError, ValueError) as error:
        print(f"plan-store: {error}", file=sys.stderr)
        return 2
    print(root)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

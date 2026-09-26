#!/usr/bin/env python3
"""Sync or verify byte-for-byte mirror copies of shared sources."""

from __future__ import annotations

import argparse
import shutil
import stat
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# (source_dir, mirror_dir, excluded) — excluded maps each relative path that is
# intentionally NOT byte-identical to the reason the divergence is maintained.
MIRRORS = (
    (
        "configs/claude/scripts/constitution",
        "plugins/manifest-code-quality/skills/code-audit-constitution/scripts/constitution",
        {
            "__init__.py": "the docstring names the JSON policy",
            "registry.py": "stdlib JSON loader instead of PyYAML",
        },
    ),
    (
        "configs/claude/scripts/smoke_orchestrator",
        "plugins/manifest-code-quality/skills/smoke-manage/scripts/smoke_orchestrator",
        {"cli.py": "prog name smoke.py versus smoke_test.py"},
    ),
    (
        "plugins/manifest-ops/runtime/bin/ci_platform.sh",
        "plugins/manifest-security/runtime/bin/ci_platform.sh",
        {},
    ),
)


class MirrorError(ValueError):
    """The mirror tree cannot be enumerated or written safely."""


def _git_files(prefix: Path) -> list[Path]:
    """Git-tracked files under ``prefix`` (a dir or a single file), sorted."""
    try:
        out = subprocess.run(
            ["git", "-C", str(ROOT), "ls-files", "--", str(prefix)],
            capture_output=True,
            text=True,
            check=True,
        ).stdout
    except subprocess.CalledProcessError as err:
        raise MirrorError(f"git ls-files failed for {prefix}: {err}") from err
    files = sorted(
        ROOT / line
        for line in out.splitlines()
        if line.strip() and "__pycache__" not in Path(line).parts
    )
    return files


def _pairs(source_dir: Path, mirror_dir: Path) -> dict[Path, Path]:
    """Map each tracked source file to its expected mirror path."""
    if source_dir.is_dir():
        return {
            src: mirror_dir / src.relative_to(source_dir)
            for src in _git_files(source_dir)
        }
    return dict.fromkeys(_git_files(source_dir), mirror_dir)


def _same_mode(a: Path, b: Path) -> bool:
    return stat.S_IMODE(a.stat().st_mode) == stat.S_IMODE(b.stat().st_mode)


def _describe(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def check() -> int:
    """Verify every mirror; print DRIFT/MISSING/EXTRA per mismatch."""
    problems = 0
    for source_dir, mirror_dir, excluded in MIRRORS:
        source_dir, mirror_dir = ROOT / source_dir, ROOT / mirror_dir
        pairs = _pairs(source_dir, mirror_dir)
        excluded_paths = {Path(rel) for rel in excluded}
        expected_mirror_files = {
            dst
            for src, dst in pairs.items()
            if src.relative_to(source_dir) not in excluded_paths
        }
        for src, dst in sorted(pairs.items()):
            if src.relative_to(source_dir) in excluded_paths:
                for side in (src, dst):
                    if not side.exists():
                        print(f"MISSING {_describe(side)}")
                        problems += 1
                continue
            if not dst.exists():
                print(f"MISSING {_describe(dst)}")
                problems += 1
            elif src.read_bytes() != dst.read_bytes() or not _same_mode(src, dst):
                print(f"DRIFT {_describe(dst)}")
                problems += 1
        for extra in sorted(
            set(_git_files(mirror_dir))
            - set(expected_mirror_files)
            - {mirror_dir / rel for rel in excluded_paths}
        ):
            print(f"EXTRA {_describe(extra)}")
            problems += 1
    if problems:
        return 1
    print("bundle mirrors in sync")
    return 0


def sync() -> int:
    """Copy every non-excluded source file byte-for-byte over its mirror."""
    for source_dir, mirror_dir, excluded in MIRRORS:
        source_dir, mirror_dir = ROOT / source_dir, ROOT / mirror_dir
        pairs = _pairs(source_dir, mirror_dir)
        excluded_paths = {Path(rel) for rel in excluded}
        expected = {
            dst
            for src, dst in pairs.items()
            if src.relative_to(source_dir) not in excluded_paths
        }
        for src, dst in sorted(pairs.items()):
            if src.relative_to(source_dir) in excluded_paths:
                continue
            dst.parent.mkdir(parents=True, exist_ok=True)
            if (
                not dst.exists()
                or src.read_bytes() != dst.read_bytes()
                or not _same_mode(src, dst)
            ):
                shutil.copy2(src, dst)
                print(f"synced {_describe(dst)}")
        for extra in sorted(
            set(_git_files(mirror_dir))
            - expected
            - {mirror_dir / rel for rel in excluded_paths}
        ):
            extra.unlink()
            print(f"removed {_describe(extra)}")
    print("bundle mirrors synced")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="verify without writing")
    args = parser.parse_args(argv)
    try:
        return check() if args.check else sync()
    except MirrorError as err:
        print(f"sync_bundle_mirrors.py: {err}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

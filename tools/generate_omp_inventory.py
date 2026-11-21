#!/usr/bin/env python3
"""Mirror the dependency-free OMP reader into the portable reconcile skill."""

from __future__ import annotations

import argparse
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = Path("src/manifest_agent/omp_readonly")
TARGET = Path(
    "plugins/manifest-workspace/skills/deploy-reconcile/scripts/_omp_readonly"
)


def mirror(root: Path, *, check: bool) -> list[str]:
    """Copy exact source bytes, or report drift without writing."""
    drift = []
    sources = {path.name: path for path in (root / SOURCE).glob("*.py")}
    target = root / TARGET
    for name, source in sorted(sources.items()):
        destination = target / name
        contents = source.read_bytes()
        if not destination.is_file() or destination.read_bytes() != contents:
            drift.append(str(TARGET / name))
            if not check:
                target.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(contents)
    drift.extend(
        str(path.relative_to(root))
        for path in target.glob("*.py")
        if path.name not in sources
    )
    return drift


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    drift = mirror(ROOT, check=args.check)
    for path in drift:
        print(path)
    return int(args.check and bool(drift))


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Generate ADHD guidance files from the canonical skill."""

from __future__ import annotations

import argparse
import os
import tempfile
from pathlib import Path

BUNDLE_PATH = Path("plugins/manifest-i-have-adhd")
SKILL_PATH = Path("skills/i-have-adhd/SKILL.md")
GENERATED_PATHS = (
    Path("guidance/always-on.md"),
    Path("devin/global-rule.md"),
)


class GenerationError(RuntimeError):
    """The canonical skill cannot be rendered into its guidance files."""


def _write_atomic(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _guidance(skill: bytes) -> bytes:
    text = skill.decode("utf-8")
    if text.startswith("---\n"):
        end = text.find("\n---\n", 4)
        if end < 0:
            raise GenerationError("skill has unterminated frontmatter")
        text = text[end + 5 :]
    return text.lstrip().encode("utf-8")


def generated_files(bundle: Path) -> dict[Path, bytes]:
    try:
        skill = (bundle / SKILL_PATH).read_bytes()
    except OSError as error:
        raise GenerationError(
            f"unable to read canonical skill: {SKILL_PATH}"
        ) from error
    guidance = _guidance(skill)
    return dict.fromkeys(GENERATED_PATHS, guidance)


def drifted_files(bundle: Path) -> tuple[Path, ...]:
    return tuple(
        path
        for path, expected in generated_files(bundle).items()
        if not (target := bundle / path).is_file() or target.read_bytes() != expected
    )


def generate(bundle: Path) -> tuple[Path, ...]:
    drifted = drifted_files(bundle)
    expected = generated_files(bundle)
    for path in drifted:
        _write_atomic(bundle / path, expected[path])
    return drifted


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", type=Path, default=BUNDLE_PATH)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    try:
        drifted = drifted_files(args.bundle) if args.check else generate(args.bundle)
    except GenerationError as error:
        print(f"sync_i_have_adhd.py: {error}")
        return 2
    for path in drifted:
        print(path)
    return int(args.check and bool(drifted))


if __name__ == "__main__":
    raise SystemExit(main())

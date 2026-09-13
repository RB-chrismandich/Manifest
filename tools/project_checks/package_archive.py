"""Validate that the release inputs form a readable self-contained archive."""

from __future__ import annotations

import argparse
import os
import subprocess
import tarfile
import tempfile
from pathlib import Path

PASS = 0
FAIL = 2
BLOCKED = 3
REQUIRED = ("pyproject.toml", "src", "configs", "plugins", "bootstrap", "bootstrap.sh")


def validate_archive(root: Path) -> tuple[int, str]:
    """Build and inspect a temporary archive without mutating the candidate."""
    try:
        resolved = root.resolve(strict=True)
    except OSError as error:
        return BLOCKED, f"candidate root unavailable: {error}"
    missing = [name for name in REQUIRED if not (resolved / name).exists()]
    if missing:
        return BLOCKED, "required package inputs unavailable: " + ", ".join(missing)
    try:
        with tempfile.TemporaryDirectory(prefix="manifest-package-") as temporary:
            temporary_root = Path(temporary)
            archive = temporary_root / "manifest.tar.gz"
            with tarfile.open(archive, "w:gz") as handle:
                for name in REQUIRED:
                    handle.add(resolved / name, arcname=name, recursive=True)
            extracted = temporary_root / "extracted"
            with tarfile.open(archive, "r:gz") as handle:
                roots = {member.name.split("/", 1)[0] for member in handle.getmembers()}
                handle.extractall(extracted, filter="data")
            completed = subprocess.run(
                ["bash", str(extracted / "bootstrap.sh"), "--help"],
                cwd=extracted,
                env={**os.environ, "HOME": str(temporary_root / "home")},
                capture_output=True,
                text=True,
                timeout=30,
            )
    except (OSError, tarfile.TarError) as error:
        return FAIL, f"package archive validation failed: {error}"
    absent = sorted(set(REQUIRED) - roots)
    if absent:
        return FAIL, "package archive omitted required roots: " + ", ".join(absent)
    if completed.returncode:
        return FAIL, "packaged bootstrap --help failed: " + (
            completed.stderr or completed.stdout
        )[-1024:]
    return PASS, ""


def main(argv: list[str] | None = None) -> int:
    """Return PASS only when every required package root survives archiving."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True, type=Path)
    arguments = parser.parse_args(argv)
    status, diagnostic = validate_archive(arguments.root)
    if diagnostic:
        print(("BLOCKED" if status == BLOCKED else "FAIL") + ": " + diagnostic)
    return status


if __name__ == "__main__":
    raise SystemExit(main())

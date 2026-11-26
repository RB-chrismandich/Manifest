"""Shared Git fixtures for release identity and recovery tests."""

from __future__ import annotations

import subprocess
from pathlib import Path


def _git(repo: Path, *args: str) -> str:
    completed = subprocess.run(
        ("git", "-C", str(repo), *args),
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def _local_checkout(tmp_path: Path) -> Path:
    repo = tmp_path / "checkout"
    repo.mkdir()
    (repo / "tools").mkdir()
    (repo / "plugins").mkdir()
    (repo / "plugins" / "bundle.txt").write_text("portable\n", encoding="utf-8")
    (repo / "tools" / "generate_plugin_views.py").write_text(
        "import sys\n"
        "from pathlib import Path\n"
        "root = Path(sys.argv[sys.argv.index('--repo-root') + 1])\n"
        "expected = Path(__file__).resolve().parents[1]\n"
        "raise SystemExit(0 if '--check' in sys.argv and root == expected else 2)\n",
        encoding="utf-8",
    )
    _git(repo, "init")
    _git(repo, "config", "user.email", "manifest@example.invalid")
    _git(repo, "config", "user.name", "Manifest Test")
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "fixture")
    return repo

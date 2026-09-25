"""Tests for tools/sync_bundle_mirrors.py (F-17)."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from tools import sync_bundle_mirrors as sbm


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)


@pytest.fixture
def mirror_repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A git-init'd tmp repo with a mirrored and an excluded source file."""
    repo = tmp_path / "repo"
    source = repo / "src/pkg"
    mirror = repo / "bundle/pkg"
    source.mkdir(parents=True)
    mirror.mkdir(parents=True)
    (source / "shared.py").write_bytes(b"shared = 1\n")
    (source / "excluded.py").write_bytes(b"reason docstring\n")
    (mirror / "shared.py").write_bytes(b"shared = 1\n")
    (mirror / "excluded.py").write_bytes(b"different but allowed\n")
    _git(repo, "init", "-q")
    _git(repo, "add", "-A")
    monkeypatch.setattr(sbm, "ROOT", repo)
    monkeypatch.setattr(
        sbm,
        "MIRRORS",
        (("src/pkg", "bundle/pkg", {"excluded.py": "bundle rewrites the header"}),),
    )
    return repo


def test_check_passes_when_pair_is_in_sync(mirror_repo: Path, capsys) -> None:
    assert sbm.main(["--check"]) == 0
    assert "bundle mirrors in sync" in capsys.readouterr().out


def test_check_reports_drift(mirror_repo: Path, capsys) -> None:
    target = mirror_repo / "bundle/pkg/shared.py"
    target.write_bytes(b"shared = 2\n")
    assert sbm.main(["--check"]) == 1
    assert f"DRIFT {target.relative_to(mirror_repo)}" in capsys.readouterr().out


def test_check_ignores_excluded_drift(mirror_repo: Path) -> None:
    (mirror_repo / "bundle/pkg/excluded.py").write_bytes(b"bundle-local\n")
    assert sbm.main(["--check"]) == 0


def test_check_flags_missing_excluded(
    mirror_repo: Path, capsys, monkeypatch: pytest.MonkeyPatch
) -> None:
    (mirror_repo / "bundle/pkg/excluded.py").unlink()
    assert sbm.main(["--check"]) == 1
    assert "MISSING" in capsys.readouterr().out


def test_default_mode_restores_sync(mirror_repo: Path) -> None:
    target = mirror_repo / "bundle/pkg/shared.py"
    target.write_bytes(b"corrupted\n")
    assert sbm.main([]) == 0
    assert target.read_bytes() == (mirror_repo / "src/pkg/shared.py").read_bytes()
    assert sbm.main(["--check"]) == 0


def test_real_repo_mirrors_are_in_sync(capsys) -> None:
    assert sbm.main(["--check"]) == 0
    assert "bundle mirrors in sync" in capsys.readouterr().out

"""Shared filesystem fixtures for isolated Stitch bundle tests."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest


@pytest.fixture
def repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


@pytest.fixture
def stitch_bundle(repo_root: Path, tmp_path: Path) -> Path:
    installed = tmp_path / "stitch-design"
    shutil.copytree(
        repo_root / "plugins/stitch-design",
        installed,
        ignore=shutil.ignore_patterns("node_modules"),
    )
    return installed

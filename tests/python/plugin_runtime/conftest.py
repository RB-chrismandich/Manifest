"""Fixtures shared by plugin-runtime tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.python.plugin_runtime.omp_portable_support import build_portable
from tests.python.plugin_runtime.stitch_runtime_support import repo_root, stitch_bundle

__all__ = ["portable", "repo_root", "stitch_bundle"]


@pytest.fixture
def portable(tmp_path: Path):
    return build_portable(tmp_path)

"""Portable OMP source and mirror contract."""

from __future__ import annotations

import importlib.util

from tests.python.plugin_runtime.omp_portable_support import ROOT


def test_portable_mirror_is_exact_and_checked():
    spec = importlib.util.spec_from_file_location(
        "omp_mirror", ROOT / "tools/generate_omp_inventory.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.mirror(ROOT, check=True) == []

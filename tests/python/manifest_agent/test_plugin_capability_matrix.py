"""Generated capability-matrix release evidence."""

from __future__ import annotations

import importlib.util
from pathlib import Path


def _renderer_module():
    root = Path(__file__).resolve().parents[3]
    spec = importlib.util.spec_from_file_location(
        "render_plugin_capability_matrix", root / "tools/render_plugin_capability_matrix.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_matrix_has_an_explicit_state_for_every_harness_cell() -> None:
    renderer = _renderer_module()
    root = Path(__file__).resolve().parents[3]
    inspection = renderer._load_inspection(
        root / "tests/fixtures/plugin_capability_inspection.json"
    )
    rendered = renderer.render(inspection)

    lines = [line for line in rendered.splitlines() if line.startswith("|")][2:]
    assert lines
    assert all(line.count("|") == 9 for line in lines)
    assert "|  |" not in rendered
    assert all(
        state in rendered for state in ("READY", "DEGRADED(", "N/A(")
    )


def test_matrix_checked_in_rendering_is_current() -> None:
    renderer = _renderer_module()
    root = Path(__file__).resolve().parents[3]
    inspection = renderer._load_inspection(
        root / "tests/fixtures/plugin_capability_inspection.json"
    )

    assert (root / "docs/PLUGIN_CAPABILITY_MATRIX.md").read_text(
        encoding="utf-8"
    ) == renderer.render(inspection)


def test_matrix_without_inspection_is_explicitly_blocked() -> None:
    renderer = _renderer_module()

    assert "BLOCKED(adapter inspection missing)" in renderer.render()

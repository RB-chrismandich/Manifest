"""Generated capability-matrix release evidence."""

from __future__ import annotations

import copy
import importlib.util
import json
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


def test_matrix_blocks_ready_harness_without_matching_plugin_component_or_capability(
    tmp_path: Path,
) -> None:
    renderer = _renderer_module()
    root = Path(__file__).resolve().parents[3]
    inspection = renderer._load_inspection(
        root / "tests/fixtures/plugin_capability_inspection.json"
    )
    assert inspection is not None
    missing = copy.deepcopy(inspection)
    claude = missing["harnesses"]["claude"]
    claude["installed_plugin_ids"].remove("manifest-docs")
    claude["components"]["manifest-code-quality"].remove("skill:ai-code-audit")
    claude["capabilities"]["manifest-code-quality"].remove("executable:git")

    rendered = renderer.render(missing)

    assert "BLOCKED(plugin 'manifest-docs' is not installed)" in rendered
    assert "BLOCKED(components evidence missing manifest-code-quality:skill:ai-code-audit)" in rendered
    assert "BLOCKED(capabilities evidence missing manifest-code-quality:executable:git)" in rendered
    evidence_path = tmp_path / "inspection.json"
    evidence_path.write_text(json.dumps(missing), encoding="utf-8")
    assert renderer.main(["--check", "--inspection", str(evidence_path)]) == 2

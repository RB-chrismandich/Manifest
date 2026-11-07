"""Generated capability-matrix release evidence."""

from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path
from typing import Any


def _renderer_module():
    root = Path(__file__).resolve().parents[3]
    spec = importlib.util.spec_from_file_location(
        "render_plugin_capability_matrix",
        root / "tools/render_plugin_capability_matrix.py",
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
    assert all(line.count("|") == 10 for line in lines)
    assert "|  |" not in rendered
    assert all(state in rendered for state in ("READY", "DEGRADED(", "N/A("))
    for line in lines:
        omp_cell = line.split("|")[-2].strip()
        assert omp_cell.startswith("UNVERIFIED(")
        assert "READY" not in omp_cell
    for identity in ("skill:i-have-adhd", "executable:python3"):
        row = next(
            line for line in lines if f"`manifest-i-have-adhd:{identity}`" in line
        )
        assert row.count("READY") == 6
        assert "N/A(" not in row
    for identity in (
        "hook:adhd-session-start",
        "guidance:adhd-always-on-guidance",
        "runtime:adhd-hook-runtime",
    ):
        row = next(
            line for line in lines if f"`manifest-i-have-adhd:{identity}`" in line
        )
        assert row.count("READY") == 6
        assert "BLOCKED(" not in row

    for identity in (
        "hook:codex-session-start",
        "hook:codex-stop",
        "hook:codex-permission-request",
    ):
        row = next(line for line in lines if f"`manifest-workspace:{identity}`" in line)
        assert row.count("READY") == 1
        assert row.count("N/A(") == 5


def test_omp_cells_reflect_declarations_but_ignore_ready_looking_inspection() -> None:
    renderer = _renderer_module()
    root = Path(__file__).resolve().parents[3]
    inspection = renderer._load_inspection(
        root / "tests/fixtures/plugin_capability_inspection.json"
    )
    assert inspection is not None
    fabricated_omp = copy.deepcopy(inspection)
    fabricated_omp["harnesses"]["omp"] = {
        "state": "READY",
        "version": "injected",
        "verified": True,
        "installed_plugin_ids": ["manifest-code-quality"],
        "components": {"manifest-code-quality": ["skill:ai-code-audit"]},
        "capabilities": {"manifest-code-quality": ["executable:git"]},
    }
    rendered = renderer.render(fabricated_omp)
    lines = [line for line in rendered.splitlines() if line.startswith("|")][2:]

    def cell(identity: str) -> str:
        row = next(line for line in lines if f"`{identity}`" in line)
        return row.split("|")[-2].strip()

    assert cell("manifest-code-quality:skill:ai-code-audit") == (
        "UNVERIFIED(declared=native; OMP native qualification not recorded)"
    )
    assert cell("manifest-ops:hook:version-pin").startswith(
        "UNVERIFIED(declared=degraded; reason=The related on-demand skill"
    )
    assert cell("manifest-workspace:agent:explore").startswith(
        "UNVERIFIED(declared=unsupported; reason=These bundle-local role prompts"
    )
    assert cell("manifest-workspace:hook:claude-compaction-continuity").startswith(
        "UNVERIFIED(declared=not_applicable; reason=This component records"
    )
    assert cell("manifest-workspace:runtime:env-check-scripts").startswith(
        "UNVERIFIED(declared=degraded; reason=OMP manifest-health requires"
    )
    assert cell("manifest-i-have-adhd:hook:adhd-session-start").startswith(
        "UNVERIFIED(declared=unsupported; reason=ADHD always-on activation"
    )
    assert cell("stitch-design:agent:ui-builder").startswith(
        "UNVERIFIED(declared=native; OMP native qualification not recorded)"
    )
    assert cell("manifest-code-quality:executable:browser-use").startswith(
        "UNVERIFIED(optional capability not selected; declared=native;"
    )
    assert all(line.split("|")[-2].strip().startswith("UNVERIFIED(") for line in lines)


def _component_only_contracts(renderer: Any) -> tuple[Any, ...]:
    from dataclasses import replace

    from manifest_agent.contracts import CompatibilityStatus

    contracts = []
    plugin_root = Path(__file__).resolve().parents[3] / "plugins"
    for contract in renderer.load_domain_contracts(plugin_root):
        bundle_compatibility = {
            key: status
            for key, status in contract.compatibility.items()
            if key != "omp"
        }
        component_lists = {}
        for kind in ("agents", "hooks", "runtime", "guidance"):
            converted = []
            for component in getattr(contract.components, kind):
                compatibility = (
                    {
                        key: status
                        for key, status in component.compatibility.items()
                        if key != "omp"
                    }
                    if component.compatibility is not None
                    else None
                )
                if (
                    contract.name == "manifest-docs"
                    and kind == "runtime"
                    and component.id == "docs-lint"
                ):
                    compatibility = {
                        **dict(contract.compatibility),
                        "omp": CompatibilityStatus(
                            mode="degraded",
                            reason="matrix component-only source limitation",
                        ),
                    }
                converted.append(
                    replace(component, compatibility=compatibility)
                    if compatibility is not None
                    else component
                )
            component_lists[kind] = tuple(converted)
        contracts.append(
            replace(
                contract,
                components=replace(contract.components, **component_lists),
                compatibility=bundle_compatibility,
            )
        )
    return tuple(contracts)


def test_matrix_preserves_component_only_and_undeclared_omp_cells(
    monkeypatch,
) -> None:
    renderer = _renderer_module()
    root = Path(__file__).resolve().parents[3]
    contracts = _component_only_contracts(renderer)

    monkeypatch.setattr(
        renderer, "load_domain_contracts", lambda _root: tuple(contracts)
    )
    monkeypatch.setattr(renderer, "load_addon_contracts", lambda _root: ())
    inspection = renderer._load_inspection(
        root / "tests/fixtures/plugin_capability_inspection.json"
    )
    rendered = renderer.render(inspection)
    lines = [line for line in rendered.splitlines() if line.startswith("|")][2:]

    def cell(identity: str) -> str:
        row = next(line for line in lines if f"`{identity}`" in line)
        return row.split("|")[-2].strip()

    assert cell("manifest-docs:skill:docs-all") == (
        "UNVERIFIED(undeclared; OMP native qualification not recorded)"
    )
    assert cell("manifest-docs:runtime:docs-lint") == (
        "UNVERIFIED(declared=degraded; reason=matrix component-only source limitation; "
        "OMP native qualification not recorded)"
    )
    assert cell("manifest-docs:runtime:docs-references") == (
        "UNVERIFIED(undeclared; OMP native qualification not recorded)"
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


def test_check_success_discloses_omp_is_unverified_and_excluded(
    capsys,
) -> None:
    renderer = _renderer_module()
    root = Path(__file__).resolve().parents[3]
    inspection_path = root / "tests/fixtures/plugin_capability_inspection.json"

    assert renderer.main(["--check", "--inspection", str(inspection_path)]) == 0
    assert (
        "OMP coverage is UNVERIFIED and excluded from this six-harness qualification."
        in capsys.readouterr().out
    )


def test_synthetic_fixture_evidence_is_not_rendered_as_live_native_inspection() -> None:
    renderer = _renderer_module()
    root = Path(__file__).resolve().parents[3]
    inspection = renderer._load_inspection(
        root / "tests/fixtures/plugin_capability_inspection.json"
    )

    assert inspection is not None
    assert inspection["provenance"] == "synthetic-fixture"
    rendered = renderer.render(inspection)
    assert "synthetic fixture evidence; not live native inspection" in rendered


def test_matrix_without_inspection_is_explicitly_blocked() -> None:
    renderer = _renderer_module()

    rendered = renderer.render()

    assert "no native adapter inspection evidence" in rendered
    assert "verified native adapter inspection evidence" not in rendered
    assert "BLOCKED(adapter inspection missing)" in rendered


def test_ready_contract_names_all_enforced_evidence_predicates() -> None:
    renderer = _renderer_module()

    rendered = renderer.render()

    assert (
        "`READY` requires a verified native harness state and non-empty native version,"
        in rendered
    )
    assert "matching installed plugin, component, and capability evidence." in rendered


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
    assert (
        "BLOCKED(components evidence missing manifest-code-quality:skill:ai-code-audit)"
        in rendered
    )
    assert (
        "BLOCKED(capabilities evidence missing manifest-code-quality:executable:git)"
        in rendered
    )
    evidence_path = tmp_path / "inspection.json"
    evidence_path.write_text(json.dumps(missing), encoding="utf-8")
    assert renderer.main(["--check", "--inspection", str(evidence_path)]) == 2


def test_matrix_check_ignores_blocked_text_in_omp_reason(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    renderer = _renderer_module()
    root = Path(__file__).resolve().parents[3]
    inspection_path = root / "tests/fixtures/plugin_capability_inspection.json"
    inspection = renderer._load_inspection(inspection_path)
    rows = [
        (
            "fixture:skill:example",
            "contract skill",
            ["READY"] * 6
            + [
                "UNVERIFIED(declared=degraded; reason=literal BLOCKED( from OMP; "
                "OMP native qualification not recorded)"
            ],
        )
    ]
    target = tmp_path / "docs/PLUGIN_CAPABILITY_MATRIX.md"
    target.parent.mkdir(parents=True)
    target.write_text(renderer._render_rows(inspection, rows), encoding="utf-8")
    monkeypatch.setattr(renderer, "ROOT", tmp_path)
    monkeypatch.setattr(renderer, "_rows", lambda _inspection: rows)

    assert renderer.main(["--check", "--inspection", str(inspection_path)]) == 0
    assert (
        "OMP coverage is UNVERIFIED and excluded from this six-harness qualification."
        in capsys.readouterr().out
    )

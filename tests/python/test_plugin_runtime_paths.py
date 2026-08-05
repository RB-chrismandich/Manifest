"""Release gates for bundle-local runtime dependencies."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


def _checker_module():
    root = Path(__file__).resolve().parents[2]
    spec = importlib.util.spec_from_file_location(
        "check_plugin_runtime_paths", root / "tools/check_plugin_runtime_paths.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_runtime_path_gate_accepts_checked_in_domain_bundles() -> None:
    checker = _checker_module()
    root = Path(__file__).resolve().parents[2]

    report = checker.scan(root)

    assert report.violations == ()
    assert tuple(name for name, _path, _document in checker._contract_files(root)) == (
        "manifest-code-quality",
        "manifest-docs",
        "manifest-forge",
        "manifest-ops",
        "manifest-security",
        "manifest-spec-planning",
        "manifest-workspace",
        "stitch-design",
    )


def test_runtime_path_gate_reports_forbidden_instruction_dependency(tmp_path: Path) -> None:
    checker = _checker_module()
    bundle = tmp_path / "plugins/manifest-docs"
    (bundle / "skills/demo").mkdir(parents=True)
    (bundle / "skills/demo/SKILL.md").write_text(
        "---\nname: demo\ndescription: demo\n---\nRun bootstrap.sh now.\n",
        encoding="utf-8",
    )
    (bundle / "manifest-capabilities.yml").write_text(
        "schema_version: 1\nbundle: {name: manifest-docs, version: 0.1.0, description: x, category: x}\n"
        "components: {skills: {root: skills, include: ['*/SKILL.md']}, agents: [], hooks: [], runtime: [], guidance: []}\n"
        "capabilities: {mcp: {required: [], default: [], optional: []}, executables: {required: [], default: [], optional: []}}\n"
        "compatibility: {claude: {mode: native}, codex: {mode: native}, gemini: {mode: generated}, cursor: {mode: generated}, antigravity: {mode: imported}, devin: {mode: native}}\n"
        "provenance: {repository: x, license: MIT, license_file: LICENSE, generated_by: x}\n",
        encoding="utf-8",
    )

    report = checker.scan(tmp_path)

    assert any(
        violation.path.name == "SKILL.md" and violation.kind == "forbidden-runtime-path"
        for violation in report.violations
    )


def test_runtime_path_gate_reports_undeclared_python_runtime_dependency(
    tmp_path: Path,
) -> None:
    checker = _checker_module()
    bundle = tmp_path / "plugins/manifest-docs"
    (bundle / "runtime").mkdir(parents=True)
    (bundle / "runtime/runner.py").write_text("import requests\n", encoding="utf-8")
    (bundle / "manifest-capabilities.yml").write_text(
        "schema_version: 1\nbundle: {name: manifest-docs, version: 0.1.0, description: x, category: x}\n"
        "components: {skills: {root: skills, include: ['*/SKILL.md']}, agents: [], hooks: [], runtime: [{id: runner, path: runtime/runner.py}], guidance: []}\n"
        "capabilities: {mcp: {required: [], default: [], optional: []}, executables: {required: [], default: [], optional: []}}\n"
        "compatibility: {claude: {mode: native}, codex: {mode: native}, gemini: {mode: generated}, cursor: {mode: generated}, antigravity: {mode: imported}, devin: {mode: native}}\n"
        "provenance: {repository: x, license: MIT, license_file: LICENSE, generated_by: x}\n",
        encoding="utf-8",
    )

    report = checker.scan(tmp_path)

    assert any(
        violation.kind == "undeclared-python-dependency" and violation.value == "requests"
        for violation in report.violations
    )


def test_runtime_path_gate_reports_direct_undeclared_shell_command(
    tmp_path: Path,
) -> None:
    checker = _checker_module()
    bundle = tmp_path / "plugins/manifest-docs"
    (bundle / "runtime").mkdir(parents=True)
    (bundle / "runtime/runner.sh").write_text("curl https://example.invalid\n", encoding="utf-8")
    (bundle / "manifest-capabilities.yml").write_text(
        "schema_version: 1\nbundle: {name: manifest-docs, version: 0.1.0, description: x, category: x}\n"
        "components: {skills: {root: skills, include: ['*/SKILL.md']}, agents: [], hooks: [], runtime: [{id: runner, path: runtime/runner.sh}], guidance: []}\n"
        "capabilities: {mcp: {required: [], default: [], optional: []}, executables: {required: [], default: [], optional: []}}\n"
        "compatibility: {claude: {mode: native}, codex: {mode: native}, gemini: {mode: generated}, cursor: {mode: generated}, antigravity: {mode: imported}, devin: {mode: native}}\n"
        "provenance: {repository: x, license: MIT, license_file: LICENSE, generated_by: x}\n",
        encoding="utf-8",
    )

    report = checker.scan(tmp_path)

    assert any(
        violation.kind == "undeclared-shell-dependency" and violation.value == "curl"
        for violation in report.violations
    )


def test_runtime_path_gate_rejects_unknown_direct_shell_command(tmp_path: Path) -> None:
    checker = _checker_module()
    bundle = tmp_path / "plugins/manifest-docs"
    (bundle / "runtime").mkdir(parents=True)
    (bundle / "runtime/runner.sh").write_text(
        "future-tool --offline\n", encoding="utf-8"
    )
    (bundle / "manifest-capabilities.yml").write_text(
        "schema_version: 1\nbundle: {name: manifest-docs, version: 0.1.0, description: x, category: x}\n"
        "components: {skills: {root: skills, include: ['*/SKILL.md']}, agents: [], hooks: [], runtime: [{id: runner, path: runtime/runner.sh}], guidance: []}\n"
        "capabilities: {mcp: {required: [], default: [], optional: []}, executables: {required: [], default: [], optional: []}}\n"
        "compatibility: {claude: {mode: native}, codex: {mode: native}, gemini: {mode: generated}, cursor: {mode: generated}, antigravity: {mode: imported}, devin: {mode: native}}\n"
        "provenance: {repository: x, license: MIT, license_file: LICENSE, generated_by: x}\n",
        encoding="utf-8",
    )

    report = checker.scan(tmp_path)

    assert any(
        violation.kind == "undeclared-shell-dependency"
        and violation.value == "future-tool"
        for violation in report.violations
    )


def test_runtime_path_gate_ignores_embedded_python_and_dynamic_command(tmp_path: Path) -> None:
    checker = _checker_module()
    bundle = tmp_path / "plugins/manifest-docs"
    (bundle / "runtime").mkdir(parents=True)
    (bundle / "runtime/runner.sh").write_text(
        "runner=\"$(command -v python3)\"\n"
        "\"$runner\" -c '\n"
        "import json\n"
        "print(json.dumps({\"command\": \"future-tool\"}))\n"
        "'\n",
        encoding="utf-8",
    )
    (bundle / "manifest-capabilities.yml").write_text(
        "schema_version: 1\nbundle: {name: manifest-docs, version: 0.1.0, description: x, category: x}\n"
        "components: {skills: {root: skills, include: ['*/SKILL.md']}, agents: [], hooks: [], runtime: [{id: runner, path: runtime/runner.sh}], guidance: []}\n"
        "capabilities: {mcp: {required: [], default: [], optional: []}, executables: {required: [python3], default: [], optional: []}}\n"
        "compatibility: {claude: {mode: native}, codex: {mode: native}, gemini: {mode: generated}, cursor: {mode: generated}, antigravity: {mode: imported}, devin: {mode: native}}\n"
        "provenance: {repository: x, license: MIT, license_file: LICENSE, generated_by: x}\n",
        encoding="utf-8",
    )

    report = checker.scan(tmp_path)

    assert not any(violation.path.name == "runner.sh" for violation in report.violations)

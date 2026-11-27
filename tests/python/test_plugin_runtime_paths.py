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


def test_runtime_path_gate_accepts_checked_in_portable_bundles() -> None:
    """Every portable bundle is scanned, addons included.

    Addon bundles ship with generated native views just as domain bundles do,
    so scanning only the domain set left an addon exempt from the
    ungoverned-bundle flag yet passed through no scan at all.
    """
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
        "manifest-i-have-adhd",
    )


def test_runtime_path_gate_ignores_evaluation_fixtures(tmp_path: Path) -> None:
    """Eval prompts describe failure modes; they are not installed runtime."""
    checker = _checker_module()
    bundle = tmp_path / "plugins/manifest-docs"
    prompt = bundle / "evals/case/prompt.md"
    nested_prompt = bundle / "skills/demo/evals/prompt.md"
    prompt.parent.mkdir(parents=True)
    nested_prompt.parent.mkdir(parents=True)
    prompt.write_text("Run bootstrap.sh now.\n")
    nested_prompt.write_text("Run bootstrap.sh now.\n")
    (bundle / "manifest-capabilities.yml").write_text(
        "schema_version: 1\nbundle: {name: manifest-docs, version: 0.1.0}\n"
        "components: {skills: {root: skills}, agents: [], hooks: [], runtime: [], guidance: []}\n",
        encoding="utf-8",
    )

    violations = checker.scan(tmp_path).violations
    assert not [violation for violation in violations if violation.path == prompt]
    assert any(
        violation.path == nested_prompt and violation.kind == "forbidden-runtime-path"
        for violation in violations
    )


def test_runtime_path_gate_reports_forbidden_instruction_dependency(
    tmp_path: Path,
) -> None:
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
        "compatibility: {claude: {mode: native}, codex: {mode: native}, cursor: {mode: generated}, antigravity: {mode: imported}, devin: {mode: native}}\n"
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
        "compatibility: {claude: {mode: native}, codex: {mode: native}, cursor: {mode: generated}, antigravity: {mode: imported}, devin: {mode: native}}\n"
        "provenance: {repository: x, license: MIT, license_file: LICENSE, generated_by: x}\n",
        encoding="utf-8",
    )

    report = checker.scan(tmp_path)

    assert any(
        violation.kind == "undeclared-python-dependency"
        and violation.value == "requests"
        for violation in report.violations
    )


def test_runtime_path_gate_reports_direct_undeclared_shell_command(
    tmp_path: Path,
) -> None:
    checker = _checker_module()
    bundle = tmp_path / "plugins/manifest-docs"
    (bundle / "runtime").mkdir(parents=True)
    (bundle / "runtime/runner.sh").write_text(
        "curl https://example.invalid\n", encoding="utf-8"
    )
    (bundle / "manifest-capabilities.yml").write_text(
        "schema_version: 1\nbundle: {name: manifest-docs, version: 0.1.0, description: x, category: x}\n"
        "components: {skills: {root: skills, include: ['*/SKILL.md']}, agents: [], hooks: [], runtime: [{id: runner, path: runtime/runner.sh}], guidance: []}\n"
        "capabilities: {mcp: {required: [], default: [], optional: []}, executables: {required: [], default: [], optional: []}}\n"
        "compatibility: {claude: {mode: native}, codex: {mode: native}, cursor: {mode: generated}, antigravity: {mode: imported}, devin: {mode: native}}\n"
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
        "compatibility: {claude: {mode: native}, codex: {mode: native}, cursor: {mode: generated}, antigravity: {mode: imported}, devin: {mode: native}}\n"
        "provenance: {repository: x, license: MIT, license_file: LICENSE, generated_by: x}\n",
        encoding="utf-8",
    )

    report = checker.scan(tmp_path)

    assert any(
        violation.kind == "undeclared-shell-dependency"
        and violation.value == "future-tool"
        for violation in report.violations
    )


def test_runtime_path_gate_ignores_embedded_python_and_dynamic_command(
    tmp_path: Path,
) -> None:
    checker = _checker_module()
    bundle = tmp_path / "plugins/manifest-docs"
    (bundle / "runtime").mkdir(parents=True)
    (bundle / "runtime/runner.sh").write_text(
        'runner="$(command -v python3)"\n'
        '"$runner" -c \'\n'
        "import json\n"
        'print(json.dumps({"command": "future-tool"}))\n'
        "'\n",
        encoding="utf-8",
    )
    (bundle / "manifest-capabilities.yml").write_text(
        "schema_version: 1\nbundle: {name: manifest-docs, version: 0.1.0, description: x, category: x}\n"
        "components: {skills: {root: skills, include: ['*/SKILL.md']}, agents: [], hooks: [], runtime: [{id: runner, path: runtime/runner.sh}], guidance: []}\n"
        "capabilities: {mcp: {required: [], default: [], optional: []}, executables: {required: [python3], default: [], optional: []}}\n"
        "compatibility: {claude: {mode: native}, codex: {mode: native}, cursor: {mode: generated}, antigravity: {mode: imported}, devin: {mode: native}}\n"
        "provenance: {repository: x, license: MIT, license_file: LICENSE, generated_by: x}\n",
        encoding="utf-8",
    )

    report = checker.scan(tmp_path)

    assert not any(
        violation.path.name == "runner.sh" for violation in report.violations
    )


def test_unregistered_bundle_is_flagged_not_silently_skipped(tmp_path) -> None:
    """A bundle outside PORTABLE_BUNDLES must fail, never report clean.

    Coverage used to be opt-in: enumeration walked a hardcoded tuple, so a
    directory added under plugins/ was scanned by nothing and the gate returned
    an empty violation list regardless of its contents.
    """
    checker = _checker_module()
    (tmp_path / "plugins" / "manifest-unregistered").mkdir(parents=True)

    report = checker.scan(tmp_path)

    kinds = {violation.kind for violation in report.violations}
    assert "ungoverned-bundle" in kinds
    assert any(
        violation.value == "manifest-unregistered" for violation in report.violations
    )


def test_declared_ungoverned_bundle_is_accepted(tmp_path) -> None:
    """An exclusion recorded in UNGOVERNED_BUNDLES is declared, so it passes."""
    checker = _checker_module()
    (tmp_path / "plugins" / "manifest-delegate").mkdir(parents=True)

    report = checker.scan(tmp_path)

    assert not [v for v in report.violations if v.kind == "ungoverned-bundle"]


def test_legacy_path_in_undeclared_bundle_file_is_caught(tmp_path) -> None:
    """A shipped file at an undeclared path must still be scanned.

    The gate used to enumerate only declared components and SKILL.md, but the
    whole bundle directory is what gets installed. A helper dropped at an
    undeclared path therefore shipped and ran while reporting no violations.
    """
    checker = _checker_module()
    bundle = tmp_path / "plugins" / "manifest-forge"
    (bundle / "lib").mkdir(parents=True)
    (bundle / "manifest-capabilities.yml").write_text(
        "schema_version: 1\n"
        "bundle: {name: manifest-forge, version: 0.0.0}\n"
        "components: {skills: {root: skills}, agents: [], hooks: [], "
        "runtime: [], guidance: []}\n",
        encoding="utf-8",
    )
    (bundle / "lib" / "helper.sh").write_text(
        "#!/usr/bin/env bash\nsource ~/.claude/scripts/git_ops.sh\n", encoding="utf-8"
    )

    report = checker.scan(tmp_path)

    assert [v for v in report.violations if v.kind == "forbidden-runtime-path"], (
        "undeclared bundle file was not scanned for legacy shared-home paths"
    )


def test_undeclared_files_skip_dependency_conformance_checks(tmp_path) -> None:
    """Undeclared files are swept for legacy paths only.

    Dependency declarations are a contract-conformance concern, so running them
    over bundle tests and helper scripts would report undeclared imports for
    files that were never contract surfaces.
    """
    checker = _checker_module()
    bundle = tmp_path / "plugins" / "manifest-forge"
    (bundle / "tests").mkdir(parents=True)
    (bundle / "manifest-capabilities.yml").write_text(
        "schema_version: 1\n"
        "bundle: {name: manifest-forge, version: 0.0.0}\n"
        "components: {skills: {root: skills}, agents: [], hooks: [], "
        "runtime: [], guidance: []}\n",
        encoding="utf-8",
    )
    (bundle / "tests" / "test_thing.py").write_text(
        "import some_third_party_package\n", encoding="utf-8"
    )

    report = checker.scan(tmp_path)

    assert not [
        v for v in report.violations if v.kind == "undeclared-python-dependency"
    ]


def test_home_variable_spelling_is_caught(tmp_path) -> None:
    """`$HOME/.claude/...` must be caught, not just the tilde spelling.

    Pattern matching is literal substring, so the tilde forms do not cover the
    `$HOME` and `${HOME}` spellings. An adversarial probe walked straight
    through the gate with `source "$HOME/.claude/scripts/git_ops.sh"`.
    """
    checker = _checker_module()
    bundle = tmp_path / "plugins" / "manifest-forge"
    (bundle / "lib").mkdir(parents=True)
    (bundle / "manifest-capabilities.yml").write_text(
        "schema_version: 1\n"
        "bundle: {name: manifest-forge, version: 0.0.0}\n"
        "components: {skills: {root: skills}, agents: [], hooks: [], "
        "runtime: [], guidance: []}\n",
        encoding="utf-8",
    )
    (bundle / "lib" / "obf.sh").write_text(
        '#!/usr/bin/env bash\nsource "$HOME/.claude/scripts/git_ops.sh"\n'
        'cat "${HOME}/.claude/config/labels.yml"\n',
        encoding="utf-8",
    )

    report = checker.scan(tmp_path)

    values = {v.value for v in report.violations}
    assert any("scripts" in value for value in values)
    assert any("config" in value for value in values)


def test_addon_bundle_files_are_scanned_not_merely_exempted(tmp_path) -> None:
    """An addon must be scanned, not just skipped by the ungoverned-bundle flag.

    Listing a bundle in ADDON_BUNDLES silences the ungoverned flag for it. If
    the contract loop still walked only DOMAIN_BUNDLES, that silence would be
    the whole story: the bundle would ship its files to every harness while no
    scan ever read them.
    """
    checker = _checker_module()
    bundle = tmp_path / "plugins" / "manifest-i-have-adhd"
    bundle.mkdir(parents=True)
    (bundle / "manifest-capabilities.yml").write_text(
        "schema_version: 1\n"
        "bundle: {name: manifest-i-have-adhd, version: 0.0.0}\n"
        "components: {skills: {root: skills}, agents: [], hooks: [], "
        "runtime: [], guidance: []}\n",
        encoding="utf-8",
    )
    (bundle / "leak.sh").write_text(
        "#!/usr/bin/env bash\nsource ~/.claude/scripts/git_ops.sh\n", encoding="utf-8"
    )

    report = checker.scan(tmp_path)

    assert [v for v in report.violations if v.kind == "forbidden-runtime-path"], (
        "addon bundle was exempted from the ungoverned flag but never scanned"
    )


def test_observer_path_exception_requires_exact_line_and_occurrence(
    tmp_path: Path,
) -> None:
    """Audited path evidence is line-bound and cannot bless extra reuse."""
    import hashlib
    import json

    checker = _checker_module()
    relative = "plugins/manifest-workspace/runtime/observer/src/manifest_agent/data/__init__.py"
    path = tmp_path / relative
    source = tmp_path / "src/manifest_agent/data/__init__.py"
    line = '"""Package data used by manifest-agent at runtime."""'
    path.parent.mkdir(parents=True)
    source.parent.mkdir(parents=True)
    path.write_text(line + "\n", encoding="utf-8")
    source.write_text(line + "\n", encoding="utf-8")
    record = {
        "kind": "forbidden-runtime-path",
        "path": relative,
        "line": 1,
        "value": "manifest-agent",
        "source_line": line,
        "line_sha256": hashlib.sha256(line.encode()).hexdigest(),
        "source_sha256": hashlib.sha256((line + "\n").encode()).hexdigest(),
        "classification": "package docstring",
    }
    (tmp_path / "tools").mkdir()
    (tmp_path / "tools/observer_runtime_path_evidence.json").write_text(
        json.dumps([record]), encoding="utf-8"
    )

    assert checker._observer_path_exception(tmp_path, path, "manifest-agent", 1, line)
    assert not checker._observer_path_exception(
        tmp_path, path, "manifest-agent", 1, line + " manifest-agent"
    )
    path.write_text(
        '"""Changed context mentions manifest-agent."""\n', encoding="utf-8"
    )
    assert not checker._observer_path_exception(
        tmp_path,
        path,
        "manifest-agent",
        1,
        '"""Changed context mentions manifest-agent."""',
    )


def _copy_observer_contract_fixture(tmp_path: Path) -> Path:
    import shutil

    root = Path(__file__).resolve().parents[2]
    runtime = tmp_path / "plugins/manifest-workspace/runtime/observer"
    shutil.copytree(
        root / "plugins/manifest-workspace/runtime/observer",
        runtime,
        ignore=shutil.ignore_patterns(".venv", "__pycache__"),
    )
    for relative in (
        "tools/observer_locked_wheel_evidence.json",
        "configs/claude/scripts/manifest_model_policy",
        "src/manifest_agent",
    ):
        source = root / relative
        destination = tmp_path / relative
        if source.is_dir():
            shutil.copytree(source, destination)
        else:
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)
    return runtime


def test_observer_dependency_contract_rejects_stale_pins_and_unlisted_imports(
    tmp_path: Path,
) -> None:
    """Pins and hash-locked wheels are required; unrelated imports stay errors."""
    checker = _checker_module()
    runtime = _copy_observer_contract_fixture(tmp_path)

    assert checker._observer_dependency_contract(tmp_path) == {
        "click",
        "jsonschema",
        "yaml",
        "manifest_model_policy",
    }
    lock = runtime / "uv.lock"
    original_lock = lock.read_text(encoding="utf-8")
    lock.write_text(
        original_lock.replace(
            'name = "click"\nversion = "8.4.2"', 'name = "click"\nversion = "8.4.3"'
        ),
        encoding="utf-8",
    )
    assert checker._observer_dependency_contract(tmp_path) is None
    lock.write_text(original_lock, encoding="utf-8")

    project = runtime / "pyproject.toml"
    project.write_text(
        project.read_text(encoding="utf-8").replace("click==8.4.2", "click==8.4.3"),
        encoding="utf-8",
    )
    assert checker._observer_dependency_contract(tmp_path) is None

    report = checker._python_import_violations(
        runtime / "src/manifest_agent/unexpected.py",
        "import requests\n",
        "native-observer-runtime",
        checker._BundleScan(
            tmp_path,
            "manifest-workspace",
            runtime,
            set(),
            {"click", "jsonschema", "yaml", "manifest_model_policy"},
        ),
    )
    assert [(item.kind, item.value) for item in report] == [
        ("undeclared-python-dependency", "requests")
    ]

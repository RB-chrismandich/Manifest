"""Release gate: `agent:` frontmatter must be namespaced `plugin:agent`."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


def _checker_module():
    root = Path(__file__).resolve().parents[2]
    spec = importlib.util.spec_from_file_location(
        "check_agent_frontmatter", root / "tools/check_agent_frontmatter.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _write_skill(tmp_path: Path, bundle: str, name: str, frontmatter: str) -> Path:
    skill_dir = tmp_path / "plugins" / bundle / "skills" / name
    skill_dir.mkdir(parents=True)
    path = skill_dir / "SKILL.md"
    path.write_text(f"---\n{frontmatter}\n---\nBody.\n", encoding="utf-8")
    return path


def test_no_agent_field_is_not_a_violation(tmp_path: Path) -> None:
    """A skill that declares no `agent:` at all is untouched by the gate."""
    checker = _checker_module()
    _write_skill(tmp_path, "manifest-docs", "demo", "name: demo\ndescription: demo")

    report = checker.scan(tmp_path)

    assert report.violations == ()
    assert report.agent_field_users == ()


def test_bare_agent_name_is_a_violation(tmp_path: Path) -> None:
    """A bare name silently falls back to general-purpose with no error."""
    checker = _checker_module()
    path = _write_skill(
        tmp_path,
        "manifest-workspace",
        "orchestrate",
        "name: orchestrate\ndescription: demo\ncontext: fork\nagent: scout",
    )

    report = checker.scan(tmp_path)

    assert report.agent_field_users == (path,)
    assert len(report.violations) == 1
    assert report.violations[0].path == path
    assert "scout" in report.violations[0].message


def test_fully_qualified_agent_name_passes(tmp_path: Path) -> None:
    """`plugin:agent` is the namespaced form the gate exists to permit."""
    checker = _checker_module()
    path = _write_skill(
        tmp_path,
        "manifest-workspace",
        "orchestrate",
        "name: orchestrate\ndescription: demo\ncontext: fork\n"
        "agent: manifest-workspace:scout",
    )

    report = checker.scan(tmp_path)

    assert report.violations == ()
    assert report.agent_field_users == (path,)


def test_double_colon_agent_name_is_rejected(tmp_path: Path) -> None:
    """`a::b` is not a valid namespace and must not be mistaken for one."""
    checker = _checker_module()
    _write_skill(
        tmp_path,
        "manifest-workspace",
        "orchestrate",
        "name: orchestrate\ndescription: demo\ncontext: fork\n"
        "agent: manifest-workspace:scout:extra",
    )

    report = checker.scan(tmp_path)

    assert len(report.violations) == 1


def test_non_string_agent_value_is_rejected(tmp_path: Path) -> None:
    """A non-string `agent:` (list, mapping, number) is rejected, not coerced."""
    checker = _checker_module()
    _write_skill(
        tmp_path,
        "manifest-workspace",
        "orchestrate",
        "name: orchestrate\ndescription: demo\ncontext: fork\nagent: [scout]",
    )

    report = checker.scan(tmp_path)

    assert len(report.violations) == 1


def test_repository_skills_use_no_bare_agent_names(tmp_path: Path) -> None:
    """The live invariant the CI gate enforces: no skill may declare a BARE
    `agent:` value.

    Deliberately does NOT assert `agent_field_users == ()`. An earlier revision
    did, which made the suite fail the moment any skill adopted a correctly
    namespaced `plugin:agent` value -- i.e. it blocked the very usage the gate
    exists to permit, and would have been "fixed" by deleting the assertion
    rather than by reading it.
    """
    checker = _checker_module()
    root = Path(__file__).resolve().parents[2]

    report = checker.scan(root)

    assert report.violations == ()


def test_main_exits_nonzero_on_violation(tmp_path: Path, capsys) -> None:
    """The CLI entry point fails the build, so CI can gate on it."""
    checker = _checker_module()
    _write_skill(
        tmp_path,
        "manifest-workspace",
        "orchestrate",
        "name: orchestrate\ndescription: demo\ncontext: fork\nagent: scout",
    )

    exit_code = checker.main(["--repo-root", str(tmp_path)])

    assert exit_code == 1
    captured = capsys.readouterr()
    assert "not namespaced" in captured.out


def test_report_mode_exits_zero_even_with_violations(tmp_path: Path, capsys) -> None:
    """Report mode surfaces findings without failing, for inventory runs."""
    checker = _checker_module()
    _write_skill(
        tmp_path,
        "manifest-workspace",
        "orchestrate",
        "name: orchestrate\ndescription: demo\ncontext: fork\nagent: scout",
    )

    exit_code = checker.main(["--repo-root", str(tmp_path), "--report"])

    assert exit_code == 0
    captured = capsys.readouterr()
    assert "1" in captured.out.splitlines()[0]

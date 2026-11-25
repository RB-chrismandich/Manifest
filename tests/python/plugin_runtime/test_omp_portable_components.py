"""Portable OMP skill component evidence contracts."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.python.plugin_runtime.omp_portable_support import put, run


def _apply_component_observation_failure(path: Path, document: dict, failure: str):
    if failure == "missing":
        path.unlink()
    elif failure == "json":
        path.write_text("{broken")
    elif failure == "shape":
        put(path, {"skills": [], "warnings": {}})
    elif failure == "row":
        document["skills"][0]["filePath"] = 1
        put(path, document)
    elif failure == "warnings":
        document["warnings"] = [{"skillPath": "", "message": "discovery incomplete"}]
        put(path, document)
    else:
        skill = Path(document["skills"][0]["filePath"])
        skill.unlink()
        if failure == "symlink-file":
            target = skill.parent / "other.md"
            target.write_text("foreign")
            skill.symlink_to(target)
        elif failure == "directory-file":
            skill.mkdir()
        elif failure == "symlink-parent":
            target = skill.parent.with_name("other-skill")
            skill.parent.rename(target)
            (target / skill.name).write_text("foreign")
            skill.parent.symlink_to(target, target_is_directory=True)
        elif failure == "parent-file":
            skill.parent.rmdir()
            skill.parent.write_text("not a directory")


@pytest.mark.parametrize(
    "failure",
    [
        "missing",
        "json",
        "shape",
        "row",
        "warnings",
        "unavailable-file",
        "symlink-file",
        "directory-file",
        "symlink-parent",
        "parent-file",
    ],
)
def test_native_component_observation_failures_never_converge(portable, failure):
    _scripts, _root, env, _cwd = portable
    path = Path(env["OMP_TEST_SKILLS"])
    document = json.loads(path.read_text())
    _apply_component_observation_failure(path, document, failure)
    native = run(portable, "omp_native_inspection.py")["harnesses"]["omp"][
        "native_inspection"
    ]
    assert native["inventory_errors"]
    assert native["activation"] == "not-observed"
    report = run(portable, "plugin_reconcile.py", "--json", "--inspect-omp")
    assert report["status"] == "degraded"
    assert report["verified"] is False
    if failure == "warnings":
        assert native["components"][0]["status"] == "resolved"


def test_native_skill_attribution_never_uses_foreign_provider_paths(portable):
    _scripts, root, env, cwd = portable
    path = Path(env["OMP_TEST_SKILLS"])
    document = json.loads(path.read_text())
    original = document["skills"][0]
    for foreign in (
        Path(env["HOME"]) / ".claude/skills/native-skill/SKILL.md",
        root / "agent/managed-skills/native-skill/SKILL.md",
        cwd / "other-package/skills/native-skill/SKILL.md",
        Path(str(Path(original["filePath"]).parents[2]) + "-sibling")
        / "skills/native-skill/SKILL.md",
    ):
        foreign.parent.mkdir(parents=True, exist_ok=True)
        foreign.write_text("foreign")
        document["skills"].append(
            {
                **original,
                "filePath": str(foreign),
                "baseDir": str(foreign.parent),
            }
        )
    put(path, document)
    native = run(portable, "omp_native_inspection.py")["harnesses"]["omp"][
        "native_inspection"
    ]
    assert native["inventory_errors"] == []
    assert len(native["components"]) == 1
    assert native["components"][0]["resolved_path"] == original["filePath"]


def test_empty_native_skill_inventory_retains_unknown_package_coverage(portable):
    _scripts, _root, env, _cwd = portable
    put(Path(env["OMP_TEST_SKILLS"]), {"skills": [], "warnings": []})
    native = run(portable, "omp_native_inspection.py")["harnesses"]["omp"][
        "native_inspection"
    ]
    assert native["components"][0]["status"] == "unobserved"
    report = run(portable, "plugin_reconcile.py", "--json", "--inspect-omp")
    assert report["status"] == "degraded"
    assert any("package-components:" in row["reason"] for row in report["unverified"])

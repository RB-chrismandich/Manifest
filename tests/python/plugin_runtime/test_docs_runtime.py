"""Isolation tests for the installed manifest-docs bundle."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from manifest_agent.contracts import CapabilityTier, load_contract


@pytest.fixture
def repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


@pytest.fixture
def docs_bundle(repo_root: Path) -> Path:
    return repo_root / "plugins" / "manifest-docs"


def _isolated_env(tmp_path: Path) -> dict[str, str]:
    home = tmp_path / "home"
    home.mkdir(parents=True)
    return {
        **os.environ,
        "HOME": str(home),
        "UV_NO_NETWORK": "1",
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONNOUSERSITE": "1",
        "PYTHONPATH": "",
    }


def test_docs_lint_runs_from_installed_bundle_offline(
    docs_bundle: Path, tmp_path: Path
) -> None:
    readme = tmp_path / "README.md"
    readme.write_text("# Example\n", encoding="utf-8")
    script = docs_bundle / "runtime/docs_lint.py"

    result = subprocess.run(
        [sys.executable, "-S", "-B", str(script), str(readme)],
        cwd=tmp_path,
        env=_isolated_env(tmp_path),
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "doc-limits.json" in result.stdout
    assert "configs/claude" not in result.stderr


def test_docs_concision_reference_is_bundle_local(
    docs_bundle: Path,
) -> None:
    concision = (docs_bundle / "runtime/references/doc-concision.md").read_text(
        encoding="utf-8"
    )
    assert concision.startswith("# Doc Concision Contract")
    assert "../../runtime/docs_lint.py" in concision
    assert "configs/claude" not in concision
    assert (docs_bundle / "runtime/references/doc-limits.json").is_file()


def test_docs_skills_use_only_bundle_runtime_and_skill_interfaces(
    docs_bundle: Path,
) -> None:
    for skill in docs_bundle.glob("skills/*/SKILL.md"):
        source = skill.read_text(encoding="utf-8")
        assert "../../runtime/docs_lint.py" in source
        assert "configs/claude" not in source
        assert "manifest parallel-agent" not in source
        assert "parallel_agent.py" not in source


def test_docs_contract_declares_runtime_tree(docs_bundle: Path) -> None:
    contract = load_contract(docs_bundle / "manifest-capabilities.yml")
    runtime_paths = {component.path for component in contract.components.runtime}

    assert runtime_paths == {"runtime/docs_lint.py", "runtime/references"}
    assert contract.capabilities.executables[CapabilityTier.REQUIRED] == (
        "git",
        "python3",
    )

"""Isolation tests for the installed manifest-graphify bundle."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from manifest_agent.contracts import CapabilityTier, load_contract


@pytest.fixture
def graphify_bundle(repo_root: Path, tmp_path: Path) -> Path:
    installed = tmp_path / "manifest-graphify"
    shutil.copytree(repo_root / "plugins/manifest-graphify", installed)
    return installed


@pytest.fixture
def repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def test_graphify_skill_uses_coordinator_executable_and_xdg_cache(
    graphify_bundle: Path,
) -> None:
    skill = (graphify_bundle / "skills/graphify/SKILL.md").read_text(encoding="utf-8")

    assert "command -v graphify" in skill
    assert "${XDG_CACHE_HOME:-$HOME/.cache}/manifest/graphify" in skill
    assert "DEGRADED" in skill
    assert "bootstrap.sh" not in skill
    assert "uv tool install" not in skill
    assert ".claude" not in skill


def test_graphify_contract_declares_default_executable_and_cache(
    graphify_bundle: Path,
) -> None:
    contract = load_contract(graphify_bundle / "manifest-capabilities.yml")
    runtime_paths = {component.path for component in contract.components.runtime}

    assert contract.capabilities.executables[CapabilityTier.DEFAULT] == ("graphify",)
    assert runtime_paths == {"runtime/graphify.json"}

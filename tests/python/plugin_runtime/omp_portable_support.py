"""Helpers for isolated portable OMP inventory producer tests."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

from tests.python.plugin_runtime.workspace_runtime_helpers import (
    _harness_receipt,
    _valid_receipt,
)

ROOT = Path(__file__).resolve().parents[3]
SCRIPTS = ROOT / "plugins/manifest-workspace/skills/deploy-reconcile/scripts"


def put(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value))


def _write_catalog(root: Path, source: Path) -> Path:
    catalog = {
        "name": "manifest",
        "plugins": [{"name": "manifest-workspace", "version": "1.0.0"}],
    }
    catalog_path = root / "plugins/cache/marketplaces/manifest/marketplace.json"
    put(catalog_path, catalog)
    put(source / ".claude-plugin/marketplace.json", catalog)
    put(
        root / "marketplaces.json",
        {
            "version": 1,
            "marketplaces": [
                {
                    "name": "manifest",
                    "catalogPath": str(catalog_path),
                    "sourceType": "local",
                    "sourceUri": str(source),
                }
            ],
        },
    )
    return catalog_path


def _write_package(root: Path) -> tuple[Path, dict[str, str]]:
    cache = root / "plugins/cache/plugins/manifest___manifest-workspace___1.0.0"
    put(cache / "package.json", {"name": "@manifest/workspace", "version": "1.0.0"})
    link = root / "plugins/node_modules/@manifest/workspace"
    link.parent.mkdir(parents=True)
    link.symlink_to(cache)
    entry = {
        "installPath": str(cache),
        "scope": "user",
        "version": "1.0.0",
        "installedAt": "2026-11-13",
        "lastUpdated": "2026-11-13",
    }
    put(
        root / "plugins/installed_plugins.json",
        {"version": 2, "plugins": {"manifest-workspace@manifest": [entry]}},
    )
    put(
        root / "plugins/omp-plugins.lock.json",
        {"plugins": {"@manifest/workspace": {"version": "1.0.0", "enabled": True}}},
    )
    return cache, entry


def _write_observations(
    tmp_path: Path, cache: Path, entry: dict[str, str]
) -> tuple[Path, Path]:
    plugin_observation = tmp_path / "list.json"
    put(
        plugin_observation,
        {
            "marketplace": [
                {
                    "id": "manifest-workspace@manifest",
                    "scope": "user",
                    "entries": [entry],
                }
            ],
            "npm": [],
        },
    )
    # Captured OMP 18.20.0 `omp skill list --json` row shape; producer is
    # packages/coding-agent/src/cli/skill-list.ts (embedded binary strings
    # 1070277-1070287). Paths are rebound to this disposable native install.
    skill = cache / "skills/native-skill/SKILL.md"
    skill.parent.mkdir(parents=True)
    skill.write_text("---\nname: native-skill\ndescription: fixture\n---\n")
    skill_observation = tmp_path / "skills.json"
    put(
        skill_observation,
        {
            "skills": [
                {
                    "name": "native-skill",
                    "description": "fixture",
                    "filePath": str(skill),
                    "baseDir": str(skill.parent),
                    "source": "claude-plugins:user",
                    "hide": False,
                }
            ],
            "warnings": [],
        },
    )
    return plugin_observation, skill_observation


def _write_omp_shim(tmp_path: Path) -> Path:
    binary = tmp_path / "bin/omp"
    binary.parent.mkdir()
    binary.write_text(
        f"#!{sys.executable}\nimport os, sys\nfrom pathlib import Path\n"
        "keys = {('plugin', 'list', '--json'): 'OMP_TEST_LIST', "
        "('skill', 'list', '--json'): 'OMP_TEST_SKILLS'}\n"
        "print(Path(os.environ[keys[tuple(sys.argv[1:])]]).read_text())\n"
    )
    binary.chmod(0o755)
    return binary


def _write_installation_receipt(state: Path) -> None:
    put(
        state / "manifest/installation.json",
        _valid_receipt({"omp": _harness_receipt("omp", ["manifest-workspace"])}),
    )


def _isolated_environment(
    home: Path,
    state: Path,
    binary: Path,
    plugin_observation: Path,
    skill_observation: Path,
) -> dict[str, str]:
    env = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith(("OMP_", "PI_", "XDG_", "PYTHON"))
    }
    env.update(
        HOME=str(home),
        PATH=str(binary.parent),
        XDG_STATE_HOME=str(state),
        OMP_TEST_LIST=str(plugin_observation),
        OMP_TEST_SKILLS=str(skill_observation),
    )
    return env


def build_portable(tmp_path: Path) -> tuple[Path, Path, dict[str, str], Path]:
    # Keep the bundle's skill layout: reconcile loads the sibling env-check
    # receipt contract.
    skills = tmp_path / "portable/skills"
    scripts = skills / "deploy-reconcile/scripts"
    shutil.copytree(SCRIPTS, scripts)
    shutil.copytree(
        SCRIPTS.parents[1] / "env-check/scripts", skills / "env-check/scripts"
    )
    home = tmp_path / "home"
    root = home / ".omp"
    source = tmp_path / "release"
    _write_catalog(root, source)
    cache, entry = _write_package(root)
    plugin_observation, skill_observation = _write_observations(tmp_path, cache, entry)
    binary = _write_omp_shim(tmp_path)
    state = tmp_path / "state"
    _write_installation_receipt(state)
    env = _isolated_environment(
        home, state, binary, plugin_observation, skill_observation
    )
    return scripts, root, env, tmp_path


def run(portable, script: str, *arguments: str):
    scripts, _root, env, cwd = portable
    result = subprocess.run(
        [sys.executable, "-B", str(scripts / script), *arguments],
        env=env,
        cwd=cwd,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)

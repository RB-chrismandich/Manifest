"""Claude MCP project/local scope coverage and OMP agent-root precedence.

Regression coverage for the harness-reliability review threads:
- ``load_claude_expectations`` must expect the project-scope (``.mcp.json``)
  and local-scope (``.claude.json["projects"]``) servers that
  ``claude mcp list`` reports, so a failed non-user server cannot hide behind
  a healthy user server.
- ``health_install_files._paths`` must honor ``PI_CODING_AGENT_DIR`` before
  ``OMP_AGENT_DIR``, matching ``mcp_health.py`` and ``health_report.py``.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.python.plugin_runtime.health_test_helpers import (
    load_runtime_module,
)
from tests.python.plugin_runtime.health_test_helpers import (
    repo_root as _repo_root,
)

SCRIPTS = "plugins/manifest-workspace/skills/env-check/scripts"


@pytest.fixture
def expectations_module(tmp_path):
    scripts = _repo_root() / SCRIPTS
    return load_runtime_module(
        scripts / "mcp_health_expectations.py",
        f"mcp_health_expectations_{tmp_path.name}",
    )


@pytest.fixture
def install_files_module(tmp_path):
    scripts = _repo_root() / SCRIPTS
    return load_runtime_module(
        scripts / "health_install_files.py",
        f"health_install_files_{tmp_path.name}",
    )


def _runtime_paths(module, tmp_path: Path, home: Path):
    return module.RuntimePaths(
        home=home,
        state_dir=tmp_path / "state",
        claude_config=home / ".claude.json",
        claude_settings=home / ".claude" / "settings.json",
        plugin_index=home / ".claude" / "plugins" / "installed_plugins.json",
        omp_agent_dir=tmp_path / "omp-agent",
    )


def _write_claude_config(home: Path, payload: dict) -> None:
    home.mkdir(parents=True, exist_ok=True)
    (home / ".claude.json").write_text(json.dumps(payload), encoding="utf-8")


def test_project_scope_servers_become_expectations(
    expectations_module, tmp_path: Path
) -> None:
    home = tmp_path / "home"
    project = tmp_path / "repo" / "subdir"
    project.mkdir(parents=True)
    _write_claude_config(home, {"mcpServers": {"user-server": {}}})
    (tmp_path / "repo" / ".mcp.json").write_text(
        json.dumps({"mcpServers": {"project-server": {}}}), encoding="utf-8"
    )
    paths = _runtime_paths(expectations_module, tmp_path, home)

    expectations = expectations_module.load_claude_expectations(
        paths, required=True, project_dir=project
    )

    assert expectations.errors == set()
    assert expectations.disabled == {
        "user-server": False,
        "project-server": False,
    }


def test_local_scope_servers_become_expectations(
    expectations_module, tmp_path: Path
) -> None:
    home = tmp_path / "home"
    project = tmp_path / "repo"
    other = tmp_path / "other"
    project.mkdir(parents=True)
    _write_claude_config(
        home,
        {
            "mcpServers": {"user-server": {}},
            "projects": {
                str(project): {
                    "mcpServers": {
                        "local-server": {},
                        "local-disabled": {"disabled": True},
                    }
                },
                str(other): {"mcpServers": {"other-server": {}}},
            },
        },
    )
    paths = _runtime_paths(expectations_module, tmp_path, home)

    expectations = expectations_module.load_claude_expectations(
        paths, required=True, project_dir=project
    )

    assert expectations.errors == set()
    assert expectations.disabled == {
        "user-server": False,
        "local-server": False,
        "local-disabled": True,
    }


def test_project_scopes_are_excluded_from_omp_import(
    expectations_module, tmp_path: Path
) -> None:
    home = tmp_path / "home"
    project = tmp_path / "repo"
    project.mkdir(parents=True)
    _write_claude_config(
        home,
        {
            "mcpServers": {"user-server": {}},
            "projects": {str(project): {"mcpServers": {"local-server": {}}}},
        },
    )
    (project / ".mcp.json").write_text(
        json.dumps({"mcpServers": {"project-server": {}}}), encoding="utf-8"
    )
    paths = _runtime_paths(expectations_module, tmp_path, home)

    imported = expectations_module.load_claude_expectations(
        paths, required=False, claude_namespace=False
    )

    assert imported.disabled == {"user-server": False}


def test_unparseable_project_manifest_degrades(
    expectations_module, tmp_path: Path
) -> None:
    home = tmp_path / "home"
    project = tmp_path / "repo"
    project.mkdir(parents=True)
    _write_claude_config(home, {"mcpServers": {"user-server": {}}})
    (project / ".mcp.json").write_text("{not json", encoding="utf-8")
    paths = _runtime_paths(expectations_module, tmp_path, home)

    expectations = expectations_module.load_claude_expectations(
        paths, required=True, project_dir=project
    )

    assert "unparseable" in expectations.errors


def _environment(home: Path, extra: dict[str, str]) -> dict[str, str]:
    env = {"HOME": str(home)}
    env.update(extra)
    return env


def test_installer_honors_pi_coding_agent_dir_first(
    install_files_module, tmp_path: Path
) -> None:
    home = tmp_path / "home"
    pi_dir = tmp_path / "pi-agent"
    omp_dir = tmp_path / "omp-agent"
    paths = install_files_module._paths(
        _environment(
            home,
            {
                "PI_CODING_AGENT_DIR": str(pi_dir),
                "OMP_AGENT_DIR": str(omp_dir),
            },
        )
    )
    assert paths.agent_root == pi_dir.resolve()
    assert paths.extension == pi_dir.resolve() / "extensions" / "manifest-health.ts"


def test_installer_uses_omp_agent_dir_without_pi_override(
    install_files_module, tmp_path: Path
) -> None:
    home = tmp_path / "home"
    omp_dir = tmp_path / "omp-agent"
    paths = install_files_module._paths(
        _environment(home, {"OMP_AGENT_DIR": str(omp_dir)})
    )
    assert paths.agent_root == omp_dir.resolve()


def test_installer_defaults_to_home_omp_agent(
    install_files_module, tmp_path: Path
) -> None:
    home = tmp_path / "home"
    paths = install_files_module._paths(_environment(home, {}))
    assert paths.agent_root == home.resolve() / ".omp" / "agent"

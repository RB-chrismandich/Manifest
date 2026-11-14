"""Shared isolation fixtures and helpers for workspace bundle runtime tests."""

from __future__ import annotations

import os
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

import pytest


@pytest.fixture(name="repo_root")
def repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


@pytest.fixture(name="workspace_bundle")
def workspace_bundle(repo_root: Path) -> Path:
    return repo_root / "plugins" / "manifest-workspace"


def _isolated_env(tmp_path: Path) -> dict[str, str]:
    home = tmp_path / "home"
    state = tmp_path / "state"
    data = tmp_path / "data"
    config = tmp_path / "config"
    cache = tmp_path / "cache"
    bin_dir = tmp_path / "bin"
    for path in (home, state, data, config, cache, bin_dir):
        path.mkdir(parents=True)
    manifest_stub = bin_dir / "manifest"
    manifest_stub.write_text("#!/bin/sh\nexit 127\n", encoding="utf-8")
    manifest_stub.chmod(0o755)
    inherited_path = os.environ.get("PATH", "")
    path = (
        str(bin_dir)
        if not inherited_path
        else str(bin_dir) + os.pathsep + inherited_path
    )
    return {
        **os.environ,
        "HOME": str(home),
        "XDG_STATE_HOME": str(state),
        "XDG_DATA_HOME": str(data),
        "XDG_CONFIG_HOME": str(config),
        "XDG_CACHE_HOME": str(cache),
        "PATH": path,
        "UV_NO_NETWORK": "1",
        "PYTHONDONTWRITEBYTECODE": "1",
    }


def _run(
    script: Path, *args: str, env: dict[str, str], cwd: Path
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-B", str(script), *args],
        cwd=cwd,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )


def _valid_receipt(harnesses: dict[str, dict]) -> dict:
    return {
        "schema_version": 1,
        "coordinator_version": "1",
        "release_version": "1",
        "source_commit": "a" * 40,
        "source_dirty": False,
        "archive_sha256": "b" * 64,
        "bundle_checksums": {"manifest-workspace": "c" * 64},
        "selected_optional": [],
        "harnesses": harnesses,
        "migration_backup": None,
    }


def _with_omp_fixture(
    env: dict[str, str], tmp_path: Path, version: str | None = None
) -> dict[str, str]:
    bin_dir = tmp_path / "omp-bin"
    bin_dir.mkdir()
    executable = bin_dir / "omp"
    body = (
        "#!/bin/sh\n"
        'if [ "$1" = "--version" ]; then\n'
        f"  printf '%s\\n' {shlex.quote(version or 'omp 18.6.1')}\n"
        "  exit 0\n"
        "fi\n"
        'if [ "$1" = "plugin" ] && [ "$2" = "list" ] && [ "$3" = "--json" ]; then\n'
        '  exec python3 -c \'import json,pathlib,os; p=pathlib.Path(os.environ["HOME"])/".omp/plugins/installed_plugins.json"; d=json.loads(p.read_text()) if p.exists() else {"version":2,"plugins":{}}; print(json.dumps({"marketplace":[{"id":k,"scope":"user","entries":v} for k,v in d["plugins"].items() if v]}))\'\n'
        "fi\n"
        "exit 97\n"
    )
    executable.write_text(body, encoding="utf-8")
    executable.chmod(0o755)
    return {**env, "PATH": str(bin_dir) + os.pathsep + env.get("PATH", "")}


def _with_manifest_cli(
    env: dict[str, str], tmp_path: Path, repo_root: Path
) -> dict[str, str]:
    """Expose a copied packaged runtime through its supported CLI command."""
    bin_dir = tmp_path / "manifest-bin"
    bin_dir.mkdir()
    runtime_root = tmp_path / "manifest-runtime"
    shutil.copytree(
        repo_root / "src" / "manifest_agent",
        runtime_root / "manifest_agent",
        ignore=shutil.ignore_patterns("__pycache__"),
    )
    data_root = runtime_root / "manifest_agent" / "data"
    data_root.mkdir(parents=True, exist_ok=True)
    for source, destination in (
        (
            repo_root / "schemas/manifest-capabilities.schema.json",
            "manifest-capabilities.schema.json",
        ),
        (
            repo_root / "schemas/project-checks.schema.json",
            "project-checks.schema.json",
        ),
        (repo_root / "configs/claude/config/model_policy.yml", "model_policy.yml"),
    ):
        shutil.copy2(source, data_root / destination)
    executable = bin_dir / "manifest"
    executable.write_text(
        f"#!{sys.executable}\n"
        "import sys\n"
        f"sys.path.insert(0, {str(runtime_root)!r})\n"
        "from manifest_agent.cli import main\n"
        "main()\n",
        encoding="utf-8",
    )
    executable.chmod(0o755)
    existing_path = env.get("PATH", "")
    path = (
        str(bin_dir) if not existing_path else str(bin_dir) + os.pathsep + existing_path
    )
    return {**env, "PATH": path}


def _harness_receipt(name: str, plugins: list[str] | None = None) -> dict:
    return {
        "harness": name,
        "adapter_version": "1",
        "native_version": "1.0",
        "plugin_ids": plugins or [],
        "owned_entries": [],
        "capabilities": {},
        "verified": True,
        "errors": [],
    }

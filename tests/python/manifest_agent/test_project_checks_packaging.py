"""Installed-wheel contracts for the project checks registry schema."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


def _registry(checkout: Path) -> Path:
    """Write the smallest schema-valid registry and policy anchors."""
    config = checkout / "config"
    config.mkdir(parents=True)
    (config / "debt-baseline.json").write_text(
        '{"schema_version":1,"findings":[]}', encoding="utf-8"
    )
    (config / "check-preservation.json").write_text(
        '{"schema_version":1,"invariants":[{"id":"shared-checks.exit-status","description":"valid"}]}',
        encoding="utf-8",
    )
    path = checkout / "project-checks.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "checks": [
                    {
                        "id": "test.probe",
                        "group": "test",
                        "category": "test",
                        "argv": ["true"],
                        "cwd": ".",
                        "inputs": [],
                        "dependencies": [],
                        "timeout_seconds": 2,
                        "selection": "project",
                        "tool": "fixture",
                        "version": "fixture",
                        "honors_status_contract": False,
                    }
                ],
                "profiles": {
                    "quick": ["test.probe"],
                    "full": ["test.probe"],
                    "security": ["test.probe"],
                    "release": ["test.probe"],
                },
                "debt_baseline": "config/debt-baseline.json",
                "preservation": "config/check-preservation.json",
            }
        ),
        encoding="utf-8",
    )
    return path


def _wheel_site_packages(repo_root: Path, tmp_path: Path) -> Path:
    """Build the root wheel and install only its files into an isolated target."""
    wheels = tmp_path / "wheels"
    wheels.mkdir()
    built = subprocess.run(
        [
            "uv",
            "build",
            "--project",
            str(repo_root),
            "--wheel",
            "--out-dir",
            str(wheels),
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )
    assert built.returncode == 0, built.stderr
    site_packages = tmp_path / "site-packages"
    installed = subprocess.run(
        [
            "uv",
            "pip",
            "install",
            "--python",
            sys.executable,
            "--target",
            str(site_packages),
            "--offline",
            "--reinstall",
            "--no-deps",
            str(next(wheels.glob("manifest_agent-*.whl"))),
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )
    assert installed.returncode == 0, installed.stderr
    return site_packages


def test_built_wheel_loads_project_checks_schema_without_checkout(
    tmp_path: Path,
) -> None:
    """The installed registry loads its schema without a source checkout present."""
    repo_root = Path(__file__).parents[3]
    site_packages = _wheel_site_packages(repo_root, tmp_path)
    registry = _registry(tmp_path / "checkout")
    foreign_cwd = tmp_path / "foreign"
    foreign_cwd.mkdir()
    probe = subprocess.run(
        [
            "uv",
            "run",
            "--project",
            str(repo_root),
            "python",
            "-c",
            (
                "from pathlib import Path; "
                "from manifest_agent.checks.registry import load_registry; "
                f"print(len(load_registry(Path({str(registry)!r}))))"
            ),
        ],
        cwd=foreign_cwd,
        env={**os.environ, "PYTHONPATH": str(site_packages)},
        capture_output=True,
        text=True,
        check=False,
    )
    assert probe.returncode == 0, probe.stderr

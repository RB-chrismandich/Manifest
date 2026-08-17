"""Throwaway interpreters and home layouts for the delegate trust-gate suites.

Split out of test_delegate_distribution.py so neither suite crosses the
module-size ceiling, and so the venv/home builders have exactly one definition.
Named `_delegate_runtime_env` (not `conftest`) for the same reason as
_delegate_harness.py: these are plain helpers, not pytest fixtures.
"""

import os
import shutil
import subprocess
import sys
from collections.abc import Sequence
from importlib import metadata
from pathlib import Path

import pytest


def _install_offline_pyyaml(venv: Path) -> None:
    python = venv / "bin/python"
    site_query = subprocess.run(
        [
            str(python),
            "-c",
            "import site; print(site.getsitepackages()[0])",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert site_query.returncode == 0, site_query.stderr
    site_packages = Path(site_query.stdout.strip()).resolve()
    assert site_packages.is_relative_to(venv.resolve())

    distribution = metadata.distribution("pyyaml")
    files = distribution.files or ()
    assert files, "installed PyYAML distribution has no file inventory"
    for item in files:
        relative = Path(item)
        assert not relative.is_absolute() and ".." not in relative.parts
        source = Path(distribution.locate_file(item))
        if not source.is_file():
            continue
        destination = site_packages / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
    location = subprocess.run(
        [
            str(python),
            "-c",
            "import pathlib, yaml; print(pathlib.Path(yaml.__file__).resolve())",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert location.returncode == 0, location.stderr
    assert Path(location.stdout.strip()).is_relative_to(venv.resolve())


def _build_wheels(tmp_path: Path, projects: Sequence[Path], directory: str) -> Path:
    wheel_dir = tmp_path / directory
    wheel_dir.mkdir()
    for project in projects:
        built = subprocess.run(
            [
                "uv",
                "build",
                "--project",
                str(project),
                "--wheel",
                "--out-dir",
                str(wheel_dir),
            ],
            cwd=tmp_path,
            capture_output=True,
            text=True,
            check=False,
        )
        assert built.returncode == 0, built.stderr
    return wheel_dir


def _create_venv(tmp_path: Path, name: str) -> Path:
    venv = tmp_path / name
    subprocess.run(
        [sys.executable, "-m", "venv", "--system-site-packages", str(venv)],
        check=True,
    )
    return venv


def _require_isolated_venv(venv: Path) -> None:
    """Skip before installation if the target interpreter is not isolated."""
    isolation = subprocess.run(
        [
            str(venv / "bin/python"),
            "-c",
            "import sys; print(sys.prefix); print(sys.base_prefix)",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    prefixes = isolation.stdout.split()
    if isolation.returncode == 0 and len(prefixes) == 2 and prefixes[0] != prefixes[1]:
        return
    pytest.skip(
        "`python -m venv` produced a non-isolating environment "
        f"(sys.prefix == sys.base_prefix) for {sys.executable}; installing "
        "would write to system site-packages instead of the temp venv"
    )


def _install_distribution_wheels(
    venv: Path, wheels: Path, cwd: Path
) -> subprocess.CompletedProcess[str]:
    """Install local wheels through the venv interpreter without retargeting."""
    return subprocess.run(
        [
            str(venv / "bin/python"),
            "-m",
            "pip",
            "install",
            "--no-index",
            "--no-deps",
            "--ignore-installed",
            *map(str, sorted(wheels.glob("*.whl"))),
        ],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )


def _uv_install(python: Path, *arguments: str) -> None:
    """Install into one interpreter from local artifacts only.

    `--offline` keeps a test from reaching the network for a build backend, and
    `--no-deps` keeps it from pulling anything the fixture did not ask for.
    """
    installed = subprocess.run(
        [
            "uv",
            "pip",
            "install",
            "--python",
            str(python),
            "--offline",
            "--no-deps",
            *arguments,
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert installed.returncode == 0, installed.stderr


def _trusted_policy_venv(tmp_path: Path) -> Path:
    repo_root = Path(__file__).resolve().parents[2]
    wheel_dir = _build_wheels(
        tmp_path,
        (repo_root / "configs/claude/scripts/manifest_model_policy",),
        "policy-wheel",
    )
    venv = _create_venv(tmp_path, "trusted-venv")
    _install_offline_pyyaml(venv)
    _uv_install(venv / "bin/python", str(next(wheel_dir.glob("*.whl"))))
    return venv


def _recorder_runtime_home(tmp_path: Path) -> tuple[Path, Path, Path]:
    """Home whose `.claude/.venv/bin/python` symlinks to an argv[0] recorder.

    Returns the home, the symlink the guard must exec, and the resolved target.
    Execing the resolved target instead of the symlink is what strands a venv
    re-exec in the base interpreter, so the two paths stay distinguishable.
    """
    home = tmp_path / "runtime-home"
    binaries = home / ".claude/.venv/bin"
    binaries.mkdir(parents=True)
    recorder = binaries / "real-python"
    recorder.write_text('#!/bin/sh\nprintf "%s\\n" "$0"\nexit 0\n', encoding="utf-8")
    recorder.chmod(0o755)
    symlink = binaries / "python"
    symlink.symlink_to(recorder.name)
    return home, symlink, recorder


def _policyless_launcher(tmp_path: Path) -> Path:
    """Interpreter without manifest-model-policy, so the guard must re-exec."""
    venv = tmp_path / "policyless-venv"
    subprocess.run([sys.executable, "-m", "venv", str(venv)], check=True)
    _require_isolated_venv(venv)
    return venv / "bin/python"


def _copied_plugin(tmp_path: Path) -> Path:
    """A plugin copy with no repo above it, like the installed marketplace cache.

    The trust gate derives one of its editable anchors from `__file__`, so a copy
    outside the repo is the only way to exercise what an installed user runs.
    """
    plugin = tmp_path / "installed/manifest-delegate"
    shutil.copytree(
        Path(__file__).resolve().parents[2] / "plugins/manifest-delegate", plugin
    )
    return plugin


def _run_guard(launcher: Path, home: Path, cwd: Path, script=None, **extra: str):
    """Run `delegate.py --help` through `launcher`, with `home` as HOME.

    `--help` is the cheapest command that still runs the full trust gate: the
    gate executes at import time, before any argument dispatch.
    """
    if script is None:
        script = (
            Path(__file__).resolve().parents[2]
            / "plugins/manifest-delegate/scripts/delegate.py"
        )
    environment = dict(os.environ)
    environment.update({"HOME": str(home), "PYTHONPATH": ""})
    environment.pop("MANIFEST_DELEGATE_RUNTIME_REEXEC", None)
    environment.update(extra)
    return subprocess.run(
        [str(launcher), str(script), "--help"],
        cwd=cwd,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )


def _deployed_home(tmp_path: Path) -> Path:
    """Home shaped like a bootstrap deploy: policy editable from ~/.claude/scripts.

    `~/.claude/pyproject.toml` pins manifest-model-policy as an editable source
    under `scripts/`, so every `uv sync` of the home runtime reproduces exactly
    this layout — the deployed copy is the normal case, not a repaired one.
    """
    repo_root = Path(__file__).resolve().parents[2]
    home = tmp_path / "deployed-home"
    scripts = home / ".claude/scripts"
    scripts.mkdir(parents=True)
    shutil.copytree(
        repo_root / "configs/claude/scripts/manifest_model_policy",
        scripts / "manifest_model_policy",
    )
    venv = _create_venv(tmp_path, "deployed-venv")
    _require_isolated_venv(venv)
    _install_offline_pyyaml(venv)
    _uv_install(
        venv / "bin/python", "--editable", str(scripts / "manifest_model_policy")
    )
    (home / ".claude/.venv").symlink_to(venv, target_is_directory=True)
    return home


def _site_packages(python: Path) -> Path:
    query = subprocess.run(
        [str(python), "-c", "import site; print(site.getsitepackages()[0])"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert query.returncode == 0, query.stderr
    return Path(query.stdout.strip())

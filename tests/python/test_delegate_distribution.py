#!/usr/bin/env python3
"""Installed and unpacked manifest-delegate distribution boundaries."""

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


def _trusted_policy_venv(tmp_path: Path) -> Path:
    repo_root = Path(__file__).resolve().parents[2]
    wheel_dir = _build_wheels(
        tmp_path,
        (repo_root / "configs/claude/scripts/manifest_model_policy",),
        "policy-wheel",
    )
    venv = _create_venv(tmp_path, "trusted-venv")
    _install_offline_pyyaml(venv)
    installed = subprocess.run(
        [
            "uv",
            "pip",
            "install",
            "--python",
            str(venv / "bin/python"),
            "--offline",
            "--no-deps",
            str(next(wheel_dir.glob("*.whl"))),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert installed.returncode == 0, installed.stderr
    return venv


def test_unpacked_plugin_delegate_uses_root_model_policy_distribution(
    tmp_path: Path,
) -> None:
    repo_root = Path(__file__).resolve().parents[2]
    plugin = tmp_path / "installed/manifest-delegate"
    shutil.copytree(repo_root / "plugins/manifest-delegate", plugin)
    environment = dict(os.environ)
    environment["PYTHONPATH"] = ""
    environment["HOME"] = str(tmp_path / "empty-home")
    assert not (plugin / "manifest_model_policy").exists()

    result = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import importlib.metadata as m, pathlib, sys; "
                f"sys.path.insert(0, {str(plugin)!r}); "
                "import manifest_delegate, manifest_model_policy; "
                "print(m.version('manifest-model-policy')); "
                "print(pathlib.Path(manifest_model_policy.__file__).resolve())"
            ),
        ],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    lines = result.stdout.splitlines()
    assert lines[0] == "0.1.0"
    assert not Path(lines[1]).is_relative_to(plugin)


def test_unpacked_delegate_script_accepts_only_trusted_installed_policy(
    tmp_path: Path,
) -> None:
    repo_root = Path(__file__).resolve().parents[2]
    plugin = tmp_path / "installed/manifest-delegate"
    shutil.copytree(repo_root / "plugins/manifest-delegate", plugin)
    venv = _trusted_policy_venv(tmp_path)
    environment = dict(os.environ)
    environment.update({"HOME": str(tmp_path / "empty-home"), "PYTHONPATH": ""})

    result = subprocess.run(
        [str(venv / "bin/python"), str(plugin / "scripts/delegate.py"), "--help"],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "Delegate tasks/reviews" in result.stdout


def test_unpacked_delegate_rejects_shadow_policy_and_poisoned_runtime(
    tmp_path: Path,
) -> None:
    repo_root = Path(__file__).resolve().parents[2]
    plugin = tmp_path / "installed/manifest-delegate"
    shutil.copytree(repo_root / "plugins/manifest-delegate", plugin)
    venv = _trusted_policy_venv(tmp_path)
    shadow = tmp_path / "shadow/manifest_model_policy"
    shadow.mkdir(parents=True)
    (shadow / "__init__.py").write_text("SHADOW = True\n", encoding="utf-8")
    metadata = shadow.parent / "manifest_model_policy-9.9.9.dist-info"
    metadata.mkdir()
    (metadata / "METADATA").write_text(
        "Metadata-Version: 2.4\nName: manifest-model-policy\nVersion: 9.9.9\n",
        encoding="utf-8",
    )
    environment = dict(os.environ)
    environment.update(
        {
            "HOME": str(tmp_path / "empty-home"),
            "PYTHONPATH": str(shadow.parent),
            "MANIFEST_RUNTIME_PYTHON": str(tmp_path / "attacker/python"),
        }
    )

    result = subprocess.run(
        [str(venv / "bin/python"), str(plugin / "scripts/delegate.py"), "--help"],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 2
    assert "rejected untrusted MANIFEST_RUNTIME_PYTHON" in result.stderr
    assert "Delegate tasks/reviews" not in result.stdout


def test_unpacked_delegate_rejects_plugin_local_policy_shadow(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[2]
    plugin = tmp_path / "installed/manifest-delegate"
    shutil.copytree(repo_root / "plugins/manifest-delegate", plugin)
    shadow = plugin / "manifest_model_policy"
    shadow.mkdir()
    (shadow / "__init__.py").write_text("SHADOW = True\n", encoding="utf-8")
    venv = _trusted_policy_venv(tmp_path)
    environment = dict(os.environ)
    environment.update({"HOME": str(tmp_path / "empty-home"), "PYTHONPATH": ""})

    result = subprocess.run(
        [str(venv / "bin/python"), str(plugin / "scripts/delegate.py"), "--help"],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 2
    assert "invalid manifest-model-policy distribution" in result.stderr
    assert "Delegate tasks/reviews" not in result.stdout


def test_installed_delegate_uses_explicit_model_policy_distribution(
    tmp_path: Path,
) -> None:
    repo_root = Path(__file__).resolve().parents[2]
    wheels = _build_wheels(
        tmp_path,
        (
            repo_root / "configs/claude/scripts/manifest_model_policy",
            repo_root / "plugins/manifest-delegate",
        ),
        "wheels",
    )
    venv = _create_venv(tmp_path, "venv")
    _require_isolated_venv(venv)
    _install_offline_pyyaml(venv)
    installed = _install_distribution_wheels(venv, wheels, tmp_path)
    assert installed.returncode == 0, installed.stderr

    script = venv / "bin" / "manifest-delegate"
    assert script.is_file(), (
        f"manifest-delegate console script missing from {venv}; "
        f"pip reported: {installed.stdout}"
    )
    environment = dict(os.environ)
    environment.update({"PYTHONPATH": "", "HOME": str(tmp_path / "empty-home")})
    result = subprocess.run(
        [str(script), "--help"],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "Delegate tasks/reviews" in result.stdout

    metadata = subprocess.run(
        [
            str(venv / "bin/python"),
            "-c",
            "import importlib.metadata as m; "
            "print(m.requires('manifest-delegate-runtime'))",
        ],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    assert metadata.returncode == 0, metadata.stderr
    assert "manifest-model-policy==0.1.0" in metadata.stdout


def test_module_cli_reports_malformed_skill_policy_without_traceback(
    tmp_path: Path,
) -> None:
    repo_root = Path(__file__).resolve().parents[2]
    skill = tmp_path / "bad-skill.md"
    skill.write_text("---\nname: bad\n", encoding="utf-8")
    environment = dict(os.environ)
    environment.update(
        {
            "HOME": str(tmp_path / "empty-home"),
            "PYTHONPATH": os.pathsep.join(
                (
                    str(repo_root / "plugins/manifest-delegate"),
                    str(repo_root / "configs/claude/scripts"),
                )
            ),
        }
    )

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "manifest_delegate",
            "task",
            "--backend",
            "codex",
            "--skill-path",
            str(skill),
            "-",
        ],
        cwd=tmp_path,
        env=environment,
        input="private task",
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 2
    assert (
        "delegate: invalid skill policy: unterminated skill frontmatter"
        in result.stderr
    )
    assert "Traceback" not in result.stderr


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


def _run_guard(launcher: Path, home: Path, cwd: Path, **extra: str):
    repo_root = Path(__file__).resolve().parents[2]
    environment = dict(os.environ)
    environment.update({"HOME": str(home), "PYTHONPATH": ""})
    environment.pop("MANIFEST_DELEGATE_RUNTIME_REEXEC", None)
    environment.update(extra)
    return subprocess.run(
        [
            str(launcher),
            str(repo_root / "plugins/manifest-delegate/scripts/delegate.py"),
            "--help",
        ],
        cwd=cwd,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )


def test_reexec_targets_the_symlink_not_its_resolved_interpreter(
    tmp_path: Path,
) -> None:
    home, symlink, recorder = _recorder_runtime_home(tmp_path)

    result = _run_guard(_policyless_launcher(tmp_path), home, tmp_path)

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == str(symlink)
    assert result.stdout.strip() != str(recorder)


def test_reexec_reaches_policy_inside_a_symlinked_venv(tmp_path: Path) -> None:
    trusted = _trusted_policy_venv(tmp_path)
    assert (trusted / "bin/python").is_symlink(), "venv did not symlink its interpreter"
    home = tmp_path / "venv-home"
    (home / ".claude").mkdir(parents=True)
    (home / ".claude/.venv").symlink_to(trusted, target_is_directory=True)

    result = _run_guard(_policyless_launcher(tmp_path), home, tmp_path)

    assert result.returncode == 0, result.stderr
    assert "Delegate tasks/reviews" in result.stdout
    assert "manifest-model-policy" not in result.stderr


def test_runtime_override_accepts_an_equivalent_spelling(tmp_path: Path) -> None:
    home, symlink, _ = _recorder_runtime_home(tmp_path)
    equivalent = symlink.parent / ".." / "bin" / symlink.name

    result = _run_guard(
        _policyless_launcher(tmp_path),
        home,
        tmp_path,
        MANIFEST_RUNTIME_PYTHON=str(equivalent),
    )

    assert result.returncode == 0, result.stderr
    assert "rejected untrusted MANIFEST_RUNTIME_PYTHON" not in result.stderr
    assert result.stdout.strip() == str(symlink)

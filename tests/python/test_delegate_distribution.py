#!/usr/bin/env python3
"""Installed and unpacked manifest-delegate distribution boundaries.

Runtime trust-gate behaviour (re-exec target, editable-source trust) lives in
test_delegate_runtime_trust.py; shared builders in _delegate_runtime_env.py.
"""

import os
import shutil
import subprocess
import sys
from pathlib import Path

from _delegate_runtime_env import (
    _build_wheels,
    _create_venv,
    _install_distribution_wheels,
    _install_offline_pyyaml,
    _require_isolated_venv,
    _trusted_policy_venv,
)


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

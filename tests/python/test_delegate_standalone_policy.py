"""Release-owned policy provenance and clean standalone runtime acceptance."""

import hashlib
import importlib.util
import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

from _delegate_runtime_env import _build_wheels

ROOT = Path(__file__).resolve().parents[2]
PLUGIN = ROOT / "plugins/manifest-delegate"


def test_bundled_policy_is_exactly_producer_derived():
    spec = importlib.util.spec_from_file_location(
        "policy_build", PLUGIN / "vendor/build_policy.py"
    )
    builder = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(builder)
    content = builder.archive_bytes(ROOT)
    assert content == (PLUGIN / "vendor/model-policy.zip").read_bytes()
    spec = importlib.util.spec_from_file_location(
        "policy_loader", PLUGIN / "manifest_delegate_policy.py"
    )
    loader = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(loader)
    assert hashlib.sha256(content).hexdigest() == loader.POLICY_SHA256
    with zipfile.ZipFile(loader.POLICY_ARCHIVE) as archive:
        for source in (ROOT / "configs/claude/scripts/manifest_model_policy").glob(
            "*.py"
        ):
            assert (
                archive.read("manifest_model_policy/" + source.name)
                == source.read_bytes()
            )


def _assert_tampered_policy_rejected(python, unpacked, env, cwd):
    # A changed release archive must be rejected before importing any policy.
    with (unpacked / "vendor/model-policy.zip").open("ab") as handle:
        handle.write(b"tampered")
    result = subprocess.run(
        [str(python), str(unpacked / "scripts/delegate.py"), "setup"],
        env=env,
        cwd=cwd,
        text=True,
        capture_output=True,
    )
    assert result.returncode == 2
    assert "digest mismatch" in result.stderr


def test_clean_standalone_artifact_setup_and_imports(tmp_path):
    artifact = tmp_path / "artifact"
    shutil.copytree(PLUGIN, artifact)
    wheels = _build_wheels(tmp_path, (artifact,), "wheels")
    venv = tmp_path / "runtime"
    subprocess.run(
        ["uv", "venv", "--no-project", "--python", sys.executable, str(venv)],
        check=True,
    )
    python = venv / "bin/python"
    subprocess.run(
        [
            "uv",
            "pip",
            "install",
            "--offline",
            "--no-deps",
            "--python",
            str(python),
            str(next(wheels.glob("*.whl"))),
        ],
        check=True,
    )
    env = dict(
        os.environ,
        HOME=str(tmp_path / "home"),
        PYTHONPATH="",
        XDG_STATE_HOME=str(tmp_path / "state"),
    )
    env.pop("MANIFEST_RUNTIME_PYTHON", None)
    env.pop("MANIFEST_DELEGATE_RUNTIME_REEXEC", None)
    # Delete the build input: the installed artifact must not use the checkout.
    shutil.rmtree(artifact)
    for args in (("setup",), ("task", "--help"), ("status", "--all")):
        result = subprocess.run(
            [str(venv / "bin/manifest-delegate"), *args],
            env=env,
            cwd=tmp_path,
            text=True,
            capture_output=True,
        )
        assert result.returncode == 0, (args, result.stdout, result.stderr)
    unpacked = tmp_path / "unpacked"
    shutil.copytree(PLUGIN, unpacked)
    result = subprocess.run(
        [str(python), str(unpacked / "scripts/delegate.py"), "setup"],
        env=env,
        cwd=tmp_path,
        text=True,
        capture_output=True,
    )
    assert result.returncode == 0, (result.stdout, result.stderr)
    assert not (tmp_path / "home/.claude/.venv").exists()
    _assert_tampered_policy_rejected(python, unpacked, env, tmp_path)

"""Upgrade and retirement isolation tests for the install_health_reporting.py installer."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from tests.python.plugin_runtime.health_test_helpers import (
    isolated_env,
    run_script,
)
from tests.python.plugin_runtime.health_test_helpers import (
    repo_root as _repo_root,
)
from tests.python.plugin_runtime.test_health_installer import (
    _copy_health_source,
    _install,
    _installer,
    _seed_claude_settings,
    _write_health_tool_fakes,
)


@pytest.fixture
def repo_root() -> Path:
    return _repo_root()


def test_health_installer_cleans_up_owned_retired_file_on_upgrade(
    repo_root: Path, tmp_path: Path
) -> None:
    source_root = _copy_health_source(repo_root, tmp_path / "source")
    env = isolated_env(tmp_path)
    _write_health_tool_fakes(tmp_path, env)
    _seed_claude_settings(env)
    _install(source_root, env, tmp_path)
    runtime_root = Path(env["XDG_DATA_HOME"]) / "manifest/health"
    receipt_path = Path(env["XDG_STATE_HOME"]) / "manifest/health/installation.json"

    retired_file = runtime_root / "plugin_reconcile.py"
    retired_content = b"# retired reconcile script\n"
    retired_file.write_bytes(retired_content)
    digest = hashlib.sha256(retired_content).hexdigest()

    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    receipt["files"]["plugin_reconcile.py"] = {
        "source": str(retired_file.resolve()),
        "destination": str(retired_file.resolve()),
        "source_sha256": digest,
        "destination_sha256": digest,
    }
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
    _install(source_root, env, tmp_path)
    assert not retired_file.exists()


def test_health_installer_refuses_to_clean_up_modified_retired_file_on_upgrade(
    repo_root: Path, tmp_path: Path
) -> None:
    source_root = _copy_health_source(repo_root, tmp_path / "source")
    env = isolated_env(tmp_path)
    _write_health_tool_fakes(tmp_path, env)
    _seed_claude_settings(env)
    _install(source_root, env, tmp_path)
    runtime_root = Path(env["XDG_DATA_HOME"]) / "manifest/health"
    receipt_path = Path(env["XDG_STATE_HOME"]) / "manifest/health/installation.json"

    retired_file = runtime_root / "plugin_reconcile.py"
    retired_file.write_bytes(b"# modified locally\n")
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    receipt["files"]["plugin_reconcile.py"] = {
        "source": str(retired_file.resolve()),
        "destination": str(retired_file.resolve()),
        "source_sha256": "0" * 64,
        "destination_sha256": "0" * 64,
    }
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")

    result = run_script(
        _installer(source_root),
        "--source-root",
        str(source_root),
        "--install",
        env=env,
        cwd=tmp_path,
    )
    assert result.returncode != 0
    assert (
        "refusing to replace" in result.stderr
        or "refusing" in result.stderr
        or "destination" in result.stderr
    )
    assert retired_file.exists()

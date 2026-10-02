"""Transaction-safety tests for install_health_reporting.py (PR-953 threads 13/18/19).

Covers the exclusive installation lock, rollback failure aggregation, and
uninstall-time removal of receipt-owned retired runtime files.
"""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

from tests.python.plugin_runtime.health_test_helpers import (
    isolated_env,
    load_runtime_module,
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


def _files_module(repo_root: Path):
    return load_runtime_module(
        repo_root
        / "plugins/manifest-workspace/skills/env-check/scripts/health_install_files.py",
        "health_install_files_test",
    )


def _reconcile_module(repo_root: Path):
    scripts = repo_root / "plugins/manifest-workspace/skills/env-check/scripts"
    sys.path.insert(0, str(scripts))
    try:
        return load_runtime_module(
            scripts / "health_install_reconcile.py",
            "health_install_reconcile_txn",
        )
    finally:
        sys.path.remove(str(scripts))


def test_install_waits_for_exclusive_installation_lock(
    repo_root: Path, tmp_path: Path
) -> None:
    source_root = _copy_health_source(repo_root, tmp_path / "source")
    env = isolated_env(tmp_path)
    _write_health_tool_fakes(tmp_path, env)
    _seed_claude_settings(env)

    files = _files_module(repo_root)
    paths = files._paths(env)
    lock_dir = paths.state_root.parent
    lock_dir.mkdir(parents=True)
    descriptor = os.open(lock_dir / files.INSTALL_LOCK_NAME, os.O_RDWR | os.O_CREAT)
    fcntl.flock(descriptor, fcntl.LOCK_EX)
    try:
        process = subprocess.Popen(
            [
                sys.executable,
                "-B",
                str(_installer(source_root)),
                "--source-root",
                str(source_root),
                "--install",
            ],
            cwd=tmp_path,
            env=env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        time.sleep(3)
        assert process.poll() is None, (
            f"installer finished while the install lock was held: "
            f"{process.communicate()}"
        )
        fcntl.flock(descriptor, fcntl.LOCK_UN)
        stdout, stderr = process.communicate(timeout=60)
        assert process.returncode == 0, stderr
        assert "health reporting installed" in stdout
    finally:
        os.close(descriptor)


def test_restore_snapshots_aggregates_failures(
    repo_root: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    files = _files_module(repo_root)

    good = tmp_path / "restored.py"
    good.write_bytes(b"original\n")
    good_snapshot = files._snapshot(good)
    good.write_bytes(b"overwritten\n")

    broken_dir = tmp_path / "broken"
    broken_dir.mkdir()
    broken = broken_dir / "stuck.py"
    broken.write_bytes(b"original\n")
    broken_snapshot = files._snapshot(broken)

    original_atomic_write = files._atomic_write

    def fail_broken(path: Path, data: bytes, mode: int) -> None:
        if path == broken:
            raise OSError("injected restore failure")
        original_atomic_write(path, data, mode)

    monkeypatch.setattr(files, "_atomic_write", fail_broken)
    with pytest.raises(files.InstallError, match="rollback") as raised:
        files._restore_snapshots([good_snapshot, broken_snapshot])

    message = str(raised.value)
    assert str(broken) in message
    # The healthy snapshot is still restored despite the sibling failure.
    assert good.read_bytes() == b"original\n"


def test_uninstall_removes_receipt_owned_retired_runtime(
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

    result = run_script(
        _installer(source_root),
        "--source-root",
        str(source_root),
        "--uninstall",
        env=env,
        cwd=tmp_path,
    )
    assert result.returncode == 0, result.stderr
    assert not retired_file.exists()
    assert not runtime_root.exists()
    assert not receipt_path.exists()


def test_failed_snapshot_restore_skips_reactivation_and_reports_both(
    repo_root: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A partially restored runtime is an unknown state: the prior scheduler
    must not be re-armed, and the raised error names the restore failure."""
    reconcile = _reconcile_module(repo_root)
    InstallError = reconcile.InstallError

    reactivated = []

    def fail_restore(snapshots):
        raise InstallError("injected restore failure")

    monkeypatch.setattr(reconcile, "_restore_snapshots", fail_restore)
    monkeypatch.setattr(
        reconcile,
        "_scheduler_reactivate",
        lambda *args: reactivated.append(args),
    )

    original = InstallError("original install failure")
    prior = type("Prior", (), {"kind": "systemd"})()

    with pytest.raises(InstallError) as caught:
        reconcile._rollback_transaction([], prior, tmp_path, "python", {}, original)

    message = str(caught.value)
    assert "original install failure" in message
    assert "injected restore failure" in message
    assert reactivated == []

#!/usr/bin/env python3
"""Which interpreter delegate.py re-execs, and which policy copies it trusts.

Every test here drives the executable trust gate through a real subprocess: the
gate runs at import time, so an in-process call would skip it entirely.
"""

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest
from _delegate_runtime_env import (
    _copied_plugin,
    _deployed_home,
    _install_offline_pyyaml,
    _policyless_launcher,
    _recorder_runtime_home,
    _run_guard,
    _site_packages,
    _trusted_policy_venv,
    _uv_install,
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


def test_deployed_home_editable_policy_is_trusted(tmp_path: Path) -> None:
    """Trusted source missing PyYAML in the launcher must still reach home runtime."""
    plugin = _copied_plugin(tmp_path)
    home = _deployed_home(tmp_path)
    launcher = _policyless_launcher(tmp_path)
    dependencies = subprocess.run(
        [
            str(launcher),
            "-c",
            "import importlib.util; "
            "assert importlib.util.find_spec('yaml') is None; "
            "assert importlib.util.find_spec('manifest_model_policy') is None",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert dependencies.returncode == 0, dependencies.stderr

    result = _run_guard(
        launcher,
        home,
        tmp_path,
        script=plugin / "scripts/delegate.py",
    )

    assert result.returncode == 0, result.stderr
    assert "Delegate tasks/reviews" in result.stdout
    assert "manifest-model-policy" not in result.stderr


def test_source_only_policy_rejects_shadow_before_runtime_reexec(
    tmp_path: Path,
) -> None:
    """Missing metadata/dependencies cannot make a shadow eligible for re-exec."""
    plugin = _copied_plugin(tmp_path)
    home = _deployed_home(tmp_path)
    shadow = plugin / "manifest_model_policy"
    shadow.mkdir()
    (shadow / "__init__.py").write_text(
        "raise RuntimeError('untrusted shadow executed')\n", encoding="utf-8"
    )

    result = _run_guard(
        _policyless_launcher(tmp_path),
        home,
        tmp_path,
        script=plugin / "scripts/delegate.py",
    )

    assert result.returncode == 2
    assert "invalid manifest-model-policy distribution" in result.stderr
    assert "untrusted shadow executed" not in result.stderr
    assert "Delegate tasks/reviews" not in result.stdout


@pytest.mark.parametrize("with_pyyaml", [True, False])
def test_session_start_captures_with_path_python_and_trusted_source_only(
    tmp_path: Path, with_pyyaml: bool
) -> None:
    """Trusted source captures with or without interpreter-provided PyYAML."""
    plugin = _copied_plugin(tmp_path)
    python = _policyless_launcher(tmp_path)
    if with_pyyaml:
        _install_offline_pyyaml(python.parent.parent)
    else:
        dependencies = subprocess.run(
            [
                str(python),
                "-c",
                "import importlib.util; assert importlib.util.find_spec('yaml') is None",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        assert dependencies.returncode == 0, dependencies.stderr
    home = tmp_path / "path-python-home"
    policy_source = home / ".claude/scripts/manifest_model_policy"
    policy_source.parent.mkdir(parents=True)
    shutil.copytree(
        Path(__file__).resolve().parents[2]
        / "configs/claude/scripts/manifest_model_policy",
        policy_source,
    )
    payload = {
        "hook_event_name": "SessionStart",
        "session_id": "path-python-session",
        "transcript_path": str(tmp_path / "transcript.jsonl"),
        "cwd": str(tmp_path),
    }
    environment = dict(os.environ)
    environment.update(
        {
            "HOME": str(home),
            "PYTHONPATH": "" if with_pyyaml else str(policy_source.parent),
        }
    )
    result = subprocess.run(
        [str(python), str(plugin / "scripts/session_hook.py")],
        cwd=tmp_path,
        env=environment,
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    captured = json.loads((home / ".manifest/delegate/sessions.json").read_text())[
        "path-python-session"
    ]
    assert captured["transcript_path"] == payload["transcript_path"]
    assert captured["cwd"] == payload["cwd"]
    assert isinstance(captured["captured_at"], (int, float))


def _create_orphan_delegation_record(
    python: Path,
    plugin: Path,
    tmp_path: Path,
    environment: dict[str, str],
) -> Path:
    create_job = (
        "import json, sys, time\n"
        f"sys.path.insert(0, {str(plugin)!r})\n"
        "from manifest_delegate import JobStore, WORKER_STARTUP_GRACE_SECONDS\n"
        f"store = JobStore(cwd={str(tmp_path)!r})\n"
        "record = store.create('codex')\n"
        "def mark_dead(value):\n"
        "    value.update(state='running', worker_pid=999999999, pgid=None, "
        "created_at=time.time() - WORKER_STARTUP_GRACE_SECONDS - 1)\n"
        "    return value\n"
        "store.mutate(record['job_id'], mark_dead)\n"
        "print(json.dumps({'record_path': "
        "store.job_dir(record['job_id']) + '/record.json'}))\n"
    )
    created = subprocess.run(
        [str(python), "-c", create_job],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    assert created.returncode == 0, created.stderr
    return Path(json.loads(created.stdout)["record_path"])


def test_session_end_reaps_orphan_with_path_python_and_trusted_source_only(
    tmp_path: Path,
) -> None:
    """Source-only hook imports must still reach SessionEnd's orphan reaper."""
    plugin = _copied_plugin(tmp_path)
    python = _policyless_launcher(tmp_path)
    home = tmp_path / "path-python-home"
    policy_source = home / ".claude/scripts/manifest_model_policy"
    policy_source.parent.mkdir(parents=True)
    shutil.copytree(
        Path(__file__).resolve().parents[2]
        / "configs/claude/scripts/manifest_model_policy",
        policy_source,
    )
    root = tmp_path / "delegations"
    environment = dict(os.environ)
    environment.update(
        {
            "HOME": str(home),
            "PYTHONPATH": str(policy_source.parent),
            "MANIFEST_DELEGATIONS_DIR": str(root),
        }
    )
    record_path = _create_orphan_delegation_record(
        python, plugin, tmp_path, environment
    )

    payload = {
        "hook_event_name": "SessionEnd",
        "session_id": "source-only-session",
        "cwd": str(tmp_path),
    }
    result = subprocess.run(
        [str(python), str(plugin / "scripts/session_hook.py")],
        cwd=tmp_path,
        env=environment,
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert json.loads(record_path.read_text())["state"] == "failed"


@pytest.mark.parametrize("valid_metadata", [True, False])
def test_session_start_uses_home_runtime_policy_metadata(
    tmp_path: Path, valid_metadata: bool
) -> None:
    """PATH Python must not bypass the home runtime's policy metadata."""
    plugin = _copied_plugin(tmp_path)
    home = _deployed_home(tmp_path)
    python = _policyless_launcher(tmp_path)
    if not valid_metadata:
        metadata = next(
            _site_packages(home / ".claude/.venv/bin/python").glob(
                "manifest_model_policy-*.dist-info/direct_url.json"
            )
        )
        metadata.write_text(
            json.dumps(
                {
                    "url": (tmp_path / "untrusted-policy").as_uri(),
                    "dir_info": {"editable": True},
                }
            ),
            encoding="utf-8",
        )
    environment = dict(os.environ)
    environment.update({"HOME": str(home), "PYTHONPATH": str(home / ".claude/scripts")})
    environment.pop("MANIFEST_DELEGATE_RUNTIME_REEXEC", None)
    payload = {
        "hook_event_name": "SessionStart",
        "session_id": "home-runtime-session",
        "transcript_path": str(tmp_path / "transcript.jsonl"),
        "cwd": str(tmp_path),
    }
    result = subprocess.run(
        [str(python), str(plugin / "scripts/session_hook.py")],
        cwd=tmp_path,
        env=environment,
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        check=False,
    )
    sessions_file = home / ".manifest/delegate/sessions.json"
    if valid_metadata:
        assert result.returncode == 0, result.stderr
        assert "home-runtime-session" in json.loads(sessions_file.read_text())
    else:
        assert result.returncode == 0, result.stderr
        assert "invalid manifest-model-policy distribution" in result.stderr
        assert not sessions_file.exists()


def test_session_start_skips_capture_when_trusted_runtime_cannot_exec(
    tmp_path: Path,
) -> None:
    """An unusable trusted runtime must not block session startup or capture."""
    plugin = _copied_plugin(tmp_path)
    home = _deployed_home(tmp_path)
    python = _policyless_launcher(tmp_path)
    trusted_python = home / ".claude/.venv/bin/python"
    trusted_python.unlink()
    trusted_python.write_bytes(b"invalid executable format\n")
    trusted_python.chmod(0o755)
    environment = dict(os.environ)
    environment.update({"HOME": str(home), "PYTHONPATH": str(home / ".claude/scripts")})
    environment.pop("MANIFEST_DELEGATE_RUNTIME_REEXEC", None)
    payload = {
        "hook_event_name": "SessionStart",
        "session_id": "invalid-runtime-session",
        "transcript_path": str(tmp_path / "transcript.jsonl"),
        "cwd": str(tmp_path),
    }

    result = subprocess.run(
        [str(python), str(plugin / "scripts/session_hook.py")],
        cwd=tmp_path,
        env=environment,
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "Traceback" not in result.stderr
    assert not (home / ".manifest/delegate/sessions.json").exists()


def test_editable_policy_outside_the_trusted_home_is_rejected(tmp_path: Path) -> None:
    """Same editable shape, planted outside ~/.claude/scripts, stays untrusted."""
    plugin = _copied_plugin(tmp_path)
    home = _deployed_home(tmp_path)
    attacker = tmp_path / "attacker-scripts"
    attacker.mkdir()
    shutil.copytree(
        home / ".claude/scripts/manifest_model_policy",
        attacker / "manifest_model_policy",
    )
    _uv_install(
        home / ".claude/.venv/bin/python",
        "--reinstall",
        "--editable",
        str(attacker / "manifest_model_policy"),
    )

    result = _run_guard(
        _policyless_launcher(tmp_path),
        home,
        tmp_path,
        script=plugin / "scripts/delegate.py",
    )

    assert result.returncode == 2
    assert "invalid manifest-model-policy distribution" in result.stderr
    assert "Delegate tasks/reviews" not in result.stdout


def test_editable_metadata_must_name_the_path_it_imports_from(tmp_path: Path) -> None:
    """A trusted import path cannot launder metadata that points somewhere else.

    The attacker owns the distribution record (editable, from their own tree)
    while an unrelated legitimate `.pth` still puts `~/.claude/scripts` first on
    sys.path, so the module imports from the trusted location. Only comparing
    `direct_url` against that same location rejects this.
    """
    plugin = _copied_plugin(tmp_path)
    home = _deployed_home(tmp_path)
    attacker = tmp_path / "attacker-tree"
    attacker.mkdir()
    shutil.copytree(
        home / ".claude/scripts/manifest_model_policy",
        attacker / "manifest_model_policy",
    )
    python = home / ".claude/.venv/bin/python"
    _uv_install(
        python, "--reinstall", "--editable", str(attacker / "manifest_model_policy")
    )
    # Sorts before the attacker's `_manifest_model_policy.pth`, so the trusted
    # directory reaches sys.path first and wins the import.
    (_site_packages(python) / "_a_trusted_scripts.pth").write_text(
        f"{home / '.claude/scripts'}\n", encoding="utf-8"
    )
    origin = subprocess.run(
        [
            str(python),
            "-c",
            "import importlib.util, pathlib; "
            "print(pathlib.Path("
            "importlib.util.find_spec('manifest_model_policy').origin).resolve())",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert origin.returncode == 0, origin.stderr
    assert Path(origin.stdout.strip()).is_relative_to(home), (
        "precondition failed: the import did not resolve to the trusted tree, "
        "so this test would pass for the wrong reason"
    )

    result = _run_guard(
        _policyless_launcher(tmp_path),
        home,
        tmp_path,
        script=plugin / "scripts/delegate.py",
    )

    assert result.returncode == 2
    assert "invalid manifest-model-policy distribution" in result.stderr
    assert "Delegate tasks/reviews" not in result.stdout


def test_reexec_that_still_lacks_policy_names_the_runtime_not_tampering(
    tmp_path: Path,
) -> None:
    """The second pass reports a runtime gap, not a shadowed distribution.

    Reusing the tamper wording here sent diagnosis hunting a planted copy that
    was never there, so the two outcomes must stay distinguishable.
    """
    home = tmp_path / "empty-home"
    home.mkdir()

    result = _run_guard(
        _policyless_launcher(tmp_path),
        home,
        tmp_path,
        MANIFEST_DELEGATE_RUNTIME_REEXEC="1",
    )

    assert result.returncode == 2
    assert "did not provide manifest-model-policy" in result.stderr
    assert "invalid manifest-model-policy distribution" not in result.stderr
    assert "Delegate tasks/reviews" not in result.stdout


def test_non_object_editable_metadata_is_untrusted_not_absent(tmp_path: Path) -> None:
    """Unreadable editable metadata must stay a hard failure, not a missing one.

    `direct_url.json` holding valid JSON that is not an object makes the field
    lookups raise. If that escapes to the distribution-level handler the gate
    reports the policy as merely absent and `--help` answers normally, turning a
    tamper signal into a benign one.
    """
    plugin = _copied_plugin(tmp_path)
    home = _deployed_home(tmp_path)
    python = tmp_path / "deployed-venv/bin/python"
    metadata = (
        _site_packages(python) / "manifest_model_policy-0.1.0.dist-info/direct_url.json"
    )
    metadata.write_text("[1, 2]", encoding="utf-8")
    # Without a home runtime to re-exec into, the verdict is decided in this
    # process, so the exit distinguishes "untrusted" from "absent" directly.
    (home / ".claude/.venv").unlink()

    result = _run_guard(python, home, tmp_path, script=plugin / "scripts/delegate.py")

    assert result.returncode == 2
    assert "invalid manifest-model-policy distribution" in result.stderr
    assert "Delegate tasks/reviews" not in result.stdout

"""Offline readiness checks for the deployed fail-closed Stop hook."""

from __future__ import annotations

import importlib.util
import json
import os
import stat
import subprocess
import sys
import time
from pathlib import Path

import manifest_model_policy
import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "configs/claude/scripts/hook_smoke.py"
PLUGIN_ROOT = REPO_ROOT / "plugins/manifest-delegate"


def _load_module():
    spec = importlib.util.spec_from_file_location("hook_smoke", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _fake_jq(binary_dir: Path) -> None:
    jq = binary_dir / "jq"
    jq.write_text(
        """#!/usr/bin/env python3
import json
import sys

args = sys.argv[1:]
path = args[-1]
expression = next((arg for arg in args[:-1] if not arg.startswith('-')), '')
try:
    with open(path, encoding='utf-8') as handle:
        document = json.load(handle)
except Exception:
    raise SystemExit(1)
if '-c' in args:
    print(json.dumps(
        {'decision': document.get('decision'), 'reason': document.get('reason')},
        separators=(',', ':'),
    ))
    raise SystemExit(0)
if 'stop_hook_active == true' in expression:
    raise SystemExit(0 if document.get('stop_hook_active') is True else 1)
valid = isinstance(document, dict)
if '.decision' in expression:
    valid = (
        valid
        and document.get('decision') in {'approve', 'block'}
        and isinstance(document.get('reason'), str)
        and bool(document['reason'])
    )
raise SystemExit(0 if valid else 1)
""",
        encoding="utf-8",
    )
    jq.chmod(0o755)


def _isolated_environment(tmp_path: Path, *, with_runtime: bool) -> dict[str, str]:
    home = tmp_path / "home"
    state = tmp_path / "state"
    config = tmp_path / "xdg-config"
    binary_dir = tmp_path / "bin"
    for path in (home, state, config, binary_dir):
        path.mkdir(parents=True)
    _fake_jq(binary_dir)
    policy_module_file = getattr(manifest_model_policy, "__file__", None)
    if policy_module_file is None:
        pytest.fail(
            "test fixture requires manifest_model_policy.__file__ to locate "
            "the managed interpreter's imported policy package"
        )
    policy_source = Path(policy_module_file).resolve().parent
    policy_link = home / ".claude/scripts/manifest_model_policy"
    policy_link.parent.mkdir(parents=True)
    policy_link.symlink_to(policy_source, target_is_directory=True)
    if with_runtime:
        runtime = home / ".claude/.venv"
        runtime.parent.mkdir(parents=True, exist_ok=True)
        runtime.symlink_to(Path(sys.prefix), target_is_directory=True)
    return {
        **os.environ,
        "HOME": str(home),
        "XDG_STATE_HOME": str(state),
        "XDG_CONFIG_HOME": str(config),
        "PATH": f"{binary_dir}{os.pathsep}{os.environ.get('PATH', '')}",
        "PYTHONDONTWRITEBYTECODE": "1",
    }


def _run_smoke(
    tmp_path: Path,
    *,
    plugin_root: Path = PLUGIN_ROOT,
    with_runtime: bool = True,
    timeout_seconds: str = "30",
) -> subprocess.CompletedProcess[str]:
    environment = _isolated_environment(tmp_path, with_runtime=with_runtime)
    state_dir = tmp_path / "health"
    return subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--json",
            "--plugin-root",
            str(plugin_root),
            "--state-dir",
            str(state_dir),
            "--timeout-seconds",
            timeout_seconds,
        ],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
        timeout=35,
    )


def test_smoke_proves_clean_block_and_recursion_paths_and_writes_receipt(tmp_path):
    result = _run_smoke(tmp_path)

    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    assert report["status"] == "ok"
    assert {item["name"]: item["status"] for item in report["checks"]} == {
        "clean_review": "ok",
        "invalid_review": "ok",
        "recursion_guard": "ok",
    }
    assert set(report["hashes"]) == {
        "delegate.py",
        "hooks.json",
        "stop_gate_hook.py",
        "stop_gate_hook.sh",
    }
    assert all(len(value) == 64 for value in report["hashes"].values())

    receipt = tmp_path / "health/hooks.json"
    assert json.loads(receipt.read_text(encoding="utf-8")) == report
    assert stat.S_IMODE(receipt.stat().st_mode) == 0o600
    assert "prompt" not in result.stdout.lower()


def test_missing_managed_runtime_is_degraded_and_still_records_receipt(tmp_path):
    result = _run_smoke(tmp_path, with_runtime=False)

    assert result.returncode == 1
    report = json.loads(result.stdout)
    assert report["status"] == "degraded"
    assert report["findings"] == ["runtime_unavailable"]
    assert (tmp_path / "health/hooks.json").is_file()


def test_installed_plugin_index_is_the_default_plugin_authority(tmp_path, monkeypatch):
    module = _load_module()
    home = tmp_path / "home"
    index = home / ".claude/plugins/installed_plugins.json"
    index.parent.mkdir(parents=True)
    index.write_text(
        json.dumps(
            {
                "plugins": {
                    "manifest-delegate@manifest": [
                        {"installPath": str(PLUGIN_ROOT)}
                    ]
                }
            }
        ),
        encoding="utf-8",
    )

    assert module.resolve_plugin_root(home, None) == PLUGIN_ROOT.resolve()


@pytest.mark.skipif(os.name != "posix", reason="process-group deadline is POSIX-only")
def test_aggregate_deadline_kills_a_sleeping_launcher(tmp_path):
    plugin = tmp_path / "plugin"
    (plugin / "hooks").mkdir(parents=True)
    (plugin / "scripts").mkdir()
    (plugin / "hooks/hooks.json").write_text(
        json.dumps(
            {
                "hooks": {
                    "Stop": [
                        {
                            "hooks": [
                                {
                                    "type": "command",
                                    "command": "/bin/sh \"${CLAUDE_PLUGIN_ROOT}/scripts/stop_gate_hook.sh\"",
                                    "timeout": 900,
                                }
                            ]
                        }
                    ]
                }
            }
        ),
        encoding="utf-8",
    )
    launcher = plugin / "scripts/stop_gate_hook.sh"
    launcher.write_text("#!/bin/sh\nsleep 20\n", encoding="utf-8")
    launcher.chmod(0o755)
    for name in ("stop_gate_hook.py", "delegate.py"):
        (plugin / "scripts" / name).write_text("# fixture\n", encoding="utf-8")

    started = time.monotonic()
    result = _run_smoke(
        tmp_path,
        plugin_root=plugin,
        with_runtime=True,
        timeout_seconds="3",
    )
    elapsed = time.monotonic() - started

    assert result.returncode == 1
    assert elapsed < 3.5
    report = json.loads(result.stdout)
    assert report["status"] == "degraded"
    assert "timeout" in report["findings"]

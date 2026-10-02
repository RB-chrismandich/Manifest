"""Stale-receipt health-hook tests for merge_runtime_settings.py.

A receipt whose recorded wrapper no longer matches the installed file (deleted
or tampered) is not ownership evidence: the merge must retire the broken
SessionStart hook instead of preserving it.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from tests.python.plugin_runtime.health_test_helpers import (
    write_valid_health_receipt,
)

REPO = Path(__file__).resolve().parents[2]
MERGER = REPO / "configs/claude/scripts/merge_runtime_settings.py"


@pytest.fixture
def deployment(tmp_path, monkeypatch):
    home = tmp_path / "ambient"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    for key in (
        "CLAUDE_CODE_SUBAGENT_MODEL",
        "CLAUDE_CODE_SUBAGENT_MODEL_FORCE",
        "CLAUDE_CONFIG_DIR",
    ):
        monkeypatch.delenv(key, raising=False)
    target = tmp_path / "target/.claude/settings.json"
    target.parent.mkdir(parents=True)
    return target


def _merge(target, version="2.1.263"):
    return subprocess.run(
        [
            sys.executable,
            str(MERGER),
            str(REPO / "configs/claude/settings.runtime.json"),
            str(target),
            "--host-version",
            version,
        ],
        text=True,
        capture_output=True,
        check=False,
    )


def _session_commands(settings: dict) -> list[str]:
    return [
        hook["command"]
        for entry in settings.get("hooks", {}).get("SessionStart", [])
        for hook in entry.get("hooks", [])
    ]


def _owned_hook_setup(deployment, monkeypatch, tmp_path):
    """Install a valid health receipt + hook; return (command, wrapper)."""
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("OMP_AGENT_DIR", str(tmp_path / "omp-agent"))
    monkeypatch.delenv("PI_CODING_AGENT_DIR", raising=False)
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    source_root = tmp_path / "source"
    source_root.mkdir()
    receipt_path = tmp_path / "state" / "manifest" / "health" / "installation.json"
    receipt_path.parent.mkdir(parents=True)
    command = write_valid_health_receipt(
        receipt_path, source_root, dict(os.environ)
    )
    deployment.write_text(
        json.dumps(
            {
                "hooks": {
                    "SessionStart": [
                        {"hooks": [{"type": "command", "command": command}]}
                    ]
                }
            }
        )
    )
    return command, Path(command)


def test_deleted_wrapper_receipt_retires_hook(deployment, monkeypatch, tmp_path):
    command, wrapper = _owned_hook_setup(deployment, monkeypatch, tmp_path)
    wrapper.unlink()

    assert _merge(deployment).returncode == 0
    commands = _session_commands(json.loads(deployment.read_text()))
    assert command not in commands


def test_tampered_wrapper_receipt_retires_hook(
    deployment, monkeypatch, tmp_path
):
    command, wrapper = _owned_hook_setup(deployment, monkeypatch, tmp_path)
    wrapper.write_text("# tampered\n", encoding="utf-8")

    assert _merge(deployment).returncode == 0
    commands = _session_commands(json.loads(deployment.read_text()))
    assert command not in commands

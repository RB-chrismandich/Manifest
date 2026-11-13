"""Focused migration coverage for legacy guidance hook commands."""

import json
import shlex
import subprocess
import sys
from pathlib import Path

import pytest

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
    target = tmp_path / "target with spaces/.claude/settings.json"
    target.parent.mkdir(parents=True)
    return target


def test_legacy_quoted_guidance_hook_is_migrated_without_duplicate(deployment):
    command = shlex.quote(str(deployment.parent / "scripts/guidance_hint.py"))
    unrelated = "echo preserve-me"
    deployment.write_text(
        json.dumps(
            {
                "hooks": {
                    "PreToolUse": [
                        {
                            "matcher": "Bash",
                            "hooks": [
                                {"type": "command", "command": command},
                                {"type": "command", "command": unrelated},
                            ],
                        }
                    ]
                }
            }
        )
    )
    result = subprocess.run(
        [
            sys.executable,
            str(MERGER),
            str(REPO / "configs/claude/settings.runtime.json"),
            str(deployment),
            "--host-version",
            "2.1.250",
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    hooks = json.loads(deployment.read_text())["hooks"]["PreToolUse"]
    guidance = [
        h
        for entry in hooks
        for h in entry["hooks"]
        if "guidance_hint.py" in h.get("command", "")
    ]
    assert len(guidance) == 1
    assert (
        " run --quiet --no-project --with pyyaml --python 3.11 "
        in guidance[0]["command"]
    )
    assert any(h.get("command") == unrelated for entry in hooks for h in entry["hooks"])

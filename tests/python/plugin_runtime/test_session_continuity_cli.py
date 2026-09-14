"""CLI and hook-integration behavior tests for session continuity."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from tests.python.plugin_runtime.session_continuity_helpers import (
    _checkpoint,
    _completed,
    _precompact,
)
from tests.python.plugin_runtime.session_continuity_helpers import (
    repo_root as repo_root,
)
from tests.python.plugin_runtime.session_continuity_helpers import (
    runtime as runtime,
)
from tests.python.plugin_runtime.session_continuity_helpers import (
    state_home as state_home,
)


def test_claude_hooks_confirm_compaction_through_real_lifecycle_sequence(
    repo_root: Path, state_home: Path
) -> None:
    script = (
        repo_root
        / "plugins/manifest-workspace/skills/session-checkpoint/scripts/session_continuity.py"
    )
    env = {
        **os.environ,
        "XDG_STATE_HOME": str(state_home),
        "PYTHONDONTWRITEBYTECODE": "1",
    }

    for event in (_precompact(), _precompact(), _completed(), _completed()):
        result = subprocess.run(
            [sys.executable, "-B", str(script), "hook-event", "--harness", "claude"],
            input=json.dumps(event),
            text=True,
            capture_output=True,
            env=env,
            check=False,
        )
        assert result.returncode == 0, result.stderr
        assert result.stdout == ""

    status = subprocess.run(
        [
            sys.executable,
            "-B",
            str(script),
            "status",
            "--harness",
            "claude",
            "--session-id",
            "primary",
        ],
        text=True,
        capture_output=True,
        env=env,
        check=False,
    )
    assert status.returncode == 0, status.stderr
    assert json.loads(status.stdout)["compaction_count"] == 1


def test_workspace_declares_claude_compaction_hooks_and_continuity_runtime(
    repo_root: Path,
) -> None:
    import yaml

    bundle = repo_root / "plugins/manifest-workspace"
    hooks = json.loads((bundle / "hooks/session-continuity.json").read_text())
    assert set(hooks["hooks"]) == {"PreCompact", "SessionStart"}
    precompact = hooks["hooks"]["PreCompact"][0]
    session_start = hooks["hooks"]["SessionStart"][0]
    assert precompact["matcher"] == "manual|auto"
    assert session_start["matcher"] == "compact"
    for entry in (precompact, session_start):
        command = entry["hooks"][0]["command"]
        assert command == (
            'python3 "${CLAUDE_PLUGIN_ROOT}/skills/session-checkpoint/scripts/'
            'session_continuity.py" hook-event --harness claude'
        )

    contract = yaml.safe_load((bundle / "manifest-capabilities.yml").read_text())
    assert {row["id"] for row in contract["components"]["runtime"]} >= {
        "session-continuity-scripts"
    }
    continuity_hooks = {
        row["id"]: row
        for row in contract["components"]["hooks"]
        if row["path"] == "hooks/session-continuity.json"
    }
    assert set(continuity_hooks) == {"claude-compaction-continuity"}
    for hook in continuity_hooks.values():
        assert hook["compatibility"]["claude"]["mode"] == "native"
        for harness in ("codex", "gemini", "cursor", "antigravity", "devin"):
            assert hook["compatibility"][harness]["mode"] == "not_applicable"


def test_hook_commands_run_when_plugin_root_contains_spaces(
    runtime, repo_root: Path, state_home: Path, tmp_path: Path
) -> None:
    bundle = repo_root / "plugins/manifest-workspace"
    plugin_root = tmp_path / "plugin root"
    plugin_root.symlink_to(bundle, target_is_directory=True)
    hooks = json.loads((bundle / "hooks/session-continuity.json").read_text())
    commands = [
        hooks["hooks"]["PreCompact"][0]["hooks"][0]["command"],
        hooks["hooks"]["SessionStart"][0]["hooks"][0]["command"],
    ]
    environment = {
        **os.environ,
        "CLAUDE_PLUGIN_ROOT": str(plugin_root),
        "XDG_STATE_HOME": str(state_home),
        "PYTHONDONTWRITEBYTECODE": "1",
    }

    for command, event in zip(commands, (_precompact(), _completed()), strict=True):
        result = subprocess.run(
            ["/bin/sh", "-c", command],
            input=json.dumps(event),
            text=True,
            capture_output=True,
            env=environment,
            check=False,
        )
        assert result.returncode == 0, result.stderr

    assert (
        runtime.SessionContinuityStore(state_home)
        .status("primary", "claude")
        .compaction_count
        == 1
    )


def test_cli_writes_checkpoint_and_emits_one_safe_boundary_reminder(
    repo_root: Path, state_home: Path
) -> None:
    script = (
        repo_root
        / "plugins/manifest-workspace/skills/session-checkpoint/scripts/session_continuity.py"
    )
    env = {**os.environ, "XDG_STATE_HOME": str(state_home)}
    for event in (_precompact(), _completed(), _precompact(), _completed()):
        result = subprocess.run(
            [sys.executable, str(script), "hook-event", "--harness", "claude"],
            input=json.dumps(event),
            text=True,
            capture_output=True,
            env=env,
            check=False,
        )
        assert result.returncode == 0, result.stderr

    written = subprocess.run(
        [sys.executable, str(script), "checkpoint", "--input", "-"],
        input=json.dumps(_checkpoint()),
        text=True,
        capture_output=True,
        env=env,
        check=False,
    )
    assert written.returncode == 0, written.stderr
    checkpoint_path = Path(json.loads(written.stdout)["checkpoint_path"])
    assert checkpoint_path.is_file()

    command = [
        sys.executable,
        str(script),
        "recommend",
        "--session-id",
        "primary",
        "--boundary",
        "safe",
        "--checkpoint",
        str(checkpoint_path),
    ]
    first = subprocess.run(
        command, text=True, capture_output=True, env=env, check=False
    )
    second = subprocess.run(
        command, text=True, capture_output=True, env=env, check=False
    )
    assert json.loads(first.stdout)["recommend_fresh_session"] is True
    assert json.loads(second.stdout)["reason"] == "already-reminded"


def test_cli_revalidation_reports_authority_changes(
    repo_root: Path, state_home: Path
) -> None:
    script = (
        repo_root
        / "plugins/manifest-workspace/skills/session-checkpoint/scripts/session_continuity.py"
    )
    checkpoint_path = state_home / "fixture.json"
    env = {**os.environ, "XDG_STATE_HOME": str(state_home)}
    written = subprocess.run(
        [sys.executable, str(script), "checkpoint", "--input", "-"],
        input=json.dumps(_checkpoint()),
        text=True,
        capture_output=True,
        env=env,
        check=False,
    )
    assert written.returncode == 0, written.stderr
    checkpoint_path = Path(json.loads(written.stdout)["checkpoint_path"])

    result = subprocess.run(
        [
            sys.executable,
            str(script),
            "verify",
            "--checkpoint",
            str(checkpoint_path),
            "--repository-json",
            json.dumps(
                {
                    "path": "/repo",
                    "branch": "feature",
                    "head": "abc123",
                    "dirty_tree": [" M retained-change.py"],
                }
            ),
            "--operations-json",
            "[]",
        ],
        text=True,
        capture_output=True,
        env=env,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    assert report["trusted"] is False
    assert report["git_changes"] == ["branch"]
    assert report["ownership_changes"] == ["job-17"]
    assert report["continuation_goal"].startswith("Continue implementing")

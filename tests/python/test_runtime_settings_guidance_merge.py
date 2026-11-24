"""Locked guidance migration preserves unrelated settings and is idempotent."""

import json
import shlex
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
MERGER = REPO / "configs/claude/scripts/merge_runtime_settings.py"
SOURCE = REPO / "configs/claude/settings.runtime.json"
SHIPPED = "~/.claude/.venv/bin/python3 -I ~/.claude/scripts/guidance_hint.py"


@pytest.fixture
def deployment(tmp_path, monkeypatch):
    home = tmp_path / "ambient"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("XDG_STATE_HOME", str(home / "state"))
    for key in (
        "CLAUDE_CODE_SUBAGENT_MODEL",
        "CLAUDE_CODE_SUBAGENT_MODEL_FORCE",
        "CLAUDE_CONFIG_DIR",
    ):
        monkeypatch.delenv(key, raising=False)
    target = tmp_path / "target with spaces/.claude/settings.json"
    target.parent.mkdir(parents=True)
    return target


def hook(command):
    return {"type": "command", "command": command}


def merge_twice(deployment, document):
    deployment.write_text(json.dumps(document))
    first = None
    for _ in range(2):
        result = subprocess.run(
            [
                sys.executable,
                str(MERGER),
                str(SOURCE),
                str(deployment),
                "--host-version",
                "2.1.250",
            ],
            text=True,
            capture_output=True,
            check=False,
        )
        assert result.returncode == 0, result.stderr
        current = deployment.read_bytes()
        if first is not None:
            assert current == first
        first = current
    return json.loads(first)


def canonical(deployment):
    return shlex.join(
        [
            str(deployment.parent / ".venv/bin/python3"),
            "-I",
            str(deployment.parent / "scripts/guidance_hint.py"),
        ]
    )


def launchers(deployment):
    script = str(deployment.parent / "scripts/guidance_hint.py")
    quoted = shlex.quote(script)
    return [
        "~/.claude/scripts/guidance_hint.py",
        script,
        quoted,
        '"~/.claude/scripts/guidance_hint.py"',
        "python " + quoted,
        "python3 -I " + quoted,
        "/opt/python3.11 " + quoted,
        "~/.local/bin/uv run --no-project --with pyyaml --python 3.11 " + quoted,
        "/opt/uv run --quiet --no-project --with pyyaml --python 3.11 " + quoted,
        SHIPPED,
        canonical(deployment),
    ]


def test_all_owned_launchers_collapse_preserving_order_and_permissions(deployment):
    variants = launchers(deployment)
    unrelated = [
        "echo preserve-first # user's hook",
        "python3 /opt/other/guidance_hint.py",
        "echo ~/.claude/scripts/guidance_hint.py",
        "uv run --with other ~/.claude/scripts/guidance_hint.py",
        "python3 ~/.claude/scripts/guidance_hint.py --help",
        "python3 'unterminated",
        "echo preserve-last",
    ]
    hooks = [hook(unrelated[0]), hook(variants[0]), hook(unrelated[1])]
    hooks += [hook(command) for command in variants[1:]]
    hooks += [hook(command) for command in unrelated[2:]]
    grants = ["Bash(git status:*)", "Bash(python3 /opt/other/guidance_hint.py:*)"]
    document = {
        "model": "user-model",
        "skillListingBudgetFraction": 0.17,
        "permissions": {
            "allow": grants + [f"Bash({command}:*)" for command in variants] * 2,
            "deny": ["Bash(secret:*)"],
            "defaultMode": "default",
        },
        "hooks": {
            "PreToolUse": [
                {"matcher": "Bash", "hooks": hooks, "userMetadata": "keep"},
                {"matcher": "Bash", "hooks": [hook(canonical(deployment))]},
                {"matcher": "Read", "hooks": [hook("echo read")]},
            ]
        },
    }
    merged = merge_twice(deployment, document)
    entries = merged["hooks"]["PreToolUse"]
    commands = [h["command"] for e in entries for h in e["hooks"]]
    assert commands[: len(unrelated) + 1] == [
        unrelated[0],
        canonical(deployment),
        *unrelated[1:],
    ]
    assert commands.count(canonical(deployment)) == 1
    assert entries[0]["userMetadata"] == "keep"
    assert {"matcher": "Read", "hooks": [hook("echo read")]} in entries
    allow = merged["permissions"]["allow"]
    assert allow[:2] == grants
    assert [r for r in allow if "guidance_hint.py" in r] == [
        grants[1],
        f"Bash({SHIPPED}:*)",
    ]
    assert merged["permissions"]["deny"] == ["Bash(secret:*)"]
    assert merged["permissions"]["defaultMode"] == "default"
    assert merged["model"] == "user-model"
    assert merged["skillListingBudgetFraction"] == 0.17


@pytest.mark.parametrize(
    "event,matcher",
    [
        ("PreToolUse", "Read"),
        ("PostToolUse", "Bash"),
        ("SessionStart", None),
    ],
)
def test_direct_owned_retirement_outside_bash_is_preserved(deployment, event, matcher):
    direct = launchers(deployment)[:4]
    entry = {"hooks": [hook(c) for c in direct] + [hook("echo keep")]}
    if matcher is not None:
        entry["matcher"] = matcher
    merged = merge_twice(deployment, {"hooks": {event: [entry]}})
    preserved = next(
        e for e in merged["hooks"][event] if hook("echo keep") in e["hooks"]
    )
    assert preserved == {**entry, "hooks": [hook("echo keep")]}


@pytest.mark.parametrize("index", range(11))
def test_each_supported_launcher_migrates_individually(deployment, index):
    command = launchers(deployment)[index]
    merged = merge_twice(
        deployment,
        {
            "hooks": {"PreToolUse": [{"matcher": "Bash", "hooks": [hook(command)]}]},
            "permissions": {"allow": [f"Bash({command}:*)"]},
        },
    )
    commands = [
        h["command"]
        for e in merged["hooks"]["PreToolUse"]
        for h in e["hooks"]
        if "guidance_hint.py" in h.get("command", "")
    ]
    assert commands == [canonical(deployment)]
    assert [r for r in merged["permissions"]["allow"] if "guidance_hint.py" in r] == [
        f"Bash({SHIPPED}:*)",
    ]


def test_shipped_commands_have_no_dependency_resolution():
    claude = json.loads(SOURCE.read_text())
    commands = [
        h["command"]
        for e in claude["hooks"]["PreToolUse"]
        for h in e["hooks"]
        if "guidance_hint.py" in h.get("command", "")
    ]
    assert commands == [SHIPPED]
    cursor = json.loads((REPO / "configs/cursor/hooks.json").read_text())
    assert cursor["hooks"]["beforeShellExecution"] == [
        {
            "command": "~/.claude/.venv/bin/python3 -I ~/.cursor/scripts/guidance_hint.py",
            "type": "command",
        }
    ]

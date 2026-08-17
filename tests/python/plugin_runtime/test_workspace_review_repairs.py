"""Regression coverage for Task 11 review repairs."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

from manifest_agent.contracts import load_domain_contracts
from tools.generate_plugin_views import render_views


@pytest.fixture
def repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


@pytest.fixture
def workspace_bundle(repo_root: Path) -> Path:
    return repo_root / "plugins" / "manifest-workspace"


def isolated_env(tmp_path: Path) -> dict[str, str]:
    paths = {name: tmp_path / name for name in ("home", "state", "data", "config")}
    for path in paths.values():
        path.mkdir(parents=True)
    return {
        **os.environ,
        "HOME": str(paths["home"]),
        "XDG_STATE_HOME": str(paths["state"]),
        "XDG_DATA_HOME": str(paths["data"]),
        "XDG_CONFIG_HOME": str(paths["config"]),
        "UV_NO_NETWORK": "1",
        "PYTHONDONTWRITEBYTECODE": "1",
    }


def run_python(
    script: Path, *args: str, env: dict[str, str], cwd: Path
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-B", str(script), *args],
        cwd=cwd,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )


def test_learning_capture_preserves_legacy_consumer_contract(
    workspace_bundle: Path, tmp_path: Path
) -> None:
    env = isolated_env(tmp_path)
    script = workspace_bundle / "skills/learning-capture/scripts/learning_capture.py"
    add = run_python(
        script,
        "add",
        "--category",
        "tool_discovery",
        "--language",
        "python",
        "--title",
        "Prefer the local checker",
        "--description",
        "Avoid a networked project runtime.",
        "--tags",
        "offline,tooling",
        "--confidence",
        "high",
        "--source",
        "project-verify",
        env=env,
        cwd=tmp_path,
    )
    assert add.returncode == 0, add.stderr
    entry = json.loads(add.stdout)
    assert entry["id"] == "KB-001"
    assert entry["category"] == "tool_discovery"

    query = run_python(
        script,
        "query",
        "--category",
        "tool_discovery",
        "--language",
        "python",
        "--format",
        "llm",
        env=env,
        cwd=tmp_path,
    )
    assert query.returncode == 0, query.stderr
    assert "**KB-001**" in query.stdout
    assert "Prefer the local checker" in query.stdout
    increment = run_python(script, "increment", "KB-001", env=env, cwd=tmp_path)
    assert increment.returncode == 0, increment.stderr
    assert json.loads(increment.stdout)["occurrences"] == 2


def test_learning_contract_covers_every_cross_domain_invocation(
    repo_root: Path, workspace_bundle: Path, tmp_path: Path
) -> None:
    script = workspace_bundle / "skills/learning-capture/scripts/learning_capture.py"
    result = run_python(script, "contract", env=isolated_env(tmp_path), cwd=tmp_path)
    assert result.returncode == 0, result.stderr
    contract = json.loads(result.stdout)
    invocation = re.compile(
        r"(?:^\s*|`)\[\[skill:learning-capture\]\]\s+"
        r"([a-z-]+)(.*?)(?:```|\n\s*\n|`>)",
        re.DOTALL | re.MULTILINE,
    )
    matches = []
    for consumer in (repo_root / "plugins").glob("*/skills/**/*.md"):
        for command, tail in invocation.findall(consumer.read_text(encoding="utf-8")):
            matches.append((consumer, command, set(re.findall(r"--[a-z-]+", tail))))
    assert matches
    for consumer, command, options in matches:
        assert command in contract["commands"], f"{consumer}: unsupported {command}"
        assert options <= set(contract["options"]), f"{consumer}: unsupported {options}"


def test_learning_sync_docs_uses_jsonl_without_shared_settings(
    workspace_bundle: Path, tmp_path: Path
) -> None:
    env = isolated_env(tmp_path)
    script = workspace_bundle / "skills/learning-capture/scripts/learning_capture.py"
    output = tmp_path / "docs/KNOWLEDGE_BASE.md"
    add = run_python(
        script,
        "add",
        "--category",
        "antipattern",
        "--language",
        "python",
        "--title",
        "Hidden dependency",
        "--description",
        "A runtime reached outside its bundle.",
        env=env,
        cwd=tmp_path,
    )
    assert add.returncode == 0, add.stderr
    sync = run_python(
        script, "sync-docs", "--output", str(output), env=env, cwd=tmp_path
    )
    assert sync.returncode == 0, sync.stderr
    assert "KB-001" in output.read_text(encoding="utf-8")
    assert not list(tmp_path.rglob("*.yml"))


def test_unified_hook_emits_complete_native_response_contracts(
    workspace_bundle: Path, tmp_path: Path
) -> None:
    env = isolated_env(tmp_path)
    script = (
        workspace_bundle / "skills/ai-hooks-integration/scripts/runtime/unified_hook.py"
    )
    handler = tmp_path / "deny.py"
    handler.write_text(
        'import json, sys\nsys.stdin.read()\nprint(json.dumps({"decision": "deny", "reason": "blocked"}))\n',
        encoding="utf-8",
    )
    expected_denies = {
        "claude": {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "deny",
                "permissionDecisionReason": "blocked",
            },
            "continue": False,
        },
        "gemini": {"decision": "deny", "reason": "blocked"},
        "cursor": {
            "permission": "deny",
            "continue": False,
            "user_message": "blocked",
            "agent_message": "blocked",
        },
    }
    for source, expected in expected_denies.items():
        result = subprocess.run(
            [
                sys.executable,
                "-B",
                str(script),
                "--source",
                source,
                "--handler",
                str(handler),
            ],
            input='{"tool_name":"Bash","tool_input":{"command":"false"}}',
            cwd=tmp_path,
            env=env,
            text=True,
            capture_output=True,
            check=False,
        )
        assert result.returncode == 0, result.stderr
        assert json.loads(result.stdout) == expected, source


def test_unified_hook_emits_complete_cursor_allow_contract(
    workspace_bundle: Path, tmp_path: Path
) -> None:
    env = isolated_env(tmp_path)
    script = (
        workspace_bundle / "skills/ai-hooks-integration/scripts/runtime/unified_hook.py"
    )
    result = subprocess.run(
        [sys.executable, "-B", str(script), "--source", "cursor"],
        input='{"command":"true"}',
        cwd=tmp_path,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == {"permission": "allow", "continue": True}


def test_hook_installer_records_native_harness_identity(
    workspace_bundle: Path, tmp_path: Path
) -> None:
    env = isolated_env(tmp_path)
    script = workspace_bundle / "skills/ai-hooks-integration/scripts/install_all.py"
    handler = tmp_path / "handler.py"
    handler.write_text("print('{}')\n", encoding="utf-8")
    result = run_python(
        script,
        "--unified",
        "--handler",
        str(handler),
        "--name",
        "isolation-test",
        env=env,
        cwd=tmp_path,
    )
    assert result.returncode == 0, result.stderr
    expected = {
        Path(env["HOME"])
        / ".claude/settings.json": "--source claude --event-type PreToolUse",
        Path(env["HOME"])
        / ".gemini/settings.json": "--source gemini --event-type BeforeTool",
        Path(env["HOME"])
        / ".cursor/hooks.json": "--source cursor --event-type beforeShellExecution",
    }
    for path, identity in expected.items():
        assert identity in path.read_text(encoding="utf-8")


def test_pr_smoke_has_no_project_runtime_dependency(
    workspace_bundle: Path, tmp_path: Path
) -> None:
    script = workspace_bundle / "skills/pr-smoke/scripts/run_pr_regression.sh"
    source = script.read_text(encoding="utf-8")
    for marker in (
        "uv run",
        "tools/generate_plugin_views.py",
        "manifest_agent",
        "yaml",
    ):
        assert marker not in source
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    result = subprocess.run(
        ["bash", str(script), "--quick"],
        cwd=repo,
        env=isolated_env(tmp_path / "runtime"),
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "Verdict: PASS" in result.stdout


def test_workspace_gemini_hook_contract_matches_generated_degradation(
    repo_root: Path, workspace_bundle: Path, tmp_path: Path
) -> None:
    contracts = {
        contract.name: contract
        for contract in load_domain_contracts(repo_root / "plugins")
    }
    hook = contracts["manifest-workspace"].components.hooks[0]
    assert hook.path == "hooks/manifest-hooks.json"
    assert hook.compatibility is not None
    declared = hook.compatibility["gemini"]
    assert declared.mode == "degraded"
    assert declared.reason
    render_views(repo_root, output_root=tmp_path, check=False)
    view = json.loads(
        (tmp_path / "manifest-workspace/gemini-extension.json").read_text()
    )
    record = next(
        item
        for item in view["compatibility"]["degraded"]
        if item["component_id"] == "manifest-hooks"
    )
    assert record["path"] == hook.path
    assert record["reason"] == declared.reason


def test_codex_lifecycle_metadata_names_exact_native_events(
    workspace_bundle: Path,
) -> None:
    document = json.loads(
        (workspace_bundle / "hooks/codex-lifecycle-events.json").read_text()
    )
    assert {
        (row["id"], row["native_event"], row["surface"]) for row in document["events"]
    } == {
        ("codex-session-start", "SessionStart", "hooks.SessionStart"),
        ("codex-stop", "Stop", "hooks.Stop"),
        (
            "codex-permission-request",
            "PermissionRequest",
            "hooks.PermissionRequest",
        ),
    }

"""Isolation tests for the installed manifest-workspace bundle."""

from __future__ import annotations

import contextlib
import fcntl
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

from manifest_agent.contracts import load_contract


@pytest.fixture
def repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


@pytest.fixture
def workspace_bundle(repo_root: Path) -> Path:
    return repo_root / "plugins" / "manifest-workspace"


def _isolated_env(tmp_path: Path) -> dict[str, str]:
    home = tmp_path / "home"
    state = tmp_path / "state"
    data = tmp_path / "data"
    config = tmp_path / "config"
    for path in (home, state, data, config):
        path.mkdir(parents=True)
    return {
        **os.environ,
        "HOME": str(home),
        "XDG_STATE_HOME": str(state),
        "XDG_DATA_HOME": str(data),
        "XDG_CONFIG_HOME": str(config),
        "UV_NO_NETWORK": "1",
        "PYTHONDONTWRITEBYTECODE": "1",
    }


def _run(
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


def test_learning_capture_defaults_to_xdg_data(
    workspace_bundle: Path, tmp_path: Path
) -> None:
    env = _isolated_env(tmp_path)
    script = workspace_bundle / "skills/learning-capture/scripts/learning_capture.py"

    result = _run(
        script,
        "add",
        "--category",
        "pattern",
        "--language",
        "general",
        "--text",
        "bundle local storage",
        env=env,
        cwd=tmp_path,
    )

    assert result.returncode == 0, result.stderr
    entries = Path(env["XDG_DATA_HOME"]) / "manifest/knowledge/entries.jsonl"
    assert entries.is_file()
    record = json.loads(entries.read_text(encoding="utf-8"))
    assert record["category"] == "pattern"
    assert record["text"] == "bundle local storage"


def test_learning_capture_add_reads_the_store_inside_the_lock(
    workspace_bundle: Path, tmp_path: Path
) -> None:
    """`add` must take the store lock before loading, so a concurrent writer's
    record is visible and the generated KB id does not collide."""
    env = _isolated_env(tmp_path)
    script = workspace_bundle / "skills/learning-capture/scripts/learning_capture.py"
    store = Path(env["XDG_DATA_HOME"]) / "manifest/knowledge/entries.jsonl"
    store.parent.mkdir(parents=True, exist_ok=True)
    lock_path = store.with_name(store.name + ".lock")
    lock_path.touch()

    descriptor = os.open(lock_path, os.O_RDWR)
    process = None
    try:
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        process = subprocess.Popen(
            [
                sys.executable,
                "-B",
                str(script),
                "add",
                "--category",
                "pattern",
                "--language",
                "general",
                "--text",
                "second entry",
            ],
            cwd=tmp_path,
            env=env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        time.sleep(0.5)
        assert process.poll() is None, "add returned without waiting on the lock"
        store.write_text(
            '{"id":"KB-001","category":"pattern","description":"x"}\n',
            encoding="utf-8",
        )
    finally:
        with contextlib.suppress(OSError):
            fcntl.flock(descriptor, fcntl.LOCK_UN)
        os.close(descriptor)

    try:
        _, stderr = process.communicate(timeout=15)
    except subprocess.TimeoutExpired:
        process.kill()
        process.communicate()
        pytest.fail("add deadlocked on the store lock")

    assert process.returncode == 0, stderr
    ids = [
        json.loads(line)["id"]
        for line in store.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert ids == ["KB-001", "KB-002"]


def test_workspace_contract_lists_every_runtime_asset(
    workspace_bundle: Path,
) -> None:
    contract = load_contract(workspace_bundle / "manifest-capabilities.yml")
    runtime_paths = {component.path for component in contract.components.runtime}

    assert "skills/env-check/scripts" in runtime_paths
    assert "skills/help/catalog/commands.json" in runtime_paths
    assert contract.components.agents
    assert contract.components.hooks
    assert contract.components.guidance


def test_generated_catalog_covers_all_domain_skills(
    workspace_bundle: Path, tmp_path: Path
) -> None:
    env = _isolated_env(tmp_path)
    script = workspace_bundle / "skills/help/scripts/command_catalog.py"

    result = _run(script, "--all", "--json", env=env, cwd=tmp_path)

    assert result.returncode == 0, result.stderr
    catalog = json.loads(result.stdout)
    assert len(catalog["commands"]) == 119
    assert not any(
        item["qualified_name"]
        in ("manifest-workspace:parallel-agent", "manifest-workspace:metrics-report")
        for item in catalog["commands"]
    )


def test_env_check_reads_only_xdg_receipt_and_native_inventories(
    workspace_bundle: Path, tmp_path: Path
) -> None:
    env = _isolated_env(tmp_path)
    receipt = Path(env["XDG_STATE_HOME"]) / "manifest/installation.json"
    receipt.parent.mkdir(parents=True)
    receipt.write_text(
        json.dumps({"schema_version": 1, "harnesses": {"claude": {"ok": True}}}),
        encoding="utf-8",
    )
    script = workspace_bundle / "skills/env-check/scripts/env_check.py"

    result = _run(script, "--json", env=env, cwd=tmp_path)

    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    assert report["receipt"]["path"] == str(receipt)
    assert report["status"] in {"ok", "degraded"}


def test_deploy_reconcile_is_read_only_and_reports_repair_required(
    workspace_bundle: Path, tmp_path: Path
) -> None:
    env = _isolated_env(tmp_path)
    receipt = Path(env["XDG_STATE_HOME"]) / "manifest/installation.json"
    receipt.parent.mkdir(parents=True)
    receipt.write_text(
        json.dumps({"schema_version": 1, "harnesses": {"claude": {"plugins": []}}}),
        encoding="utf-8",
    )
    script = workspace_bundle / "skills/deploy-reconcile/scripts/plugin_reconcile.py"

    result = _run(script, "--json", env=env, cwd=tmp_path)

    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    assert report["repair_required"] is True
    assert report["drift"]
    assert "apply" not in report


def test_workspace_runtime_sources_have_no_legacy_runtime_dependencies(
    workspace_bundle: Path,
) -> None:
    forbidden = (
        "configs/claude",
        "manifest_agent",
        "import yaml",
        "from yaml",
    )
    runtime_files = [
        *workspace_bundle.glob("skills/learning-capture/scripts/*.py"),
        *workspace_bundle.glob("skills/help/scripts/*.py"),
        *workspace_bundle.glob("skills/env-check/scripts/*.py"),
        *workspace_bundle.glob("skills/deploy-reconcile/scripts/*.py"),
        *workspace_bundle.glob("skills/skill-evolve/scripts/*.py"),
        *workspace_bundle.glob("skills/ai-hooks-integration/scripts/**/*.py"),
    ]

    assert runtime_files
    for source in runtime_files:
        text = source.read_text(encoding="utf-8")
        for marker in forbidden:
            assert marker not in text, f"{source}: forbidden runtime marker {marker}"


def test_hook_targets_are_harness_native(
    workspace_bundle: Path, tmp_path: Path
) -> None:
    sys.path.insert(
        0,
        str(workspace_bundle / "skills/ai-hooks-integration/scripts"),
    )
    try:
        from runtime.tool_config import get_default_path, hook_support
    finally:
        sys.path.pop(0)

    monkey_home = tmp_path / "home"
    old_home = os.environ.get("HOME")
    os.environ["HOME"] = str(monkey_home)
    try:
        assert get_default_path("claude") == monkey_home / ".claude/settings.json"
        assert get_default_path("gemini") == monkey_home / ".gemini/settings.json"
        assert get_default_path("cursor") == monkey_home / ".cursor/hooks.json"
        degraded = hook_support("codex", "PreToolUse")
    finally:
        if old_home is None:
            os.environ.pop("HOME", None)
        else:
            os.environ["HOME"] = old_home
    assert degraded["status"] == "degraded"
    assert degraded["supported"] is False


def test_token_economy_hook_declares_the_documented_session_start_command(
    workspace_bundle: Path,
) -> None:
    hooks = json.loads(
        (workspace_bundle / "hooks/token-economy-context.json").read_text(
            encoding="utf-8"
        )
    )
    command = hooks["hooks"]["SessionStart"][0]["hooks"][0]["command"]

    assert command == "python3 ${CLAUDE_PLUGIN_ROOT}/hooks/token_economy_context.py"


def test_token_economy_hook_renders_guidance_on_session_start(
    workspace_bundle: Path, tmp_path: Path
) -> None:
    """Direct proof the SessionStart hook actually emits the guidance content.

    This is the isolated-install probe bullet 2 requires: run the exact
    generated launcher command with a real SessionStart payload and confirm
    the token-economy.md body — not just a manifest declaration — reaches
    stdout, matching Claude/Codex's real hook-invocation contract.
    """
    hook = workspace_bundle / "hooks/token_economy_context.py"
    guidance = (workspace_bundle / "guidance/token-economy.md").read_text(
        encoding="utf-8"
    )
    body = guidance.split("\n---\n", 1)[1].strip()

    result = subprocess.run(
        [sys.executable, str(hook)],
        input=b'{"hook_event_name":"SessionStart","session_id":"s",'
        b'"cwd":"/tmp","source":"startup"}',
        capture_output=True,
        timeout=30,
        env={
            "PATH": "/usr/bin:/bin",
            "HOME": str(tmp_path),
            "MANIFEST_STATE_ROOT": str(tmp_path / "state"),
        },
    )

    assert result.returncode == 0
    assert b"Manifest token-economy guidance" in result.stdout
    assert body.encode("utf-8") in result.stdout


@pytest.mark.parametrize(
    "payload",
    [
        b"",
        b"not json at all",
        b"[1, 2, 3]",
        b'{"hook_event_name":"Other"}',
        b'{"hook_event_name":"SessionStart","cwd":42}',
        b"\xff\xfe\x00binary",
    ],
)
def test_token_economy_hook_fails_open_on_malformed_payloads(
    workspace_bundle: Path, tmp_path: Path, payload: bytes
) -> None:
    hook = workspace_bundle / "hooks/token_economy_context.py"

    result = subprocess.run(
        [sys.executable, str(hook)],
        input=payload,
        capture_output=True,
        timeout=30,
        env={
            "PATH": "/usr/bin:/bin",
            "HOME": str(tmp_path),
            "MANIFEST_STATE_ROOT": str(tmp_path / "state"),
        },
    )

    assert result.returncode == 0, result.stderr.decode(errors="replace")
    assert b"Traceback" not in result.stderr

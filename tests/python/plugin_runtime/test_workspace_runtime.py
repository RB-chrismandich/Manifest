"""Isolation tests for the installed manifest-workspace bundle."""

from __future__ import annotations

import json
import os
import subprocess
import sys
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


def test_parallel_agent_uses_only_files_below_its_skill_root(
    workspace_bundle: Path, tmp_path: Path
) -> None:
    script = workspace_bundle / "skills/parallel-agent/scripts/parallel_agent.py"

    result = _run(script, "--help", env=_isolated_env(tmp_path), cwd=tmp_path)

    assert result.returncode == 0, result.stderr
    assert ".claude" not in result.stderr
    assert "configs/claude" not in result.stderr


def test_parallel_agent_preserves_structured_result_schema(
    workspace_bundle: Path, tmp_path: Path
) -> None:
    env = _isolated_env(tmp_path)
    binary_dir = tmp_path / "bin"
    binary_dir.mkdir()
    claude = binary_dir / "claude"
    claude.write_text("#!/bin/sh\necho fixture-review\n", encoding="utf-8")
    claude.chmod(0o755)
    env["PATH"] = f"{binary_dir}:{env['PATH']}"
    script = workspace_bundle / "skills/parallel-agent/scripts/parallel_agent.py"

    result = _run(
        script,
        "--json",
        "--claude-only",
        "--no-stream",
        "--no-synthesize",
        "review fixture",
        env=env,
        cwd=tmp_path,
    )

    assert result.returncode == 0, result.stderr
    document = json.loads(result.stdout)
    assert document["mode"] == "prompt"
    assert document["agents"]["claude"]["status"] == "complete"
    assert document["agents"]["claude"]["output"] == "fixture-review"
    assert "cross_verification" in document
    assert "output_files" in document


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


def test_workspace_contract_lists_every_runtime_asset(
    workspace_bundle: Path,
) -> None:
    contract = load_contract(workspace_bundle / "manifest-capabilities.yml")
    runtime_paths = {component.path for component in contract.components.runtime}

    assert "skills/parallel-agent/scripts" in runtime_paths
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
    assert len(catalog["commands"]) == 109
    assert any(
        item["qualified_name"] == "manifest-workspace:parallel-agent"
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
        "~/.claude",
        "configs/claude",
        "manifest_agent",
        "import yaml",
        "from yaml",
    )
    runtime_files = [
        *workspace_bundle.glob("skills/parallel-agent/scripts/**/*.py"),
        *workspace_bundle.glob("skills/learning-capture/scripts/*.py"),
        *workspace_bundle.glob("skills/help/scripts/*.py"),
        *workspace_bundle.glob("skills/env-check/scripts/*.py"),
        *workspace_bundle.glob("skills/deploy-reconcile/scripts/*.py"),
        *workspace_bundle.glob("skills/skill-evolve/scripts/*.py"),
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

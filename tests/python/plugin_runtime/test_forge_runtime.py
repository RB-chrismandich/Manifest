"""Isolation and packaging tests for the manifest-forge runtime."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

from manifest_agent.contracts import load_contract


@pytest.fixture
def repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


@pytest.fixture
def forge_bundle(repo_root: Path) -> Path:
    return repo_root / "plugins" / "manifest-forge"


@pytest.fixture
def isolated_env(tmp_path: Path) -> dict[str, str]:
    roots = {name: tmp_path / name for name in ("home", "state", "config", "data")}
    for root in roots.values():
        root.mkdir()
    return {
        **os.environ,
        "HOME": str(roots["home"]),
        "XDG_STATE_HOME": str(roots["state"]),
        "XDG_CONFIG_HOME": str(roots["config"]),
        "XDG_DATA_HOME": str(roots["data"]),
        "PYTHONDONTWRITEBYTECODE": "1",
        "UV_NO_NETWORK": "1",
    }


def _run(
    script: Path, *args: str, env: dict[str, str], cwd: Path
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(script), *args],
        cwd=cwd,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )


@pytest.mark.parametrize(
    "command",
    [
        "audit_log.sh",
        "auto_issue_dev.sh",
        "branch_clean.sh",
        "git_ops.sh",
        "git_platform.sh",
        "install_issue_hooks.sh",
        "issue_support.sh",
        "lifecycle.sh",
        "linear_ops.sh",
        "pr_review.sh",
        "tracker_ops.sh",
    ],
)
def test_forge_runtime_is_packaged_and_executable(
    forge_bundle: Path, command: str
) -> None:
    path = forge_bundle / "runtime/bin" / command
    assert path.is_file()
    assert os.access(path, os.X_OK)


def test_tracker_config_is_resolved_from_forge_bundle(
    forge_bundle: Path, isolated_env: dict[str, str], tmp_path: Path
) -> None:
    script = forge_bundle / "runtime/bin/tracker_ops.sh"

    result = _run(script, "resolve-provider", env=isolated_env, cwd=tmp_path)

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "github"
    assert ".claude" not in result.stderr
    assert "configs/claude" not in result.stderr


def test_tracker_registry_merges_xdg_overlay_and_rejects_unknown_type(
    forge_bundle: Path, isolated_env: dict[str, str], tmp_path: Path
) -> None:
    config_dir = Path(isolated_env["XDG_CONFIG_HOME"]) / "manifest/forge"
    config_dir.mkdir(parents=True)
    overlay = config_dir / "tracker_providers.json"
    registry = forge_bundle / "runtime/python/tracker_registry.py"

    overlay.write_text(
        json.dumps(
            {"default_provider": "linear", "providers": {"linear": {"verified": True}}}
        ),
        encoding="utf-8",
    )
    result = subprocess.run(
        ["python3", "-B", str(registry), "default-provider"],
        cwd=tmp_path,
        env=isolated_env,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "linear"

    overlay.write_text(
        json.dumps({"providers": {"acme": {"type": "acme-secret-api"}}}),
        encoding="utf-8",
    )
    rejected = subprocess.run(
        ["python3", "-B", str(registry), "default-provider"],
        cwd=tmp_path,
        env=isolated_env,
        text=True,
        capture_output=True,
        check=False,
    )
    assert rejected.returncode == 2
    assert "unknown provider type" in rejected.stderr


def test_audit_log_defaults_to_xdg_state_and_redacts_secrets(
    forge_bundle: Path, isolated_env: dict[str, str], tmp_path: Path
) -> None:
    script = forge_bundle / "runtime/bin/audit_log.sh"
    secret = "ghp_" + ("a" * 32)

    result = _run(
        script,
        "append",
        json.dumps({"token": secret}),
        env=isolated_env,
        cwd=tmp_path,
    )

    assert result.returncode == 0, result.stderr
    audit = Path(isolated_env["XDG_STATE_HOME"]) / "manifest/forge/audit.jsonl"
    assert audit.is_file()
    text = audit.read_text(encoding="utf-8")
    assert secret not in text
    assert "REDACTED" in text


def test_tracker_dispatch_propagates_engine_failure(
    forge_bundle: Path, isolated_env: dict[str, str], tmp_path: Path
) -> None:
    stub = tmp_path / "git-ops-stub"
    stub.write_text("#!/bin/sh\nexit 17\n", encoding="utf-8")
    stub.chmod(0o755)
    env = {**isolated_env, "MANIFEST_TRACKER": "github", "GIT_OPS_BIN": str(stub)}

    result = _run(
        forge_bundle / "runtime/bin/tracker_ops.sh",
        "issue-list",
        env=env,
        cwd=tmp_path,
    )

    assert result.returncode == 17


def test_forge_runtime_uses_json_and_has_no_legacy_runtime_dependencies(
    forge_bundle: Path,
) -> None:
    config_dir = forge_bundle / "runtime/config"
    for name in ("labels", "review_bots", "tracker_providers", "tracker_triage"):
        json.loads((config_dir / f"{name}.json").read_text(encoding="utf-8"))

    forbidden = (
        "configs/claude",
        "~/.claude",
        "/.claude/",
        "CLAUDE_PLUGIN_ROOT",
        "import yaml",
        "from yaml",
    )
    sources = [
        *forge_bundle.glob("runtime/bin/*.sh"),
        *forge_bundle.glob("runtime/python/*.py"),
        forge_bundle / "skills/repo-clean/scripts/hygiene_gather.py",
    ]
    assert sources
    for source in sources:
        text = source.read_text(encoding="utf-8")
        for marker in forbidden:
            assert marker not in text, f"{source}: forbidden runtime marker {marker}"


def test_forge_instructions_use_bundle_relative_runtime_contract(
    forge_bundle: Path,
) -> None:
    forbidden = ("configs/claude", "~/.claude", "CLAUDE_PLUGIN_ROOT")
    allowed_cross_domain = {"parallel-agent", "learning-capture"}
    documents = [
        *forge_bundle.glob("skills/**/*.md"),
        *forge_bundle.glob("runtime/references/*.md"),
    ]

    for document in documents:
        text = document.read_text(encoding="utf-8")
        for marker in forbidden:
            assert marker not in text, (
                f"{document}: forbidden instruction marker {marker}"
            )
        for reference in text.split("[[skill:")[1:]:
            name = reference.split("]]", 1)[0]
            assert name in allowed_cross_domain, (
                f"{document}: unqualified cross-domain skill {name}"
            )


def test_forge_contract_lists_all_runtime_directories(forge_bundle: Path) -> None:
    contract = load_contract(forge_bundle / "manifest-capabilities.yml")
    runtime_paths = {component.path for component in contract.components.runtime}

    assert runtime_paths == {
        "runtime/bin",
        "runtime/python",
        "runtime/config",
        "runtime/references",
    }
    assert set(contract.capabilities.mcp["optional"]) == {
        "atlassian",
        "github",
        "linear",
    }
    assert set(contract.capabilities.executables["optional"]) == {"gh", "glab"}

"""Isolation tests for the installed manifest-ops bundle."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from manifest_agent.contracts import CapabilityTier, load_contract

HARNESSES = ("claude", "codex", "gemini", "cursor", "antigravity", "devin")


@pytest.fixture
def repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


@pytest.fixture
def ops_bundle(repo_root: Path) -> Path:
    return repo_root / "plugins/manifest-ops"


def _isolated_env(tmp_path: Path) -> dict[str, str]:
    roots = {name: tmp_path / name for name in ("home", "state", "data", "config")}
    for root in roots.values():
        root.mkdir(parents=True, exist_ok=True)
    return {
        **os.environ,
        "HOME": str(roots["home"]),
        "XDG_STATE_HOME": str(roots["state"]),
        "XDG_DATA_HOME": str(roots["data"]),
        "XDG_CONFIG_HOME": str(roots["config"]),
        "PYTHONNOUSERSITE": "1",
        "PYTHONPATH": "",
        "UV_NO_NETWORK": "1",
    }


def _run(
    script: Path,
    *args: str,
    env: dict[str, str],
    cwd: Path,
    input_text: str | None = None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(script), *args],
        cwd=cwd,
        env=env,
        input=input_text,
        text=True,
        capture_output=True,
        check=False,
    )


@pytest.mark.parametrize(
    "command",
    ["ci_platform.sh", "git_platform.sh", "version_pin.sh", "version_pin_hook.sh"],
)
def test_ops_runtime_commands_are_packaged_and_executable(
    ops_bundle: Path, command: str
) -> None:
    path = ops_bundle / "runtime/bin" / command
    assert path.is_file()
    assert os.access(path, os.X_OK)


@pytest.mark.parametrize(
    ("files", "remote", "expected"),
    [
        ((".github/workflows/ci.yml",), None, "github-actions"),
        ((".gitlab-ci.yml",), None, "gitlab-ci"),
        ((), None, "none"),
        (
            (".github/workflows/ci.yml", ".gitlab-ci.yml"),
            "https://gitlab.com/acme/repo.git",
            "gitlab-ci",
        ),
    ],
)
def test_ops_ci_platform_preserves_the_shared_behavior_contract(
    ops_bundle: Path,
    tmp_path: Path,
    files: tuple[str, ...],
    remote: str | None,
    expected: str,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    if remote:
        subprocess.run(
            ["git", "-C", str(repo), "remote", "add", "origin", remote], check=True
        )
    for relative in files:
        path = repo / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("fixture\n", encoding="utf-8")

    result = _run(
        ops_bundle / "runtime/bin/ci_platform.sh",
        env=_isolated_env(tmp_path),
        cwd=repo,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == expected


@pytest.mark.parametrize(
    ("remote", "expected"),
    [
        ("git@github.com:acme/repo.git", "github"),
        ("https://gitlab.example.com/acme/repo.git", "gitlab"),
        ("https://example.com/acme/repo.git", "git"),
    ],
)
def test_ops_git_platform_preserves_the_shared_behavior_contract(
    ops_bundle: Path, tmp_path: Path, remote: str, expected: str
) -> None:
    repo = tmp_path / "repo"
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    subprocess.run(
        ["git", "-C", str(repo), "remote", "add", "origin", remote], check=True
    )

    result = _run(
        ops_bundle / "runtime/bin/git_platform.sh",
        env=_isolated_env(tmp_path),
        cwd=repo,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == expected


def test_ops_bundle_runs_without_security_or_a_deployed_home(
    ops_bundle: Path, tmp_path: Path
) -> None:
    installed = tmp_path / "installed/manifest-ops"
    shutil.copytree(ops_bundle, installed)
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / ".gitlab-ci.yml").write_text("stages: [test]\n", encoding="utf-8")
    env = _isolated_env(tmp_path)

    ci_result = _run(installed / "runtime/bin/ci_platform.sh", env=env, cwd=repo)
    help_result = _run(
        installed / "runtime/bin/version_pin.sh", "--help", env=env, cwd=repo
    )

    assert not (tmp_path / "installed/manifest-security").exists()
    assert ci_result.returncode == 0, ci_result.stderr
    assert ci_result.stdout.strip() == "gitlab-ci"
    assert help_result.returncode == 0, help_result.stderr
    assert "Usage: version_pin.sh" in help_result.stdout
    assert ".claude" not in help_result.stderr


def test_version_pin_uses_only_adjacent_json_and_stdlib(
    ops_bundle: Path, tmp_path: Path
) -> None:
    script = ops_bundle / "runtime/bin/version_pin.sh"
    source = script.read_text(encoding="utf-8")
    config = ops_bundle / "runtime/config/version_pin.json"
    requirements = tmp_path / "requirements.txt"
    requirements.write_text("requests\n", encoding="utf-8")
    resolver = tmp_path / "resolver.sh"
    resolver.write_text("#!/bin/sh\nprintf '2.31.0\\tabc123\\n'\n", encoding="utf-8")
    resolver.chmod(0o755)
    env = {**_isolated_env(tmp_path), "VERSION_PIN_RESOLVER": str(resolver)}

    result = _run(script, str(requirements), env=env, cwd=tmp_path)

    assert result.returncode == 0, result.stderr
    assert requirements.read_text(encoding="utf-8") == (
        "requests==2.31.0 --hash=sha256:abc123\n"
    )
    assert json.loads(config.read_text(encoding="utf-8"))["rules"]
    assert "import yaml" not in source
    assert "yaml.safe_load" not in source
    assert "command_config.yml" not in source
    assert "version_pin.json" in source


def test_version_pin_rejects_missing_target_without_success_summary(
    ops_bundle: Path, tmp_path: Path
) -> None:
    result = _run(
        ops_bundle / "runtime/bin/version_pin.sh",
        str(tmp_path / "missing-requirements.txt"),
        env=_isolated_env(tmp_path),
        cwd=tmp_path,
    )

    assert result.returncode != 0
    assert "path not found" in result.stderr
    assert "Summary:" not in result.stdout


def test_version_pin_rejects_malformed_json_without_traceback(
    ops_bundle: Path, tmp_path: Path
) -> None:
    policy = tmp_path / "version_pin.json"
    policy.write_text("{not-json\n", encoding="utf-8")
    env = {**_isolated_env(tmp_path), "VERSION_PIN_CONFIG": str(policy)}

    result = _run(
        ops_bundle / "runtime/bin/version_pin.sh", "--help", env=env, cwd=tmp_path
    )
    assert result.returncode == 0

    result = _run(ops_bundle / "runtime/bin/version_pin.sh", ".", env=env, cwd=tmp_path)

    assert result.returncode == 2
    assert "invalid JSON config" in result.stderr
    assert "Traceback" not in result.stderr
    assert "Summary:" not in result.stdout


def test_version_pin_hook_is_owned_advisory_and_fail_open(
    ops_bundle: Path, tmp_path: Path
) -> None:
    hook_catalog = json.loads(
        (ops_bundle / "hooks/version-pin.json").read_text(encoding="utf-8")
    )
    metadata = hook_catalog["_manifest"]
    requirements = tmp_path / "requirements.txt"
    requirements.write_text("requests\n", encoding="utf-8")
    env = _isolated_env(tmp_path)
    env["VERSION_PIN_RESOLVER"] = str(tmp_path / "missing-resolver")
    payload = json.dumps({"tool_input": {"file_path": str(requirements)}})

    result = _run(
        ops_bundle / "runtime/bin/version_pin_hook.sh",
        env=env,
        cwd=tmp_path,
        input_text=payload,
    )

    assert metadata == {
        "id": "version-pin",
        "mode": "advisory",
        "owner": "manifest-ops",
    }
    assert result.returncode == 0
    assert requirements.read_text(encoding="utf-8") == "requests\n"


def test_ops_contract_declares_runtime_and_explicit_hook_cells(
    ops_bundle: Path,
) -> None:
    contract = load_contract(ops_bundle / "manifest-capabilities.yml")
    runtime_paths = {component.path for component in contract.components.runtime}

    assert runtime_paths == {
        "runtime/bin",
        "runtime/config",
        "runtime/references",
        "skills/ci-setup/templates",
    }
    assert len(contract.components.hooks) == 1
    hook = contract.components.hooks[0]
    assert hook.id == "version-pin"
    assert hook.path == "hooks/version-pin.json"
    assert hook.compatibility is not None
    assert set(hook.compatibility) == set(HARNESSES)
    assert hook.compatibility["claude"].mode == "native"
    assert hook.compatibility["cursor"].mode == "generated"
    for harness in {"codex", "gemini", "antigravity", "devin"}:
        assert hook.compatibility[harness].mode == "degraded"
        assert hook.compatibility[harness].reason
    assert contract.capabilities.executables[CapabilityTier.REQUIRED] == (
        "bash",
        "git",
        "python3",
    )


def test_ci_setup_templates_are_bundle_local_and_complete(
    repo_root: Path, ops_bundle: Path
) -> None:
    templates = ops_bundle / "skills/ci-setup/templates"

    assert not (repo_root / "templates").exists()
    assert {
        path.relative_to(templates) for path in templates.rglob("*") if path.is_file()
    } == {
        Path("github/ci.yml"),
        Path("github/release.yml"),
        Path("github/security.yml"),
        Path("gitlab/.gitlab-ci.yml"),
    }
    skill = (ops_bundle / "skills/ci-setup/SKILL.md").read_text(encoding="utf-8")
    assert "templates/github/release.yml" in skill
    assert "templates/gitlab/.gitlab-ci.yml" in skill


def test_generated_ops_views_represent_every_hook_harness(ops_bundle: Path) -> None:
    claude = json.loads(
        (ops_bundle / ".claude-plugin/plugin.json").read_text(encoding="utf-8")
    )
    gemini = json.loads(
        (ops_bundle / "gemini-extension.json").read_text(encoding="utf-8")
    )
    generic = json.loads((ops_bundle / "plugin.json").read_text(encoding="utf-8"))

    records = {
        "claude": claude["compatibility"]["native"],
        "gemini": gemini["compatibility"]["degraded"],
    }
    for harness in ("codex", "cursor", "antigravity", "devin"):
        compatibility = generic["harnesses"][harness]["compatibility"]
        records[harness] = [
            record for mode_records in compatibility.values() for record in mode_records
        ]

    expected_modes = {
        "claude": "native",
        "codex": "degraded",
        "gemini": "degraded",
        "cursor": "generated",
        "antigravity": "degraded",
        "devin": "degraded",
    }
    for harness, mode in expected_modes.items():
        hook = next(
            record
            for record in records[harness]
            if record["component_type"] == "hooks"
            and record["component_id"] == "version-pin"
        )
        assert hook["mode"] == mode
        if mode == "degraded":
            assert hook["reason"]


def test_legacy_harness_configs_do_not_duplicate_the_ops_hook(repo_root: Path) -> None:
    claude_path = repo_root / "configs/claude/settings.runtime.json"
    cursor_path = repo_root / "configs/cursor/hooks.json"
    gemini_path = repo_root / "configs/gemini/settings.json"
    configs = {
        "claude": json.loads(claude_path.read_text(encoding="utf-8")),
        "cursor": json.loads(cursor_path.read_text(encoding="utf-8")),
        "gemini": json.loads(gemini_path.read_text(encoding="utf-8")),
    }

    for harness, document in configs.items():
        encoded = json.dumps(document)
        assert "version_pin_hook.sh" not in encoded, harness
        assert "version-pin" not in encoded, harness

    claude = configs["claude"]
    claude_commands = json.dumps(claude["hooks"]["PostToolUse"])
    assert "spec_review.sh --silent" in claude_commands
    assert "lint_on_edit_hook.sh" in claude_commands

    cursor = configs["cursor"]
    cursor_commands = json.dumps(cursor["hooks"]["afterFileEdit"])
    assert "spec_review.sh --silent" in cursor_commands
    assert "lint_on_edit_hook.sh" in cursor_commands

    gemini = configs["gemini"]
    gemini_commands = json.dumps(gemini["hooks"]["AfterTool"])
    assert "spec-review" in gemini_commands
    assert "lint-on-edit" in gemini_commands


def test_ops_skills_use_bundle_runtime_not_shared_home(ops_bundle: Path) -> None:
    forbidden = (
        "configs/claude",
        "~/.claude/scripts",
        "~/.claude/references",
        "version_pin_hook.sh",
    )
    combined = ""
    for skill in ops_bundle.glob("skills/*/SKILL.md"):
        source = skill.read_text(encoding="utf-8")
        combined += source
        for marker in forbidden:
            assert marker not in source, f"{skill}: forbidden runtime marker {marker}"

    assert "../../runtime/bin/ci_platform.sh" in combined
    assert "../../runtime/bin/git_platform.sh" in combined
    assert "../../runtime/bin/version_pin.sh" in combined
    assert "../../runtime/references/ci/gitlab-ci-reproduction.md" in combined
    assert "plugins/manifest-security" not in combined

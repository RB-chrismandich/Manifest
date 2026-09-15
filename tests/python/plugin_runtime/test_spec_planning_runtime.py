"""Isolation tests for the installed manifest-spec-planning bundle."""

from __future__ import annotations

import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from manifest_agent.contracts import CapabilityTier, load_contract


@pytest.fixture
def repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


@pytest.fixture
def spec_bundle(repo_root: Path, tmp_path: Path) -> Path:
    installed = tmp_path / "manifest-spec-planning"
    shutil.copytree(repo_root / "plugins/manifest-spec-planning", installed)
    return installed


def _isolated_env(tmp_path: Path) -> dict[str, str]:
    paths = {name: tmp_path / name for name in ("home", "data", "config", "state")}
    for path in paths.values():
        path.mkdir(parents=True, exist_ok=True)
    return {
        **os.environ,
        "HOME": str(paths["home"]),
        "XDG_DATA_HOME": str(paths["data"]),
        "XDG_CONFIG_HOME": str(paths["config"]),
        "XDG_STATE_HOME": str(paths["state"]),
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONNOUSERSITE": "1",
        "PYTHONPATH": "",
        "UV_NO_NETWORK": "1",
    }


def _run_python(
    script: Path, *args: str, env: dict[str, str], cwd: Path
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-S", "-B", str(script), *args],
        cwd=cwd,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )


def _load_plan_store(bundle: Path):
    path = bundle / "runtime/plan_store.py"
    spec = importlib.util.spec_from_file_location("plan_store", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_cddl_cli_resolves_adjacent_charter(spec_bundle: Path, tmp_path: Path) -> None:
    script = spec_bundle / "runtime/cddl/cddl_invoke.py"
    result = _run_python(
        script,
        "--charter",
        "qa-critic",
        "--help",
        env=_isolated_env(tmp_path),
        cwd=tmp_path,
    )

    assert result.returncode == 0, result.stderr
    assert "qa-critic" in result.stdout
    assert ".claude" not in result.stdout + result.stderr


@pytest.mark.parametrize("charter", ("../qa-critic", "/tmp/qa-critic", "unknown"))
def test_cddl_cli_rejects_unsafe_or_unknown_charter(
    spec_bundle: Path, tmp_path: Path, charter: str
) -> None:
    script = spec_bundle / "runtime/cddl/cddl_invoke.py"
    result = _run_python(
        script,
        "--charter",
        charter,
        env=_isolated_env(tmp_path),
        cwd=tmp_path,
    )

    assert result.returncode == 2
    assert "charter" in result.stderr.lower()


def test_cddl_cli_invokes_selected_native_reviewer(
    spec_bundle: Path, tmp_path: Path
) -> None:
    env = _isolated_env(tmp_path)
    fake = tmp_path / "reviewer"
    fake.write_text("#!/bin/sh\nprintf 'approved fixture\\n'\n", encoding="utf-8")
    fake.chmod(0o755)
    env["CDDL_INVOKE_PROVIDER"] = "antigravity"
    env["CDDL_INVOKE_CLI"] = str(fake)
    script = spec_bundle / "runtime/cddl/cddl_invoke.py"
    result = subprocess.run(
        [
            sys.executable,
            "-S",
            "-B",
            str(script),
            "--charter",
            "qa-critic",
        ],
        input="Review the fixture.",
        cwd=tmp_path,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout == "approved fixture\n"


def test_cddl_cli_invokes_devin_without_model(
    spec_bundle: Path, tmp_path: Path
) -> None:
    env = _isolated_env(tmp_path)
    capture = tmp_path / "devin-args"
    fake = tmp_path / "devin"
    fake.write_text(
        '#!/bin/sh\nprintf \'%s\\0\' "$@" > "$CDDL_CAPTURE_ARGS"\n'
        "printf 'approved devin fixture\\n'\n",
        encoding="utf-8",
    )
    fake.chmod(0o755)
    env.update(
        {
            "CDDL_CAPTURE_ARGS": str(capture),
            "CDDL_INVOKE_PROVIDER": "devin",
            "CDDL_INVOKE_CLI": str(fake),
        }
    )
    script = spec_bundle / "runtime/cddl/cddl_invoke.py"
    result = subprocess.run(
        [sys.executable, "-S", "-B", str(script), "--charter", "qa-critic"],
        input="Review the Devin fixture.",
        cwd=tmp_path,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout == "approved devin fixture\n"
    arguments = capture.read_bytes().split(b"\0")[:-1]
    assert arguments[:3] == [b"--permission-mode", b"auto", b"-p"]
    assert b"Review the Devin fixture." in arguments[3]
    assert b"--model" not in arguments


def test_default_plan_store_is_xdg(spec_bundle: Path, tmp_path: Path) -> None:
    env = _isolated_env(tmp_path)
    module = _load_plan_store(spec_bundle)

    assert module.resolve_plan_root(env=env, project_root=tmp_path) == (
        Path(env["XDG_DATA_HOME"]) / "manifest/plans"
    )


def test_plan_store_requires_explicit_safe_project_override(
    spec_bundle: Path, tmp_path: Path
) -> None:
    env = _isolated_env(tmp_path)
    project = tmp_path / "project"
    project.mkdir()
    module = _load_plan_store(spec_bundle)
    assert module.resolve_plan_root(env=env, project_root=project) == (
        Path(env["XDG_DATA_HOME"]) / "manifest/plans"
    )

    config = project / ".manifest/plans.yml"
    config.parent.mkdir()
    config.write_text("plan_root: .plans\n", encoding="utf-8")
    assert module.resolve_plan_root(env=env, project_root=project) == project / ".plans"

    config.write_text("plan_root: ../outside\n", encoding="utf-8")
    with pytest.raises(ValueError, match="inside the project"):
        module.resolve_plan_root(env=env, project_root=project)


def test_spec_runtime_uses_stdlib_and_bundle_assets(spec_bundle: Path) -> None:
    runtime_files = [
        *spec_bundle.glob("runtime/**/*.py"),
        spec_bundle / "runtime/spec_review.sh",
    ]
    forbidden = (
        "configs/claude",
        "~/.claude",
        "/.claude/",
        "~/.manifest",
        "command_config.yml",
        "import yaml",
        "from yaml",
    )
    assert runtime_files
    for source in runtime_files:
        text = source.read_text(encoding="utf-8")
        for marker in forbidden:
            assert marker not in text, f"{source}: forbidden marker {marker}"


def test_spec_skills_use_bundle_runtime_and_qualified_interfaces(
    spec_bundle: Path,
) -> None:
    forbidden = (
        "configs/claude",
        "~/.claude",
        "~/.manifest",
        "command_config.yml",
        "MODEL-POLICY.md",
        "git_ops.sh",
        "manifest parallel-agent",
    )
    for skill in spec_bundle.glob("skills/*/SKILL.md"):
        text = skill.read_text(encoding="utf-8")
        for marker in forbidden:
            assert marker not in text, f"{skill}: forbidden marker {marker}"

    for reference in spec_bundle.glob("runtime/references/*.md"):
        text = reference.read_text(encoding="utf-8")
        for marker in ("command_config.yml", "MODEL-POLICY.md", "~/.manifest"):
            assert marker not in text, f"{reference}: forbidden marker {marker}"

    implement_loop = (spec_bundle / "skills/spec-implement-loop/SKILL.md").read_text(
        encoding="utf-8"
    )
    assert "${XDG_STATE_HOME:-$HOME/.local/state}/manifest/cddl/runs" in implement_loop


def test_spec_contract_declares_all_runtime_assets(spec_bundle: Path) -> None:
    contract = load_contract(spec_bundle / "manifest-capabilities.yml")
    runtime_paths = {component.path for component in contract.components.runtime}

    assert runtime_paths == {
        "runtime/cddl",
        "runtime/config",
        "runtime/plan_store.py",
        "runtime/prompts",
        "runtime/references",
        "runtime/spec_review.sh",
    }
    assert json.loads((spec_bundle / "runtime/config/labels.json").read_text())[
        "labels"
    ]
    assert json.loads((spec_bundle / "runtime/config/review_models.json").read_text())[
        "providers"
    ]
    config = json.loads((spec_bundle / "runtime/config/review_models.json").read_text())
    assert config["providers"]["devin"] == {"binary": "devin", "models": {}}
    assert "devin" in contract.capabilities.executables[CapabilityTier.OPTIONAL]


def test_spec_implement_loop_defines_assurance_modes(spec_bundle: Path) -> None:
    skill = (spec_bundle / "skills/spec-implement-loop/SKILL.md").read_text(
        encoding="utf-8"
    )

    assert "--assurance standard|high-assurance" in skill
    assert "default `standard`" in skill
    assert "state.json" in skill and "`assurance`" in skill
    assert "pre-flight failure" in skill
    assert "fail before dispatching\n   anything on conflict" in skill
    assert "never reinterpret a run" in skill


def test_spec_implement_loop_phase_counts_differ_by_mode(spec_bundle: Path) -> None:
    skill = (spec_bundle / "skills/spec-implement-loop/SKILL.md").read_text(
        encoding="utf-8"
    )

    assert "**one** independent developer reviewer" in skill
    assert "dispatches all three critics (developer" in skill
    assert "reviewer, QA critic, architecture critic)." in skill


def test_spec_implement_loop_defines_same_iteration_identity(
    spec_bundle: Path,
) -> None:
    skill = (spec_bundle / "skills/spec-implement-loop/SKILL.md").read_text(
        encoding="utf-8"
    )

    assert "Same-iteration identity" in skill
    assert "stale" in skill.lower()


def test_cddl_verdict_contract_uses_plan_json_example(spec_bundle: Path) -> None:
    verdict_format = (
        spec_bundle / "skills/spec-implement-loop/prompts/verdict-format.md"
    ).read_text(encoding="utf-8")

    assert '"role": "developer-reviewer"' in verdict_format
    assert '"decision": "approve"' in verdict_format
    assert '"findings": []' in verdict_format
    assert (
        '{"title": "Optional naming improvement", "detail": "No acceptance impact."}'
        in verdict_format
    )
    assert "missing `advisories`" in verdict_format
    assert "invalidates" in verdict_format
    assert "Role match" in verdict_format
    assert "Same-iteration identity" in verdict_format


@pytest.mark.parametrize(
    "scenario",
    (
        "Legacy approval",
        "Advisory approval",
        "Contradictory approval",
        "Stale iteration",
        "Missing persona",
        "Mode conflict",
    ),
)
def test_cddl_verdict_contract_has_table_driven_examples(
    spec_bundle: Path, scenario: str
) -> None:
    verdict_format = (
        spec_bundle / "skills/spec-implement-loop/prompts/verdict-format.md"
    ).read_text(encoding="utf-8")

    assert f"**{scenario}**" in verdict_format


def test_cddl_prompt_and_charter_links_resolve(spec_bundle: Path) -> None:
    charters = {"developer", "developer-reviewer", "qa-critic", "arch-critic"}
    cddl_dir = spec_bundle / "runtime/prompts/cddl"
    assert charters.issubset({p.stem for p in cddl_dir.glob("*.md")})
    for name in charters:
        assert (cddl_dir / f"{name}.md").is_file()

    skill = (spec_bundle / "skills/spec-implement-loop/SKILL.md").read_text(
        encoding="utf-8"
    )
    for name in charters:
        assert f"`{name}.md`" in skill

    prompts_dir = spec_bundle / "skills/spec-implement-loop/prompts"
    developer_dispatch = (prompts_dir / "developer-dispatch.md").read_text(
        encoding="utf-8"
    )
    match = re.search(
        r"<BUNDLE_ROOT>/(runtime/prompts/cddl/[\w.-]+)", developer_dispatch
    )
    assert match is not None
    assert (spec_bundle / match.group(1)).is_file()

    reviewer_dispatch = (prompts_dir / "reviewer-dispatch.md").read_text(
        encoding="utf-8"
    )
    assert "{{CHARTER_FILE}}" in reviewer_dispatch
    assert "<BUNDLE_ROOT>/runtime/prompts/cddl/{{CHARTER_FILE}}" in reviewer_dispatch

    for prompt_name in (
        "cli-dispatch.md",
        "developer-dispatch.md",
        "reviewer-dispatch.md",
        "verdict-format.md",
    ):
        assert (prompts_dir / prompt_name).is_file()

    cli_dispatch = (prompts_dir / "cli-dispatch.md").read_text(encoding="utf-8")
    assert "verdict-format.md" in cli_dispatch

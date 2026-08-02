"""Isolation and packaging tests for the manifest-forge runtime."""

from __future__ import annotations

import importlib.util
import json
import os
import re
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


def _load_module(path: Path):
    spec = importlib.util.spec_from_file_location(path.stem, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


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
    binary_dir = tmp_path / "bin"
    binary_dir.mkdir()
    gh = binary_dir / "gh"
    gh.write_text("#!/bin/sh\nexit 17\n", encoding="utf-8")
    gh.chmod(0o755)
    hostile = tmp_path / "hostile-git-ops"
    marker = tmp_path / "hostile-called"
    hostile.write_text(f"#!/bin/sh\ntouch {marker}\nexit 0\n", encoding="utf-8")
    hostile.chmod(0o755)
    env = {
        **isolated_env,
        "PATH": f"{binary_dir}:{isolated_env['PATH']}",
        "MANIFEST_GIT_PLATFORM": "github",
        "MANIFEST_TRACKER": "github",
        "GIT_OPS_BIN": str(hostile),
    }

    result = _run(
        forge_bundle / "runtime/bin/tracker_ops.sh",
        "issue-list",
        env=env,
        cwd=tmp_path,
    )

    assert result.returncode == 17
    assert not marker.exists()


@pytest.mark.parametrize(
    "track_id",
    ["../outside", "../../outside", "/tmp/outside", ".", "..", "jira__BAD/ID"],
)
def test_lifecycle_rejects_track_ids_outside_xdg_state(
    forge_bundle: Path,
    isolated_env: dict[str, str],
    tmp_path: Path,
    track_id: str,
) -> None:
    outside = tmp_path / "outside.json"
    outside.write_text('{"sentinel": true}\n', encoding="utf-8")

    commands = (
        ("status", track_id, "--json"),
        (
            "advance",
            track_id,
            "--actor",
            "agent",
            "--gate",
            '{"gate_type":"artifact","present":true}',
        ),
    )
    for command in commands:
        result = _run(
            forge_bundle / "runtime/bin/lifecycle.sh",
            *command,
            env=isolated_env,
            cwd=tmp_path,
        )

        assert result.returncode != 0
        assert "invalid track id" in result.stderr
        assert "unsafe lifecycle state path" not in result.stderr
        assert outside.read_text(encoding="utf-8") == '{"sentinel": true}\n'


def test_lifecycle_rejects_symlink_track_escape(
    forge_bundle: Path, isolated_env: dict[str, str], tmp_path: Path
) -> None:
    outside = tmp_path / "outside.json"
    outside.write_text('{"sentinel": true}\n', encoding="utf-8")
    state = Path(isolated_env["XDG_STATE_HOME"]) / "manifest/forge/lifecycle"
    state.mkdir(parents=True)
    (state / "jira__SAFE-1.json").symlink_to(outside)

    result = _run(
        forge_bundle / "runtime/bin/lifecycle.sh",
        "status",
        "jira__SAFE-1",
        "--json",
        env=isolated_env,
        cwd=tmp_path,
    )

    assert result.returncode != 0
    assert "unsafe track path" in result.stderr
    assert outside.read_text(encoding="utf-8") == '{"sentinel": true}\n'


def test_lifecycle_ignores_external_state_override_for_init_and_advance(
    forge_bundle: Path, isolated_env: dict[str, str], tmp_path: Path
) -> None:
    outside = tmp_path / "outside-state"
    outside.mkdir()
    sentinel = outside / "sentinel"
    sentinel.write_text("untouched\n", encoding="utf-8")
    env = {**isolated_env, "LIFECYCLE_STATE_DIR": str(outside)}
    lifecycle = forge_bundle / "runtime/bin/lifecycle.sh"

    initialized = _run(lifecycle, "init", "PROJ-777", env=env, cwd=tmp_path)
    advanced = _run(
        lifecycle,
        "advance",
        "jira__PROJ-777",
        "--actor",
        "agent",
        "--gate",
        '{"gate_type":"artifact","present":true}',
        env=env,
        cwd=tmp_path,
    )

    assert initialized.returncode == 0, initialized.stderr
    assert advanced.returncode == 0, advanced.stderr
    expected = (
        Path(isolated_env["XDG_STATE_HOME"])
        / "manifest/forge/lifecycle/jira__PROJ-777.json"
    )
    assert expected.is_file()
    assert list(outside.iterdir()) == [sentinel]
    assert sentinel.read_text(encoding="utf-8") == "untouched\n"


def test_lifecycle_rejects_symlinked_xdg_ancestor_without_external_write(
    forge_bundle: Path, isolated_env: dict[str, str], tmp_path: Path
) -> None:
    outside = tmp_path / "outside-state"
    outside.mkdir()
    state_root = Path(isolated_env["XDG_STATE_HOME"])
    (state_root / "manifest").symlink_to(outside, target_is_directory=True)

    result = _run(
        forge_bundle / "runtime/bin/lifecycle.sh",
        "init",
        "PROJ-888",
        env=isolated_env,
        cwd=tmp_path,
    )

    assert result.returncode != 0
    assert "unsafe lifecycle state path" in result.stderr
    assert list(outside.iterdir()) == []


def test_lifecycle_state_write_survives_ancestor_swap_without_external_write(
    forge_bundle: Path,
    isolated_env: dict[str, str],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state_root = Path(isolated_env["XDG_STATE_HOME"])
    lifecycle_dir = state_root / "manifest/forge/lifecycle"
    lifecycle_dir.mkdir(parents=True)
    track_name = "jira__RACE-1.json"
    (lifecycle_dir / track_name).write_text('{"version": 1}\n', encoding="utf-8")
    outside = tmp_path / "outside-state"
    outside.mkdir()

    state_module = _load_module(forge_bundle / "runtime/python/lifecycle_state.py")
    original_write = state_module._write_atomic

    def swap_ancestor_then_write(*args, **kwargs):
        (state_root / "manifest").rename(state_root / "manifest-opened")
        (state_root / "manifest").symlink_to(outside, target_is_directory=True)
        return original_write(*args, **kwargs)

    monkeypatch.setattr(state_module, "_write_atomic", swap_ancestor_then_write)
    state_module.write_track(str(state_root), "jira__RACE-1", b'{"version": 2}\n')

    safe_track = state_root / "manifest-opened/forge/lifecycle" / track_name
    assert json.loads(safe_track.read_text(encoding="utf-8")) == {"version": 2}
    assert list(outside.iterdir()) == []


def test_lifecycle_shell_delegates_state_io_to_python_helper(
    forge_bundle: Path,
) -> None:
    lifecycle = (forge_bundle / "runtime/bin/lifecycle.sh").read_text(encoding="utf-8")

    assert 'mktemp "${STATE_DIR}' not in lifecycle
    assert 'cat "${p}"' not in lifecycle
    assert 'mv "${tmp}"' not in lifecycle


def test_lifecycle_ignores_arbitrary_provider_config_and_merges_xdg_overlay(
    forge_bundle: Path, isolated_env: dict[str, str], tmp_path: Path
) -> None:
    lifecycle = forge_bundle / "runtime/bin/lifecycle.sh"
    hostile = tmp_path / "providers.json"
    hostile.write_text(
        json.dumps(
            {
                "default_provider": "github",
                "providers": {
                    "github": {
                        "status_via": "label",
                        "status_map": {"planned": "hostile"},
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    env = {**isolated_env, "LIFECYCLE_PROVIDERS_CONFIG": str(hostile)}

    bundled = _run(lifecycle, "status-map", "github", "planned", env=env, cwd=tmp_path)

    assert bundled.returncode == 0, bundled.stderr
    assert bundled.stdout.strip() == "label\tplanned"

    overlay_dir = Path(isolated_env["XDG_CONFIG_HOME"]) / "manifest/forge"
    overlay_dir.mkdir(parents=True)
    (overlay_dir / "tracker_providers.json").write_text(
        json.dumps({"providers": {"github": {"status_map": {"planned": "queued"}}}}),
        encoding="utf-8",
    )
    overlaid = _run(lifecycle, "status-map", "github", "planned", env=env, cwd=tmp_path)

    assert overlaid.returncode == 0, overlaid.stderr
    assert overlaid.stdout.strip() == "label\tqueued"


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
        "GIT_OPS_BIN",
        "LINEAR_OPS_BIN",
        "GIT_PLATFORM_BIN",
        "TRACKER_OPS_BIN",
        "ISSUE_SUPPORT_ENGINE",
        "PR_REVIEW_FETCH",
        "LIFECYCLE_STATE_DIR",
        "LIFECYCLE_PROVIDERS_CONFIG",
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
    forbidden = (
        "configs/claude",
        "~/.claude",
        "CLAUDE_PLUGIN_ROOT",
        "~/.config/linear/token",
        "import yaml",
        "yaml.safe_load",
    )
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


@pytest.mark.parametrize(
    "relative_path",
    [
        "skills/issue-triage/references/workflow.md",
        "skills/issue-prioritize/references/workflow.md",
        "skills/pr-monitor/references/platform-commands.md",
    ],
)
def test_reference_workflows_establish_resolvable_runtime_root(
    forge_bundle: Path, relative_path: str
) -> None:
    document = forge_bundle / relative_path
    text = document.read_text(encoding="utf-8")
    resolved = (document.parent / "../../../runtime").resolve()

    assert resolved == (forge_bundle / "runtime").resolve()
    assert "REFERENCE_DIR=$(CDPATH=" in text
    assert "FORGE_RUNTIME_DIR=$(CDPATH=" in text
    assert "$FORGE_RUNTIME_DIR/bin/" in text or "$FORGE_RUNTIME_DIR/config/" in text
    assert not re.search(r"(?<!\.)\.\./\.\./runtime/(bin|config|python)", text)


def test_triage_workflow_uses_valid_stdlib_json_heredoc(forge_bundle: Path) -> None:
    workflow = forge_bundle / "skills/issue-triage/references/workflow.md"
    text = workflow.read_text(encoding="utf-8")

    assert "python3 - \"$CONFIG_FILE\" << 'PY'" in text
    assert "json.load" in text
    assert "import yaml" not in text


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
    assert set(contract.capabilities.executables["optional"]) == {
        "curl",
        "gh",
        "glab",
    }

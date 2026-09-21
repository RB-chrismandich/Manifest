"""Isolation tests for the installed manifest-workspace bundle."""

from __future__ import annotations

import contextlib
import fcntl
import hashlib
import importlib.util
import json
import os
import platform
import plistlib
import shutil
import signal
import stat
import subprocess
import sys
import time
from datetime import datetime, timezone
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


def _load_runtime_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _copy_health_source(repo_root: Path, destination: Path) -> Path:
    relative_sources = (
        "plugins/manifest-workspace/skills/env-check/scripts/env_check.py",
        "plugins/manifest-workspace/skills/env-check/scripts/mcp_health.py",
        "plugins/manifest-workspace/skills/env-check/scripts/health_report.py",
        "plugins/manifest-workspace/skills/env-check/scripts/install_health_reporting.py",
        "plugins/manifest-workspace/skills/deploy-reconcile/scripts/plugin_reconcile.py",
        "configs/claude/scripts/hook_smoke.py",
        "configs/claude/scripts/mcp_health_check.sh",
        "configs/omp/extensions/manifest-health.ts",
        "plugins/manifest-delegate/hooks/hooks.json",
        "plugins/manifest-delegate/scripts/delegate.py",
        "plugins/manifest-delegate/scripts/stop_gate_hook.py",
        "plugins/manifest-delegate/scripts/stop_gate_hook.sh",
    )
    for relative in relative_sources:
        source = repo_root / relative
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    return destination


def _write_health_tool_fakes(tmp_path: Path, env: dict[str, str]) -> Path:
    binary_dir = tmp_path / "health-bin"
    binary_dir.mkdir()
    log = tmp_path / "native-commands.log"
    for name in ("omp", "claude", "manifest", "launchctl", "plutil"):
        executable = binary_dir / name
        executable.write_text(
            "#!/bin/sh\n"
            f'printf "%s\\n" "{name} $*" >> "$MANIFEST_TEST_COMMAND_LOG"\n'
            "exit 0\n",
            encoding="utf-8",
        )
        executable.chmod(0o755)
    env["PATH"] = f"{binary_dir}:{env['PATH']}"
    env["MANIFEST_TEST_COMMAND_LOG"] = str(log)
    env["OMP_AGENT_DIR"] = str(tmp_path / "omp-agent")
    return log


def _session_start_commands(settings: dict) -> list[str]:
    return [
        hook["command"]
        for matcher in settings.get("hooks", {}).get("SessionStart", [])
        if isinstance(matcher, dict)
        for hook in matcher.get("hooks", [])
        if isinstance(hook, dict) and isinstance(hook.get("command"), str)
    ]




def test_health_installer_is_owned_idempotent_updatable_and_uninstallable(
    repo_root: Path, tmp_path: Path
) -> None:
    source_root = _copy_health_source(repo_root, tmp_path / "source")
    env = _isolated_env(tmp_path)
    command_log = _write_health_tool_fakes(tmp_path, env)
    settings_path = Path(env["HOME"]) / ".claude/settings.json"
    settings_path.parent.mkdir(parents=True)
    settings_path.write_text(
        json.dumps(
            {
                "hooks": {
                    "SessionStart": [
                        {"hooks": [{"type": "command", "command": "/custom/session"}]}
                    ]
                }
            }
        ),
        encoding="utf-8",
    )
    installer = (
        source_root
        / "plugins/manifest-workspace/skills/env-check/scripts"
        / "install_health_reporting.py"
    )

    first = _run(
        installer,
        "--source-root",
        str(source_root),
        "--install",
        env=env,
        cwd=tmp_path,
    )
    assert first.returncode == 0, first.stderr
    second = _run(
        installer,
        "--source-root",
        str(source_root),
        "--install",
        env=env,
        cwd=tmp_path,
    )
    assert second.returncode == 0, second.stderr

    installation_path = (
        Path(env["XDG_STATE_HOME"]) / "manifest/health/installation.json"
    )
    installation = json.loads(installation_path.read_text(encoding="utf-8"))
    assert stat.S_IMODE(installation_path.stat().st_mode) == 0o600
    assert Path(installation["source_root"]) == source_root.resolve()
    assert set(installation["executables"]) == {
        "python",
        "omp",
        "claude",
        "coordinator",
    }
    assert installation["installed_at"].endswith("Z")
    assert set(installation["files"]) == {
        "env_check.py",
        "health_report.py",
        "hook_smoke.py",
        "mcp_health.py",
        "plugin_reconcile.py",
    }
    for executable in installation["executables"].values():
        assert Path(executable).is_absolute()
    runtime_root = Path(env["XDG_DATA_HOME"]) / "manifest/health"
    assert (runtime_root / "health_report.py").is_file()
    assert (
        Path(env["OMP_AGENT_DIR"]) / "extensions/manifest-health.ts"
    ).read_bytes() == (
        source_root / "configs/omp/extensions/manifest-health.ts"
    ).read_bytes()
    assert stat.S_IMODE(
        (Path(env["OMP_AGENT_DIR"]) / "extensions/manifest-health.ts").stat().st_mode
    ) == 0o600
    assert {path.name for path in runtime_root.iterdir()} == set(
        installation["files"]
    )
    for name, row in installation["files"].items():
        destination = runtime_root / name
        digest = hashlib.sha256(destination.read_bytes()).hexdigest()
        assert row["destination"] == str(destination.resolve())
        assert row["source_sha256"] == digest
        assert row["destination_sha256"] == digest
        assert stat.S_IMODE(destination.stat().st_mode) == 0o600

    settings = json.loads(settings_path.read_text(encoding="utf-8"))
    commands = _session_start_commands(settings)
    assert commands.count("/custom/session") == 1
    assert commands.count(str(Path(env["HOME"]) / ".claude/scripts/mcp_health_check.sh")) == 1

    plist_path = (
        Path(env["HOME"])
        / "Library/LaunchAgents/com.manifest.health-report.plist"
    )
    with plist_path.open("rb") as handle:
        plist = plistlib.load(handle)
    assert plist["ProgramArguments"] == [
        str(Path(sys.executable).resolve()),
        str((runtime_root / "health_report.py").resolve()),
        "--json",
        "--harness",
        "claude",
        "--harness",
        "omp",
        "--out-dir",
        str(
            (
                Path(env["XDG_STATE_HOME"]) / "manifest/reports"
            ).resolve()
        ),
    ]
    assert plist["StartCalendarInterval"] == {"Weekday": 1, "Hour": 9, "Minute": 0}
    assert plist["RunAtLoad"] is False
    assert plist["ProcessType"] == "Background"
    assert plist["ManifestManagedBy"] == "manifest-health-reporting"
    assert plist["EnvironmentVariables"] == {
        "HOME": str(Path(env["HOME"]).resolve()),
        "PATH": env["PATH"],
        "XDG_CONFIG_HOME": str(Path(env["XDG_CONFIG_HOME"]).resolve()),
        "XDG_DATA_HOME": str(Path(env["XDG_DATA_HOME"]).resolve()),
        "XDG_STATE_HOME": str(Path(env["XDG_STATE_HOME"]).resolve()),
    }
    wrapper_path = Path(env["HOME"]) / ".claude/scripts/mcp_health_check.sh"
    assert stat.S_IMODE(wrapper_path.stat().st_mode) == 0o700
    assert stat.S_IMODE(plist_path.stat().st_mode) == 0o600
    assert stat.S_IMODE(settings_path.stat().st_mode) == 0o600
    for key, destination in (
        ("omp_extension", Path(env["OMP_AGENT_DIR"]) / "extensions/manifest-health.ts"),
        ("claude_wrapper", wrapper_path),
        ("launchd_plist", plist_path),
    ):
        row = installation[key]
        digest = hashlib.sha256(destination.read_bytes()).hexdigest()
        assert row["destination"] == str(destination.resolve())
        assert row["source_sha256"] == digest
        assert row["destination_sha256"] == digest

    source_health = (
        source_root
        / "plugins/manifest-workspace/skills/env-check/scripts/mcp_health.py"
    )
    source_health.write_text(
        source_health.read_text(encoding="utf-8") + "\n", encoding="utf-8"
    )
    updated = _run(
        installer,
        "--source-root",
        str(source_root),
        "--install",
        env=env,
        cwd=tmp_path,
    )
    assert updated.returncode == 0, updated.stderr
    assert hashlib.sha256((runtime_root / "mcp_health.py").read_bytes()).hexdigest() == (
        hashlib.sha256(source_health.read_bytes()).hexdigest()
    )

    removed = _run(
        installer,
        "--source-root",
        str(source_root),
        "--uninstall",
        env=env,
        cwd=tmp_path,
    )
    assert removed.returncode == 0, removed.stderr
    removed_again = _run(
        installer,
        "--source-root",
        str(source_root),
        "--uninstall",
        env=env,
        cwd=tmp_path,
    )
    assert removed_again.returncode == 0, removed_again.stderr
    assert not installation_path.exists()
    assert not (Path(env["OMP_AGENT_DIR"]) / "extensions/manifest-health.ts").exists()
    assert not (Path(env["HOME"]) / ".claude/scripts/mcp_health_check.sh").exists()
    assert not plist_path.exists()
    remaining = json.loads(settings_path.read_text(encoding="utf-8"))
    assert _session_start_commands(remaining) == ["/custom/session"]
    log_lines = command_log.read_text(encoding="utf-8").splitlines()
    assert any("bootstrap gui/" in line for line in log_lines)
    assert any("kickstart -k gui/" in line for line in log_lines)
    assert any("plutil -lint " in line for line in log_lines)
    assert sum("kickstart -k gui/" in line for line in log_lines) == 3


def test_health_installer_refuses_unowned_or_edited_destinations(
    repo_root: Path, tmp_path: Path
) -> None:
    source_root = _copy_health_source(repo_root, tmp_path / "source")
    env = _isolated_env(tmp_path)
    _write_health_tool_fakes(tmp_path, env)
    extension = Path(env["OMP_AGENT_DIR"]) / "extensions/manifest-health.ts"
    extension.parent.mkdir(parents=True)
    extension.write_text("user-owned\n", encoding="utf-8")
    installer = (
        source_root
        / "plugins/manifest-workspace/skills/env-check/scripts"
        / "install_health_reporting.py"
    )

    result = _run(
        installer,
        "--source-root",
        str(source_root),
        "--install",
        env=env,
        cwd=tmp_path,
    )

    assert result.returncode == 1
    assert extension.read_text(encoding="utf-8") == "user-owned\n"
    assert not (
        Path(env["XDG_STATE_HOME"]) / "manifest/health/installation.json"
    ).exists()


def test_health_installer_preserves_an_unowned_launchd_job(
    repo_root: Path, tmp_path: Path
) -> None:
    source_root = _copy_health_source(repo_root, tmp_path / "source")
    env = _isolated_env(tmp_path)
    _write_health_tool_fakes(tmp_path, env)
    plist_path = (
        Path(env["HOME"])
        / "Library/LaunchAgents/com.manifest.health-report.plist"
    )
    plist_path.parent.mkdir(parents=True)
    original = plistlib.dumps(
        {
            "Label": "com.manifest.health-report",
            "ProgramArguments": ["/user/owned/reporter"],
        }
    )
    plist_path.write_bytes(original)
    installer = (
        source_root
        / "plugins/manifest-workspace/skills/env-check/scripts"
        / "install_health_reporting.py"
    )

    result = _run(
        installer,
        "--source-root",
        str(source_root),
        "--install",
        env=env,
        cwd=tmp_path,
    )

    assert result.returncode == 1
    assert plist_path.read_bytes() == original
    assert not (Path(env["XDG_DATA_HOME"]) / "manifest/health").exists()
    assert not (
        Path(env["XDG_STATE_HOME"]) / "manifest/health/installation.json"
    ).exists()


def test_health_installer_requires_one_explicit_action(
    repo_root: Path, tmp_path: Path
) -> None:
    source_root = _copy_health_source(repo_root, tmp_path / "source")
    env = _isolated_env(tmp_path)
    installer = (
        source_root
        / "plugins/manifest-workspace/skills/env-check/scripts"
        / "install_health_reporting.py"
    )

    missing = _run(
        installer,
        "--source-root",
        str(source_root),
        env=env,
        cwd=tmp_path,
    )
    conflicting = _run(
        installer,
        "--source-root",
        str(source_root),
        "--install",
        "--uninstall",
        env=env,
        cwd=tmp_path,
    )

    assert missing.returncode == 2
    assert conflicting.returncode == 2
    assert not (Path(env["XDG_DATA_HOME"]) / "manifest/health").exists()
    assert not (
        Path(env["XDG_STATE_HOME"]) / "manifest/health/installation.json"
    ).exists()


def test_health_installer_refuses_to_uninstall_edited_owned_files(
    repo_root: Path, tmp_path: Path
) -> None:
    source_root = _copy_health_source(repo_root, tmp_path / "source")
    env = _isolated_env(tmp_path)
    _write_health_tool_fakes(tmp_path, env)
    installer = (
        source_root
        / "plugins/manifest-workspace/skills/env-check/scripts"
        / "install_health_reporting.py"
    )
    installed = _run(
        installer,
        "--source-root",
        str(source_root),
        "--install",
        env=env,
        cwd=tmp_path,
    )
    assert installed.returncode == 0, installed.stderr
    extension = Path(env["OMP_AGENT_DIR"]) / "extensions/manifest-health.ts"
    extension.write_text("externally edited\n", encoding="utf-8")

    removed = _run(
        installer,
        "--source-root",
        str(source_root),
        "--uninstall",
        env=env,
        cwd=tmp_path,
    )

    assert removed.returncode == 1
    assert extension.read_text(encoding="utf-8") == "externally edited\n"
    assert (
        Path(env["XDG_STATE_HOME"]) / "manifest/health/installation.json"
    ).is_file()
    assert (Path(env["HOME"]) / ".claude/scripts/mcp_health_check.sh").is_file()
    assert (
        Path(env["HOME"])
        / "Library/LaunchAgents/com.manifest.health-report.plist"
    ).is_file()


def test_health_installer_does_not_bootout_an_unowned_loaded_label_after_failed_bootstrap(
    repo_root: Path, tmp_path: Path
) -> None:
    source_root = _copy_health_source(repo_root, tmp_path / "source")
    env = _isolated_env(tmp_path)
    command_log = _write_health_tool_fakes(tmp_path, env)
    launchd_state = tmp_path / "launchd-state"
    launchd_state.write_text("unowned\n", encoding="utf-8")
    env["MANIFEST_TEST_LAUNCHD_STATE"] = str(launchd_state)
    launchctl = Path(env["PATH"].split(os.pathsep, 1)[0]) / "launchctl"
    launchctl.write_text(
        "#!/bin/sh\n"
        'printf "%s\\n" "launchctl $*" >> "$MANIFEST_TEST_COMMAND_LOG"\n'
        'case "$1" in\n'
        "  bootstrap)\n"
        '    test ! -e "$MANIFEST_TEST_LAUNCHD_STATE" || exit 36\n'
        '    printf "manifest\\n" > "$MANIFEST_TEST_LAUNCHD_STATE"\n'
        "    ;;\n"
        "  bootout)\n"
        '    rm -f "$MANIFEST_TEST_LAUNCHD_STATE"\n'
        "    ;;\n"
        "esac\n"
        "exit 0\n",
        encoding="utf-8",
    )
    launchctl.chmod(0o755)
    installer = (
        source_root
        / "plugins/manifest-workspace/skills/env-check/scripts"
        / "install_health_reporting.py"
    )

    result = _run(
        installer,
        "--source-root",
        str(source_root),
        "--install",
        env=env,
        cwd=tmp_path,
    )

    log_lines = command_log.read_text(encoding="utf-8").splitlines()
    assert result.returncode == 1
    assert "launchd bootstrap failed" in result.stderr
    assert any(line.startswith("launchctl bootstrap gui/") for line in log_lines)
    assert launchd_state.is_file()
    assert launchd_state.read_text(encoding="utf-8") == "unowned\n"
    assert not any(line.startswith("launchctl bootout ") for line in log_lines)


def _write_report_fixture(
    tmp_path: Path,
    health_module,
    now: datetime,
) -> tuple[dict[str, str], Path, Path]:
    env = _isolated_env(tmp_path)
    agent_root = tmp_path / "omp-agent"
    env["OMP_AGENT_DIR"] = str(agent_root)
    source_root = tmp_path / "report-source"
    contract_root = source_root / "plugins/manifest-workspace"
    contract_root.mkdir(parents=True)
    (contract_root / "manifest-capabilities.yml").write_text(
        """schema_version: 1
bundle:
  name: manifest-workspace
  version: 1.0.0
components:
  skills:
    root: skills
    include: ["*/SKILL.md"]
  agents: []
  hooks: []
  runtime: []
  guidance: []
capabilities:
  mcp:
    required: []
    default: [context7]
    optional: []
  executables:
    required: [python3]
    default: []
    optional: []
compatibility:
  claude: {mode: native}
  codex: {mode: native}
  gemini: {mode: generated}
  cursor: {mode: generated}
  antigravity: {mode: imported}
  devin: {mode: native}
""",
        encoding="utf-8",
    )
    contract_code = source_root / "src/manifest_agent/contracts.py"
    contract_code.parent.mkdir(parents=True)
    contract_code.write_text(
        "DOMAIN_BUNDLES = ('manifest-workspace',)\n"
        "ADDON_BUNDLES = ()\n",
        encoding="utf-8",
    )

    receipt = Path(env["XDG_STATE_HOME"]) / "manifest/installation.json"
    receipt.parent.mkdir(parents=True)
    receipt.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "coordinator_version": "1.0.0",
                "release_version": "1.0.0",
                "source_commit": "a" * 40,
                "source_dirty": False,
                "archive_sha256": "b" * 64,
                "bundle_checksums": {"manifest-workspace": "c" * 64},
                "selected_optional": [],
                "harnesses": {
                    "claude": {
                        "harness": "claude",
                        "adapter_version": "1",
                        "native_version": "2.1.0",
                        "plugin_ids": ["manifest-workspace"],
                        "owned_entries": [],
                        "capabilities": {
                            "manifest-workspace:mcp:context7": "verified",
                            "manifest-workspace:executable:python3": "verified",
                        },
                        "verified": True,
                        "errors": [],
                    }
                },
                "migration_backup": None,
            }
        ),
        encoding="utf-8",
    )
    timestamp = now.timestamp()
    os.utime(receipt, (timestamp, timestamp))

    owned = agent_root / "ui-expert.md"
    owned.parent.mkdir(parents=True)
    owned.write_text("owned\n", encoding="utf-8")
    pins = agent_root / "ui-workflow/dependencies.lock.json"
    pins.parent.mkdir(parents=True)
    pins.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "omp_version": "18.2.6",
                "python_version": platform.python_version(),
                "python_packages": {"PyYAML": "6.0.3", "jsonschema": "4.26.0"},
                "owned_files": {
                    "ui-expert.md": hashlib.sha256(owned.read_bytes()).hexdigest()
                },
            }
        ),
        encoding="utf-8",
    )

    runtime_root = tmp_path / "runtime"
    runtime_root.mkdir()
    file_rows: dict[str, dict[str, str]] = {}
    for name in (
        "health_report.py",
        "mcp_health.py",
        "env_check.py",
        "plugin_reconcile.py",
        "hook_smoke.py",
    ):
        path = runtime_root / name
        path.write_text(f"# {name}\n", encoding="utf-8")
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        file_rows[name] = {
            "source": str(path),
            "destination": str(path),
            "source_sha256": digest,
            "destination_sha256": digest,
        }
    extension = agent_root / "extensions/manifest-health.ts"
    extension.parent.mkdir(parents=True)
    extension.write_text("extension\n", encoding="utf-8")
    extension_digest = hashlib.sha256(extension.read_bytes()).hexdigest()
    wrapper = Path(env["HOME"]) / ".claude/scripts/mcp_health_check.sh"
    wrapper.parent.mkdir(parents=True)
    wrapper.write_text("#!/bin/sh\n", encoding="utf-8")
    wrapper_digest = hashlib.sha256(wrapper.read_bytes()).hexdigest()
    health_state = Path(env["XDG_STATE_HOME"]) / "manifest/health"
    health_state.mkdir(parents=True)
    installation = health_state / "installation.json"
    installation.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "installed_at": now.isoformat().replace("+00:00", "Z"),
                "source_root": str(source_root),
                "executables": {
                    "python": str(Path(sys.executable).resolve()),
                    "omp": str(tmp_path / "bin/omp"),
                    "claude": str(tmp_path / "bin/claude"),
                    "coordinator": str(tmp_path / "bin/manifest"),
                },
                "files": file_rows,
                "omp_extension": {
                    "source": str(extension),
                    "destination": str(extension),
                    "source_sha256": extension_digest,
                    "destination_sha256": extension_digest,
                },
                "claude_wrapper": {
                    "source": str(wrapper),
                    "destination": str(wrapper),
                    "source_sha256": wrapper_digest,
                    "destination_sha256": wrapper_digest,
                },
                "hook_hashes": {
                    "hooks.json": "a" * 64,
                    "stop_gate_hook.sh": "b" * 64,
                },
            }
        ),
        encoding="utf-8",
    )
    return env, runtime_root, receipt


class _HealthyReportRunner:
    def __init__(self, module) -> None:
        self.module = module

    def __call__(self, argv, timeout_seconds, environment):
        del timeout_seconds, environment
        command = [str(item) for item in argv]
        if command[-1:] == ["--version"]:
            version = "18.2.6" if Path(command[0]).name == "omp" else "2.1.0"
            return self.module.CommandResult("complete", 0, version + "\n")
        if "reconcile" in command:
            return self.module.CommandResult(
                "complete",
                0,
                json.dumps(
                    {
                        "operation": "reconcile",
                        "state": "READY",
                        "harnesses": {
                            "claude": {
                                "state": "READY",
                                "installed_plugin_ids": ["manifest-workspace"],
                                "capabilities": {
                                    "manifest-workspace:mcp:context7": "verified",
                                    "manifest-workspace:executable:python3": "verified",
                                },
                                "errors": [],
                                "warnings": [],
                            }
                        },
                        "notes": [],
                        "errors": [],
                    }
                ),
            )
        if Path(command[1]).name == "mcp_health.py":
            harness = command[command.index("--harness") + 1]
            return self.module.CommandResult(
                "complete",
                0,
                json.dumps(
                    {
                        "schema_version": 1,
                        "observed_at": "2026-09-20T12:00:00Z",
                        "harness": harness,
                        "status": "ok",
                        "servers": [
                            {
                                "name": "context7",
                                "status": "healthy",
                                "reason_code": "connected",
                            }
                        ],
                    }
                ),
            )
        if Path(command[1]).name == "hook_smoke.py":
            return self.module.CommandResult(
                "complete",
                0,
                json.dumps(
                    {
                        "schema_version": 1,
                        "observed_at": "2026-09-20T12:00:00Z",
                        "status": "ok",
                        "hashes": {
                            "hooks.json": "a" * 64,
                            "stop_gate_hook.sh": "b" * 64,
                        },
                        "checks": [],
                        "findings": [],
                    }
                ),
            )
        raise AssertionError(f"unexpected health command kind: {Path(command[0]).name}")


def _collect_report_fixture(tmp_path: Path, workspace_bundle: Path):
    script = workspace_bundle / "skills/env-check/scripts/health_report.py"
    module = _load_runtime_module(script, f"health_report_{tmp_path.name}")
    now = datetime(2026, 9, 20, 12, tzinfo=timezone.utc)
    env, runtime_root, receipt = _write_report_fixture(tmp_path, module, now)
    report = module.collect_report(
        harnesses=("claude", "omp"),
        environment=env,
        runtime_dir=runtime_root,
        clock=lambda: now,
        runner=_HealthyReportRunner(module),
        package_version=lambda name: {
            "PyYAML": "6.0.3",
            "jsonschema": "4.26.0",
        }[name],
    )
    return module, report, env, runtime_root, receipt, now


def test_weekly_health_report_accepts_only_complete_fresh_evidence_and_retains_twelve(
    workspace_bundle: Path, tmp_path: Path
) -> None:
    module, report, env, _runtime_root, _receipt, _now = _collect_report_fixture(
        tmp_path, workspace_bundle
    )

    assert report["schema_version"] == 1
    assert report["status"] == "ok"
    assert report["findings"] == []
    assert report["receipt"]["status"] == "ok"
    assert report["harnesses"]["claude"]["status"] == "ok"
    assert report["harnesses"]["omp"]["status"] == "ok"
    assert report["mcp"]["claude"]["status"] == "ok"
    assert report["hooks"]["status"] == "ok"
    assert report["pins"]["status"] == "ok"

    out_dir = Path(env["XDG_STATE_HOME"]) / "manifest/reports"
    out_dir.mkdir(parents=True)
    for day in range(1, 14):
        (out_dir / f"weekly-202608{day:02d}.json").write_text(
            "{}\n", encoding="utf-8"
        )
    unrelated = out_dir / "operator-note.json"
    unrelated.write_text("{}\n", encoding="utf-8")
    module.write_reports(report, out_dir)

    weekly = sorted(out_dir.glob("weekly-*.json"))
    assert len(weekly) == 12
    assert unrelated.exists()
    assert (out_dir / "latest.json").read_bytes() == (
        out_dir / "weekly-20260920.json"
    ).read_bytes()
    assert stat.S_IMODE((out_dir / "latest.json").stat().st_mode) == 0o600


@pytest.mark.parametrize(
    ("failure", "expected_code"),
    (
        ("missing", "receipt_missing"),
        ("malformed", "receipt_malformed"),
        ("stale", "receipt_stale"),
        ("blocked", "capability_blocked"),
        ("pin-drift", "pin_hash_mismatch"),
        ("native-missing", "native_cli_missing"),
    ),
)
def test_weekly_health_report_degrades_on_unverifiable_local_state(
    workspace_bundle: Path,
    tmp_path: Path,
    failure: str,
    expected_code: str,
) -> None:
    script = workspace_bundle / "skills/env-check/scripts/health_report.py"
    module = _load_runtime_module(script, f"health_report_failure_{failure}_{tmp_path.name}")
    now = datetime(2026, 9, 20, 12, tzinfo=timezone.utc)
    env, runtime_root, receipt, = _write_report_fixture(tmp_path, module, now)
    if failure == "missing":
        receipt.unlink()
    elif failure == "malformed":
        receipt.write_text("{", encoding="utf-8")
    elif failure == "stale":
        stale = now.timestamp() - (8 * 24 * 60 * 60)
        os.utime(receipt, (stale, stale))
    elif failure == "blocked":
        document = json.loads(receipt.read_text(encoding="utf-8"))
        document["harnesses"]["claude"]["capabilities"][
            "manifest-workspace:mcp:context7"
        ] = "blocked"
        receipt.write_text(json.dumps(document), encoding="utf-8")
    elif failure == "pin-drift":
        (Path(env["OMP_AGENT_DIR"]) / "ui-expert.md").write_text(
            "drifted\n", encoding="utf-8"
        )
    elif failure == "native-missing":
        installation = (
            Path(env["XDG_STATE_HOME"]) / "manifest/health/installation.json"
        )
        document = json.loads(installation.read_text(encoding="utf-8"))
        del document["executables"]["claude"]
        installation.write_text(json.dumps(document), encoding="utf-8")

    report = module.collect_report(
        harnesses=("claude", "omp"),
        environment=env,
        runtime_dir=runtime_root,
        clock=lambda: now,
        runner=_HealthyReportRunner(module),
        package_version=lambda name: {
            "PyYAML": "6.0.3",
            "jsonschema": "4.26.0",
        }[name],
    )

    assert report["status"] == "degraded"
    assert expected_code in {finding["code"] for finding in report["findings"]}


def test_weekly_health_report_degrades_safely_on_probe_timeout_and_hook_failure(
    workspace_bundle: Path, tmp_path: Path
) -> None:
    script = workspace_bundle / "skills/env-check/scripts/health_report.py"
    module = _load_runtime_module(script, f"health_report_probe_{tmp_path.name}")
    now = datetime(2026, 9, 20, 12, tzinfo=timezone.utc)
    env, runtime_root, _receipt = _write_report_fixture(tmp_path, module, now)
    healthy = _HealthyReportRunner(module)

    def failed_runner(argv, timeout_seconds, environment):
        command = [str(item) for item in argv]
        if len(command) > 1 and Path(command[1]).name == "mcp_health.py":
            return module.CommandResult("timeout")
        if len(command) > 1 and Path(command[1]).name == "hook_smoke.py":
            return module.CommandResult(
                "complete",
                1,
                json.dumps(
                    {
                        "schema_version": 1,
                        "observed_at": "2026-09-20T12:00:00Z",
                        "status": "degraded",
                        "hashes": {},
                        "checks": [],
                        "findings": ["runtime_unavailable"],
                    }
                )
                + " https://secret.invalid/token",
            )
        return healthy(argv, timeout_seconds, environment)

    report = module.collect_report(
        harnesses=("claude", "omp"),
        environment=env,
        runtime_dir=runtime_root,
        clock=lambda: now,
        runner=failed_runner,
        package_version=lambda name: {
            "PyYAML": "6.0.3",
            "jsonschema": "4.26.0",
        }[name],
    )

    encoded = json.dumps(report, sort_keys=True)
    assert report["status"] == "degraded"
    assert {"mcp_timeout", "hook_unparseable"} <= {
        finding["code"] for finding in report["findings"]
    }
    assert "secret.invalid" not in encoded


def test_health_report_bounded_runner_terminates_a_sleeping_process_group(
    workspace_bundle: Path, tmp_path: Path
) -> None:
    module = _load_runtime_module(
        workspace_bundle / "skills/env-check/scripts/health_report.py",
        f"health_report_timeout_{tmp_path.name}",
    )
    started = time.monotonic()

    result = module.run_bounded(
        [sys.executable, "-c", "import time; time.sleep(30)"],
        0.2,
        _isolated_env(tmp_path),
    )

    assert result.outcome == "timeout"
    assert time.monotonic() - started < 3


def test_health_report_reserves_time_for_nested_mcp_probe_cleanup(
    workspace_bundle: Path, tmp_path: Path
) -> None:
    module = _load_runtime_module(
        workspace_bundle / "skills/env-check/scripts/health_report.py",
        f"health_report_nested_probe_{tmp_path.name}",
    )
    helper = tmp_path / "nested_probe.py"
    pid_file = tmp_path / "nested-child.pid"
    helper.write_text(
        """\
import argparse
import os
from pathlib import Path
import signal
import subprocess
import sys

parser = argparse.ArgumentParser(add_help=False)
parser.add_argument("--timeout-seconds", type=float, required=True)
args, _unknown = parser.parse_known_args()
child = subprocess.Popen(
    [sys.executable, "-c", "import time; time.sleep(30)"],
    start_new_session=True,
)
Path(os.environ["NESTED_CHILD_PID_FILE"]).write_text(str(child.pid), encoding="utf-8")
try:
    child.wait(timeout=args.timeout_seconds)
except subprocess.TimeoutExpired:
    os.killpg(child.pid, signal.SIGKILL)
    child.wait(timeout=1)
print("{}")
raise SystemExit(1)
""",
        encoding="utf-8",
    )
    environment = _isolated_env(tmp_path)
    environment["NESTED_CHILD_PID_FILE"] = str(pid_file)
    started = time.monotonic()
    observation = module.Observation(
        "mcp:claude",
        "mcp",
        "claude",
        (
            sys.executable,
            str(helper),
            "--json",
            "--probe",
            "--harness",
            "claude",
            "--timeout-seconds",
            "20",
        ),
        2.5,
    )

    result = module._observation_result(
        observation,
        started + 2.5,
        time.monotonic,
        module.run_bounded,
        environment,
    )
    child_pid = int(pid_file.read_text(encoding="utf-8"))
    try:
        assert result.outcome == "complete"
        assert result.returncode == 1
        with pytest.raises(ProcessLookupError):
            os.kill(child_pid, 0)
    finally:
        try:
            os.killpg(child_pid, 9)
        except ProcessLookupError:
            pass


def test_health_report_degrades_unobserved_receipt_backed_harness_version(
    workspace_bundle: Path, tmp_path: Path
) -> None:
    script = workspace_bundle / "skills/env-check/scripts/health_report.py"
    module = _load_runtime_module(
        script, f"health_report_unobserved_version_{tmp_path.name}"
    )
    now = datetime(2026, 9, 20, 12, tzinfo=timezone.utc)
    env, runtime_root, receipt = _write_report_fixture(tmp_path, module, now)
    receipt_document = json.loads(receipt.read_text(encoding="utf-8"))
    codex_record = json.loads(
        json.dumps(receipt_document["harnesses"]["claude"])
    )
    codex_record["harness"] = "codex"
    receipt_document["harnesses"]["codex"] = codex_record
    receipt.write_text(json.dumps(receipt_document), encoding="utf-8")
    timestamp = now.timestamp()
    os.utime(receipt, (timestamp, timestamp))
    healthy = _HealthyReportRunner(module)

    def runner(argv, timeout_seconds, environment):
        result = healthy(argv, timeout_seconds, environment)
        command = [str(item) for item in argv]
        if "reconcile" not in command:
            return result
        inventory = json.loads(result.stdout)
        inventory["harnesses"]["codex"] = {
            "state": "READY",
            "installed_plugin_ids": ["manifest-workspace"],
            "capabilities": {
                "manifest-workspace:mcp:context7": "verified",
                "manifest-workspace:executable:python3": "verified",
            },
            "errors": [],
            "warnings": [],
        }
        return module.CommandResult("complete", 0, json.dumps(inventory))

    report = module.collect_report(
        harnesses=("claude", "omp"),
        environment=env,
        runtime_dir=runtime_root,
        clock=lambda: now,
        runner=runner,
        package_version=lambda name: {
            "PyYAML": "6.0.3",
            "jsonschema": "4.26.0",
        }[name],
    )

    assert report["status"] == "degraded"
    assert report["harnesses"]["codex"]["status"] == "degraded"
    assert report["harnesses"]["codex"]["version_status"] == "not_observed"
    assert {
        (finding["code"], finding.get("harness"))
        for finding in report["findings"]
    } >= {("version_not_observed", "codex")}

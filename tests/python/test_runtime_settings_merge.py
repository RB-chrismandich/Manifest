"""Execute deployment merges with a fake HOME distinct from the actual target."""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SCRIPTS = REPO / "configs/claude/scripts"
MERGER = SCRIPTS / "merge_runtime_settings.py"


@pytest.fixture
def deployment(tmp_path, monkeypatch):
    home = tmp_path / "ambient"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    for key in (
        "CLAUDE_CODE_SUBAGENT_MODEL",
        "CLAUDE_CODE_SUBAGENT_MODEL_FORCE",
        "CLAUDE_CONFIG_DIR",
    ):
        monkeypatch.delenv(key, raising=False)
    target = tmp_path / "target with spaces/.claude/settings.json"
    target.parent.mkdir(parents=True)
    return target


def merge(target, version="2.1.263", *args):
    return subprocess.run(
        [
            sys.executable,
            str(MERGER),
            str(REPO / "configs/claude/settings.runtime.json"),
            str(target),
            "--host-version",
            version,
            *args,
        ],
        text=True,
        capture_output=True,
        check=False,
    )


def receipt(target):
    return json.loads(
        (target.parent / "config/runtime_settings_merge.json").read_text()
    )


def test_target_hook_executes_without_ambient_home(deployment):
    scripts = deployment.parent / "scripts"
    scripts.mkdir()
    shutil.copy2(SCRIPTS / "subagent_model_default.py", scripts)
    result = merge(deployment)
    assert result.returncode == 0, result.stderr
    settings = json.loads(deployment.read_text())
    command = settings["hooks"]["PreToolUse"][0]["hooks"][0]["command"]
    import shlex

    run = subprocess.run(
        shlex.split(command),
        input='{"tool_name":"Agent","tool_input":{"prompt":"p","subagent_type":"general-purpose"}}',
        text=True,
        capture_output=True,
        check=False,
    )
    assert run.returncode == 0, run.stderr
    assert run.stdout == ""
    assert "native default unobserved" in run.stderr
    assert settings["env"]["CLAUDE_CODE_SUBAGENT_MODEL"] == "sonnet"
    assert list(Path(os.environ["HOME"]).iterdir()) == []


@pytest.mark.parametrize(
    "version,seeded",
    [
        ("2.1.250", False),
        ("2.1.251", True),
        ("2.1.263", True),
        ("unknown", False),
        ("garbage", False),
    ],
)
def test_version_gate_never_overrides_pins_on_old_hosts(deployment, version, seeded):
    result = merge(deployment, version)
    assert result.returncode == 0, result.stderr
    settings = json.loads(deployment.read_text())
    assert (
        settings.get("env", {}).get("CLAUDE_CODE_SUBAGENT_MODEL") == "sonnet"
    ) is seeded
    assert "CLAUDE_CODE_SUBAGENT_MODEL_FORCE" not in settings.get("env", {})
    assert receipt(deployment)["worker_default"] == (
        "seeded" if seeded else "unsupported-host"
    )


def test_idempotent_merge_preserves_user_model_effort_permissions(deployment):
    original = {
        "model": "deliberate-model",
        "effortLevel": "deliberate-effort",
        "permissions": {"deny": ["Bash(rm:*)"]},
        "env": {"CLAUDE_CODE_SUBAGENT_MODEL": "deliberate-worker"},
    }
    deployment.write_text(json.dumps(original))
    assert merge(deployment).returncode == 0
    first = deployment.read_bytes()
    assert merge(deployment).returncode == 0
    assert deployment.read_bytes() == first
    settings = json.loads(first)
    for key in ("model", "effortLevel", "env"):
        assert settings[key] == original[key]
    assert settings["permissions"]["deny"] == original["permissions"]["deny"]
    assert receipt(deployment)["worker_default"] == "user-preserved"


@pytest.mark.parametrize(
    "key", ["CLAUDE_CODE_SUBAGENT_MODEL", "CLAUDE_CODE_SUBAGENT_MODEL_FORCE"]
)
def test_process_overrides_are_preserved_without_seeding(deployment, monkeypatch, key):
    monkeypatch.setenv(key, "deliberate")
    assert merge(deployment).returncode == 0
    assert "CLAUDE_CODE_SUBAGENT_MODEL" not in json.loads(deployment.read_text()).get(
        "env", {}
    )
    assert receipt(deployment)["worker_default"] == "process-override"


@pytest.mark.parametrize(
    "bad",
    ["not json", "[]", '{"hooks":[]}', '{"env":[]}', '{"permissions":{"allow":42}}'],
)
def test_malformed_target_is_preserved_and_failure_observable(deployment, bad):
    deployment.write_text(bad)
    result = merge(deployment)
    assert result.returncode == 1
    assert deployment.read_text() == bad
    assert "Traceback" not in result.stderr


def test_rollback_only_removes_owned_default_and_preserves_later_changes(deployment):
    assert merge(deployment).returncode == 0
    settings = json.loads(deployment.read_text())
    settings["model"] = "later-user-choice"
    deployment.write_text(json.dumps(settings))
    assert merge(deployment, "2.1.263", "--rollback-default").returncode == 0
    after = json.loads(deployment.read_text())
    assert after["model"] == "later-user-choice"
    assert "CLAUDE_CODE_SUBAGENT_MODEL" not in after["env"]
    assert after["hooks"] == settings["hooks"]


def test_rollback_will_not_remove_a_user_replacement(deployment):
    assert merge(deployment).returncode == 0
    settings = json.loads(deployment.read_text())
    settings["env"]["CLAUDE_CODE_SUBAGENT_MODEL"] = "user-replacement"
    deployment.write_text(json.dumps(settings))
    assert merge(deployment, "2.1.263", "--rollback-default").returncode == 0
    assert (
        json.loads(deployment.read_text())["env"]["CLAUDE_CODE_SUBAGENT_MODEL"]
        == "user-replacement"
    )


def test_receipt_is_redacted_and_records_effective_hash(deployment):
    import hashlib

    deployment.write_text('{"env":{"PRIVATE_SETTING":"private value"}}')
    assert merge(deployment).returncode == 0
    report = receipt(deployment)
    assert "private value" not in json.dumps(report)
    assert (
        report["settings_sha256"] == hashlib.sha256(deployment.read_bytes()).hexdigest()
    )
    assert report["host_version"] == "2.1.263"
    assert report["status"] == "merged"
    assert len(report["policy_sha256"]) == 64


def test_host_downgrade_removes_only_manifest_owned_default(deployment):
    assert merge(deployment).returncode == 0
    assert merge(deployment, "2.1.250").returncode == 0
    assert "CLAUDE_CODE_SUBAGENT_MODEL" not in json.loads(deployment.read_text())["env"]
    assert receipt(deployment)["worker_default"] == "unsupported-host"


def test_symlink_target_cannot_write_outside_target(deployment):
    outside = deployment.parents[2] / "untouched.json"
    outside.write_text("{}")
    deployment.symlink_to(outside)
    result = merge(deployment)
    assert result.returncode == 1
    assert outside.read_text() == "{}"


def test_busy_merge_does_not_retry_or_overwrite(deployment):
    import fcntl

    deployment.write_text("{}")
    with (deployment.parent / ".manifest-runtime.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        result = merge(deployment)
    assert result.returncode == 1
    assert deployment.read_text() == "{}"


def test_receipt_failure_cannot_commit_settings_without_ownership(deployment):
    deployment.write_text("{}")
    (deployment.parent / "config").write_text("not a directory")
    result = merge(deployment)
    assert result.returncode == 1
    assert deployment.read_text() == "{}"


def test_legacy_injecting_hook_is_migrated_without_duplicate(deployment):
    command = str(deployment.parent / "scripts/subagent_model_default.py")
    deployment.write_text(
        json.dumps(
            {
                "hooks": {
                    "PreToolUse": [
                        {
                            "matcher": "Agent",
                            "hooks": [{"type": "command", "command": command}],
                        }
                    ]
                }
            }
        )
    )
    assert merge(deployment, "2.1.250").returncode == 0
    hooks = json.loads(deployment.read_text())["hooks"]["PreToolUse"]
    matching = [
        h
        for e in hooks
        for h in e["hooks"]
        if "subagent_model_default.py" in h.get("command", "")
    ]
    assert len(matching) == 1
    assert "--native-default-only" in matching[0]["command"]


def test_prepared_receipt_recovers_ownership_after_final_receipt_failure(
    deployment, monkeypatch
):
    import importlib.util

    monkeypatch.syspath_prepend(str(SCRIPTS))
    spec = importlib.util.spec_from_file_location("merge_runtime_settings", MERGER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    writer = module.write_private_json
    calls = 0

    def failing_receipt(path, value):
        nonlocal calls
        calls += 1
        if calls == 3:
            raise OSError("simulated final receipt failure")
        writer(path, value)

    monkeypatch.setattr(module, "write_private_json", failing_receipt)
    with pytest.raises(OSError):
        module.perform(
            REPO / "configs/claude/settings.runtime.json", deployment, "2.1.263", False
        )
    assert receipt(deployment)["status"] == "prepared"
    assert receipt(deployment)["owned_default"] is True
    assert merge(deployment, "2.1.263", "--rollback-default").returncode == 0
    assert "CLAUDE_CODE_SUBAGENT_MODEL" not in json.loads(deployment.read_text())["env"]


def test_failed_downgrade_keeps_prior_ownership(deployment, monkeypatch):
    import importlib.util

    assert merge(deployment).returncode == 0
    monkeypatch.syspath_prepend(str(SCRIPTS))
    spec = importlib.util.spec_from_file_location("merge_runtime_settings", MERGER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    writer = module.write_private_json

    def fail_settings(path, value):
        if path == deployment:
            raise OSError("simulated settings failure")
        writer(path, value)

    monkeypatch.setattr(module, "write_private_json", fail_settings)
    with pytest.raises(OSError):
        module.perform(
            REPO / "configs/claude/settings.runtime.json", deployment, "2.1.250", False
        )
    assert merge(deployment, "2.1.263", "--rollback-default").returncode == 0
    assert "CLAUDE_CODE_SUBAGENT_MODEL" not in json.loads(deployment.read_text())["env"]

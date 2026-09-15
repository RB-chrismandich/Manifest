"""Behavior tests for compaction-aware session handoff continuity."""

from __future__ import annotations

import json
import os
import stat
import subprocess
import sys
from pathlib import Path

import pytest

from tests.python.plugin_runtime.session_continuity_helpers import (
    _checkpoint,
    _completed,
    _precompact,
)
from tests.python.plugin_runtime.session_continuity_helpers import (
    repo_root as repo_root,
)
from tests.python.plugin_runtime.session_continuity_helpers import (
    runtime as runtime,
)
from tests.python.plugin_runtime.session_continuity_helpers import (
    state_home as state_home,
)


def test_counts_only_completed_claude_compaction_sequences(
    runtime, state_home: Path
) -> None:
    store = runtime.SessionContinuityStore(state_home)

    attempted = store.record_claude_event(_precompact())
    failed = store.record_claude_event(
        {
            "hook_event_name": "SessionStart",
            "source": "resume",
            "session_id": "primary",
        }
    )
    store.record_claude_event(_precompact())
    completed = store.record_claude_event(_completed())

    assert attempted.compaction_count == 0
    assert failed.compaction_count == 0
    assert completed.compaction_count == 1
    assert completed.telemetry == "confirmed"


def test_deduplicates_retries_excludes_child_agents_and_keeps_agent_sessions(
    runtime, state_home: Path
) -> None:
    store = runtime.SessionContinuityStore(state_home)

    store.record_claude_event(_precompact())
    store.record_claude_event(_precompact())
    store.record_claude_event(_completed())
    retried = store.record_claude_event(_completed())
    store.record_claude_event(_precompact("agent", agent_type="reviewer"))
    agent_session = store.record_claude_event(
        _completed("agent", agent_type="reviewer")
    )
    store.record_claude_event(_precompact("child", agent_id="child-123"))
    child = store.record_claude_event(_completed("child", agent_id="child-123"))

    assert retried.compaction_count == 1
    assert agent_session.compaction_count == 1
    assert child.excluded is True
    assert store.status("child", "claude").compaction_count == 0


@pytest.mark.parametrize("value", [None, "2", "5"])
def test_threshold_configuration(runtime, monkeypatch, value: str | None) -> None:
    monkeypatch.delenv("MANIFEST_COMPACTION_REMINDER_THRESHOLD", raising=False)
    if value is not None:
        monkeypatch.setenv("MANIFEST_COMPACTION_REMINDER_THRESHOLD", value)

    assert runtime.reminder_threshold() == (2 if value is None else int(value))


@pytest.mark.parametrize("value", ["", "0", "-1", "two"])
def test_invalid_threshold_configuration_is_rejected(
    runtime, monkeypatch, value: str
) -> None:
    monkeypatch.setenv("MANIFEST_COMPACTION_REMINDER_THRESHOLD", value)

    with pytest.raises(runtime.ConfigurationError, match="positive integer"):
        runtime.reminder_threshold()


@pytest.mark.parametrize(
    "harness", ["codex", "gemini", "cursor", "antigravity", "devin", "other"]
)
def test_unavailable_compaction_telemetry_is_unknown(
    runtime, state_home: Path, harness: str
) -> None:
    status = runtime.SessionContinuityStore(state_home).status("session", harness)

    assert status.telemetry == "unknown"
    assert status.compaction_count is None


@pytest.mark.parametrize(
    ("boundary", "recommend"),
    [("safe", True), ("active", False), ("unknown", False)],
)
def test_reminder_requires_verified_safe_boundary_and_checkpoint(
    runtime, state_home: Path, boundary: str, recommend: bool
) -> None:
    store = runtime.SessionContinuityStore(state_home)
    for _ in range(2):
        store.record_claude_event(_precompact())
        store.record_claude_event(_completed())
    checkpoint = runtime.write_checkpoint(_checkpoint(), state_home)

    decision = store.handoff_decision(
        "primary", boundary=boundary, checkpoint_path=checkpoint
    )

    assert decision.recommend_fresh_session is recommend
    if recommend:
        assert decision.checkpoint_path == checkpoint
        assert decision.continuation_goal.startswith("Continue implementing")


def test_reminder_is_once_per_session(runtime, state_home: Path) -> None:
    store = runtime.SessionContinuityStore(state_home)
    for _ in range(2):
        store.record_claude_event(_precompact())
        store.record_claude_event(_completed())
    checkpoint = runtime.write_checkpoint(_checkpoint(), state_home)

    first = store.handoff_decision("primary", "safe", checkpoint)
    second = store.handoff_decision("primary", "safe", checkpoint)

    assert first.recommend_fresh_session is True
    assert second.recommend_fresh_session is False
    assert second.reason == "already-reminded"


def test_explicit_deferral_suppresses_reminders(runtime, state_home: Path) -> None:
    store = runtime.SessionContinuityStore(state_home)
    for _ in range(2):
        store.record_claude_event(_precompact())
        store.record_claude_event(_completed())
    checkpoint = runtime.write_checkpoint(_checkpoint(), state_home)

    store.defer("primary")

    decision = store.handoff_decision("primary", "safe", checkpoint)
    assert decision.recommend_fresh_session is False
    assert decision.reason == "deferred"


def test_checkpoint_persistence_is_atomic_private_and_integrity_checked(
    runtime, state_home: Path
) -> None:
    path = runtime.write_checkpoint(_checkpoint(), state_home)

    assert path.parent == state_home / "manifest/checkpoints"
    assert stat.S_IMODE(path.parent.stat().st_mode) == 0o700
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert not list(path.parent.glob("*.tmp"))
    verified = runtime.read_checkpoint(path)
    assert verified["original_goal"] == _checkpoint()["original_goal"]
    assert verified["verification_evidence"] == _checkpoint()["verification_evidence"]
    assert verified["live_operations"] == _checkpoint()["live_operations"]


def test_checkpoint_persistence_failure_is_reported(
    runtime, state_home: Path, monkeypatch
) -> None:
    def fail_replace(source: os.PathLike[str], target: os.PathLike[str]) -> None:
        raise OSError("disk unavailable")

    monkeypatch.setattr(runtime.os, "replace", fail_replace)

    with pytest.raises(runtime.PersistenceError, match="disk unavailable"):
        runtime.write_checkpoint(_checkpoint(), state_home)


def test_corrupt_checkpoint_is_rejected(runtime, state_home: Path) -> None:
    path = runtime.write_checkpoint(_checkpoint(), state_home)
    envelope = json.loads(path.read_text(encoding="utf-8"))
    envelope["checkpoint"]["completed_work"] = ["fabricated completion"]
    path.write_text(json.dumps(envelope), encoding="utf-8")

    with pytest.raises(runtime.IntegrityError, match="integrity"):
        runtime.read_checkpoint(path)


def test_truncated_checkpoint_is_rejected_as_corruption(
    runtime, state_home: Path
) -> None:
    path = runtime.write_checkpoint(_checkpoint(), state_home)
    path.write_text('{"checkpoint":', encoding="utf-8")

    with pytest.raises(runtime.IntegrityError, match="integrity"):
        runtime.read_checkpoint(path)


def test_corrupt_session_state_is_rejected_and_hook_delivery_stays_nonblocking(
    runtime, repo_root: Path, state_home: Path
) -> None:
    store = runtime.SessionContinuityStore(state_home)
    store.record_claude_event(_precompact())
    state_path = next(store.root.glob("*.json"))
    state_path.write_text("{}", encoding="utf-8")

    with pytest.raises(runtime.PersistenceError, match="session state"):
        store.status("primary", "claude")

    script = (
        repo_root
        / "plugins/manifest-workspace/skills/session-checkpoint/scripts/session_continuity.py"
    )
    result = subprocess.run(
        [sys.executable, "-B", str(script), "hook-event", "--harness", "claude"],
        input=json.dumps(_completed()),
        text=True,
        capture_output=True,
        env={**os.environ, "XDG_STATE_HOME": str(state_home)},
        check=False,
    )
    assert result.returncode == 0
    assert "session state" in result.stderr


@pytest.mark.parametrize(
    ("field", "value", "match"),
    [
        ("schema_version", 2, "schema_version"),
        ("session_id", "other-session", "session_id"),
        ("compaction_count", "one", "compaction_count"),
        ("pending_precompact", 1, "pending_precompact"),
        ("reminded", None, "reminded"),
        ("deferred", "no", "deferred"),
    ],
)
def test_session_state_schema_is_validated_before_use(
    runtime, state_home: Path, field: str, value: object, match: str
) -> None:
    store = runtime.SessionContinuityStore(state_home)
    store.record_claude_event(_precompact())
    state_path = next(store.root.glob("*.json"))
    state = json.loads(state_path.read_text(encoding="utf-8"))
    state[field] = value
    state_path.write_text(json.dumps(state), encoding="utf-8")

    with pytest.raises(runtime.PersistenceError, match=match):
        store.status("primary", "claude")


def test_checkpoint_rejects_missing_durable_evidence_and_operation_ownership(
    runtime, state_home: Path
) -> None:
    checkpoint = _checkpoint()
    checkpoint["verification_evidence"] = [{"command": "pytest", "outcome": "pass"}]
    checkpoint["live_operations"] = [{"handle": "job-17", "status": "running"}]

    with pytest.raises(runtime.CheckpointValidationError) as error:
        runtime.write_checkpoint(checkpoint, state_home)

    assert "evidence" in str(error.value)
    assert "owner" in str(error.value)


def test_continuation_revalidates_git_and_live_operation_ownership(
    runtime, state_home: Path
) -> None:
    path = runtime.write_checkpoint(_checkpoint(), state_home)

    report = runtime.revalidate_continuation(
        path,
        current_repository={
            "path": "/repo",
            "branch": "feature",
            "head": "def456",
            "dirty_tree": [" M retained-change.py", "?? new.py"],
        },
        current_live_operations=[
            {
                "owner": "replacement-session",
                "handle": "job-17",
                "status": "running",
                "obligation": "Continue polling; never duplicate the job.",
            }
        ],
    )

    assert report.trusted is False
    assert set(report.git_changes) == {"branch", "head", "dirty_tree"}
    assert report.ownership_changes == ("job-17",)
    assert report.continuation_goal.startswith("Continue implementing")


@pytest.mark.parametrize(
    ("repository", "expected"),
    (
        ({"head": "   "}, "repository.head must be a non-empty string"),
        ({"path": ""}, "repository.path must be a non-empty string"),
        (
            {"dirty_tree": [3]},
            "repository.dirty_tree entries must be non-empty strings",
        ),
    ),
)
def test_checkpoint_rejects_unusable_repository_identity(
    runtime, state_home: Path, repository: dict, expected: str
) -> None:
    """An empty or non-string identity can never match a real Git snapshot."""
    checkpoint = _checkpoint()
    checkpoint["repository"] = {**checkpoint["repository"], **repository}

    with pytest.raises(runtime.CheckpointValidationError) as error:
        runtime.write_checkpoint(checkpoint, state_home)

    assert expected in str(error.value)


@pytest.mark.parametrize("operation", (1, {"handle": "job-17"}, {"owner": "  "}))
def test_revalidation_refuses_unverifiable_live_operations(
    runtime, state_home: Path, operation: object
) -> None:
    """Silently dropping these would report `trusted` for an unowned job."""
    path = runtime.write_checkpoint(_checkpoint(), state_home)

    with pytest.raises(runtime.CheckpointValidationError) as error:
        runtime.revalidate_continuation(
            path,
            current_repository=_checkpoint()["repository"],
            current_live_operations=[operation],
        )

    assert "live_operations[0] requires owner and handle" in str(error.value)


@pytest.mark.parametrize("version", (None, "1", 2, True))
def test_checkpoint_envelope_version_is_verified_before_the_body(
    runtime, state_home: Path, version: object
) -> None:
    """The digest covers the body only, so the version is attacker-writable."""
    path = runtime.write_checkpoint(_checkpoint(), state_home)
    envelope = json.loads(path.read_text(encoding="utf-8"))
    if version is None:
        envelope.pop("schema_version")
    else:
        envelope["schema_version"] = version
    path.write_text(json.dumps(envelope), encoding="utf-8")

    with pytest.raises(runtime.IntegrityError) as error:
        runtime.read_checkpoint(path)

    assert "schema version" in str(error.value)

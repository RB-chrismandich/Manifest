"""Shared fixtures and payload builders for session-continuity behavior tests."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest


@pytest.fixture
def repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


@pytest.fixture
def runtime(repo_root: Path):
    path = (
        repo_root
        / "plugins/manifest-workspace/skills/session-checkpoint/scripts/session_continuity.py"
    )
    spec = importlib.util.spec_from_file_location("session_continuity", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def state_home(tmp_path: Path) -> Path:
    path = tmp_path / "state"
    path.mkdir()
    return path


def _precompact(session_id: str = "primary", **extra: object) -> dict[str, object]:
    return {
        "hook_event_name": "PreCompact",
        "session_id": session_id,
        "trigger": "auto",
        "transcript_path": "/private/session.jsonl",
        **extra,
    }


def _completed(session_id: str = "primary", **extra: object) -> dict[str, object]:
    return {
        "hook_event_name": "SessionStart",
        "source": "compact",
        "session_id": session_id,
        "transcript_path": "/private/session.jsonl",
        **extra,
    }


def _checkpoint() -> dict[str, object]:
    return {
        "source_session_id": "primary",
        "original_goal": "Implement compaction-aware handoff without losing work.",
        "constraints": ["Do not restart automatically."],
        "decisions": [
            {
                "decision": "Count confirmed lifecycle sequences only.",
                "rationale": "PreCompact alone is only an attempt.",
            }
        ],
        "repository": {
            "path": "/repo",
            "branch": "main",
            "head": "abc123",
            "dirty_tree": [" M retained-change.py"],
        },
        "completed_work": ["Research complete."],
        "remaining_work": ["Implement runtime."],
        "verification_evidence": [
            {
                "command": "pytest tests/python/plugin_runtime/test_session_continuity.py",
                "outcome": "14 passed",
                "evidence": "pytest terminal output captured in checkpoint",
            }
        ],
        "unresolved_uncertainty": ["Other harness telemetry is unavailable."],
        "next_action": "Open session_continuity.py and inspect the event adapter.",
        "live_operations": [
            {
                "owner": "primary",
                "handle": "job-17",
                "status": "running",
                "obligation": "Continue polling; never duplicate the job.",
            }
        ],
        "continuation_goal": (
            "Continue implementing compaction-aware handoff. First inspect Git state "
            "and verify job-17 ownership."
        ),
    }

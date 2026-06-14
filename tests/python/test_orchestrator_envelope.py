"""T013 — Foundational: response-envelope validation (FR-001, FR-002, FR-004, FR-005)."""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "configs" / "claude" / "scripts"))

from orchestrator import engine  # noqa: E402


def ok_envelope():
    return {"phase": 1, "status": "ok", "payload": {"x": 1},
            "reasoning_log": ["chose x"], "escalation": None}


def test_valid_ok_envelope_passes():
    assert engine.validate_envelope(ok_envelope()) == []


def test_missing_key_fails():
    env = ok_envelope()
    del env["escalation"]
    assert any("missing required keys" in e for e in engine.validate_envelope(env))


def test_extra_key_outside_envelope_fails():  # FR-002
    env = ok_envelope()
    env["extra"] = "nope"
    assert any("unexpected keys" in e for e in engine.validate_envelope(env))


def test_bad_phase_fails():
    env = ok_envelope()
    env["phase"] = 7
    assert any("phase must be" in e for e in engine.validate_envelope(env))


def test_non_ok_with_nonempty_payload_fails():  # FR-005
    env = ok_envelope()
    env["status"] = "blocked"
    env["escalation"] = {"reason": "x", "blocking_state": {"type": "missing_input", "transient": False}}
    assert any("payload MUST be {}" in e for e in engine.validate_envelope(env))


def test_ok_with_escalation_fails():
    env = ok_envelope()
    env["escalation"] = {"reason": "x", "blocking_state": {"type": "t", "transient": False}}
    assert any("escalation MUST be null" in e for e in engine.validate_envelope(env))


def test_reasoning_log_must_be_list_of_strings():  # FR-004
    env = ok_envelope()
    env["reasoning_log"] = "not a list"
    assert any("reasoning_log must be a list" in e for e in engine.validate_envelope(env))


def test_justification_only_in_reasoning_log():  # FR-004 — structured payload carries no prose justification
    result = engine.prioritize([{"id": "#1", "labels": ["severity:high"], "depends_on": []}])
    payload = result.to_payload()
    # the only free-text justification field is top_choice_justification; rationale lives in reasoning_log
    assert set(payload.keys()) == {"ranked_issue_ids", "top_choice_justification", "dependency_notes"}


def test_blocked_envelope_helper_is_valid():  # FR-005 / FR-035
    env = engine.blocked_envelope(4, "tool unavailable", transient=True, bs_type="resource_unavailable")
    assert engine.validate_envelope(env) == []
    assert env["escalation"]["blocking_state"]["transient"] is True

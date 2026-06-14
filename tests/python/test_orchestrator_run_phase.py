"""R1 — run_phase orchestration: invoke→validate→retry→escalate→persist (FR-001/027/025/035/029)."""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "configs" / "claude" / "scripts"))

from orchestrator import daemon, pipeline, audit  # noqa: E402

VALID = {"phase": 1, "status": "ok", "payload": {"x": 1}, "reasoning_log": ["r"], "escalation": None}
INVALID = {"phase": 1}   # missing required keys → fails validate_envelope


class FakeBackend:
    def __init__(self, envelopes):
        self.queue = list(envelopes)
        self.calls = 0

    def invoke(self, payload):
        self.calls += 1
        return self.queue.pop(0)


def test_valid_envelope_returned_and_audited(tmp_path):
    log = audit.AuditLog(tmp_path, run_id="r1")
    st = pipeline.PipelineState(run_id="r1")
    be = FakeBackend([VALID])
    env = daemon.run_phase(be, 1, {"issues": []}, st, audit_log=log)
    assert env["status"] == "ok" and be.calls == 1
    assert log.path.read_text().strip()                 # persisted (FR-029)


def test_invalid_then_valid_retries_under_cap():  # FR-027
    st = pipeline.PipelineState(run_id="r2")
    be = FakeBackend([INVALID, VALID])
    env = daemon.run_phase(be, 1, {}, st)
    assert env["status"] == "ok" and be.calls == 2      # retried once, then succeeded


def test_two_invalid_escalates():  # FR-027
    st = pipeline.PipelineState(run_id="r3")
    be = FakeBackend([INVALID, INVALID])
    env = daemon.run_phase(be, 1, {}, st)
    assert env["status"] == "needs_escalation"
    assert env["escalation"]["blocking_state"]["type"] == "invalid_envelope"
    assert be.calls == 2                                 # capped at 2 attempts


def test_critical_flag_short_circuits_before_invoke():  # FR-025
    st = pipeline.PipelineState(run_id="r4")
    be = FakeBackend([VALID])
    env = daemon.run_phase(be, 4, {}, st, critical_failure=True)
    assert env["status"] == "needs_escalation" and be.calls == 0


def test_resource_pause_short_circuits_before_invoke():  # FR-035
    st = pipeline.PipelineState(run_id="r5")
    be = FakeBackend([VALID])
    env = daemon.run_phase(be, 4, {}, st, resource_available=False)
    assert env["status"] == "blocked"
    assert env["escalation"]["blocking_state"]["transient"] is True
    assert be.calls == 0 and st.paused is True

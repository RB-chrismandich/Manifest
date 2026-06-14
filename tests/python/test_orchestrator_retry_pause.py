"""T040 — US5: retry cap, resource pause, critical-flag escalation (FR-025, FR-027, FR-035)."""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "configs" / "claude" / "scripts"))

from orchestrator import pipeline, daemon, engine  # noqa: E402


def test_attempt_cap_escalates_on_second_failure():  # FR-027
    st = pipeline.PipelineState(run_id="r")
    st.record_attempt(4)
    assert not st.should_escalate(4)
    st.record_attempt(4)
    assert st.should_escalate(4)


def test_critical_flag_escalates():  # FR-025
    st = pipeline.PipelineState(run_id="r")
    env = daemon.handle_control_flags(4, st, critical_failure=True)
    assert env["status"] == "needs_escalation"
    assert env["escalation"]["blocking_state"]["type"] == "critical_failure"


def test_resource_exhaustion_pauses_without_attempt_increment():  # FR-035
    st = pipeline.PipelineState(run_id="r")
    st.record_attempt(4)                      # one prior attempt
    env = daemon.handle_control_flags(4, st, resource_available=False)
    assert env["status"] == "blocked"
    assert env["escalation"]["blocking_state"]["transient"] is True
    assert st.paused is True
    assert st.attempt_counts["4"] == 1        # pause did NOT consume an attempt
    assert engine.validate_envelope(env) == []


def test_no_control_condition_returns_none():
    st = pipeline.PipelineState(run_id="r")
    assert daemon.handle_control_flags(4, st) is None


def test_resource_pause_is_distinct_from_missing_input():  # FR-035 vs FR-005
    st = pipeline.PipelineState(run_id="r")
    pause = daemon.handle_control_flags(4, st, resource_available=False)
    miss = engine.require_inputs(4, {}, ["analysis"])
    assert pause["escalation"]["blocking_state"]["transient"] is True
    assert miss["escalation"]["blocking_state"]["transient"] is False

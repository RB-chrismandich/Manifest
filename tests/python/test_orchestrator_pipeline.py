"""T014 — Foundational: pipeline state machine, gating, cycle detection (FR-027, FR-035, FR-037)."""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "configs" / "claude" / "scripts"))

from orchestrator import pipeline  # noqa: E402


def test_advance_walks_six_phases_then_stops():
    st = pipeline.PipelineState(run_id="r1")
    seen = [st.current_phase]
    while (nxt := st.advance()) is not None:
        seen.append(nxt)
    assert seen == [1, 2, 3, 4, 5, 6]


def test_attempt_cap_escalates_on_second_failure():  # FR-027
    st = pipeline.PipelineState(run_id="r1")
    st.record_attempt(3)
    assert st.should_escalate(3, cap=2) is False
    st.record_attempt(3)
    assert st.should_escalate(3, cap=2) is True


def test_resource_pause_does_not_increment_attempts():  # FR-035
    st = pipeline.PipelineState(run_id="r1")
    st.record_attempt(4)
    st.pause_for_resource()
    assert st.paused is True
    assert st.attempt_counts["4"] == 1  # unchanged by the pause
    st.resume()
    assert st.paused is False


def test_state_roundtrips_to_disk(tmp_path):
    st = pipeline.PipelineState(run_id="r1", selected_issue="#11", current_phase=3)
    st.record_attempt(3)
    p = tmp_path / "state.json"
    st.save(p)
    loaded = pipeline.PipelineState.load(p)
    assert loaded.selected_issue == "#11"
    assert loaded.current_phase == 3
    assert loaded.attempt_counts == {"3": 1}


def test_filter_automatable_excludes_block_label():  # FR-037
    issues = [{"id": "#1", "labels": []}, {"id": "#2", "labels": ["no-automation"]}]
    assert [i["id"] for i in pipeline.filter_automatable(issues)] == ["#1"]
    assert pipeline.is_blocked(issues[1]) is True


def test_detect_cycle_finds_circular_dependency():
    issues = [
        {"id": "a", "depends_on": ["b"]},
        {"id": "b", "depends_on": ["c"]},
        {"id": "c", "depends_on": ["a"]},
    ]
    cycle = pipeline.detect_cycle(issues)
    assert cycle is not None and set(cycle) >= {"a", "b", "c"}


def test_detect_cycle_none_for_acyclic():
    issues = [{"id": "a", "depends_on": ["b"]}, {"id": "b", "depends_on": []}]
    assert pipeline.detect_cycle(issues) is None

"""T017 — US1: prioritization behavior (FR-008, FR-009, FR-010, FR-036, FR-037)."""

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "configs" / "claude" / "scripts"))

from orchestrator import engine  # noqa: E402
from orchestrator import daemon  # noqa: E402

FIXTURE = Path(__file__).parent / "fixtures" / "orchestrator" / "backlog.json"


def load_issues():
    return json.loads(FIXTURE.read_text())["issues"]


def test_unblocking_issue_outranks_isolated_higher_severity():  # FR-009
    issues = load_issues()
    result = engine.prioritize(issues)
    # #11 (high, unblocks #12 & #13) must rank above #12 (critical, isolated/blocked)
    assert result.ranked_issue_ids[0] == "#11"
    assert result.ranked_issue_ids.index("#11") < result.ranked_issue_ids.index("#12")
    assert "unblock" in result.top_choice_justification.lower()


def test_no_automation_issue_is_held_not_selected():  # FR-037
    result = engine.prioritize(load_issues())
    assert "#14" in result.held_issue_ids
    assert "#14" not in result.ranked_issue_ids


def test_all_held_backlog_returns_empty_with_note():
    issues = [{"id": "#1", "labels": ["no-automation"], "depends_on": []}]
    result = engine.prioritize(issues)
    assert result.ranked_issue_ids == []
    assert "held" in result.top_choice_justification.lower() or "no implementable" in result.top_choice_justification.lower()


def test_determinism_identical_input_identical_output():  # FR-003 / SC-002
    issues = load_issues()
    a = engine.prioritize(issues).to_payload()
    b = engine.prioritize(list(issues)).to_payload()
    assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)


def test_severity_source_metadata_first_then_inferred():  # FR-036
    assert engine.derive_severity({"severity": "critical"}) == ("critical", "field")
    assert engine.derive_severity({"labels": ["severity:high"]}) == ("high", "label")
    sev, src = engine.derive_severity({"body": "this causes a security vulnerability"})
    assert sev == "critical" and src == "inferred"


def test_dependency_notes_map_blocks():  # FR-010
    notes = {n["issue_id"]: n["blocks"] for n in engine.prioritize(load_issues()).dependency_notes}
    assert set(notes["#11"]) == {"#12", "#13"}


def test_daemon_phase1_dispatch_produces_valid_envelope():
    envelope = daemon.dispatch_phase1(load_issues())
    assert envelope["status"] == "ok"
    assert envelope["phase"] == 1
    assert engine.validate_envelope(envelope) == []


def test_daemon_detects_cycle_and_blocks():
    cyclic = [{"id": "a", "labels": [], "depends_on": ["b"]},
              {"id": "b", "labels": [], "depends_on": ["a"]}]
    envelope = daemon.dispatch_phase1(cyclic)
    assert envelope["status"] == "blocked"
    assert "cycle" in envelope["escalation"]["reason"].lower()

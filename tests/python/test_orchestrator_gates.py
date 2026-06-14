"""T023 — US2: doubly-gated flow (FR-017/019, FR-030/032/033, FR-034, FR-037).

Covers SC-004 (no impl on dirty analysis), SC-011 (no PR-open with Tier 1),
SC-015 (no-automation mid-pipeline halt), SC-013 (low-consensus escalation).
"""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "configs" / "claude" / "scripts"))

from orchestrator import gates, daemon, pipeline, engine  # noqa: E402


# -- Pre-implementation analysis gate (Phase 4) ---------------------------- #
def test_dirty_analysis_blocks_implementation():  # SC-004 / FR-017
    env = daemon.dispatch_analysis_gate([{"finding": "unused var", "severity": "warning",
                                          "fix_directive": "remove it"}])
    assert env["status"] == "ok"
    assert env["payload"]["gate"] == "blocked"
    assert env["payload"]["implement_approved"] is False
    assert len(env["payload"]["required_fixes"]) == 1


def test_clean_analysis_approves_implementation():  # FR-018
    env = daemon.dispatch_analysis_gate([])
    assert env["payload"]["gate"] == "clean"
    assert env["payload"]["implement_approved"] is True
    assert env["payload"]["required_fixes"] == []


# -- Post-implementation verification gate (Phase 5) ----------------------- #
def test_unmet_acceptance_criterion_blocks_pr_even_if_tests_pass():  # FR-032 / SC-011
    findings = [{"dimension": "design_intent", "tier": 1,
                 "detail": "acceptance criterion 2 unmet", "remediation": "implement it"}]
    env = daemon.dispatch_verification_gate(findings)
    assert env["payload"]["verdict"] == "blocked"
    assert env["payload"]["pr_open_approved"] is False
    assert env["payload"]["dimensions"]["design_intent"] == "fail"


def test_tier2_only_opens_pr_with_advisory():  # FR-031
    findings = [{"dimension": "standards", "tier": 2, "detail": "naming nit", "remediation": None}]
    env = daemon.dispatch_verification_gate(findings)
    assert env["payload"]["verdict"] == "verified"
    assert env["payload"]["pr_open_approved"] is True
    assert gates.advisory_verdict_label(findings) in {"APPROVED", "NEEDS_REVIEW"}


# -- Gate cross-verification (FR-034) -------------------------------------- #
def test_low_consensus_escalates_gate():  # SC-013
    env = daemon.dispatch_analysis_gate([], votes=[True, False, False])  # 0.33 → low
    assert env["status"] == "needs_escalation"
    assert env["payload"] == {}
    assert "consensus" in env["escalation"]["reason"].lower()


def test_high_consensus_proceeds():
    env = daemon.dispatch_analysis_gate([], votes=[True, True, True])
    assert env["status"] == "ok"
    assert env["payload"]["implement_approved"] is True


def test_medium_consensus_proceeds_with_flag():
    env = daemon.dispatch_verification_gate(
        [{"dimension": "standards", "tier": 2, "detail": "x", "remediation": None}],
        votes=[True, True, False],  # 0.66 → medium
    )
    assert env["status"] == "ok"
    assert any("advisory" in line for line in env["reasoning_log"])


# -- Mid-pipeline kill-switch (FR-037 / SC-015) ---------------------------- #
def test_no_automation_applied_midpipeline_halts():  # SC-015
    issue = {"id": "#11", "labels": ["no-automation"]}
    reason = pipeline.block_check(issue)
    assert reason is not None and "no-automation" in reason


def test_no_label_does_not_halt():
    assert pipeline.block_check({"id": "#11", "labels": ["severity:high"]}) is None


# -- envelopes stay contract-valid throughout ------------------------------ #
def test_gate_envelopes_are_contract_valid():
    for env in (
        daemon.dispatch_analysis_gate([]),
        daemon.dispatch_analysis_gate([{"finding": "x", "severity": "error", "fix_directive": "y"}]),
        daemon.dispatch_verification_gate([{"dimension": "functionality", "tier": 1,
                                            "detail": "test fails", "remediation": "fix"}]),
        daemon.dispatch_analysis_gate([], votes=[False, False, True]),
    ):
        assert engine.validate_envelope(env) == []

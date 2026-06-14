"""T037 — US5: determinism (FR-003, SC-002). Identical input -> identical output."""

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "configs" / "claude" / "scripts"))

from orchestrator import daemon, gates  # noqa: E402

BACKLOG = json.loads((Path(__file__).parent / "fixtures" / "orchestrator" / "backlog.json").read_text())["issues"]


def _stable(obj):
    return json.dumps(obj, sort_keys=True)


def test_phase1_dispatch_is_deterministic():
    a = daemon.dispatch_phase1(BACKLOG)
    b = daemon.dispatch_phase1([dict(i) for i in BACKLOG])
    assert _stable(a) == _stable(b)


def test_analysis_gate_is_deterministic():
    findings = [{"finding": "x", "severity": "warning", "fix_directive": "y"}]
    assert _stable(gates.evaluate_analysis_gate(findings)) == _stable(gates.evaluate_analysis_gate(list(findings)))


def test_verification_gate_is_deterministic():
    findings = [{"dimension": "standards", "tier": 2, "detail": "n", "remediation": None}]
    assert _stable(gates.evaluate_verification_gate(findings)) == _stable(gates.evaluate_verification_gate(list(findings)))


def test_golden_phase1_top_choice_stable_across_runs():
    tops = {daemon.dispatch_phase1(BACKLOG)["payload"]["ranked_issue_ids"][0] for _ in range(5)}
    assert tops == {"#11"}   # identical selection every run

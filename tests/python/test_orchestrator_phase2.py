"""T031 — US3: Phase 2 arbitration (FR-011, FR-012, FR-028 exemption)."""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "configs" / "claude" / "scripts"))

from orchestrator import engine, daemon  # noqa: E402

REPO_OPT = {"label": "reuse-existing", "repo_consistent": True, "reversible": True}
AGY_OPT = {"label": "new-framework", "repo_consistent": False, "reversible": False}


def test_repo_consistent_option_wins_and_conflict_logged():  # FR-011/012
    chosen, conflict = engine.arbitrate("storage", REPO_OPT, AGY_OPT)
    assert chosen["label"] == "reuse-existing"
    assert conflict["chosen"] == "reuse-existing" and conflict["rejected"] == "new-framework"


def test_agy_absent_proceeds_without_conflict():  # FR-028 exemption
    chosen, conflict = engine.arbitrate("storage", REPO_OPT, None)
    assert chosen["label"] == "reuse-existing" and conflict is None


def test_agy_agreement_no_conflict():
    chosen, conflict = engine.arbitrate("storage", REPO_OPT, {"label": "reuse-existing"})
    assert conflict is None


def test_tie_retains_engine_choice():  # FR-012 — do not defer to agy by default
    a = {"label": "engine", "repo_consistent": True, "reversible": True}
    b = {"label": "agy", "repo_consistent": True, "reversible": True}
    chosen, _ = engine.arbitrate("x", a, b)
    assert chosen["label"] == "engine"


def test_reversibility_breaks_tie_under_thin_evidence():  # FR-011 (3)
    a = {"label": "irreversible", "repo_consistent": False, "reversible": False}
    b = {"label": "reversible", "repo_consistent": False, "reversible": True}
    chosen, _ = engine.arbitrate("x", a, b)
    assert chosen["label"] == "reversible"


def test_dispatch_phase2_builds_valid_envelope():
    decisions = [{"topic": "storage", "engine_choice": REPO_OPT, "agy_choice": AGY_OPT}]
    env = daemon.dispatch_phase2(decisions, open_questions=[])
    assert env["status"] == "ok" and env["phase"] == 2
    assert len(env["payload"]["agy_conflicts"]) == 1
    assert engine.validate_envelope(env) == []

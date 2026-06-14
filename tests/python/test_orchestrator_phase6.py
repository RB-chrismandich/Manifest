"""T034 — US4: Phase 6 PR resolution (FR-020, FR-021, FR-022)."""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "configs" / "claude" / "scripts"))

from orchestrator import engine, daemon  # noqa: E402

MODS = [{"file": "src/a.py", "location": "fetch()", "change": "add retry",
         "addresses": "CI: flaky network test"}]


def test_reply_marker_required():  # FR-022
    assert engine.pr_reply_has_marker("Resolved the flaky test. ✅")
    assert engine.pr_reply_has_marker("Fixed at the source. 🛠️")
    assert not engine.pr_reply_has_marker("Resolved the flaky test.")


def test_dispatch_phase6_valid():
    env = daemon.dispatch_phase6(MODS, "Root-caused and fixed. ✅", ci_root_cause="missing retry")
    assert env["status"] == "ok" and env["phase"] == 6
    assert env["payload"]["modifications"][0]["addresses"].startswith("CI")
    assert env["payload"]["ci_root_cause"] == "missing retry"
    assert engine.validate_envelope(env) == []


def test_dispatch_phase6_blocks_without_marker():
    env = daemon.dispatch_phase6(MODS, "fixed it")
    assert env["status"] == "blocked"
    assert "marker" in env["escalation"]["reason"].lower()


def test_ci_root_cause_optional():
    env = daemon.dispatch_phase6([], "No CI failure; addressed review nits. ✅", ci_root_cause=None)
    assert env["status"] == "ok" and env["payload"]["ci_root_cause"] is None

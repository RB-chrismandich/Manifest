"""US3 — chaining + state: real value flow, blocked cascade, persistence (T021).

All cases use ``cli`` steps so they run without a browser. ``cli_tool.py expect``
asserts in-band that a downstream step received the upstream value.
"""

import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "configs" / "claude" / "scripts"))

from smoke_orchestrator.executor import SmokeTestExecutor  # noqa: E402

FIXTURES = Path(__file__).resolve().parent / "fixtures"
CLI_TOOL = str(FIXTURES / "cli_tool.py")


def _cli(name, *args, **extra):
    return {"name": name, "type": "cli", "command": [sys.executable, CLI_TOOL, *args], **extra}


def _write(catalog_dir, app, tests):
    catalog_dir.mkdir(parents=True, exist_ok=True)
    (catalog_dir / f"{app}.yaml").write_text(
        yaml.safe_dump({"version": 1, "app": app, "tests": tests}), encoding="utf-8")


def _statuses(test_result):
    return {s.name: s.status for s in test_result.steps}


def test_downstream_receives_real_upstream_value(tmp_path):
    """FR-009/FR-012: B sees A's actual captured runtime value."""
    _write(tmp_path, "demo", [{
        "id": "chain", "tier": "Lite", "steps": [
            _cli("emit", "emit", "42", captures={"invoice_id": r"invoice_id=(\d+)"}),
            # 'expect 42 <resolved>' exits 0 only if the chained value is really 42.
            _cli("consume", "expect", "42", "${state.invoice_id}", needs=["invoice_id"]),
        ],
    }])
    rep = SmokeTestExecutor(catalog_dir=str(tmp_path)).run("demo", tier="Lite")
    assert rep.exit_code == 0
    assert _statuses(rep.results[0]) == {"emit": "passed", "consume": "passed"}


def test_missing_upstream_blocks_and_cascades(tmp_path):
    """FR-011: upstream fails → dependents blocked (cascade), verdict non-zero, never a false pass."""
    _write(tmp_path, "demo", [{
        "id": "broken-chain", "tier": "Lite", "steps": [
            _cli("a", "fail", "1", captures={"invoice_id": r"invoice_id=(\d+)"}),  # fails → no capture
            _cli("b", "emit", "7", needs=["invoice_id"], captures={"token": r"invoice_id=(\d+)"}),
            _cli("c", "ok", needs=["token"]),  # cascade-blocked: b never produced token
        ],
    }])
    rep = SmokeTestExecutor(catalog_dir=str(tmp_path)).run("demo", tier="Lite")
    assert rep.exit_code == 1 and rep.verdict == "FAIL"
    assert _statuses(rep.results[0]) == {"a": "failed", "b": "blocked", "c": "blocked"}


def test_blocked_step_is_never_run(tmp_path):
    """A blocked step must NOT execute its command (no false pass, no missing-value run)."""
    marker = tmp_path / "ran.txt"
    _write(tmp_path, "demo", [{
        "id": "guard", "tier": "Lite", "steps": [
            _cli("upstream", "fail", "1", captures={"id": r"id=(\d+)"}),
            # If this ever runs it would create the marker file; it must stay blocked.
            {"name": "downstream", "type": "cli", "needs": ["id"],
             "command": [sys.executable, "-c", f"open({str(marker)!r}, 'w').close()"]},
        ],
    }])
    rep = SmokeTestExecutor(catalog_dir=str(tmp_path)).run("demo", tier="Lite")
    assert _statuses(rep.results[0])["downstream"] == "blocked"
    assert not marker.exists(), "blocked step must not have executed"


def test_persisted_state_reused_across_runs(tmp_path, monkeypatch):
    """FR-010 / US3 scenario 3: a persisted (non-secret) value is reused by a later run."""
    monkeypatch.setenv("MANIFEST_STATE_ROOT", str(tmp_path / "state"))
    cat_dir = tmp_path / "cat"

    # Run 1: produce + persist invoice_id.
    _write(cat_dir, "demo", [{
        "id": "produce", "tier": "Lite",
        "steps": [_cli("emit", "emit", "99", captures={"invoice_id": r"invoice_id=(\d+)"})],
    }])
    r1 = SmokeTestExecutor(catalog_dir=str(cat_dir), persist_state=True).run("demo", tier="Lite")
    assert r1.exit_code == 0

    # Run 2 (fresh executor): a step needs invoice_id with no upstream producer in this run.
    _write(cat_dir, "demo", [{
        "id": "reuse", "tier": "Lite",
        "steps": [_cli("use", "expect", "99", "${state.invoice_id}", needs=["invoice_id"])],
    }])
    r2 = SmokeTestExecutor(catalog_dir=str(cat_dir), persist_state=True).run("demo", tier="Lite")
    assert r2.exit_code == 0, _statuses(r2.results[0])


def test_retry_eventually_succeeds(tmp_path):
    """FR-017: opt-in retry re-runs a flaky step; a stateful script fails then passes."""
    flag = tmp_path / "attempt.flag"
    script = (
        "import os,sys;\n"
        f"p={str(flag)!r}\n"
        "first = not os.path.exists(p)\n"
        "open(p,'w').close()\n"
        "sys.exit(1 if first else 0)\n"
    )
    _write(tmp_path, "demo", [{
        "id": "flaky", "tier": "Full+Extra", "steps": [
            {"name": "poll", "type": "cli", "command": [sys.executable, "-c", script],
             "retry": {"attempts": 3}},
        ],
    }])
    rep = SmokeTestExecutor(catalog_dir=str(tmp_path)).run("demo", tier="Full+Extra")
    assert rep.exit_code == 0, _statuses(rep.results[0])

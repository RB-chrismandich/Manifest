"""US4 — catalog lifecycle: coverage listing, update-in-place, prune (T027)."""

import json
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPTS = REPO_ROOT / "configs" / "claude" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from smoke_orchestrator.appender import SmokeTestAppender


def _wf(app="demo", id_="login-flow", tier="Lite", steps=None):
    return {
        "app": app,
        "id": id_,
        "title": id_,
        "tier": tier,
        "steps": steps
        or [{"name": "open", "type": "api", "method": "GET", "path": "/health"}],
    }


def _cli_steps(n):
    return [{"name": f"s{i}", "type": "cli", "command": ["true"]} for i in range(n)]


def test_coverage_lists_id_tier_stepcount(tmp_path):
    ap = SmokeTestAppender(catalog_dir=str(tmp_path))
    ap.append(_wf(id_="a", tier="Lite"))
    ap.append(_wf(id_="b", tier="Full", steps=_cli_steps(2)))
    cov = {r["id"]: r for r in ap.list_coverage("demo")}
    assert cov["a"] == {"id": "a", "tier": "Lite", "steps": 1}
    assert cov["b"] == {"id": "b", "tier": "Full", "steps": 2}


def test_update_in_place_single_entry(tmp_path):
    """US4 independent test: append, then append-with-changes → one updated entry."""
    ap = SmokeTestAppender(catalog_dir=str(tmp_path))
    ap.append(_wf(id_="flow", tier="Lite"))
    ap.append(_wf(id_="flow", tier="Full", steps=_cli_steps(3)))
    cov = ap.list_coverage("demo")
    assert cov == [{"id": "flow", "tier": "Full", "steps": 3}]


def test_prune_removes_only_target(tmp_path):
    ap = SmokeTestAppender(catalog_dir=str(tmp_path))
    ap.append(_wf(id_="keep"))
    ap.append(_wf(id_="drop"))
    assert ap.prune("demo", "drop") is True
    assert [r["id"] for r in ap.list_coverage("demo")] == ["keep"]
    assert ap.prune("demo", "drop") is False  # idempotent on absent id (FR-018)


def test_list_unknown_app_is_empty(tmp_path):
    assert (
        SmokeTestAppender(catalog_dir=str(tmp_path)).list_coverage("nonexistent") == []
    )


# --- CLI surface (list --json / prune idempotent) ---------------------------
def _run_cli(*args):
    env = dict(os.environ, PYTHONPATH=str(SCRIPTS))
    return subprocess.run(
        [sys.executable, "-m", "smoke_orchestrator", *args],
        capture_output=True,
        text=True,
        env=env,
    )


def test_cli_list_json_and_prune(tmp_path):
    ap = SmokeTestAppender(catalog_dir=str(tmp_path))
    ap.append(_wf(id_="a"))
    ap.append(_wf(id_="b"))

    out = _run_cli("list", "--app", "demo", "--json", "--catalog-dir", str(tmp_path))
    assert out.returncode == 0, out.stderr
    assert {r["id"] for r in json.loads(out.stdout)["demo"]} == {"a", "b"}

    assert (
        _run_cli(
            "prune", "--app", "demo", "--id", "a", "--catalog-dir", str(tmp_path)
        ).returncode
        == 0
    )
    assert [r["id"] for r in ap.list_coverage("demo")] == ["b"]
    # pruning an absent id is still exit 0 (idempotent)
    assert (
        _run_cli(
            "prune", "--app", "demo", "--id", "zzz", "--catalog-dir", str(tmp_path)
        ).returncode
        == 0
    )

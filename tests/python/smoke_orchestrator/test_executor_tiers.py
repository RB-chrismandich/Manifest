"""US2 — SmokeTestExecutor: cumulative tiers, exit codes, mixed step types (T015).

The tier/exit-code/perf cases drive the engine with ``cli`` steps so they run in
any CI without a browser. The mixed UI+API+CLI case (SC-009) is gated behind a
real Playwright + Chromium install and a local stub server.
"""

import sys
import time
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "configs" / "claude" / "scripts"))

from smoke_orchestrator.executor import SmokeTestExecutor, _test_status  # noqa: E402

FIXTURES = Path(__file__).resolve().parent / "fixtures"
CLI_TOOL = str(FIXTURES / "cli_tool.py")


def _cli_step(name, *cli_args, expect_exit=0, **extra):
    return {"name": name, "type": "cli",
            "command": [sys.executable, CLI_TOOL, *cli_args],
            "expect_exit": expect_exit, **extra}


def _test(id_, tier, steps):
    return {"id": id_, "tier": tier, "title": id_, "steps": steps}


def _write_catalog(catalog_dir, app, tests, base_url=None):
    catalog_dir.mkdir(parents=True, exist_ok=True)
    catalog = {"version": 1, "app": app, "tests": tests}
    if base_url:
        catalog["base_url"] = base_url
    (catalog_dir / f"{app}.yaml").write_text(yaml.safe_dump(catalog), encoding="utf-8")


# --- cumulative tier selection (FR-006) -------------------------------------
def test_cumulative_selection(tmp_path):
    _write_catalog(tmp_path, "demo", [
        _test("lite-a", "Lite", [_cli_step("ok", "ok")]),
        _test("full-b", "Full", [_cli_step("ok", "ok")]),
        _test("extra-c", "Full+Extra", [_cli_step("ok", "ok")]),
    ])
    ex = SmokeTestExecutor(catalog_dir=str(tmp_path))
    assert [r.id for r in ex.run("demo", tier="Lite").results] == ["lite-a"]
    assert sorted(r.id for r in ex.run("demo", tier="Full").results) == ["full-b", "lite-a"]
    assert len(ex.run("demo", tier="Full+Extra").results) == 3


def test_all_pass_is_zero(tmp_path):
    _write_catalog(tmp_path, "demo", [_test("a", "Lite", [_cli_step("ok", "ok")])])
    rep = SmokeTestExecutor(catalog_dir=str(tmp_path)).run("demo", tier="Lite")
    assert rep.verdict == "PASS" and rep.exit_code == 0


def test_failure_is_nonzero(tmp_path):
    _write_catalog(tmp_path, "demo", [
        _test("good", "Lite", [_cli_step("ok", "ok")]),
        _test("bad", "Lite", [_cli_step("boom", "fail", "3")]),  # exits 3, expects 0
    ])
    rep = SmokeTestExecutor(catalog_dir=str(tmp_path)).run("demo", tier="Lite")
    assert rep.verdict == "FAIL" and rep.exit_code == 1
    assert {r.id: r.status for r in rep.results} == {"good": "passed", "bad": "failed"}


def test_empty_selection_distinct_from_pass(tmp_path):
    """FR-008: a Lite run over a Full-only catalog is EMPTY (exit 2), not PASS."""
    _write_catalog(tmp_path, "demo", [_test("full-only", "Full", [_cli_step("ok", "ok")])])
    rep = SmokeTestExecutor(catalog_dir=str(tmp_path)).run("demo", tier="Lite")
    assert rep.selected == 0
    assert rep.verdict == "EMPTY" and rep.exit_code == 2


def test_expect_nonzero_exit_passes(tmp_path):
    _write_catalog(tmp_path, "demo", [
        _test("expects-3", "Lite", [_cli_step("x", "fail", "3", expect_exit=3)]),
    ])
    assert SmokeTestExecutor(catalog_dir=str(tmp_path)).run("demo", tier="Lite").exit_code == 0


def test_unknown_requested_tier_raises(tmp_path):
    _write_catalog(tmp_path, "demo", [_test("a", "Lite", [_cli_step("ok", "ok")])])
    with pytest.raises(ValueError):
        SmokeTestExecutor(catalog_dir=str(tmp_path)).run("demo", tier="Mega")


def test_lite_run_within_perf_budget(tmp_path):
    """SC-003 / T039: a representative Lite run completes well under 2 minutes."""
    _write_catalog(tmp_path, "demo",
                   [_test(f"t{i}", "Lite", [_cli_step("ok", "ok")]) for i in range(5)])
    t0 = time.monotonic()
    rep = SmokeTestExecutor(catalog_dir=str(tmp_path)).run("demo", tier="Lite")
    elapsed = time.monotonic() - t0
    assert rep.exit_code == 0
    assert elapsed < 120, f"Lite run took {elapsed:.1f}s (over the 2-min budget)"


# --- error-handling hardening (Tier-1 review) -------------------------------
def test_empty_steps_never_passes():
    """A test that ran zero steps must never be 'passed' (no green gate on no evidence)."""
    assert _test_status([]) == "failed"


def test_runner_oserror_fails_step_without_aborting_run(tmp_path):
    """A bad CLI step (OSError) fails just that step; sibling tests still run (FR-011)."""
    cat_dir = tmp_path / "cat"
    _write_catalog(cat_dir, "demo", [
        _test("breaks", "Lite", [{"name": "x", "type": "cli", "command": [str(tmp_path)]}]),  # dir → OSError
        _test("works", "Lite", [_cli_step("ok", "ok")]),
    ])
    rep = SmokeTestExecutor(catalog_dir=str(cat_dir)).run("demo", tier="Lite")
    statuses = {r.id: r.status for r in rep.results}
    assert statuses == {"breaks": "failed", "works": "passed"}
    assert rep.exit_code == 1


def test_unexpected_runner_exception_is_contained_and_not_leaked(tmp_path, monkeypatch):
    """An unexpected runner exception fails the step cleanly and never leaks its detail."""
    from smoke_orchestrator import executor as ex_mod
    _write_catalog(tmp_path / "cat", "demo", [_test("t", "Lite", [_cli_step("ok", "ok")])])

    def boom(*a, **k):
        raise ValueError("kaboom-secretish-detail")

    monkeypatch.setattr(ex_mod.cli_runner, "run", boom)
    rep = SmokeTestExecutor(catalog_dir=str(tmp_path / "cat")).run("demo", tier="Lite")
    msg = rep.results[0].steps[0].message
    assert rep.results[0].steps[0].status == "failed" and rep.exit_code == 1
    assert "kaboom-secretish-detail" not in msg  # exception content never surfaced
    assert "ValueError" in msg                    # only the type is reported


# --- mixed UI + API + CLI end-to-end (SC-009), gated on a real browser -------
def _chromium_available() -> bool:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return False
    try:
        with sync_playwright() as pw:
            pw.chromium.launch().close()
        return True
    except Exception:
        return False


@pytest.fixture
def stub_base_url():
    sys.path.insert(0, str(FIXTURES))
    from stub_server import run_stub_server
    with run_stub_server() as base:
        yield base


@pytest.mark.skipif(not _chromium_available(), reason="Playwright+Chromium not installed")
def test_mixed_ui_api_cli_dispatch(tmp_path, stub_base_url):
    """SC-009: api → cli → ui steps all dispatch from one catalog and pass."""
    catalog_dir = tmp_path / "cat"
    _write_catalog(catalog_dir, "shop", [
        _test("end-to-end", "Lite", [
            {"name": "create", "type": "api", "method": "POST", "path": "/invoices",
             "expect_status": 201, "captures": {"invoice_id": "$.id"}},
            _cli_step("echo_id", "echo", "${state.invoice_id}", needs=["invoice_id"]),
            {"name": "view", "type": "ui", "action": "goto",
             "value": "/invoices/${state.invoice_id}", "needs": ["invoice_id"]},
            {"name": "amount", "type": "ui", "action": "expect_text",
             "selector": "[data-test=amount]", "value": "$100.00"},
        ]),
    ], base_url=stub_base_url)
    rep = SmokeTestExecutor(catalog_dir=str(catalog_dir)).run("shop", tier="Lite")
    assert rep.results[0].status == "passed", \
        [(s.name, s.status, s.message) for s in rep.results[0].steps]
    assert rep.exit_code == 0

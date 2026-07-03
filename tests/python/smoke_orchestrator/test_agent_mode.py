"""mode: agent (browser-use) UI steps — schema validation, runner contract,
executor routing (design: smoke subsumes the legacy browser-use flow).

The browser-use call is an injectable seam (``runner``) so every path here runs
offline with stubs — no browser, no LLM, no creds. The default live adapter
(executor → browser_use) is exercised manually per the design's e2e step.
"""

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "configs" / "claude" / "scripts"))

from smoke_orchestrator.executor import SmokeTestExecutor
from smoke_orchestrator.steps import StepOutcome
from smoke_orchestrator.steps import agent as agent_runner
from smoke_orchestrator.validation import (
    ValidationError,
    validate_catalog,
)


# --- helpers ---------------------------------------------------------------
def _agent_step(
    name="login",
    *,
    task="Log in and reach the dashboard",
    judge=("user reaches the dashboard",),
    **extra,
):
    step = {
        "name": name,
        "type": "ui",
        "mode": "agent",
        "task": task,
        "judge_context": list(judge),
    }
    step.update(extra)
    return step


def _catalog(steps, *, tier="Full", app="demo"):
    return {
        "version": 1,
        "app": app,
        "tests": [{"id": "t1", "tier": tier, "steps": steps}],
    }


class _Result:
    """Stand-in for the agent runner's return value."""

    def __init__(self, passed, detail="", captures=None):
        self.passed = passed
        self.detail = detail
        self.captures = captures or {}


# --- schema validation -----------------------------------------------------
def test_ui_agent_mode_is_accepted_at_full_tier():
    validate_catalog(_catalog([_agent_step()], tier="Full"))  # no raise


def test_ui_agent_mode_does_not_require_action():
    # agent steps carry task/judge_context, never the deterministic 'action'
    step = _agent_step()
    assert "action" not in step
    validate_catalog(_catalog([step], tier="Full"))  # no raise


def test_ui_agent_mode_requires_task():
    step = _agent_step()
    del step["task"]
    with pytest.raises(ValidationError):
        validate_catalog(_catalog([step], tier="Full"))


def test_ui_agent_mode_requires_nonempty_judge_context():
    with pytest.raises(ValidationError):
        validate_catalog(_catalog([_agent_step(judge=())], tier="Full"))


def test_invalid_ui_mode_is_rejected():
    step = _agent_step()
    step["mode"] = "bogus"
    with pytest.raises(ValidationError):
        validate_catalog(_catalog([step], tier="Full"))


def test_agent_step_forbidden_at_lite_tier():
    # the safety rule: LLM-judged steps may never gate the deterministic Lite tier
    with pytest.raises(ValidationError):
        validate_catalog(_catalog([_agent_step()], tier="Lite"))


def test_deterministic_ui_still_requires_action():
    # regression: mode absent ⇒ deterministic ⇒ 'action' still mandatory
    with pytest.raises(ValidationError):
        validate_catalog(_catalog([{"name": "x", "type": "ui"}], tier="Lite"))


# --- runner contract (steps/agent.py) --------------------------------------
def test_agent_step_passes_when_runner_passes():
    out = agent_runner.run(
        _agent_step(),
        runner=lambda *a, **k: _Result(True, "ok"),
        base_url=None,
        timeout_ms=1000,
    )
    assert isinstance(out, StepOutcome) and out.passed


def test_agent_step_fails_when_runner_judges_fail():
    out = agent_runner.run(
        _agent_step(),
        runner=lambda *a, **k: _Result(False, "no dashboard"),
        base_url=None,
        timeout_ms=1000,
    )
    assert not out.passed
    assert "no dashboard" in out.message


def test_agent_step_contains_runner_exception_without_aborting():
    def boom(*a, **k):
        raise RuntimeError("secret-token-leak")

    out = agent_runner.run(_agent_step(), runner=boom, base_url=None, timeout_ms=1000)
    assert not out.passed
    assert "secret-token-leak" not in out.message  # type only, never the content


def test_agent_captures_are_best_effort_present():
    step = _agent_step(captures={"order_id": "n/a"})
    out = agent_runner.run(
        step,
        runner=lambda *a, **k: _Result(True, captures={"order_id": "42"}),
        base_url=None,
        timeout_ms=1000,
    )
    assert out.passed and out.captures == {"order_id": "42"}


def test_agent_captures_unavailable_are_omitted_not_errored():
    # design finding #2: an unavailable capture is dropped (→ downstream needs blocks),
    # never raised — the runtime 'needs' gate is the safeguard, not a static error.
    step = _agent_step(captures={"order_id": "n/a"})
    out = agent_runner.run(
        step,
        runner=lambda *a, **k: _Result(True, captures={}),
        base_url=None,
        timeout_ms=1000,
    )
    assert out.passed and out.captures == {}


def test_agent_start_url_joins_base_url():
    seen = {}

    def capture_args(task, *, judge_context, start_url, max_steps, timeout_ms):
        seen["start_url"] = start_url
        return _Result(True)

    agent_runner.run(
        _agent_step(url="/login"),
        runner=capture_args,
        base_url="https://app.test",
        timeout_ms=1000,
    )
    assert seen["start_url"] == "https://app.test/login"


# --- executor routing ------------------------------------------------------
def test_executor_routes_agent_step_to_injected_runner(tmp_path):
    import yaml

    calls = []

    def runner(task, **k):
        calls.append(task)
        return _Result(True, "done")

    cat_dir = tmp_path / "smoke-catalog"
    cat_dir.mkdir()
    (cat_dir / "demo.yaml").write_text(
        yaml.safe_dump(_catalog([_agent_step()], tier="Full"))
    )
    execu = SmokeTestExecutor(catalog_dir=str(cat_dir), agent_runner=runner)
    report = execu.run("demo", tier="Full")
    assert calls and report.verdict == "PASS"


def test_agent_only_test_needs_no_playwright(tmp_path, monkeypatch):
    # an agent-only Full run must not try to launch Playwright (separate engines)
    import smoke_orchestrator.executor as ex
    import yaml

    def fail_open(self, need_browser, need_api):
        assert not need_browser, "agent steps must not require the Playwright browser"

    monkeypatch.setattr(ex._RunContext, "open", fail_open)
    cat_dir = tmp_path / "smoke-catalog"
    cat_dir.mkdir()
    (cat_dir / "demo.yaml").write_text(
        yaml.safe_dump(_catalog([_agent_step()], tier="Full"))
    )
    execu = SmokeTestExecutor(
        catalog_dir=str(cat_dir), agent_runner=lambda *a, **k: _Result(True)
    )
    report = execu.run("demo", tier="Full")
    assert report.verdict == "PASS"

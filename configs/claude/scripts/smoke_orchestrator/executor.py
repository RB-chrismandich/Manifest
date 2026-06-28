"""SmokeTestExecutor — run a catalog filtered by tier (T017; US3 T023/T024).

Responsibilities:
  * cumulative tier selection (FR-006) and distinct empty-selection (FR-008);
  * authored-order step execution with ``needs``-gated blocking + cascade (FR-011);
  * per-step bounded timeout, opt-in ``retry`` only (FR-017);
  * secret-safe ``${state.*}``/``${env.*}`` resolution + central redaction (FR-013);
  * JUnit XML + console summary via :mod:`report`.

Playwright is imported lazily and only when a selected step is ``ui``/``api`` —
``cli``-only runs (and most of the test suite) need no browser at all.
"""

from __future__ import annotations

import time

from . import catalog as cat
from .models import RunReport, StepResult, TestResult, select_by_tier
from .redact import Redactor
from .state import StateError, StateManager
from .steps import CaptureError, StepOutcome
from .steps import cli as cli_runner
from .validation import validate_catalog

DEFAULT_TIMEOUT_MS = 30_000


class SmokeTestExecutor:
    """Run one app's catalog filtered by tier, chaining state between steps."""

    def __init__(self, catalog_dir: str = "smoke-catalog", persist_state: bool = False,
                 default_timeout_ms: int = DEFAULT_TIMEOUT_MS, agent_runner=None) -> None:
        self.catalog_dir = catalog_dir
        self.persist_state = persist_state
        self.default_timeout_ms = default_timeout_ms
        self._agent_runner = agent_runner  # injectable browser-use seam (mode: agent)

    def run(self, app: str, tier: str = "Lite", base_url: str | None = None,
            redactor: Redactor | None = None) -> RunReport:
        """Run one app's catalog at ``tier`` and return a RunReport (pure: no I/O).

        Secrets seen during the run are registered into ``redactor`` (a fresh one
        is made if not supplied) so the caller can render JUnit/console with the
        same instance — letting a multi-app run scrub every app's secrets.
        """
        redactor = redactor if redactor is not None else Redactor()
        path = cat.catalog_path(self.catalog_dir, app)
        catalog = cat.load_catalog(path, app)
        validate_catalog(catalog)
        effective_base = base_url or catalog.get("base_url")
        tests = select_by_tier(catalog.get("tests", []), tier)  # raises on unknown tier
        report = RunReport(app=app, tier=tier)

        if tests:  # empty selection ⇒ no Playwright, distinct EMPTY verdict (FR-008)
            need_browser = any(  # agent (browser-use) steps drive their own browser, not Playwright
                s.get("type") == "ui" and s.get("mode", "deterministic") != "agent"
                for t in tests for s in t["steps"])
            need_api = any(s.get("type") == "api" for t in tests for s in t["steps"])
            ctx = _RunContext(effective_base)
            try:
                ctx.open(need_browser, need_api)
                for test in tests:
                    report.results.append(self._run_test(test, app, ctx, effective_base, redactor))
            finally:
                ctx.close()
        return report

    # --- per test / per step ------------------------------------------------
    def _run_test(self, test: dict, app: str, ctx: "_RunContext",
                  base_url: str | None, redactor: Redactor) -> TestResult:
        state = StateManager(persist=self.persist_state)
        if self.persist_state:
            state.load_persisted(app)
        t0 = time.monotonic()
        steps = [self._run_step(s, state, app, ctx, base_url, redactor) for s in test["steps"]]
        return TestResult(id=test["id"], tier=test["tier"], status=_test_status(steps),
                          steps=steps, duration_s=time.monotonic() - t0)

    def _run_step(self, step: dict, state: StateManager, app: str, ctx: "_RunContext",
                  base_url: str | None, redactor: Redactor) -> StepResult:
        name = step["name"]
        s0 = time.monotonic()
        needs = step.get("needs") or []
        if not state.satisfies(needs):  # FR-011 — never run with missing upstream state
            missing = [n for n in needs if not state.has(n)]
            return StepResult(name, "blocked", f"missing required state: {missing}",
                              time.monotonic() - s0)

        sensitive = bool(step.get("sensitive", False))
        try:
            resolved = state.resolve(step, redactor, sensitive=sensitive)
        except StateError as exc:  # e.g. a sensitive ref with no env source (FR-013)
            return StepResult(name, "failed", redactor.scrub(str(exc)), time.monotonic() - s0)

        timeout_ms = int(step.get("timeout_ms") or self.default_timeout_ms)
        outcome = self._dispatch_with_retry(resolved, step, ctx, base_url, timeout_ms)
        if outcome.passed:
            for cname, cval in outcome.captures.items():
                state.capture(cname, cval, app=app, sensitive=sensitive,
                              scope="persisted" if self.persist_state else "run",
                              redactor=redactor)
        status = "passed" if outcome.passed else "failed"
        return StepResult(name, status, redactor.scrub(outcome.message), time.monotonic() - s0)

    def _dispatch_with_retry(self, resolved: dict, step: dict, ctx: "_RunContext",
                             base_url: str | None, timeout_ms: int) -> StepOutcome:
        attempts = 1
        retry = step.get("retry")
        if isinstance(retry, dict):  # opt-in only; absent ⇒ single attempt (FR-017)
            attempts = max(1, int(retry.get("attempts", 1)))
        outcome = StepOutcome(False, "no attempt ran")
        for _ in range(attempts):
            outcome = self._dispatch(resolved, step, ctx, base_url, timeout_ms)
            if outcome.passed:
                break
        return outcome

    def _dispatch(self, resolved: dict, step: dict, ctx: "_RunContext",
                  base_url: str | None, timeout_ms: int) -> StepOutcome:
        stype = step["type"]
        try:
            if stype == "cli":
                return cli_runner.run(resolved, timeout_s=timeout_ms / 1000.0)
            if stype == "api":
                from .steps import api as api_runner
                return api_runner.run(resolved, api_ctx=ctx.api_ctx,
                                      base_url=base_url, timeout_ms=timeout_ms)
            if stype == "ui":
                if step.get("mode") == "agent":  # LLM-driven (browser-use), own browser
                    from .steps import agent as agent_runner
                    runner = self._agent_runner or agent_runner.default_agent_runner
                    return agent_runner.run(resolved, runner=runner,
                                            base_url=base_url, timeout_ms=timeout_ms)
                from .steps import ui as ui_runner
                return ui_runner.run(resolved, page=ctx.page,
                                     base_url=base_url, timeout_ms=timeout_ms)
        except CaptureError as exc:
            return StepOutcome(False, f"capture failed: {exc}")
        except Exception as exc:  # noqa: BLE001 - no runner error may abort the run or
            # leak a traceback: the resolved step (with substituted secrets) must never
            # reach stderr. Report the type only (FR-011 completeness, secret-safe).
            return StepOutcome(False, f"unexpected {type(exc).__name__} during {stype} step")
        return StepOutcome(False, f"unknown step type: {stype!r}")


def _test_status(steps: list[StepResult]) -> str:
    """Failed dominates; else any blocked ⇒ blocked; else passed. Both gate (FR-011)."""
    if not steps:  # a test that ran zero steps is never a pass (no evidence ⇒ no green gate)
        return "failed"
    if any(s.status == "failed" for s in steps):
        return "failed"
    if any(s.status == "blocked" for s in steps):
        return "blocked"
    return "passed"


class _RunContext:
    """Owns the lazily-created Playwright lifecycle (browser/page + API context)."""

    def __init__(self, base_url: str | None) -> None:
        self.base_url = base_url
        self._pw = None
        self._browser = None
        self._standalone_api = False
        self.page = None
        self.api_ctx = None

    def open(self, need_browser: bool, need_api: bool) -> None:
        if not (need_browser or need_api):
            return
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as exc:
            raise RuntimeError(
                "ui/api steps require Playwright — install tests/requirements-smoke.txt "
                "and run `python -m playwright install chromium`"
            ) from exc
        self._pw = sync_playwright().start()
        if need_browser:
            self._browser = self._pw.chromium.launch()
            bctx = self._browser.new_context(base_url=self.base_url)
            self.page = bctx.new_page()
            self.api_ctx = bctx.request  # shares cookies/auth with the browser (research R2)
        elif need_api:
            self.api_ctx = self._pw.request.new_context(base_url=self.base_url)
            self._standalone_api = True

    def close(self) -> None:
        try:
            if self._standalone_api and self.api_ctx is not None:
                self.api_ctx.dispose()
            if self._browser is not None:
                self._browser.close()
        finally:
            if self._pw is not None:
                self._pw.stop()

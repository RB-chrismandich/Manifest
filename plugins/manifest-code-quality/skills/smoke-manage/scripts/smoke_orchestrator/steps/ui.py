"""UI/browser step runner — Playwright Page (T016).

Receives a live ``Page`` from the executor. Supported actions mirror the catalog
schema: ``goto``, ``click``, ``fill``, ``expect_text``, ``expect_visible``.
Captures read a selector's text, or an attribute via ``selector@attr``.
Playwright is never imported here; errors (incl. timeouts) surface as failures.
"""

from __future__ import annotations

from . import CaptureError, StepOutcome, join_url


def run(step: dict, *, page, base_url: str | None, timeout_ms: int) -> StepOutcome:
    action = step["action"]
    selector = step.get("selector")
    value = step.get("value")
    try:
        if action == "goto":
            page.goto(join_url(base_url, value or selector or "/"), timeout=timeout_ms)
        elif action == "click":
            page.click(selector, timeout=timeout_ms)
        elif action == "fill":
            page.fill(selector, value or "", timeout=timeout_ms)
        elif action == "expect_text":
            page.wait_for_selector(selector, timeout=timeout_ms)
            actual = page.text_content(selector) or ""
            if (value or "") not in actual:
                return StepOutcome(
                    False, f"expected text {value!r} in {selector!r}, got {actual!r}"
                )
        elif action == "expect_visible":
            page.wait_for_selector(selector, state="visible", timeout=timeout_ms)
    except Exception as exc:
        return StepOutcome(False, f"ui {action} on {selector or value!r} failed: {exc}")
    return StepOutcome(True, captures=_extract(step.get("captures", {}), page))


def _extract(captures: dict, page) -> dict:
    out: dict = {}
    for name, sel in captures.items():
        if "@" in sel:
            css, attr = sel.rsplit("@", 1)
            value = page.get_attribute(css, attr)
        else:
            value = page.text_content(sel)
        if value is None:
            raise CaptureError(
                f"ui capture {name!r}: selector {sel!r} produced no value"
            )
        out[name] = value
    return out

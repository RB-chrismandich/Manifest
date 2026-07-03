"""AI/browser-use step runner — ``type: ui, mode: agent``.

An LLM drives a real browser from a natural-language ``task`` and is graded by a
judge against ``judge_context`` (the legacy browser-use model), folded into the smoke
catalog so it inherits tiering, ``retry``, ``sensitive`` redaction and JUnit.

Like the other runners this file never imports the heavy dependency: the actual
browser-use call is the injectable ``runner`` seam, so every unit test runs
offline. The executor supplies :func:`default_agent_runner` (lazy ``browser_use``
import) for live runs. ``captures`` are best-effort — an unavailable value is
omitted so the existing ``needs`` gate blocks the dependent step (never a silent
run with missing state); the secret-safe contract of the other runners is kept
(exceptions surface as the type only, never their content).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from . import StepOutcome, join_url


@dataclass
class AgentResult:
    """What a ``runner`` returns: judged verdict + any surfaced captures."""

    passed: bool
    detail: str = ""
    captures: dict[str, Any] = field(default_factory=dict)


def run(
    step: dict,
    *,
    runner: Callable[..., AgentResult],
    base_url: str | None,
    timeout_ms: int,
) -> StepOutcome:
    url = step.get("url")
    start_url = join_url(base_url, url) if url else base_url
    max_steps = int(step.get("max_steps", 15))
    try:
        res = runner(
            step["task"],
            judge_context=step.get("judge_context", []),
            start_url=start_url,
            max_steps=max_steps,
            timeout_ms=timeout_ms,
        )
    except Exception as exc:
        return StepOutcome(False, f"unexpected {type(exc).__name__} during agent step")
    if not getattr(res, "passed", False):
        return StepOutcome(False, f"agent judged fail: {getattr(res, 'detail', '')}")
    declared = step.get("captures") or {}
    available = res.captures or {}
    captures = {
        name: available[name] for name in declared if name in available
    }  # best-effort
    return StepOutcome(True, res.detail, captures=captures)


def default_agent_runner(
    task: str, *, judge_context, start_url, max_steps, timeout_ms
) -> AgentResult:  # pragma: no cover - live path
    """Live adapter over browser-use. Lazily imported; exercised in manual e2e.

    Requires the opt-in agent extra (``tests/requirements-smoke-agent.txt``) and
    an LLM credential (``OPENAI_API_KEY``; model via ``SMOKE_AGENT_MODEL``).
    browser-use has no native judge, so ``judge_context`` is folded into the task
    as explicit success criteria and the run's own success verdict is used.
    """
    try:
        from browser_use import Agent, ChatOpenAI  # type: ignore
    except ImportError as exc:
        raise RuntimeError(
            "mode: agent requires browser-use — install "
            "tests/requirements-smoke-agent.txt and set OPENAI_API_KEY"
        ) from exc
    import asyncio
    import os

    full_task = f"Start at {start_url}. {task}" if start_url else task
    if judge_context:
        full_task += "\nSucceed only if ALL are true: " + "; ".join(judge_context) + "."

    kwargs: dict[str, Any] = {
        "task": full_task,
        "llm": ChatOpenAI(model=os.environ.get("SMOKE_AGENT_MODEL", "gpt-4.1-mini")),
    }
    try:  # headless when the profile API is available; otherwise Agent defaults
        from browser_use import BrowserProfile  # type: ignore

        kwargs["browser_profile"] = BrowserProfile(headless=True)
    except Exception:
        pass

    async def _run():
        return await asyncio.wait_for(
            Agent(**kwargs).run(max_steps=max_steps), timeout=timeout_ms / 1000.0
        )

    history = asyncio.run(_run())
    detail = ""
    try:
        detail = history.final_result() or ""
    except Exception:
        detail = ""
    passed = False
    for meth in ("is_successful", "is_done"):  # prefer an explicit success verdict
        fn = getattr(history, meth, None)
        if callable(fn):
            try:
                verdict = fn()
            except Exception:
                continue
            if verdict is not None:
                passed = bool(verdict)
                break
    return AgentResult(passed=passed, detail=str(detail)[:500])

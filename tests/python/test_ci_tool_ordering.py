"""Guard: a CI step may not invoke a tool the job has not installed yet.

Written after PR #810's first run failed with ``uv: command not found``
(exit 127): the bundle-local reference gate was added above the job's
``Install uv`` step, so it could never run. yamllint passed, the workflow was
valid YAML, and the step was correct in isolation -- only its *position* was
wrong, which nothing checked.

Generalised deliberately: the same shape recurs for any tool a job installs
mid-way (``uv``, ``yamllint``, ``pre-commit``). Keyed on the install step's
own command rather than a hardcoded step name, so renaming a step does not
silently disable the guard.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

_REPO_ROOT = Path(__file__).resolve().parents[2]
_WORKFLOWS = sorted((_REPO_ROOT / ".github/workflows").glob("*.yml"))

# tool -> regex matching a step that INSTALLS it
_TOOLS = {
    "uv": re.compile(r"\b(pip|pipx) install\b[^\n]*\buv\b|astral-sh/setup-uv"),
    "yamllint": re.compile(r"\b(pip|pipx) install\b[^\n]*\byamllint\b"),
}
# tool -> regex matching a step that USES it
_USES = {
    "uv": re.compile(r"(?m)^\s*uv\s+\w|\buv run\b|\buv build\b"),
    "yamllint": re.compile(r"\byamllint\b\s+\S"),
}


def _step_text(step: dict) -> str:
    """Everything in a step that could invoke or install a tool."""
    parts = [str(step.get("run") or ""), str(step.get("uses") or "")]
    return "\n".join(parts)


def _jobs(path: Path):
    doc = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    for job_name, job in (doc.get("jobs") or {}).items():
        steps = job.get("steps")
        if isinstance(steps, list):
            yield job_name, steps


@pytest.mark.parametrize("path", _WORKFLOWS, ids=lambda p: p.name)
def test_no_step_uses_a_tool_before_its_install_step(path: Path) -> None:
    violations: list[str] = []
    for job_name, steps in _jobs(path):
        texts = [_step_text(s) for s in steps]
        for tool, install_re in _TOOLS.items():
            install_at = next(
                (i for i, t in enumerate(texts) if install_re.search(t)), None
            )
            if install_at is None:
                continue  # job never installs it: preinstalled or unused
            use_re = _USES[tool]
            for i, text in enumerate(texts):
                if i < install_at and use_re.search(text):
                    name = steps[i].get("name") or f"step #{i}"
                    violations.append(
                        f"{path.name}::{job_name}: step {i} ({name!r}) runs "
                        f"{tool!r} but the job installs it at step {install_at}"
                    )

    assert not violations, "\n".join(violations)

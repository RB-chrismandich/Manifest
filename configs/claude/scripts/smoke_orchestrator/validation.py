"""Internal validator enforcing the vendored schema rules (T006).

Deliberately dependency-free (no jsonschema): a focused validator yields more
actionable, field-specific errors — which FR-003 requires — and keeps the
runtime footprint light. The JSON Schemas under ``schemas/`` remain the
published contract; this code enforces the same rules.
"""

from __future__ import annotations

import re
from typing import Any

from .models import TIERS

_SLUG = re.compile(r"^[a-z0-9][a-z0-9-]*$")
_STEP_TYPES = ("ui", "api", "cli")
_HTTP_METHODS = ("GET", "POST", "PUT", "PATCH", "DELETE")
_UI_ACTIONS = ("goto", "click", "fill", "expect_text", "expect_visible")


class ValidationError(ValueError):
    """Raised with one or more human-actionable messages; catalog left untouched."""

    def __init__(self, errors: list[str]):
        self.errors = errors
        super().__init__("; ".join(errors))


def _check_step(step: Any, idx: int, errors: list[str], seen_names: set[str]) -> None:
    where = f"step[{idx}]"
    if not isinstance(step, dict):
        errors.append(f"{where}: must be a mapping")
        return
    name = step.get("name")
    if not name or not isinstance(name, str):
        errors.append(f"{where}: missing 'name'")
    elif name in seen_names:
        errors.append(f"{where}: duplicate step name {name!r}")
    else:
        seen_names.add(name)
        where = f"step[{name}]"

    stype = step.get("type")
    if stype not in _STEP_TYPES:
        errors.append(f"{where}: 'type' must be one of {_STEP_TYPES}, got {stype!r}")
        return

    if stype == "ui":
        if step.get("action") not in _UI_ACTIONS:
            errors.append(f"{where}: ui 'action' must be one of {_UI_ACTIONS}")
    elif stype == "api":
        if step.get("method") not in _HTTP_METHODS:
            errors.append(f"{where}: api 'method' must be one of {_HTTP_METHODS}")
        if not isinstance(step.get("path"), str):
            errors.append(f"{where}: api step requires a string 'path'")
    elif stype == "cli":
        cmd = step.get("command")
        if not isinstance(cmd, list) or not cmd or not all(isinstance(c, str) for c in cmd):
            # arg-array only — never a shell string (security: no injection)
            errors.append(f"{where}: cli 'command' must be a non-empty list of strings")

    needs = step.get("needs", [])
    if needs is not None and not isinstance(needs, list):
        errors.append(f"{where}: 'needs' must be a list")


def _check_test(test: Any, errors: list[str], seen_ids: set[str]) -> None:
    if not isinstance(test, dict):
        errors.append("test entry must be a mapping")
        return
    tid = test.get("id")
    if not tid or not isinstance(tid, str) or not _SLUG.match(tid):
        errors.append(f"test 'id' missing or not a slug (^[a-z0-9][a-z0-9-]*$): {tid!r}")
    elif tid in seen_ids:
        errors.append(f"duplicate test id {tid!r}")
    else:
        seen_ids.add(tid)

    if test.get("tier") not in TIERS:
        errors.append(f"test {tid!r}: 'tier' must be one of {TIERS}, got {test.get('tier')!r}")

    steps = test.get("steps")
    if not isinstance(steps, list) or len(steps) == 0:
        errors.append(f"test {tid!r}: 'steps' must be a non-empty list")
        return
    seen_names: set[str] = set()
    for i, step in enumerate(steps):
        _check_step(step, i, errors, seen_names)


def validate_workflow(workflow: Any) -> None:
    """Validate appender input (one test). Raises ValidationError if invalid."""
    errors: list[str] = []
    if not isinstance(workflow, dict):
        raise ValidationError(["workflow description must be a mapping"])
    app = workflow.get("app")
    if not app or not isinstance(app, str) or not _SLUG.match(app):
        errors.append(f"'app' missing or not a slug: {app!r}")
    _check_test(workflow, errors, set())
    if errors:
        raise ValidationError(errors)


def validate_catalog(catalog: Any) -> None:
    """Validate a whole per-app catalog. Raises ValidationError if invalid."""
    errors: list[str] = []
    if not isinstance(catalog, dict):
        raise ValidationError(["catalog must be a mapping"])
    if catalog.get("version") != 1:
        errors.append(f"unsupported catalog 'version': {catalog.get('version')!r} (expected 1)")
    app = catalog.get("app")
    if not app or not isinstance(app, str) or not _SLUG.match(app):
        errors.append(f"catalog 'app' missing or not a slug: {app!r}")
    tests = catalog.get("tests", [])
    if not isinstance(tests, list):
        errors.append("catalog 'tests' must be a list")
        raise ValidationError(errors)
    seen_ids: set[str] = set()
    for test in tests:
        _check_test(test, errors, seen_ids)
    if errors:
        raise ValidationError(errors)

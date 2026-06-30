"""One-shot migration: browser-test YAML prompts → smoke-catalog agent steps.

Translates the legacy ``tests/browser/*.yaml`` browser-use format
(``task`` / ``judge_context`` / ``url`` / ``max_steps`` / ``tags``) into smoke
catalog tests with a single ``type: ui, mode: agent`` step.

Tier is **always** ``Full``: every migrated step is ``mode: agent``, which the
safety rule forbids at ``Lite``. The original ``tags`` ride along on the step
(for filtering) but do not set the tier; ``Lite`` is reserved for hand-authored
deterministic tests.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

_SLUG_OK = re.compile(r"^[a-z0-9][a-z0-9-]*$")


def _slug(stem: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", stem.lower()).strip("-")
    return s or "test"


def translate_browser_test(doc: Any, *, test_id: str) -> dict:
    """Translate one browser-test doc into a smoke catalog test entry."""
    if not isinstance(doc, dict):
        raise ValueError(f"{test_id}: browser-test must be a mapping")
    task = doc.get("task")
    if not task or not isinstance(task, str):
        raise ValueError(f"{test_id}: missing required 'task'")
    judge = doc.get("judge_context")
    if not isinstance(judge, list) or not judge:
        raise ValueError(f"{test_id}: missing required non-empty 'judge_context'")

    step: dict = {
        "name": "agent",
        "type": "ui",
        "mode": "agent",
        "task": task,
        "judge_context": list(judge),
    }
    if isinstance(doc.get("url"), str):
        step["url"] = doc["url"]
    if isinstance(doc.get("max_steps"), int):
        step["max_steps"] = doc["max_steps"]
    if isinstance(doc.get("tags"), list) and doc["tags"]:
        step["tags"] = list(doc["tags"])
    return {"id": test_id, "tier": "Full", "steps": [step]}  # never Lite (safety rule)


def migrate_dir(src_dir: str, *, app: str) -> dict:
    """Build a per-app catalog from every ``*.yaml``/``*.yml`` under ``src_dir``."""
    import yaml  # local: PyYAML is an opt-in smoke dep

    src = Path(src_dir)
    files = sorted([*src.glob("*.yaml"), *src.glob("*.yml")])
    tests = []
    for path in files:
        test_id = _slug(path.stem)
        if not _SLUG_OK.match(test_id):
            raise ValueError(f"{path.name}: cannot derive a valid test id")
        tests.append(
            translate_browser_test(yaml.safe_load(path.read_text()), test_id=test_id)
        )
    return {"version": 1, "app": app, "tests": tests}


def main(argv: list[str] | None = None) -> int:
    """CLI: migrate tests/browser/*.yaml → a smoke catalog file."""
    import argparse

    import yaml

    p = argparse.ArgumentParser(
        prog="smoke_orchestrator.migrate",
        description="Migrate browser-test YAML prompts into a smoke catalog (mode: agent, tier Full).",
    )
    p.add_argument(
        "src_dir", help="directory of browser-test *.yaml files (e.g. tests/browser)"
    )
    p.add_argument(
        "--app", required=True, help="catalog app slug (^[a-z0-9][a-z0-9-]*$)"
    )
    p.add_argument(
        "--out", help="output catalog path (default: smoke-catalog/<app>.yaml)"
    )
    args = p.parse_args(argv)

    catalog = migrate_dir(args.src_dir, app=args.app)
    out = Path(args.out) if args.out else Path("smoke-catalog") / f"{args.app}.yaml"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(yaml.safe_dump(catalog, sort_keys=False))
    print(f"wrote {len(catalog['tests'])} test(s) → {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

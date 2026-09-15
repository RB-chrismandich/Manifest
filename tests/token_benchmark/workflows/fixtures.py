"""Frozen workflow fixture loading and per-condition request assembly.

Reads only tracked fixture files under `root` (tests/token_benchmark/workflows/
fixtures); no CLI flags, home directory, or session/conversation state is
consulted. Evaluator answers (`expected`) never enter a request payload built
here — they feed only this module's own content hashing and evaluate.py.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

CONDITIONS = ("none", "slim", "full")


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def load_fixture(root: Path, fixture_id: str) -> dict:
    """Load one frozen workflow fixture: task, expected answers, and the
    none/slim/full context text, from the fixture tree rooted at `root`."""
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    workflows = manifest.get("workflows", {})
    if fixture_id not in workflows:
        raise ValueError(f"unknown workflow fixture: {fixture_id!r}")
    entry = workflows[fixture_id]
    workflow_root = root / fixture_id
    task = json.loads((workflow_root / "task.json").read_text(encoding="utf-8"))
    expected = json.loads((workflow_root / "expected.json").read_text(encoding="utf-8"))
    slim_text = (root / entry["slim_context"]).read_text(encoding="utf-8")
    full_text = (root / entry["full_context"]).read_text(encoding="utf-8")
    return {
        "fixture_id": fixture_id,
        "kind": entry["kind"],
        "task": task,
        "expected": expected,
        "context": {"none": "", "slim": slim_text, "full": full_text},
        "source_revision": manifest["source_revision"],
    }


def build_request(fixture: dict, condition: str) -> dict:
    """Assemble a fresh request payload for one condition.

    No CLI, home directory, or session state is read; the returned dict
    carries only the fixture instruction/artifacts/output_contract and the
    selected condition's context text — never `expected` (grading answers).
    """
    if condition not in CONDITIONS:
        raise ValueError(f"unknown condition: {condition!r}")
    task = fixture["task"]
    context_text = fixture["context"][condition]
    canonical_task = json.dumps(
        {"task": task, "expected": fixture["expected"]}, sort_keys=True
    )
    return {
        "fixture_id": fixture["fixture_id"],
        "kind": fixture["kind"],
        "condition": condition,
        "instruction": task["instruction"],
        "artifacts": task["artifacts"],
        "output_contract": task["output_contract"],
        "context": context_text,
        "fixture_hash": _sha256_text(canonical_task),
        "context_hash": _sha256_text(context_text),
        "source_revision": fixture["source_revision"],
    }


def build_repair_request(
    fixture: dict, condition: str, prior_response: str, failed_criteria: list[str]
) -> dict:
    """Assemble one recovery request: the prior artifact plus only the failed
    PUBLIC criterion ids for the same condition. Hidden answers
    (`fixture["expected"]["hidden_cases"]`) never reach this dict."""
    request = build_request(fixture, condition)
    request["repair"] = {
        "prior_response": prior_response,
        "failed_public_criteria": list(failed_criteria),
    }
    return request

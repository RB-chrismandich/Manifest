"""SmokeTestAppender — idempotent append/update of one test (T012).

An agent submits a workflow description; this upserts it by stable ``id`` so
re-submitting the same workflow updates in place rather than duplicating
(FR-004, SC-002). Writes are serialized per app and atomic (FR-015).
"""

from __future__ import annotations

from dataclasses import dataclass

from . import catalog as cat
from .validation import validate_catalog, validate_workflow

_TEST_FIELDS = ("id", "title", "tier", "steps", "tags")


@dataclass
class AppendResult:
    id: str
    updated: bool  # True = replaced an existing test, False = added a new one
    path: str


def _to_test(workflow: dict) -> dict:
    """Project a workflow description down to a catalog test entry."""
    return {k: workflow[k] for k in _TEST_FIELDS if k in workflow}


class SmokeTestAppender:
    def __init__(self, catalog_dir: str = "smoke-catalog") -> None:
        self.catalog_dir = catalog_dir

    def append(self, workflow: dict, *, dry_run: bool = False) -> AppendResult:
        validate_workflow(workflow)  # raises ValidationError → catalog untouched (FR-003)
        app = workflow["app"]
        path = cat.catalog_path(self.catalog_dir, app)
        test = _to_test(workflow)
        with cat.file_lock(path):
            catalog = cat.load_catalog(path, app)
            tests = catalog.setdefault("tests", [])
            updated = False
            for i, existing in enumerate(tests):
                if existing.get("id") == test["id"]:
                    tests[i] = test
                    updated = True
                    break
            if not updated:
                tests.append(test)
            validate_catalog(catalog)  # never write an invalid catalog
            if not dry_run:
                cat.atomic_write(path, catalog)
        return AppendResult(id=test["id"], updated=updated, path=str(path))

    def list_coverage(self, app: str) -> list[dict]:
        """Coverage records (id, tier, step count) for one app — no execution (FR-014)."""
        catalog = cat.load_catalog(cat.catalog_path(self.catalog_dir, app), app)
        return [{"id": t.get("id"), "tier": t.get("tier"), "steps": len(t.get("steps", []))}
                for t in catalog.get("tests", [])]

    def prune(self, app: str, test_id: str) -> bool:
        """Remove a test by id (FR-018). Idempotent: absent id is a no-op. Returns removed?"""
        path = cat.catalog_path(self.catalog_dir, app)
        with cat.file_lock(path):
            catalog = cat.load_catalog(path, app)
            tests = catalog.get("tests", [])
            kept = [t for t in tests if t.get("id") != test_id]
            removed = len(kept) != len(tests)
            if removed:
                catalog["tests"] = kept
                cat.atomic_write(path, catalog)
        return removed

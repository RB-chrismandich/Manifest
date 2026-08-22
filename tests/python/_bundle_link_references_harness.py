"""Shared harness for check_bundle_link_references.py's test suite.

The suite is split across test_bundle_link_references.py (synthetic-fixture
cases) and test_bundle_link_references_real_repo.py (real-repo regression) so
neither file grows past the C-SIZE/CON-002 file-line ceiling -- the same
"extract a module rather than grow the file" precedent tools/bundle_link_
baseline.py already set on the checker side. Both test modules import from
here rather than duplicating the loader.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]


def checker_module():
    """Load tools/check_bundle_link_references.py as a fresh module instance."""
    spec = importlib.util.spec_from_file_location(
        "check_bundle_link_references",
        _REPO_ROOT / "tools/check_bundle_link_references.py",
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def real_repo_violation_tuples() -> set[tuple[str, str, str]]:
    """Scan this actual repository and return each violation's
    (relative path, kind, value) -- the shape every real-repo regression test
    asserts against."""
    checker = checker_module()
    report = checker.scan(_REPO_ROOT)
    return {
        (v.path.relative_to(_REPO_ROOT).as_posix(), v.kind, v.value)
        for v in report.violations
    }

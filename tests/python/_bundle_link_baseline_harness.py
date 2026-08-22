"""Shared harness for bundle_link_baseline.py's test suite.

The suite is split across test_bundle_link_baseline.py (the ratchet's core
behaviour: new_violations, record, apply/report) and
test_bundle_link_baseline_stale.py (stale_entries and the F2 fix-then-
reintroduce round trip -- the returning-defect gap the baseline used to
forgive permanently) so neither file grows past the C-SIZE/CON-002 file-line
ceiling. Same "extract a module rather than grow the file" precedent
tests/python/_bundle_link_references_harness.py already set on the checker
side. Both test modules import from here rather than duplicating the module
loader and the synthetic-violation builder.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]

# Every call site across both test modules builds a violation for this same
# synthetic SKILL.md; only (line, kind, value) actually varies per case.
SKILL_MD_RELPATH = "s/SKILL.md"


def _load(name: str, relpath: str):
    spec = importlib.util.spec_from_file_location(name, _REPO_ROOT / relpath)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def baseline_module():
    """Load tools/bundle_link_baseline.py as a fresh module instance."""
    return _load("bundle_link_baseline", "tools/bundle_link_baseline.py")


def checker_module():
    """Load tools/check_bundle_link_references.py as a fresh module instance.

    Loading it also exercises its real ``import bundle_link_baseline`` (tools/
    is on sys.path by then), so ``checker_module().bundle_link_baseline`` and
    ``baseline_module()`` are two independent module instances -- deliberate
    isolation between "test the primitives" and "test the CLI wiring that
    calls them".
    """
    return _load(
        "check_bundle_link_references", "tools/check_bundle_link_references.py"
    )


def violation(checker_mod, root: Path, line: int, kind: str, value: str):
    """Build one synthetic Violation against SKILL_MD_RELPATH under ``root``."""
    return checker_mod.Violation(
        path=root / SKILL_MD_RELPATH,
        line=line,
        kind=kind,
        value=value,
        message=f"cites {value!r}",
    )

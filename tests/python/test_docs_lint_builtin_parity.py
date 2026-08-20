"""BUILTIN_LIMITS must not drift from doc_limits.yml.

docs_lint.py falls back to BUILTIN_LIMITS when PyYAML is absent -- the
supported bare-checkout path. That fallback silently used a stale classifier
and a stale exempt list, so the dependency-free linter reported over-cap and
non-exempt docs the YAML-backed run passed. Counts, not just keys, must match:
a missing classify glob changes a page's cap, and a missing exempt glob pulls
dated records into the gate.
"""

import importlib.util
import pathlib

import pytest

yaml = pytest.importorskip("yaml")

REPO = pathlib.Path(__file__).resolve().parents[2]
SCRIPT = REPO / "configs/claude/scripts/docs_lint.py"
LIMITS = REPO / "configs/claude/config/doc_limits.yml"


def _builtin():
    spec = importlib.util.spec_from_file_location("docs_lint", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.BUILTIN_LIMITS


@pytest.fixture(scope="module")
def pair():
    return _builtin(), yaml.safe_load(LIMITS.read_text())


def test_classify_rules_match(pair):
    builtin, cfg = pair
    assert [(r["glob"], r["type"]) for r in builtin["classify"]] == [
        (r["glob"], r["type"]) for r in cfg["classify"]
    ]


def test_exempt_globs_and_markers_match(pair):
    builtin, cfg = pair
    assert builtin["exempt"]["globs"] == cfg["exempt"]["globs"]
    assert builtin["exempt"]["markers"] == cfg["exempt"]["markers"]


def test_type_caps_match(pair):
    builtin, cfg = pair
    for name, rule in cfg["types"].items():
        assert name in builtin["types"], f"type {name!r} missing from BUILTIN_LIMITS"
        assert builtin["types"][name]["max_lines"] == rule["max_lines"]


def test_defaults_match(pair):
    builtin, cfg = pair
    assert builtin["defaults"]["max_lines"] == cfg["defaults"]["max_lines"]

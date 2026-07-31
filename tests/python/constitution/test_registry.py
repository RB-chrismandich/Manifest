"""Registry loading: the YAML is the contract every other module reads."""

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "configs" / "claude" / "scripts"))

from constitution import registry


def test_loads_shipped_registry():
    """Ids are contiguous CON-001..CON-N with no gap, duplicate, or reorder.

    Derived rather than pinned to a literal count: hardcoding the number made
    *adding* an article a test failure, which is the one change that should be
    routine. A gap or a duplicate is the real defect, and this still catches it.
    """
    reg = registry.load()
    assert reg.version
    ids = [a.id for a in reg.articles]
    assert ids == [f"CON-{n:03d}" for n in range(1, len(ids) + 1)]
    assert len(set(ids)) == len(ids)


def test_article_lookup_by_id():
    reg = registry.load()
    assert reg.article("CON-004").title == "Data is not code"
    with pytest.raises(KeyError):
        reg.article("CON-999")


def test_every_check_maps_to_a_real_article():
    reg = registry.load()
    known = {a.id for a in reg.articles}
    for check in reg.checks.values():
        assert check.article in known, f"{check.id} cites unknown {check.article}"


def test_every_article_check_reference_resolves():
    """An article may not cite a check that does not exist."""
    reg = registry.load()
    for article in reg.articles:
        for check_id in article.checks:
            assert check_id in reg.checks, f"{article.id} cites unknown {check_id}"


def test_language_resolution_by_extension():
    reg = registry.load()
    assert reg.language_for(Path("a/b/mod.py")).key == "python"
    assert reg.language_for(Path("a/b/mod.PY")).key == "python"
    assert reg.language_for(Path("x.tsx")).key == "node"
    assert reg.language_for(Path("main.go")).key == "go"
    assert reg.language_for(Path("run.sh")).key == "shell"
    assert reg.language_for(Path("main.tf")).key == "terraform"
    assert reg.language_for(Path("notes.md")) is None


def test_thresholds_are_positive_ints_where_enabled():
    reg = registry.load()
    for lang in reg.languages.values():
        for name, value in lang.thresholds.items():
            if name == "comment_prefix":
                continue
            assert isinstance(value, int), f"{lang.key}.{name} is not an int"
            assert value >= 0, f"{lang.key}.{name} is negative"


def test_load_rejects_registry_missing_required_keys(tmp_path):
    bad = tmp_path / "bad.yml"
    bad.write_text("version: 1.0.0\narticles: []\n", encoding="utf-8")
    with pytest.raises(registry.RegistryError):
        registry.load(bad)


def test_load_reports_the_path_it_failed_on(tmp_path):
    missing = tmp_path / "nope.yml"
    with pytest.raises(registry.RegistryError) as excinfo:
        registry.load(missing)
    assert str(missing) in str(excinfo.value)

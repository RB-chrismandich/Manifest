"""Seed-registry invariants and store-merge behavior for learning-capture.

These invariants were ported from the retired
tests/bats/knowledge_base_registry.bats (spec 457, contracts/registry-schema.md)
when the YAML registry was folded into the bundle-shipped JSONL seed. The seed
is the bundled source of truth for proactive-coding anti-patterns consumed by
the CLAUDE.md digest, references/antipatterns.md, the code-audit skill, and the
ai-code-audit skill. These tests pin the schema so captures and edits cannot
silently break downstream consumers.
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

import pytest

from tests.python.plugin_runtime.test_workspace_runtime import _isolated_env, _run

SEVERITIES = {"critical", "high", "medium", "low", "info"}
GUARDRAIL_TAGS = {
    "arch",
    "async-state",
    "error-handling",
    "security",
    "dependency",
    "iteration",
}
GUARDRAIL_PROVENANCE = {"research-seed", "session-capture"}


@pytest.fixture
def repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


@pytest.fixture
def seed_path(repo_root: Path) -> Path:
    return (
        repo_root / "plugins/manifest-workspace/skills/learning-capture/data/seed.jsonl"
    )


@pytest.fixture
def seed_script(repo_root: Path) -> Path:
    return (
        repo_root
        / "plugins/manifest-workspace/skills/learning-capture/scripts/learning_capture.py"
    )


@pytest.fixture
def seed_entries(seed_path: Path) -> list[dict[str, object]]:
    return [
        json.loads(line)
        for line in seed_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def test_seed_is_valid_jsonl_and_nonempty(seed_entries: list) -> None:
    assert seed_entries


def test_severity_values_within_allowed_enum(
    seed_entries: list[dict[str, object]],
) -> None:
    bad = [
        e["id"]
        for e in seed_entries
        if "severity" in e and e["severity"] not in SEVERITIES
    ]
    assert not bad, f"invalid severity on: {bad}"


def test_guardrail_provenance_entries_have_rule_and_exactly_one_guardrail_tag(
    seed_entries: list[dict[str, object]],
) -> None:
    """Every research-seed and session-capture entry follows the conventions."""
    scoped = [e for e in seed_entries if e.get("provenance") in GUARDRAIL_PROVENANCE]
    seeds = [e for e in scoped if e.get("provenance") == "research-seed"]
    assert seeds, "no research-seed entries found"
    missing_rule = [
        e["id"] for e in scoped if not str(e.get("prevention_rule", "")).strip()
    ]
    bad_tags = [
        e["id"] for e in scoped if len(GUARDRAIL_TAGS & set(e.get("tags", []))) != 1
    ]
    assert not missing_rule and not bad_tags, (
        f"missing prevention_rule: {missing_rule}; !=1 guardrail tag: {bad_tags}"
    )


def test_all_six_guardrail_categories_are_represented(
    seed_entries: list[dict[str, object]],
) -> None:
    present = {
        tag for e in seed_entries for tag in e.get("tags", []) if tag in GUARDRAIL_TAGS
    }
    missing = GUARDRAIL_TAGS - present
    assert not missing, f"guardrail categories with zero entries: {sorted(missing)}"


def test_guardrail_tagged_count_meets_the_sc001_floor(
    seed_entries: list[dict[str, object]],
) -> None:
    count = sum(1 for e in seed_entries if GUARDRAIL_TAGS & set(e.get("tags", [])))
    assert count >= 25, f"only {count} guardrail-tagged entries (floor: 25)"


def test_entry_ids_are_unique(seed_entries: list[dict[str, object]]) -> None:
    dupes = [i for i, c in Counter(e["id"] for e in seed_entries).items() if c > 1]
    assert not dupes, f"duplicate entry IDs: {dupes}"


def test_query_merges_seed_into_an_empty_store(
    seed_script: Path, tmp_path: Path
) -> None:
    env = _isolated_env(tmp_path)

    result = _run(
        seed_script,
        "query",
        "--category",
        "antipattern",
        "--format",
        "json",
        env=env,
        cwd=tmp_path,
    )

    assert result.returncode == 0, result.stderr
    entries = json.loads(result.stdout)["entries"]
    assert len(entries) >= 36
    assert any(e["id"] == "ANTI-001" for e in entries)


def test_increment_on_seed_entry_writes_an_override(
    seed_script: Path, seed_entries: list[dict[str, object]], tmp_path: Path
) -> None:
    env = _isolated_env(tmp_path)
    seed_record = next(e for e in seed_entries if e["id"] == "ANTI-001")
    expected = int(seed_record["occurrences"]) + 1

    increment = _run(seed_script, "increment", "ANTI-001", env=env, cwd=tmp_path)

    assert increment.returncode == 0, increment.stderr
    store = Path(env["XDG_DATA_HOME"]) / "manifest/knowledge/entries.jsonl"
    records = [
        json.loads(line)
        for line in store.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert len(records) == 1
    assert records[0]["id"] == "ANTI-001"
    assert records[0]["occurrences"] == expected

    query = _run(
        seed_script,
        "query",
        "ANTI-001",
        "--format",
        "json",
        env=env,
        cwd=tmp_path,
    )
    assert query.returncode == 0, query.stderr
    shown = json.loads(query.stdout)["entries"]
    assert len(shown) == 1
    assert shown[0]["occurrences"] == expected

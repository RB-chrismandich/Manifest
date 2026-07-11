"""U4 — per-step content assertions for smoke-catalog/manifest.yaml.

The YAML is currently only checked structurally at run time (schema validation
inside ``smoke_orchestrator.validation``, exercised implicitly whenever the
orchestrator loads it). This suite pins the *content* invariants the catalog
must hold at rest — loaded through the orchestrator's own loader/models
(``catalog.py`` + ``models.py`` + ``schemas/``), never a parallel parser — so a
bad edit fails in CI instead of at the first real smoke run.
"""

import shutil
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "configs" / "claude" / "scripts"))

from smoke_orchestrator.catalog import catalog_path, load_catalog
from smoke_orchestrator.models import TIERS
from smoke_orchestrator.validation import validate_catalog

CATALOG_DIR = REPO_ROOT / "smoke-catalog"
APP = "manifest"


def _load():
    return load_catalog(catalog_path(CATALOG_DIR, APP), APP)


CATALOG = _load()
TESTS = CATALOG.get("tests", [])


def _step_ids():
    ids = []
    for test in TESTS:
        for step in test.get("steps", []):
            ids.append(f"{test.get('id')}::{step.get('name')}")
    return ids


def test_manifest_yaml_exists():
    assert (CATALOG_DIR / f"{APP}.yaml").is_file()


def test_catalog_is_schema_valid():
    # Raises ValidationError with the specific field(s) at fault on failure.
    validate_catalog(CATALOG)


def test_catalog_app_and_version():
    assert CATALOG.get("version") == 1
    assert CATALOG.get("app") == APP


def test_test_ids_are_unique():
    ids = [t["id"] for t in TESTS]
    assert len(ids) == len(set(ids)), f"duplicate test ids: {ids}"


def test_catalog_has_at_least_one_test():
    assert TESTS, "manifest.yaml catalog has no tests"


def test_lite_tier_is_non_empty():
    lite = [t for t in TESTS if t.get("tier") == "Lite"]
    assert lite, "manifest.yaml must carry at least one Lite-tier test (Verify gate)"


@pytest.mark.parametrize("test", TESTS, ids=[t.get("id", "?") for t in TESTS])
def test_entry_has_valid_tier(test):
    assert test.get("tier") in TIERS, f"{test['id']}: invalid tier {test.get('tier')!r}"


@pytest.mark.parametrize("test", TESTS, ids=[t.get("id", "?") for t in TESTS])
def test_entry_has_non_empty_title(test):
    title = test.get("title")
    assert isinstance(title, str) and title.strip(), (
        f"{test['id']}: 'title' must be a non-empty string"
    )


@pytest.mark.parametrize("test", TESTS, ids=[t.get("id", "?") for t in TESTS])
def test_entry_has_at_least_one_step(test):
    steps = test.get("steps")
    assert isinstance(steps, list) and steps, f"{test['id']}: 'steps' must be non-empty"


@pytest.mark.parametrize(
    "test,step",
    [(t, s) for t in TESTS for s in t.get("steps", [])],
    ids=_step_ids(),
)
class TestStepContent:
    """Per-step assertions: expectation fields non-empty, referenced
    files/commands exist where the step type implies them."""

    def test_step_has_name(self, test, step):
        assert isinstance(step.get("name"), str) and step["name"].strip()

    def test_step_type_valid(self, test, step):
        assert step.get("type") in ("ui", "api", "cli")

    def test_step_has_expectation_fields(self, test, step):
        """Every step type carries a real, non-empty assertion of success."""
        stype = step.get("type")
        if stype == "cli":
            command = step.get("command")
            assert isinstance(command, list) and command, (
                f"{test['id']}/{step['name']}: cli step needs a non-empty 'command'"
            )
            assert all(isinstance(c, str) and c for c in command), (
                f"{test['id']}/{step['name']}: cli 'command' entries must be "
                "non-empty strings"
            )
        elif stype == "api":
            assert step.get("method") in (
                "GET",
                "POST",
                "PUT",
                "PATCH",
                "DELETE",
            ), f"{test['id']}/{step['name']}: api step needs a valid 'method'"
            assert isinstance(step.get("path"), str) and step["path"], (
                f"{test['id']}/{step['name']}: api step needs a non-empty 'path'"
            )
        elif stype == "ui":
            if step.get("mode") == "agent":
                assert isinstance(step.get("task"), str) and step["task"].strip(), (
                    f"{test['id']}/{step['name']}: agent ui step needs a 'task'"
                )
                jc = step.get("judge_context")
                assert isinstance(jc, list) and jc, (
                    f"{test['id']}/{step['name']}: agent ui step needs a "
                    "non-empty 'judge_context'"
                )
            else:
                assert step.get("action") in (
                    "goto",
                    "click",
                    "fill",
                    "expect_text",
                    "expect_visible",
                ), f"{test['id']}/{step['name']}: deterministic ui step needs 'action'"

    def test_cli_command_interpreter_exists_on_path(self, test, step):
        """The step's model implies a real executable at command[0]; verify it
        resolves (skip absolute-path scripts that are generated at run time)."""
        if step.get("type") != "cli":
            pytest.skip("not a cli step")
        command = step.get("command") or []
        assert command, f"{test['id']}/{step['name']}: empty cli command"
        interpreter = command[0]
        if interpreter.startswith("$") or interpreter.startswith("/"):
            pytest.skip("interpreter path is templated/absolute at run time")
        assert shutil.which(interpreter) is not None, (
            f"{test['id']}/{step['name']}: cli interpreter {interpreter!r} not "
            "found on PATH"
        )

    def test_lite_tier_excludes_agent_ui_steps(self, test, step):
        """Safety rule mirrored from validation.py: the Lite gate stays
        deterministic — no LLM-judged agent steps at tier Lite."""
        if test.get("tier") != "Lite":
            pytest.skip("not a Lite-tier test")
        is_agent_ui = step.get("type") == "ui" and step.get("mode") == "agent"
        assert not is_agent_ui, (
            f"{test['id']}/{step['name']}: agent ui step must not run at tier Lite"
        )


def test_lock_sidecar_is_a_pure_flock_sidecar():
    """manifest.yaml.lock is an advisory flock sidecar (catalog.file_lock),
    never a data file — the loader has no lock-content consistency to check
    beyond it staying empty at rest."""
    lock_path = catalog_path(CATALOG_DIR, APP).with_suffix(".yaml.lock")
    if not lock_path.exists():
        pytest.skip("no .lock sidecar present yet")
    assert lock_path.read_bytes() == b"", (
        "manifest.yaml.lock must stay an empty flock sidecar, not a data file"
    )

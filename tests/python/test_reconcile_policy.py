"""Tests for the deploy-reconcile classification core (feature 368).

Exercises the pure read-only engine in
``configs/claude/scripts/reconcile_core.py`` against a hermetic fixture tree —
no real ~/.claude is ever touched.
"""

import importlib.util
import os

import pytest

_CORE = os.path.join(
    os.path.dirname(__file__),
    "..",
    "..",
    "configs",
    "claude",
    "scripts",
    "reconcile_core.py",
)
_spec = importlib.util.spec_from_file_location("reconcile_core", _CORE)
core = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(core)


# --------------------------------------------------------------------------- #
# Fixture: a hermetic managed-home + project tree
# --------------------------------------------------------------------------- #
@pytest.fixture
def world(tmp_path):
    """Build base (5 homes) + a project; return (base, project)."""
    base = tmp_path / "home"
    claude = base / ".claude"
    (claude / "skills").mkdir(parents=True)
    (claude / "config").mkdir(parents=True)

    # Deployed skills
    (claude / "skills" / "live-skill").mkdir()
    (claude / "skills" / "live-skill" / "SKILL.md").write_text("name: live-skill\n")
    (claude / "skills" / "dead-skill").mkdir()  # orphan -> REMOVE
    (claude / "skills" / "dead-skill" / "SKILL.md").write_text("name: dead-skill\n")
    (claude / "skills" / ".deployed-skills").write_text("manifest\n")  # protected
    (claude / "skills" / ".metadata.json").write_text("{}\n")  # protected via *.json

    # Deployed config
    (claude / "config" / "command_config.yml").write_text("x: 1\n")  # reconciled
    (claude / "config" / "old_layout.yml").write_text("stale: 1\n")  # orphan -> REMOVE
    (claude / "config" / "config.json").write_text("{}\n")  # protected via *.json

    # A secondary home that parent-dir-symlinks skills/ into ~/.claude (shared)
    cursor = base / ".cursor"
    cursor.mkdir()
    os.symlink(claude / "skills", cursor / "skills")

    # Project source of truth
    project = tmp_path / "repo"
    (project / ".skillshare" / "skills" / "live-skill").mkdir(parents=True)
    (project / "configs" / "claude" / "config").mkdir(parents=True)
    (project / "configs" / "claude" / "config" / "command_config.yml").write_text(
        "x: 1\n"
    )

    return str(base), str(project)


DEFAULT_PROTECT = ["*.json", "skills/.deployed-skills", ".deployed-skills"]


def _by_key(items):
    return {i["canonical_path"].split("/.claude/", 1)[1]: i for i in items}


# --------------------------------------------------------------------------- #
# Pure helpers
# --------------------------------------------------------------------------- #
def test_protect_match_basename_and_relkey():
    assert core.protect_match("skills/.deployed-skills", ["skills/.deployed-skills"])
    # `*` spans `/`
    assert core.protect_match("config/config.json", ["*.json"]) == "*.json"
    assert core.protect_match("skills/.metadata.json", ["*.json"]) == "*.json"
    # basename match
    assert core.protect_match("config/services.yml", ["services.yml"]) == "services.yml"
    assert core.protect_match("skills/dead-skill", ["*.json"]) is None


def test_expected_keys(world):
    _base, project = world
    keys = core.expected_keys(project)
    assert keys == {"skills/live-skill", "config/command_config.yml"}


def test_has_active_dependent_namespace_vs_leaf():
    edges = {"/home/.claude/skills": ["cursor", "gemini"]}
    # exact namespace target -> dependents
    assert core.has_active_dependent("/home/.claude/skills", edges) == [
        "cursor",
        "gemini",
    ]
    # a leaf under a still-linked parent is dangle-safe -> no direct dependent
    assert core.has_active_dependent("/home/.claude/skills/dead-skill", edges) == []


# --------------------------------------------------------------------------- #
# Classification
# --------------------------------------------------------------------------- #
def test_classify_orphans_and_protection(world):
    base, project = world
    items = core.classify(base, project, DEFAULT_PROTECT)
    by = _by_key(items)

    # reconciled units are NOT listed
    assert "skills/live-skill" not in by
    assert "config/command_config.yml" not in by

    # genuine orphans -> REMOVE
    assert by["skills/dead-skill"]["verdict"] == "REMOVE"
    assert by["skills/dead-skill"]["reason_code"] == "orphan_no_source"
    assert by["config/old_layout.yml"]["verdict"] == "REMOVE"

    # runtime files with no project source -> KEEP via protection
    assert by["config/config.json"]["verdict"] == "KEEP"
    assert by["config/config.json"]["reason_code"] == "protected"
    assert by["skills/.deployed-skills"]["verdict"] == "KEEP"
    assert by["skills/.metadata.json"]["verdict"] == "KEEP"


def test_dedup_shared_symlink_reported_once(world):
    base, project = world
    items = core.classify(base, project, DEFAULT_PROTECT)
    # dead-skill is reachable from ~/.claude AND ~/.cursor (symlink) -> exactly one item
    keys = [i["canonical_path"] for i in items]
    assert sum(k.endswith("/.claude/skills/dead-skill") for k in keys) == 1
    assert len(keys) == len(set(keys))


def test_protected_item_never_remove(world):
    """SC-004: nothing matching the policy is ever REMOVE."""
    base, project = world
    items = core.classify(base, project, DEFAULT_PROTECT)
    for i in items:
        if i["reason_code"] == "protected":
            assert i["verdict"] == "KEEP"


# --------------------------------------------------------------------------- #
# Report + render
# --------------------------------------------------------------------------- #
def test_build_report_summary_and_json_shape(world):
    base, project = world
    rep = core.build_report(base, project, DEFAULT_PROTECT)
    s = rep["summary"]
    assert s["orphans"] == s["keep"] + s["remove"]
    assert s["remove"] == 2  # dead-skill + old_layout.yml
    # canonical wire keys (contract §7)
    assert set(rep.keys()) >= {
        "mode",
        "project",
        "roots",
        "summary",
        "items",
        "removed",
        "backup_dir",
    }
    assert (
        rep["mode"] == "preview"
        and rep["removed"] is None
        and rep["backup_dir"] is None
    )
    item = rep["items"][0]
    assert set(item.keys()) >= {
        "canonical_path",
        "display_path",
        "root",
        "unit_type",
        "verdict",
        "reason_code",
        "reason",
        "dependents",
    }
    assert item["unit_type"] in ("skill", "config")


def test_render_human_keep_first_and_summary_wording(world):
    base, project = world
    rep = core.build_report(base, project, DEFAULT_PROTECT)
    text = core.render_human(rep)
    assert "KEEP   (" in text and "REMOVE (" in text
    # KEEP section appears before REMOVE section (contract §5)
    assert text.index("KEEP   (") < text.index("REMOVE (")
    # exact summary wording the deploy hook + bats grep
    s = rep["summary"]
    assert (
        f"Summary: {s['orphans']} orphans  |  {s['keep']} KEEP  |  {s['remove']} REMOVE"
        in text
    )


def test_clean_state(tmp_path):
    """FR-012: a fully-matching environment reports zero orphans."""
    base = tmp_path / "home"
    (base / ".claude" / "skills" / "only").mkdir(parents=True)
    (base / ".claude" / "config").mkdir(parents=True)
    project = tmp_path / "repo"
    (project / ".skillshare" / "skills" / "only").mkdir(parents=True)
    (project / "configs" / "claude" / "config").mkdir(parents=True)
    rep = core.build_report(str(base), str(project), [])
    assert rep["summary"]["orphans"] == 0
    assert "No orphans found." in core.render_human(rep)


def test_unresolvable_project_exit_2(tmp_path, capsys):
    rc = core.main(["--home", str(tmp_path), "--project", str(tmp_path / "nope")])
    assert rc == 2


def test_scripts_namespace_reconciled_orphan_and_protected(world):
    from pathlib import Path

    base, project = world
    scripts_src = Path(project) / "configs" / "claude" / "scripts"
    scripts_src.mkdir(parents=True, exist_ok=True)
    (scripts_src / "live_tool.sh").write_text("#!/bin/bash\n")
    deployed = Path(base) / ".claude" / "scripts"
    deployed.mkdir()
    (deployed / "live_tool.sh").write_text("#!/bin/bash\n")
    # stale bytecode of a removed package — the motivating orphan (issue #462)
    (deployed / "orchestrator").mkdir()
    (deployed / "orchestrator" / "x.cpython-314.pyc").write_text("")
    # runtime cache inside a live scripts dir — must stay protected
    (deployed / "__pycache__").mkdir()

    items = core.classify(base, project, [*DEFAULT_PROTECT, "__pycache__", "*.pyc"])
    by = _by_key(items)
    assert "scripts/live_tool.sh" not in by  # reconciled — has a repo source
    assert by["scripts/orchestrator"]["verdict"] == "REMOVE"
    assert by["scripts/orchestrator"]["reason_code"] == "orphan_no_source"
    assert by["scripts/__pycache__"]["verdict"] == "KEEP"
    assert by["scripts/__pycache__"]["reason_code"] == "protected"


def test_missing_skill_entry_point_produces_warning(world):
    from pathlib import Path

    base, project = world
    skill = Path(base) / ".claude" / "skills" / "uses-script"
    skill.mkdir()
    (skill / "SKILL.md").write_text(
        "Run `~/.claude/scripts/deploy_reconcile.sh` for the preview.\n"
    )
    rep = core.build_report(base, project, DEFAULT_PROTECT)
    assert any("deploy_reconcile.sh" in w for w in rep["warnings"])


def test_deployed_entry_point_produces_no_warning(world):
    from pathlib import Path

    base, project = world
    deployed = Path(base) / ".claude" / "scripts"
    deployed.mkdir(exist_ok=True)
    (deployed / "deploy_reconcile.sh").write_text("#!/bin/bash\n")
    skill = Path(base) / ".claude" / "skills" / "uses-script"
    skill.mkdir()
    (skill / "SKILL.md").write_text(
        "Run `~/.claude/scripts/deploy_reconcile.sh` for the preview.\n"
    )
    rep = core.build_report(base, project, DEFAULT_PROTECT)
    assert not any("deploy_reconcile.sh" in w for w in rep["warnings"])

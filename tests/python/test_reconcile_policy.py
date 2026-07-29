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

# The REAL production registry — used (not a synthetic fixture) by the
# fallback-parser test below to prove the manual parser genuinely handles
# production YAML.
_REAL_ROSTER = os.path.join(os.path.dirname(_CORE), "..", "config", "agent_roster.yml")


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
    (project / ".apm" / "skills" / "live-skill").mkdir(parents=True)
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
    (project / ".apm" / "skills" / "only").mkdir(parents=True)
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


def test_traversal_entry_point_ref_cannot_escape_scripts_root(world):
    from pathlib import Path

    base, project = world
    # A file that EXISTS outside ~/.claude/scripts — pre-guard, a '..' ref
    # resolving to it made os.path.exists() succeed and suppressed the warning.
    (Path(base) / ".claude" / "outside.sh").write_text("#!/bin/bash\n")
    # An EXISTING intermediate dir is required for the unguarded exists()
    # check to resolve the traversal (POSIX resolves each component).
    (Path(base) / ".claude" / "scripts" / "agents").mkdir(parents=True)
    skill = Path(base) / ".claude" / "skills" / "sneaky"
    skill.mkdir()
    (skill / "SKILL.md").write_text(
        "run ~/.claude/scripts/agents/../../outside.sh now\n"
    )
    rep = core.build_report(base, project, DEFAULT_PROTECT)
    assert any("outside.sh" in w for w in rep["warnings"])


def test_expected_keys_includes_top_level_files(world):
    from pathlib import Path

    _base, project = world
    skills_src = Path(project) / ".apm" / "skills"
    (skills_src / "README.md").write_text("# skills\n")
    (skills_src / ".metadata.json").write_text("{}\n")
    keys = core.expected_keys(project)
    # repo-sourced top-level files (deployed by every bootstrap) are expected units
    assert "skills/README.md" in keys
    # hidden entries are not reconciled units (stay under protection patterns)
    assert "skills/.metadata.json" not in keys


def test_repo_sourced_top_level_file_is_reconciled_not_orphan(world):
    from pathlib import Path

    base, project = world
    (Path(project) / ".apm" / "skills" / "README.md").write_text("# skills\n")
    (Path(base) / ".claude" / "skills" / "README.md").write_text("# skills\n")
    items = core.classify(base, project, DEFAULT_PROTECT)
    by = _by_key(items)
    # reconciled units are not listed at all — previously misclassified REMOVE
    assert "skills/README.md" not in by


# --------------------------------------------------------------------------- #
# Fleet tags — derived from agent_roster.yml (config-only extensibility)
# --------------------------------------------------------------------------- #
_SIXTH_AGENT_ROSTER = """\
agents:
  claude:
    name: claude
    binary: claude
    home_dir: ~/.claude
    prompt_args: ["-p", "{prompt}"]
    model_args: ["--model", "{model}"]
    auth_check: "claude auth status"
    enabled_default: true
  gemini:
    name: gemini
    binary: gemini
    home_dir: ~/.gemini
    prompt_args: ["-p", "{prompt}"]
    model_args: ["-m", "{model}"]
    auth_check: "gemini auth status"
    enabled_default: true
  cursor:
    name: cursor
    binary: cursor-agent
    home_dir: ~/.cursor
    prompt_args: ["{prompt}"]
    model_args: ["--model", "{model}"]
    auth_check: "cursor-agent --version"
    enabled_default: true
  codex:
    name: codex
    binary: codex
    home_dir: ~/.codex
    prompt_args: ["{prompt}"]
    model_args: ["--model", "{model}"]
    auth_check: "codex login status"
    enabled_default: true
  antigravity:
    name: antigravity
    binary: agy
    home_dir: ~/.antigravity
    prompt_args: ["--print", "{prompt}"]
    model_args: ["--model", "{model}"]
    auth_check: "agy models"
    enabled_default: true
  beta:
    name: beta
    binary: beta-agent
    home_dir: ~/.beta
    prompt_args: ["{prompt}"]
    model_args: ["--model", "{model}"]
    auth_check: "beta-agent --version"
    enabled_default: false
"""


def _load_core_with_roster(roster_path, monkeypatch):
    """Load a FRESH copy of reconcile_core.py with MANIFEST_AGENT_ROSTER
    pointed at ``roster_path`` — module-level ROOT_TAGS is computed once at
    exec time, so a distinct module object is required to observe a
    different registry (mirrors the module-load pattern this test file
    already uses for ``core`` itself, at the top of this file).
    """
    monkeypatch.setenv("MANIFEST_AGENT_ROSTER", str(roster_path))
    spec = importlib.util.spec_from_file_location(
        "reconcile_core_sixth_agent_fixture", _CORE
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_sixth_agent_extends_fleet_via_config_only(tmp_path, monkeypatch):
    """Acceptance test: a 6th agent added ONLY to agent_roster.yml is picked
    up by ROOT_TAGS/SECONDARY_TAGS and accepted by the CLI's --root
    validation — with zero changes to reconcile_core.py's Python source.
    """
    roster = tmp_path / "agent_roster.yml"
    roster.write_text(_SIXTH_AGENT_ROSTER)

    mod = _load_core_with_roster(roster, monkeypatch)

    # The 5 known agents keep their exact historical order; "beta" is new.
    assert mod.ROOT_TAGS == (
        "claude",
        "cursor",
        "gemini",
        "codex",
        "antigravity",
        "beta",
    )
    assert "beta" in mod.SECONDARY_TAGS
    assert mod.ROOT_TAGS[1:] == mod.SECONDARY_TAGS

    # --list-tags reflects it too (the machine-readable list deploy_reconcile.sh reads).
    import io
    from contextlib import redirect_stdout

    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = mod.main(["--list-tags"])
    assert rc == 0
    assert "beta" in buf.getvalue().splitlines()

    # --root beta is accepted (previously "unknown --root" -> exit 2).
    home = tmp_path / "home"
    project = tmp_path / "repo"
    (home / ".beta").mkdir(parents=True)
    (project / "configs" / "claude" / "config").mkdir(parents=True)
    rc = mod.main(
        [
            "--home",
            str(home),
            "--project",
            str(project),
            "--root",
            "beta",
            "--format",
            "json",
        ]
    )
    assert rc == 0


def test_fifth_agent_root_still_rejects_unknown_tag(tmp_path, monkeypatch):
    """Control: with the REAL (5-agent) registry, an unrelated tag is still
    rejected — proves the 6th-agent acceptance above is genuinely
    registry-driven, not an accidental always-accept regression.
    """
    monkeypatch.delenv("MANIFEST_AGENT_ROSTER", raising=False)
    rc = core.main(
        ["--home", str(tmp_path), "--project", str(tmp_path), "--root", "beta"]
    )
    assert rc == 2


def test_load_fleet_tags_fallback_parser_on_real_registry(monkeypatch):
    """PyYAML-unavailable fallback path: with ``_agent_roster_loader()``
    forced to return None (mirrors PyYAML being unavailable, or
    ``agents/config.py`` failing to import), ``load_fleet_tags()`` falls
    through to ``_fallback_roster_tags()``'s hand-rolled line parser. Points
    at the REAL ``configs/claude/config/agent_roster.yml`` (not a synthetic
    fixture) to prove the manual parser genuinely handles production YAML,
    not just a crafted test string.
    """
    mod = _load_core_with_roster(_REAL_ROSTER, monkeypatch)
    monkeypatch.setattr(mod, "_agent_roster_loader", lambda: None)

    assert mod.load_fleet_tags(_REAL_ROSTER) == mod._DEFAULT_ROOT_TAGS
    assert mod.load_fleet_tags(_REAL_ROSTER) == (
        "claude",
        "cursor",
        "gemini",
        "codex",
        "antigravity",
    )


def test_load_fleet_tags_hardcoded_default_when_registry_missing(tmp_path, monkeypatch):
    """Registry-absent fallback path: pointing ``roster_path`` at a
    nonexistent file makes both the loader-based read and the manual-parser
    fallback come up empty, so ``load_fleet_tags()`` returns the hardcoded
    ``_DEFAULT_ROOT_TAGS`` tuple verbatim.
    """
    missing = tmp_path / "does-not-exist" / "agent_roster.yml"
    mod = _load_core_with_roster(missing, monkeypatch)

    assert mod.ROOT_TAGS == mod._DEFAULT_ROOT_TAGS
    assert mod.ROOT_TAGS == ("claude", "cursor", "gemini", "codex", "antigravity")


# --------------------------------------------------------------------------- #
# Drift guard (goal-task-E, Part 2): reconcile_core.py's innermost fallback
# (_DEFAULT_ROOT_TAGS) is one of several independent hardcoded-default
# copies this goal's work created (see also cli.py's _FALLBACK_ROSTER /
# _MODEL_TIER_DEFAULTS in tests/python/agents/test_cli.py, and
# check_status.sh's/sync-skills.sh's tier-3 arrays in
# tests/bats/agent_roster_drift_guard.bats). _DEFAULT_ROOT_TAGS carries no
# binary/home_dir/auth_check fields -- just the agent names -- so the only
# meaningful guard here is name-set equality, read live from the REAL
# agent_roster.yml (not a hardcoded expectation in this test), so a future
# agent rename/removal not mirrored into _DEFAULT_ROOT_TAGS fails here
# instead of shipping a silently stale fully-degraded fallback.
#
# Compared against the MANAGED-ROOT subset, not every roster agent: a tag is
# resolved to "$HOME/.<tag>" by every consumer, so an agent whose home_dir is
# not "~/.<name>" (devin -> ~/.config/devin) is not a root and must not be a
# tag. That exclusion is asserted directly below.
# --------------------------------------------------------------------------- #
def test_default_root_tags_matches_real_registry_name_set():
    import yaml

    with open(_REAL_ROSTER, encoding="utf-8") as fh:
        agents = yaml.safe_load(fh)["agents"]
    managed = {n for n, e in agents.items() if e.get("home_dir") == f"~/.{n}"}
    assert set(core._DEFAULT_ROOT_TAGS) == managed


def test_agent_with_non_standard_home_is_not_a_managed_root():
    """devin lives at ~/.config/devin. If it leaked into the fleet tags,
    every consumer would resolve it to "$HOME/.devin" — the Devin Desktop
    app's data folder — and offer an unrelated product's files for removal.
    """
    import yaml

    with open(_REAL_ROSTER, encoding="utf-8") as fh:
        agents = yaml.safe_load(fh)["agents"]
    assert agents["devin"]["home_dir"] == "~/.config/devin"
    assert "devin" not in core.load_fleet_tags(_REAL_ROSTER)
    assert "devin" not in core._fallback_roster_tags(str(_REAL_ROSTER))

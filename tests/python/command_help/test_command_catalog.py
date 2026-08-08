"""T004 — failing-first tests for command_catalog.py (spec 362).

Covers: frontmatter parse (incl. symlink-following), when_to_use derivation (D2),
category precedence (D1), availability resolution (D6), and the duplicate /
empty-skill error paths. Written before the implementation — must FAIL first.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "configs/claude/scripts"))
import command_catalog as cc


# --------------------------------------------------------------------------- #
# Fixtures helpers
# --------------------------------------------------------------------------- #
def write_skill(skills_dir: Path, name: str, frontmatter: dict, body: str = "x"):
    """Create <skills_dir>/<name>/SKILL.md with the given frontmatter dict."""
    d = skills_dir / name
    d.mkdir(parents=True, exist_ok=True)
    lines = ["---"]
    for k, v in frontmatter.items():
        lines.append(f"{k}: {v}")
    lines.append("---")
    lines.append("")
    lines.append(body)
    (d / "SKILL.md").write_text("\n".join(lines), encoding="utf-8")
    return d


CATS = """
categories:
  - {key: git-pr, label: "Git & PRs", order: 1}
  - {key: docs, label: "Documentation", order: 2}
  - {key: security, label: "Security", order: 3}
overrides:
  legacy-skill: security
"""

SERVICES = """
services:
  claude:
    enabled: true
  skillclaw:
    enabled: false
"""


@pytest.fixture
def env(tmp_path):
    skills = tmp_path / "skills"
    skills.mkdir()
    cats = tmp_path / "command_categories.yml"
    cats.write_text(CATS, encoding="utf-8")
    services = tmp_path / "services.yml"
    services.write_text(SERVICES, encoding="utf-8")
    return {"skills": skills, "cats": str(cats), "services": str(services)}


def build(env, platform="claude"):
    return cc.build_catalog(
        skills_dir=str(env["skills"]),
        categories_path=env["cats"],
        services_path=env["services"],
        platform=platform,
    )


# --------------------------------------------------------------------------- #
# when_to_use derivation (D2)
# --------------------------------------------------------------------------- #
def test_when_to_use_explicit_use_when_clause():
    desc = "Use when your PR receives review feedback — fetch via gh api. Distinct from pr-review."
    assert cc.derive_when_to_use(desc, "pr-address-comments").startswith(
        "Use when your PR receives review feedback"
    )


def test_when_to_use_first_sentence_fallback():
    desc = "Run linters, unit tests, and security scans in parallel. Produces a report."
    assert (
        cc.derive_when_to_use(desc, "verify")
        == "Run linters, unit tests, and security scans in parallel."
    )


def test_when_to_use_humanized_name_fallback():
    assert cc.derive_when_to_use("", "branch-clean") == "Branch clean"


# --------------------------------------------------------------------------- #
# category precedence (D1)
# --------------------------------------------------------------------------- #
def test_category_frontmatter_authoritative(env):
    write_skill(
        env["skills"],
        "a-skill",
        {"name": "a-skill", "description": "d.", "category": "docs"},
    )
    cat = build(env)
    entry = next(c for c in cat["commands"] if c["name"] == "a-skill")
    assert entry["category"] == "docs"


def test_category_overrides_map_when_no_frontmatter(env):
    write_skill(
        env["skills"], "legacy-skill", {"name": "legacy-skill", "description": "d."}
    )
    entry = next(c for c in build(env)["commands"] if c["name"] == "legacy-skill")
    assert entry["category"] == "security"


def test_category_uncategorized_default(env):
    write_skill(env["skills"], "z-skill", {"name": "z-skill", "description": "d."})
    entry = next(c for c in build(env)["commands"] if c["name"] == "z-skill")
    assert entry["category"] == "uncategorized"


def test_category_frontmatter_beats_overrides(env):
    # legacy-skill is in overrides->security, but its own frontmatter says docs.
    write_skill(
        env["skills"],
        "legacy-skill",
        {"name": "legacy-skill", "description": "d.", "category": "docs"},
    )
    entry = next(c for c in build(env)["commands"] if c["name"] == "legacy-skill")
    assert entry["category"] == "docs"


def test_unknown_category_is_error(env):
    write_skill(
        env["skills"],
        "bad",
        {"name": "bad", "description": "d.", "category": "nonsense"},
    )
    with pytest.raises(cc.CatalogError):
        build(env)


# --------------------------------------------------------------------------- #
# availability resolution (D6)
# --------------------------------------------------------------------------- #
def test_availability_service_disabled_marks_unavailable(env):
    write_skill(
        env["skills"],
        "skillclaw-promote",
        {"name": "skillclaw-promote", "description": "d."},
    )
    entry = next(c for c in build(env)["commands"] if c["name"] == "skillclaw-promote")
    assert entry["availability"]["status"] == "unavailable"
    assert entry["availability"]["service_enabled"] is False
    assert "service disabled" in entry["availability"]["reason"]


def test_availability_default_available(env):
    write_skill(env["skills"], "verify", {"name": "verify", "description": "d."})
    entry = next(c for c in build(env)["commands"] if c["name"] == "verify")
    assert entry["availability"]["status"] == "available"
    assert entry["availability"]["reason"] is None


# --------------------------------------------------------------------------- #
# error paths
# --------------------------------------------------------------------------- #
def test_duplicate_name_is_error(env):
    write_skill(env["skills"], "dup-a", {"name": "same", "description": "d."})
    write_skill(env["skills"], "dup-b", {"name": "same", "description": "d."})
    with pytest.raises(cc.CatalogError):
        build(env)


def test_empty_description_is_error(env):
    write_skill(env["skills"], "empty", {"name": "empty", "description": '""'})
    with pytest.raises(cc.CatalogError):
        build(env)


# --------------------------------------------------------------------------- #
# frontmatter parsing — double-quoted YAML unescaping (_strip_quotes)
# --------------------------------------------------------------------------- #
def test_double_quoted_description_unescapes_inner_quotes(env):
    # Mirrors the inline double-quoted style the front-matter efficiency pass
    # used for descriptions with embedded trigger phrases (e.g. pr-monitor).
    # The raw frontmatter line is:
    #   description: "Use when \"trigger phrase\" appears: react."
    write_skill(
        env["skills"],
        "quoted-skill",
        {
            "name": "quoted-skill",
            "description": r'"Use when \"trigger phrase\" appears: react."',
        },
    )
    entry = next(c for c in build(env)["commands"] if c["name"] == "quoted-skill")
    assert entry["description"] == 'Use when "trigger phrase" appears: react.'
    assert "\\" not in entry["description"]


# --------------------------------------------------------------------------- #
# symlink-following (repo convention: skills may be reached via a symlinked dir)
# --------------------------------------------------------------------------- #
def test_symlinked_skill_dir_is_followed(env, tmp_path):
    real = tmp_path / "real_skill"
    real.mkdir()
    (real / "SKILL.md").write_text(
        "---\nname: linked\ndescription: A linked skill.\n---\n", encoding="utf-8"
    )
    (env["skills"] / "linked").symlink_to(real, target_is_directory=True)
    names = [c["name"] for c in build(env)["commands"]]
    assert "linked" in names


# --------------------------------------------------------------------------- #
# schema / stability contract
# --------------------------------------------------------------------------- #
def test_catalog_ordering_is_deterministic(env):
    write_skill(
        env["skills"],
        "b-doc",
        {"name": "b-doc", "description": "d.", "category": "docs"},
    )
    write_skill(
        env["skills"],
        "a-git",
        {"name": "a-git", "description": "d.", "category": "git-pr"},
    )
    write_skill(
        env["skills"],
        "a-doc",
        {"name": "a-doc", "description": "d.", "category": "docs"},
    )
    cmds = [c["name"] for c in build(env)["commands"]]
    # categories by order (git-pr=1 before docs=2); alpha within category
    assert cmds == ["a-git", "a-doc", "b-doc"]


def test_categories_block_is_closed_set(env):
    # One skill so the catalog is non-empty: an empty catalog is now an error,
    # and this test was only ever asserting the taxonomy, not the command set.
    write_skill(env["skills"], "a", {"name": "a", "description": "Use when a."})
    cat = build(env)
    keys = [c["key"] for c in cat["categories"]]
    assert keys == ["git-pr", "docs", "security"]


# --------------------------------------------------------------------------- #
# Source resolution and the empty-catalog floor
#
# `.apm/skills` is a gitignored, generated mirror that is EMPTY in a fresh
# checkout. Building a catalog from it used to succeed with zero commands, and
# generate_commands_doc.py rendered that as a doc with every row deleted — 178
# lines removed from COMMANDS.md, AGENTS.md and GEMINI.md, exit 0. Two guards
# now stand between an empty tree and a destructive doc write.
# --------------------------------------------------------------------------- #


def test_default_roots_prefer_the_plugin_trees_over_the_generated_mirror(
    monkeypatch, tmp_path
):
    """Source of truth wins, so a stale or absent mirror cannot drive the docs."""
    (tmp_path / "plugins" / "bundle-a" / "skills").mkdir(parents=True)
    (tmp_path / "plugins" / "bundle-b" / "skills").mkdir(parents=True)
    (tmp_path / ".apm" / "skills").mkdir(parents=True)
    monkeypatch.setattr(cc, "_REPO_ROOT", tmp_path)
    monkeypatch.setattr(cc, "DEFAULT_SKILLS_DIR", tmp_path / ".apm" / "skills")

    roots = cc.default_skills_dirs()
    assert roots == [
        tmp_path / "plugins" / "bundle-a" / "skills",
        tmp_path / "plugins" / "bundle-b" / "skills",
    ]


def test_default_roots_fall_back_to_the_mirror_when_no_plugin_trees(
    monkeypatch, tmp_path
):
    """A pre-cutover checkout still resolves."""
    mirror = tmp_path / ".apm" / "skills"
    mirror.mkdir(parents=True)
    monkeypatch.setattr(cc, "_REPO_ROOT", tmp_path)
    monkeypatch.setattr(cc, "DEFAULT_SKILLS_DIR", mirror)

    assert cc.default_skills_dirs() == [mirror]


def test_skills_are_collected_across_every_root(monkeypatch, tmp_path, env):
    """Bundles are separate trees; the catalog is their union, not just the first."""
    for bundle, skill in (("b1", "alpha"), ("b2", "beta")):
        write_skill(
            tmp_path / "plugins" / bundle / "skills",
            skill,
            {"name": skill, "description": f"Use when {skill} is needed."},
        )
    monkeypatch.setattr(cc, "_REPO_ROOT", tmp_path)
    monkeypatch.delenv("COMMAND_CATALOG_SKILLS_DIR", raising=False)

    catalog = cc.build_catalog(
        categories_path=env["cats"], services_path=env["services"]
    )
    assert {c["name"] for c in catalog["commands"]} == {"alpha", "beta"}


def test_an_empty_catalog_raises_instead_of_returning_zero_commands(tmp_path, env):
    """The floor. Without it the emptiness travels silently into the doc writer."""
    empty = tmp_path / "empty"
    empty.mkdir()
    with pytest.raises(cc.CatalogError) as excinfo:
        cc.build_catalog(
            skills_dir=str(empty),
            categories_path=env["cats"],
            services_path=env["services"],
        )
    assert "no skills found" in str(excinfo.value)


def test_the_empty_catalog_error_names_the_mirror_remedy(monkeypatch, tmp_path, env):
    """Whoever hits this locally needs to be told to generate the mirror."""
    mirror = tmp_path / ".apm" / "skills"
    mirror.mkdir(parents=True)
    monkeypatch.setattr(cc, "_REPO_ROOT", tmp_path)
    monkeypatch.setattr(cc, "DEFAULT_SKILLS_DIR", mirror)
    monkeypatch.delenv("COMMAND_CATALOG_SKILLS_DIR", raising=False)

    with pytest.raises(cc.CatalogError) as excinfo:
        cc.build_catalog(categories_path=env["cats"], services_path=env["services"])
    assert "generate_skill_mirror.sh" in str(excinfo.value)

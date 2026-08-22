"""Release gate: a SKILL.md (or a file it ships) must not cite a path absent
from its own bundle (spec docs/superpowers/specs/2026-08-19-marketplace-
restructure-design.md, Phase 1 item 1.4).

Synthetic-fixture cases only -- real-repo regression lives in
test_bundle_link_references_real_repo.py (split to stay under the
C-SIZE/CON-002 file-line ceiling; see _bundle_link_references_harness.py).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.python._bundle_link_references_harness import (
    checker_module as _checker_module,
)


def _write_bundle(tmp_path: Path, bundle: str, skill: str, skill_md: str) -> Path:
    skill_dir = tmp_path / "plugins" / bundle / "skills" / skill
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(skill_md, encoding="utf-8")
    return skill_dir


# --- true positives: each of the checker's three violation kinds ----------


def test_flags_missing_bundled_reference_when_basename_absent_from_bundle(
    tmp_path: Path,
) -> None:
    checker = _checker_module()
    _write_bundle(
        tmp_path,
        "manifest-demo",
        "demo-skill",
        "---\nname: demo-skill\ndescription: demo\n---\n"
        "Follow the bundled `sub-agent-dispatch.md` selection rules.\n",
    )

    report = checker.scan(tmp_path)

    assert len(report.violations) == 1
    violation = report.violations[0]
    assert violation.kind == "missing-bundled-reference"
    assert violation.value == "sub-agent-dispatch.md"


def test_does_not_flag_bare_reference_once_bundle_carries_a_copy(
    tmp_path: Path,
) -> None:
    checker = _checker_module()
    skill_dir = _write_bundle(
        tmp_path,
        "manifest-demo",
        "demo-skill",
        "---\nname: demo-skill\ndescription: demo\n---\n"
        "Follow the bundled `sub-agent-dispatch.md` selection rules.\n",
    )
    bundle_root = skill_dir.parents[1]
    (bundle_root / "runtime/references").mkdir(parents=True)
    (bundle_root / "runtime/references/sub-agent-dispatch.md").write_text(
        "# rules\n", encoding="utf-8"
    )

    report = checker.scan(tmp_path)

    assert report.violations == ()


def test_flags_cross_bundle_path_that_resolves_only_at_repo_root(
    tmp_path: Path,
) -> None:
    checker = _checker_module()
    _write_bundle(
        tmp_path,
        "manifest-delegate",
        "delegate",
        "---\nname: delegate\ndescription: demo\n---\n"
        "Read `configs/claude/references/harness-routing.md`, never a raw model ID.\n",
    )
    (tmp_path / "configs/claude/references").mkdir(parents=True)
    (tmp_path / "configs/claude/references/harness-routing.md").write_text(
        "# routing\n", encoding="utf-8"
    )

    report = checker.scan(tmp_path)

    assert len(report.violations) == 1
    violation = report.violations[0]
    assert violation.kind == "cross-bundle-path"
    assert violation.value == "configs/claude/references/harness-routing.md"


def test_flags_home_tree_reference_unconditionally(tmp_path: Path) -> None:
    checker = _checker_module()
    _write_bundle(
        tmp_path,
        "manifest-demo",
        "demo-skill",
        "---\nname: demo-skill\ndescription: demo\n---\n"
        "See the rules in `~/.claude/references/sub-agent-dispatch.md`.\n",
    )

    report = checker.scan(tmp_path)

    assert len(report.violations) == 1
    assert report.violations[0].kind == "home-tree-path"


# --- missing-bundle-local-target: mutation tests ---------------------------
# The pre-fix resolver returned None (no violation) both when a citation
# resolved inside the bundle AND when a bundle-anchored citation's target
# did not exist -- indistinguishable outcomes. Each case runs one citation
# twice: real target (clean), then target gone (caught). Ran all three and
# watched each go from zero violations to one missing-bundle-local-target.
# (bundle, skill, citation markdown, target path relative to bundle root)
_MUTATION_CASES = (
    (
        "manifest-ops",
        "docker-compose-commandments",
        '`"${CLAUDE_PLUGIN_ROOT}/x.py"`.\n',
        "x.py",
    ),
    # unbraced: the exact FN adversarial review found -- not bundle-anchored at all pre-fix.
    (
        "manifest-ops",
        "docker-compose-commandments",
        '`"$CLAUDE_PLUGIN_ROOT/x.py"`.\n',
        "x.py",
    ),
    (
        "manifest-security",
        "code-audit",
        "Read `../../runtime/references/x.md` first.\n",
        "runtime/references/x.md",
    ),
)


@pytest.mark.parametrize("bundle, skill, citation, target_relpath", _MUTATION_CASES)
def test_mutation_bundle_local_missing_target_is_caught(
    tmp_path: Path, bundle: str, skill: str, citation: str, target_relpath: str
) -> None:
    checker = _checker_module()
    skill_dir = _write_bundle(
        tmp_path,
        bundle,
        skill,
        f"---\nname: {skill}\ndescription: demo\n---\n{citation}",
    )
    target = skill_dir.parents[1] / target_relpath
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("# real file\n", encoding="utf-8")

    assert checker.scan(tmp_path).violations == ()  # (1) target exists -- clean

    target.unlink()  # (2) delete it -- MUST be caught
    report = checker.scan(tmp_path)
    assert len(report.violations) == 1
    assert report.violations[0].kind == "missing-bundle-local-target"


# --- false positives the three-outcome fix must not introduce --------------
# A shell-idiom `./x` naming a script in the reader's own repo, and a wrong
# `../` hop count with no real target anywhere (left unresolved, not
# guessed at) -- both real corpus patterns the fix must not flag.
_NON_DEFECT_CASES = (
    (
        "manifest-code-quality",
        "shell-refactor",
        "run `./setup.sh --skip-auth` in Docker.\n",
    ),
    (
        "manifest-security",
        "code-audit",
        "Read `../../../not-a-real-bundle/x.md` first.\n",
    ),
)


@pytest.mark.parametrize("bundle, skill, citation", _NON_DEFECT_CASES)
def test_does_not_flag_relative_path_non_defects(
    tmp_path: Path, bundle: str, skill: str, citation: str
) -> None:
    checker = _checker_module()
    _write_bundle(
        tmp_path,
        bundle,
        skill,
        f"---\nname: {skill}\ndescription: demo\n---\n{citation}",
    )

    assert checker.scan(tmp_path).violations == ()


def test_does_not_truncate_a_compound_extension_into_a_false_missing_target(
    tmp_path: Path,
) -> None:
    """``.template`` isn't a recognized extension, so a real ``x.md.template``
    citation must not backtrack onto the truncated, nonexistent ``x.md``."""
    checker = _checker_module()
    skill_dir = _write_bundle(
        tmp_path,
        "stitch-design",
        "screen-prompts",
        "---\nname: screen-prompts\ndescription: demo\n---\nSee `../t/x.md.template`.\n",
    )
    template = skill_dir.parents[1] / "t/x.md.template"
    template.parent.mkdir(parents=True)
    template.write_text("x\n", encoding="utf-8")

    assert checker.scan(tmp_path).violations == ()


# --- known non-defects: must NOT be flagged --------------------------------


def test_does_not_flag_claude_plugin_root_path_that_resolves_in_bundle(
    tmp_path: Path,
) -> None:
    checker = _checker_module()
    skill_dir = _write_bundle(
        tmp_path,
        "manifest-ops",
        "docker-compose-commandments",
        "---\nname: docker-compose-commandments\ndescription: demo\n---\n"
        'Run `python3 "$CLAUDE_PLUGIN_ROOT/runtime/bin/compose_check.py" .`.\n',
    )
    bundle_root = skill_dir.parents[1]
    (bundle_root / "runtime/bin").mkdir(parents=True)
    (bundle_root / "runtime/bin/compose_check.py").write_text(
        "pass\n", encoding="utf-8"
    )

    report = checker.scan(tmp_path)

    assert report.violations == ()


def test_does_not_flag_relative_path_that_resolves_within_same_bundle(
    tmp_path: Path,
) -> None:
    """Mirrors manifest-security/skills/code-audit, which does this correctly."""
    checker = _checker_module()
    skill_dir = _write_bundle(
        tmp_path,
        "manifest-security",
        "code-audit",
        "---\nname: code-audit\ndescription: demo\n---\n"
        "Read `../../runtime/references/code-constitution.md` and\n"
        "`../../runtime/references/antipatterns.md` first.\n",
    )
    bundle_root = skill_dir.parents[1]
    (bundle_root / "runtime/references").mkdir(parents=True)
    (bundle_root / "runtime/references/code-constitution.md").write_text(
        "# constitution\n", encoding="utf-8"
    )
    (bundle_root / "runtime/references/antipatterns.md").write_text(
        "# antipatterns\n", encoding="utf-8"
    )

    report = checker.scan(tmp_path)

    assert report.violations == ()


def test_ignores_urls_globs_and_non_plugin_root_shell_variables(tmp_path: Path) -> None:
    checker = _checker_module()
    _write_bundle(
        tmp_path,
        "manifest-demo",
        "demo-skill",
        "---\nname: demo-skill\ndescription: demo\n---\n"
        "See https://github.com/org/repo/blob/main/configs/claude/references/harness-routing.md\n"
        "for background. Skill discovery globs `*/SKILL.md` and `**/*.md`.\n"
        "Read `$OTHER_VAR/references/some-doc.md` if set.\n",
    )
    # The URL's and $OTHER_VAR's target genuinely exists at repo root, so a
    # checker that mistakenly treated them as citations would have every
    # opportunity to flag them; the assertion below is a real negative.
    (tmp_path / "configs/claude/references").mkdir(parents=True)
    (tmp_path / "configs/claude/references/harness-routing.md").write_text(
        "# routing\n", encoding="utf-8"
    )
    (tmp_path / "references").mkdir(parents=True)
    (tmp_path / "references/some-doc.md").write_text("# doc\n", encoding="utf-8")

    report = checker.scan(tmp_path)

    assert report.violations == ()


def test_ignores_generic_project_filenames_not_in_the_shared_reference_registry(
    tmp_path: Path,
) -> None:
    """A bare mention of README.md/CLAUDE.md/package.json is about the target
    project a skill operates on, not a claim that this bundle ships it."""
    checker = _checker_module()
    _write_bundle(
        tmp_path,
        "manifest-demo",
        "demo-skill",
        "---\nname: demo-skill\ndescription: demo\n---\n"
        "Update the project's `README.md`, `CLAUDE.md`, and `package.json`.\n",
    )

    report = checker.scan(tmp_path)

    assert report.violations == ()


def test_ignores_description_frontmatter_mentions(tmp_path: Path) -> None:
    checker = _checker_module()
    _write_bundle(
        tmp_path,
        "manifest-workspace",
        "token-benchmark",
        "---\nname: token-benchmark\n"
        "description: Measure token overhead; regenerates docs/TOKEN_BENCHMARK.md.\n"
        "---\n"
        "Body text with no path citations.\n",
    )
    (tmp_path / "docs").mkdir(parents=True)
    (tmp_path / "docs/TOKEN_BENCHMARK.md").write_text("# report\n", encoding="utf-8")

    report = checker.scan(tmp_path)

    assert report.violations == ()


# --- scope: SKILL.md's own directory, not the whole bundle -----------------


def test_ignores_forbidden_looking_text_outside_the_skills_tree(tmp_path: Path) -> None:
    """A bundle-root runtime/config comment is not something any SKILL.md
    cited -- scanning it would misattribute the defect to the wrong skill."""
    checker = _checker_module()
    skill_dir = _write_bundle(
        tmp_path,
        "manifest-ops",
        "docker-compose-commandments",
        "---\nname: docker-compose-commandments\ndescription: demo\n---\n"
        "No citations here.\n",
    )
    bundle_root = skill_dir.parents[1]
    (bundle_root / "runtime/config").mkdir(parents=True)
    (bundle_root / "runtime/config/compose_commandments.yml").write_text(
        "# version_pin (command_config.yml) owns image pinning.\n", encoding="utf-8"
    )

    report = checker.scan(tmp_path)

    assert report.violations == ()


# --- mutation-style regression: a fixed citation must stay fixed -----------


def test_gate_would_have_failed_before_the_relative_path_was_correct(
    tmp_path: Path,
) -> None:
    """A relative path with one extra ``../`` hop walks past the bundle root
    into a *named sibling* bundle instead of this bundle's own runtime tree --
    the exact shape of a copy-pasted-then-miscounted reference. Proves the
    passing (correct-hop-count) case elsewhere in this file is not passing
    merely because the checker never looked."""
    checker = _checker_module()
    skill_dir = _write_bundle(
        tmp_path,
        "manifest-security",
        "code-audit",
        "---\nname: code-audit\ndescription: demo\n---\n"
        "Read `../../../manifest-code-quality/runtime/references/"
        "code-constitution.md` first.\n",
    )
    bundle_root = skill_dir.parents[1]
    (bundle_root / "runtime/references").mkdir(parents=True)
    (bundle_root / "runtime/references/code-constitution.md").write_text(
        "# this bundle's own copy -- the citation above does not point here\n",
        encoding="utf-8",
    )
    sibling = tmp_path / "plugins/manifest-code-quality/runtime/references"
    sibling.mkdir(parents=True)
    (sibling / "code-constitution.md").write_text("# constitution\n", encoding="utf-8")

    report = checker.scan(tmp_path)

    assert len(report.violations) == 1
    assert report.violations[0].kind == "cross-bundle-path"
    assert report.violations[0].value == (
        "../../../manifest-code-quality/runtime/references/code-constitution.md"
    )


# Real-repo regression (the known true positives stay caught, the documented
# non-defects stay unflagged) lives in test_bundle_link_references_real_repo.py.

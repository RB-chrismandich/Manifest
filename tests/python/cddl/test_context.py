"""Foundational + US3 — artifact discovery via the spec_review.sh seam
(T006/T029, FR-001/FR-002, research D2)."""

import pytest
from cddl import PreflightError
from cddl.context import resolve_context


def test_speckit_layout_resolves(fixture_repo):
    ctx = resolve_context(fixture_repo)
    assert ctx.layout_type == "speckit"
    assert ctx.spec_path.endswith("specs/001-fixture/spec.md")
    assert ctx.plan_path.endswith("specs/001-fixture/plan.md")
    assert "Fixture Spec" in ctx.spec_content
    assert "Fixture Plan" in ctx.plan_content


def test_feature_dir_target_resolves(fixture_repo):
    ctx = resolve_context(fixture_repo / "specs" / "001-fixture")
    assert ctx.spec_path.endswith("001-fixture/spec.md")


def test_explicit_paths_win_over_detection(fixture_repo, tmp_path):
    other_spec = tmp_path / "other-spec.md"
    other_spec.write_text("# Other Spec\n")
    other_plan = tmp_path / "other-plan.md"
    other_plan.write_text("# Other Plan\n")
    ctx = resolve_context(fixture_repo, spec=other_spec, plan=other_plan)
    assert ctx.layout_type == "explicit"
    assert ctx.spec_path == str(other_spec)
    assert "Other Spec" in ctx.spec_content


def test_missing_plan_recorded_not_fatal(fixture_repo):
    (fixture_repo / "specs" / "001-fixture" / "plan.md").unlink()
    ctx = resolve_context(fixture_repo)
    assert ctx.plan_path is None
    assert ctx.plan_content is None
    assert ctx.spec_content  # spec alone is enough (FR-002)


def test_tasks_artifact_is_ignored(fixture_repo):
    (fixture_repo / "specs" / "001-fixture" / "tasks.md").write_text("# Tasks\n")
    ctx = resolve_context(fixture_repo)
    # No tasks attribute in the context contract — never required, never missing.
    assert not hasattr(ctx, "tasks_path")


def test_empty_spec_refused(fixture_repo):
    (fixture_repo / "specs" / "001-fixture" / "spec.md").write_text("")
    with pytest.raises(PreflightError, match="empty"):
        resolve_context(fixture_repo)


# --- US3: superpowers layout + unresolvable target (T029) ---


def test_superpowers_layout_resolves(make_repo):
    repo = make_repo(name="sp", layout="superpowers")
    ctx = resolve_context(repo)
    assert ctx.layout_type == "superpowers"
    assert ctx.spec_path.endswith("fixture-design.md")
    assert ctx.plan_path.endswith("fixture-plan.md")
    assert "Fixture Design" in ctx.spec_content


def test_superpowers_never_reports_missing_tasks(make_repo):
    repo = make_repo(name="sp2", layout="superpowers")
    try:
        ctx = resolve_context(repo)
    except PreflightError as exc:  # pragma: no cover - failure detail
        pytest.fail(f"superpowers run refused: {exc}")
    # Tasks are embedded in the plan in this layout: the context has no tasks
    # field at all, so nothing downstream can ever report one missing (FR-002).
    assert not hasattr(ctx, "tasks_path")
    assert ctx.plan_path is not None


def test_superpowers_design_doc_file_target(make_repo):
    # US3 scenario 1: "invokes the loop with the design doc path" — the FILE.
    repo = make_repo(name="sp-file", layout="superpowers")
    design = repo / "docs" / "superpowers" / "specs" / "2026-07-10-fixture-design.md"
    ctx = resolve_context(design)
    assert ctx.spec_path == str(design.resolve())
    assert ctx.layout_type == "superpowers"
    assert ctx.plan_path is not None  # paired plan discovered from the repo
    assert ctx.plan_path.endswith("fixture-plan.md")


def test_superpowers_file_target_in_mixed_layout_repo(fixture_repo):
    # A repo with BOTH layouts: generic discovery would rank speckit first and
    # mispair the design doc with the speckit plan (FR-001/US3).
    specs = fixture_repo / "docs" / "superpowers" / "specs"
    plans = fixture_repo / "docs" / "superpowers" / "plans"
    specs.mkdir(parents=True)
    plans.mkdir(parents=True)
    design = specs / "2026-07-10-mixed-design.md"
    design.write_text("# Mixed Design\n")
    (plans / "2026-07-10-mixed-plan.md").write_text("# Mixed Plan\n")
    ctx = resolve_context(design)
    assert ctx.spec_path == str(design.resolve())
    assert ctx.layout_type == "superpowers"
    assert ctx.plan_path.endswith("mixed-plan.md")  # never the speckit plan
    assert "Mixed Plan" in ctx.plan_content


def test_speckit_spec_file_target(fixture_repo):
    spec_file = fixture_repo / "specs" / "001-fixture" / "spec.md"
    ctx = resolve_context(spec_file)
    assert ctx.spec_path.endswith("001-fixture/spec.md")
    assert ctx.plan_path.endswith("001-fixture/plan.md")  # sibling pairing
    assert ctx.layout_type == "speckit"


def test_neither_layout_refused_actionably(tmp_path):
    empty = tmp_path / "not-a-feature"
    empty.mkdir()
    with pytest.raises(PreflightError) as exc:
        resolve_context(empty)
    msg = str(exc.value)
    assert "speckit" in msg
    assert "superpowers" in msg


def test_refusal_mutates_nothing(tmp_path):
    empty = tmp_path / "not-a-feature-2"
    empty.mkdir()
    before = sorted(p.name for p in empty.rglob("*"))
    with pytest.raises(PreflightError):
        resolve_context(empty)
    assert sorted(p.name for p in empty.rglob("*")) == before

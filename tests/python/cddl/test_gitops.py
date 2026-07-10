"""US1 — git safety mechanics (T015, FR-011; research D9)."""

import subprocess

import pytest
from cddl import PreflightError
from cddl.gitops import current_branch, preflight, repo_root_of, stage


def git(repo, *args):
    return subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, text=True, check=True
    ).stdout


def test_preflight_ok_on_clean_feature_branch(fixture_repo):
    assert preflight(fixture_repo, allow_dirty=False) == "482-fixture"


def test_repo_root_of_subdir(fixture_repo):
    sub = fixture_repo / "specs" / "001-fixture"
    assert repo_root_of(sub) == fixture_repo.resolve()


def test_repo_root_of_file_target(fixture_repo):
    # US3: the target may be the design-doc FILE itself
    spec_file = fixture_repo / "specs" / "001-fixture" / "spec.md"
    assert repo_root_of(spec_file) == fixture_repo.resolve()


def test_repo_root_of_non_repo(tmp_path):
    with pytest.raises(PreflightError, match="git"):
        repo_root_of(tmp_path)


def test_default_branch_refused(make_repo):
    repo = make_repo(name="on-main", branch=None)  # stays on main
    with pytest.raises(PreflightError, match="default branch"):
        preflight(repo, allow_dirty=False)


def test_dirty_tree_refused(fixture_repo):
    (fixture_repo / "junk.txt").write_text("dirt\n")
    with pytest.raises(PreflightError, match="dirty"):
        preflight(fixture_repo, allow_dirty=False)


def test_allow_dirty_overrides(fixture_repo):
    (fixture_repo / "junk.txt").write_text("dirt\n")
    assert preflight(fixture_repo, allow_dirty=True) == "482-fixture"


def test_stage_exactly_written_paths(fixture_repo):
    # pre-existing dirt that must never be staged (--allow-dirty semantics)
    (fixture_repo / "unrelated.txt").write_text("dirt\n")
    (fixture_repo / "loop-output.txt").write_text("approved change\n")
    stage(fixture_repo, ["loop-output.txt"])
    staged = git(fixture_repo, "diff", "--cached", "--name-only").splitlines()
    assert staged == ["loop-output.txt"]


def test_stage_handles_deleted_paths(fixture_repo):
    (fixture_repo / "README.md").unlink()
    stage(fixture_repo, ["README.md"])
    staged = git(fixture_repo, "diff", "--cached", "--name-only").splitlines()
    assert staged == ["README.md"]


def test_stage_skips_phantom_paths(fixture_repo):
    # A file created and deleted within the run was never tracked: nothing to
    # stage, and `git add` on its pathspec would be fatal.
    (fixture_repo / "kept.txt").write_text("keep\n")
    stage(fixture_repo, ["kept.txt", "phantom-never-existed.txt"])
    staged = git(fixture_repo, "diff", "--cached", "--name-only").splitlines()
    assert staged == ["kept.txt"]


def test_stage_only_phantoms_is_a_noop(fixture_repo):
    stage(fixture_repo, ["phantom.txt"])  # must not raise
    assert git(fixture_repo, "diff", "--cached", "--name-only") == ""


def test_no_commit_push_merge_ever(fixture_repo):
    head_before = git(fixture_repo, "rev-parse", "HEAD").strip()
    (fixture_repo / "f.txt").write_text("x\n")
    stage(fixture_repo, ["f.txt"])
    assert git(fixture_repo, "rev-parse", "HEAD").strip() == head_before
    assert current_branch(fixture_repo) == "482-fixture"

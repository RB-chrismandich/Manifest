"""Pin candidate identity across source and materialized copies."""

from pathlib import Path

from manifest_agent.checks.candidate import candidate_digest, materialize_candidate


def test_candidate_digest_covers_empty_directories_and_modes(tmp_path: Path):
    root = tmp_path / "candidate"
    root.mkdir()
    probe = root / "probe.py"
    probe.write_text("pass\n", encoding="utf-8")
    baseline = candidate_digest(root)
    (root / "empty").mkdir()
    assert candidate_digest(root) != baseline
    (root / "empty").rmdir()
    probe.chmod(0o755)
    assert candidate_digest(root) != baseline


def test_materialized_candidate_preserves_digest_with_nested_git_files(
    tmp_path: Path,
):
    source = tmp_path / "source"
    source.mkdir()
    nested_git = source / "submodule" / ".git"
    nested_git.parent.mkdir()
    nested_git.write_text("gitdir: ../../.git/modules/submodule\n", encoding="utf-8")
    (source / "tracked.txt").write_text("tracked\n", encoding="utf-8")

    candidate = materialize_candidate(source, tmp_path / "candidate")

    assert candidate.digest == candidate_digest(source)

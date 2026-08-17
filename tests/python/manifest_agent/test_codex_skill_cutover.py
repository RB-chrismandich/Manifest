import json
from pathlib import Path

import pytest

from manifest_agent.codex_skill_cutover import (
    SkillCutoverError,
    apply_codex_skill_cutover,
    commit_codex_skill_cutover,
    cutover_codex_skills,
    inspect_codex_skill_source,
    prepare_codex_skill_cutover,
    restore_codex_skills,
    resume_interrupted_cutover,
)


def test_cutover_and_restore_only_owned_link(tmp_path: Path) -> None:
    home = tmp_path / "home"
    source = home / ".manifest/skills"
    (source / ".system").mkdir(parents=True)
    (home / ".codex").mkdir()
    (home / ".codex/skills").symlink_to(source)
    entry = cutover_codex_skills(home, source)
    assert (home / ".codex/skills/.system").resolve() == source / ".system"
    restore_codex_skills(entry)
    assert (home / ".codex/skills").resolve() == source


def test_cutover_blocks_unowned_entries(tmp_path: Path) -> None:
    home = tmp_path / "home"
    source = home / ".manifest/skills"
    (source / ".system").mkdir(parents=True)
    skills = home / ".codex/skills"
    skills.mkdir(parents=True)
    (skills / "foreign").mkdir()
    with pytest.raises(SkillCutoverError, match="user-managed"):
        cutover_codex_skills(home, source)


def test_empty_codex_skills_directory_is_not_treated_as_converged(
    tmp_path: Path,
) -> None:
    home = tmp_path / "home"
    source = home / ".manifest/skills"
    (source / ".system").mkdir(parents=True)
    (home / ".codex/skills").mkdir(parents=True)

    state = inspect_codex_skill_source(home, source)

    assert state.kind == "user-managed"
    with pytest.raises(SkillCutoverError, match="user-managed"):
        prepare_codex_skill_cutover(home, source)


def test_cutover_backup_is_retained_until_durable_commit(tmp_path: Path) -> None:
    home = tmp_path / "home"
    source = home / ".manifest/skills"
    (source / ".system").mkdir(parents=True)
    (home / ".codex").mkdir()
    skills = home / ".codex/skills"
    skills.symlink_to(source)
    entry = prepare_codex_skill_cutover(home, source)

    apply_codex_skill_cutover(entry, source)

    backup = home / ".codex/.skills.manifest-cutover"
    assert backup.is_symlink()
    commit_codex_skill_cutover(entry)
    assert not backup.exists() and not backup.is_symlink()


def test_restore_rejects_unsafe_backup_before_removing_active_source(
    tmp_path: Path,
) -> None:
    home = tmp_path / "home"
    source = home / ".manifest/skills"
    (source / ".system").mkdir(parents=True)
    (home / ".codex").mkdir()
    skills = home / ".codex/skills"
    skills.symlink_to(source)
    entry = cutover_codex_skills(home, source)
    backup = home / ".codex/.skills.manifest-cutover"
    backup.unlink()
    backup.write_text("unsafe\n", encoding="utf-8")

    with pytest.raises(SkillCutoverError, match="backup became unsafe"):
        restore_codex_skills(entry)

    assert skills.is_dir()
    assert (skills / ".system").is_symlink()
    assert backup.read_text(encoding="utf-8") == "unsafe\n"


def test_interrupted_cutover_is_resumed_instead_of_dead_ending(tmp_path: Path) -> None:
    """A crash between the two renames must not strand ~/.codex/skills missing.

    Simulates SIGKILL landing after `path.rename(backup)` but before the
    replacement directory is created: skills is absent and only the dotted
    backup survives. Without recovery, inspect reports `missing` forever and
    every later prepare raises rather than restoring the user's link.
    """
    home = tmp_path / "home"
    source = home / ".manifest/skills"
    (source / ".system").mkdir(parents=True)
    (home / ".codex").mkdir()
    skills = home / ".codex/skills"
    skills.symlink_to(source)

    # The exact on-disk state left by a crash in the rename gap: the pending
    # marker is written first, then the rename lands, then the process dies.
    skills.with_name(".skills.manifest-cutover.pending").write_text("")
    skills.rename(skills.with_name(".skills.manifest-cutover"))
    assert not skills.exists() and not skills.is_symlink()
    assert inspect_codex_skill_source(home, source).kind == "missing"

    # The ordinary entry point must recover on its own -- no explicit repair
    # call -- or the operator is stranded with no skills and an opaque error.
    entry = cutover_codex_skills(home, source)
    assert (home / ".codex/skills/.system").resolve() == source / ".system"
    restore_codex_skills(entry)
    assert skills.resolve() == source


def test_resume_is_a_noop_when_no_transition_was_interrupted(tmp_path: Path) -> None:
    home = tmp_path / "home"
    source = home / ".manifest/skills"
    (source / ".system").mkdir(parents=True)
    (home / ".codex").mkdir()
    (home / ".codex/skills").symlink_to(source)

    assert resume_interrupted_cutover(home) is False
    assert inspect_codex_skill_source(home, source).kind == "legacy-link"


def test_stale_backup_without_a_pending_marker_is_left_alone(tmp_path: Path) -> None:
    """A backup alone is not evidence of a crash.

    It legitimately persists between apply and commit. If the user then deletes
    ~/.codex/skills on purpose, resuming on the backup alone would silently
    resurrect the link they just removed.
    """
    home = tmp_path / "home"
    source = home / ".manifest/skills"
    (source / ".system").mkdir(parents=True)
    (home / ".codex").mkdir()
    skills = home / ".codex/skills"

    # Uncommitted backup present, no transition in flight, path deliberately gone.
    (home / ".codex/.skills.manifest-cutover").symlink_to(source)

    assert resume_interrupted_cutover(home) is False
    assert not skills.exists() and not skills.is_symlink()
    assert (home / ".codex/.skills.manifest-cutover").is_symlink()


def test_restore_recovers_from_its_own_interrupted_run(tmp_path: Path) -> None:
    """A restore that died after rmdir must be finishable, not fatal.

    commit deletes the backup, so the usual restore takes the
    `path.symlink_to(target)` branch with no backup on disk. A crash between
    rmdir and that call leaves the path absent with no backup to rename back --
    only the receipt knows the prior target, so restore itself must resume it.
    """
    home = tmp_path / "home"
    source = home / ".manifest/skills"
    (source / ".system").mkdir(parents=True)
    (home / ".codex").mkdir()
    skills = home / ".codex/skills"
    skills.symlink_to(source)

    entry = cutover_codex_skills(home, source)
    commit_codex_skill_cutover(entry)
    assert not (home / ".codex/.skills.manifest-cutover").exists()

    # Exact state left by a crash after rmdir, backup already committed away.
    (skills / ".system").unlink()
    # The marker records the target the interrupted restore was heading for,
    # exactly as _begin_transition writes it.
    import json as _json

    prior_target = _json.loads(entry.previous_checksum)["prior_target"]
    (home / ".codex/.skills.manifest-cutover.pending").write_text(prior_target)
    skills.rmdir()
    assert not skills.exists() and not skills.is_symlink()

    restore_codex_skills(entry)

    assert skills.is_symlink()
    assert skills.resolve() == source
    assert not (home / ".codex/.skills.manifest-cutover.pending").exists()


def test_stale_marker_for_a_different_target_is_not_consumed(tmp_path: Path) -> None:
    """A marker naming some other target must not resurrect this path.

    Existence alone made any leftover marker usable, so unrelated cleanup that
    missed the hidden marker could silently recreate a link the user removed.
    """
    home = tmp_path / "home"
    source = home / ".manifest/skills"
    (source / ".system").mkdir(parents=True)
    (home / ".codex").mkdir()
    skills = home / ".codex/skills"
    skills.symlink_to(source)
    entry = cutover_codex_skills(home, source)
    commit_codex_skill_cutover(entry)

    (skills / ".system").unlink()
    skills.rmdir()
    # Marker left behind by something else, naming a different target.
    (home / ".codex/.skills.manifest-cutover.pending").write_text("/somewhere/else")

    with pytest.raises(SkillCutoverError):
        restore_codex_skills(entry)
    assert not skills.exists() and not skills.is_symlink()


def test_marker_survives_when_both_relink_attempts_fail(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The marker is the only recovery signal; a failed restore must keep it."""
    import manifest_agent.codex_skill_cutover as mod

    home = tmp_path / "home"
    source = home / ".manifest/skills"
    (source / ".system").mkdir(parents=True)
    (home / ".codex").mkdir()
    skills = home / ".codex/skills"
    skills.symlink_to(source)
    entry = cutover_codex_skills(home, source)
    commit_codex_skill_cutover(entry)

    def _always_fails(path, backup, target):
        raise OSError("relink failed")

    monkeypatch.setattr(mod, "_relink_prior", _always_fails)

    with pytest.raises(OSError):
        restore_codex_skills(entry)

    assert (home / ".codex/.skills.manifest-cutover.pending").exists(), (
        "recovery marker was destroyed, leaving the absence undetectable"
    )


def test_crash_after_mkdir_is_recovered_not_stranded(tmp_path: Path) -> None:
    """A half-built cutover directory must be rolled back, not left forever.

    resume gated purely on the path being absent, so a crash after mkdir left
    the marker stranded and every later prepare raising `user-managed`.
    """
    home = tmp_path / "home"
    source = home / ".manifest/skills"
    (source / ".system").mkdir(parents=True)
    (home / ".codex").mkdir()
    skills = home / ".codex/skills"
    skills.symlink_to(source)

    # Crash state: marker written, backup taken, directory created, but the
    # .system link and _end_transition never completed.
    (home / ".codex/.skills.manifest-cutover.pending").write_text(str(source))
    skills.rename(home / ".codex/.skills.manifest-cutover")
    skills.mkdir(mode=0o700)

    assert resume_interrupted_cutover(home) is True
    assert skills.is_symlink()
    assert inspect_codex_skill_source(home, source).kind == "legacy-link"
    assert not (home / ".codex/.skills.manifest-cutover.pending").exists()


def test_resume_leaves_a_user_populated_directory_alone(tmp_path: Path) -> None:
    """Only OUR half-built directory is reclaimable, never the user's files."""
    home = tmp_path / "home"
    source = home / ".manifest/skills"
    (source / ".system").mkdir(parents=True)
    (home / ".codex").mkdir()
    skills = home / ".codex/skills"
    skills.mkdir()
    (skills / "my-own-skill.md").write_text("do not delete me")
    (home / ".codex/.skills.manifest-cutover.pending").write_text("")
    (home / ".codex/.skills.manifest-cutover").symlink_to(source)

    assert resume_interrupted_cutover(home) is False
    assert (skills / "my-own-skill.md").read_text() == "do not delete me"


def test_reclaim_refuses_when_the_marker_names_a_different_target(
    tmp_path: Path,
) -> None:
    """A stale marker must not authorise deleting a user-made .system link."""
    home = tmp_path / "home"
    source = home / ".manifest/skills"
    (source / ".system").mkdir(parents=True)
    (home / ".codex").mkdir()
    skills = home / ".codex/skills"

    # User's own directory holding only their own .system symlink.
    skills.mkdir()
    (skills / ".system").symlink_to(source / ".system")
    (home / ".codex/.skills.manifest-cutover").symlink_to(source)
    (home / ".codex/.skills.manifest-cutover.pending").write_text("/somewhere/else")

    assert resume_interrupted_cutover(home) is False
    assert (skills / ".system").is_symlink()


def test_restore_resumes_from_an_empty_shell_directory(tmp_path: Path) -> None:
    """Crash between unlinking .system and rmdir must still be recoverable.

    The backup is already committed away, so resume_interrupted_cutover bails
    (no backup symlink) and the early-resume branch used to require the path be
    absent -- an empty directory is present, so it fell through to
    "Codex skills changed after Manifest cutover" with no way forward.
    """
    home = tmp_path / "home"
    source = home / ".manifest/skills"
    (source / ".system").mkdir(parents=True)
    (home / ".codex").mkdir()
    skills = home / ".codex/skills"
    skills.symlink_to(source)

    entry = cutover_codex_skills(home, source)
    commit_codex_skill_cutover(entry)

    prior_target = json.loads(entry.previous_checksum)["prior_target"]
    (home / ".codex/.skills.manifest-cutover.pending").write_text(prior_target)
    (skills / ".system").unlink()  # crash lands here: dir now empty
    assert skills.is_dir() and not any(skills.iterdir())

    restore_codex_skills(entry)

    assert skills.is_symlink()
    assert skills.resolve() == source
    assert not (home / ".codex/.skills.manifest-cutover.pending").exists()


def test_restore_refuses_a_shell_directory_the_user_has_populated(
    tmp_path: Path,
) -> None:
    """Only an EMPTY leftover is ours to clear."""
    home = tmp_path / "home"
    source = home / ".manifest/skills"
    (source / ".system").mkdir(parents=True)
    (home / ".codex").mkdir()
    skills = home / ".codex/skills"
    skills.symlink_to(source)
    entry = cutover_codex_skills(home, source)
    commit_codex_skill_cutover(entry)

    prior_target = json.loads(entry.previous_checksum)["prior_target"]
    (home / ".codex/.skills.manifest-cutover.pending").write_text(prior_target)
    (skills / ".system").unlink()
    (skills / "user-file.md").write_text("mine")

    with pytest.raises(SkillCutoverError):
        restore_codex_skills(entry)
    assert (skills / "user-file.md").read_text() == "mine"


def test_restore_clears_a_stale_marker_when_the_link_is_already_back(
    tmp_path: Path,
) -> None:
    """A crash after relinking but before clearing the marker is not a failure.

    The work already succeeded; a retry used to see the restored link as
    user-managed and raise, failing an operation that had completed.
    """
    home = tmp_path / "home"
    source = home / ".manifest/skills"
    (source / ".system").mkdir(parents=True)
    (home / ".codex").mkdir()
    skills = home / ".codex/skills"
    skills.symlink_to(source)

    entry = cutover_codex_skills(home, source)
    commit_codex_skill_cutover(entry)
    restore_codex_skills(entry)  # completes normally
    assert skills.is_symlink()

    # Re-plant only the marker: the exact residue of a crash before clearing.
    prior_target = json.loads(entry.previous_checksum)["prior_target"]
    (home / ".codex/.skills.manifest-cutover.pending").write_text(prior_target)

    restore_codex_skills(entry)  # must be a no-op, not an error

    assert skills.is_symlink()
    assert skills.resolve() == source
    assert not (home / ".codex/.skills.manifest-cutover.pending").exists()


def test_restore_still_rejects_a_link_pointing_somewhere_else(tmp_path: Path) -> None:
    """A link the user repointed is not our completed work."""
    home = tmp_path / "home"
    source = home / ".manifest/skills"
    other = home / "elsewhere"
    (source / ".system").mkdir(parents=True)
    other.mkdir(parents=True)
    (home / ".codex").mkdir()
    skills = home / ".codex/skills"
    skills.symlink_to(source)
    entry = cutover_codex_skills(home, source)
    commit_codex_skill_cutover(entry)
    restore_codex_skills(entry)

    skills.unlink()
    skills.symlink_to(other)  # user repointed it
    prior_target = json.loads(entry.previous_checksum)["prior_target"]
    (home / ".codex/.skills.manifest-cutover.pending").write_text(prior_target)

    with pytest.raises(SkillCutoverError):
        restore_codex_skills(entry)
    assert skills.resolve() == other


def test_repopulated_shell_directory_raises_a_typed_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A file appearing between the emptiness check and rmdir is our error.

    The window is real (nothing locks the directory); it must surface as
    SkillCutoverError, not a bare OSError leaking out of the restore.
    """
    import manifest_agent.codex_skill_cutover as mod

    home = tmp_path / "home"
    source = home / ".manifest/skills"
    (source / ".system").mkdir(parents=True)
    (home / ".codex").mkdir()
    skills = home / ".codex/skills"
    skills.symlink_to(source)
    entry = cutover_codex_skills(home, source)
    commit_codex_skill_cutover(entry)

    prior_target = json.loads(entry.previous_checksum)["prior_target"]
    (home / ".codex/.skills.manifest-cutover.pending").write_text(prior_target)
    (skills / ".system").unlink()

    real_resumable = mod._restore_is_resumable

    def _repopulate(path, target):
        verdict = real_resumable(path, target)
        if verdict and path.is_dir():
            (path / "raced.md").write_text("appeared after the check")
        return verdict

    monkeypatch.setattr(mod, "_restore_is_resumable", _repopulate)

    with pytest.raises(SkillCutoverError, match="could not remove"):
        restore_codex_skills(entry)
    assert (skills / "raced.md").read_text() == "appeared after the check"


def test_failed_rmdir_in_restore_keeps_the_recovery_marker(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A leftover directory is not a restored link -- the marker must survive.

    The guard used to clear on `path.exists()`, which is true for the directory
    a failed rmdir leaves behind. That deleted the only signal a later run has
    that this path still needs restoring, stranding the tree with no skills.
    """
    import manifest_agent.codex_skill_cutover as mod

    home = tmp_path / "home"
    source = home / ".manifest/skills"
    (source / ".system").mkdir(parents=True)
    (home / ".codex").mkdir()
    skills = home / ".codex/skills"
    skills.symlink_to(source)
    entry = cutover_codex_skills(home, source)
    commit_codex_skill_cutover(entry)

    # Race the main restore path: repopulate the directory after .system is
    # unlinked, so its own rmdir fails.
    real_begin = mod._begin_transition

    def _repopulate(path, target=""):
        real_begin(path, target)
        if path.is_dir() and not path.is_symlink():
            (path / "raced.md").write_text("appeared before rmdir")

    monkeypatch.setattr(mod, "_begin_transition", _repopulate)

    with pytest.raises(OSError):
        restore_codex_skills(entry)

    marker = home / ".codex/.skills.manifest-cutover.pending"
    assert marker.exists(), "recovery marker was cleared without restoring the link"
    assert not skills.is_symlink()

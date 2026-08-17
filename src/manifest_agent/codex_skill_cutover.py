"""Transactional retirement of the Manifest-wide Codex skills link."""

from __future__ import annotations

import json
import os
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from manifest_agent.models import OwnedEntry


class SkillCutoverError(RuntimeError):
    """The Codex skill source is unowned or unsafe to mutate."""


@dataclass(frozen=True)
class SkillSourceState:
    kind: Literal["legacy-link", "system-only", "user-managed", "missing"]
    path: Path
    target: str | None = None


def inspect_codex_skill_source(home: Path, expected_target: Path) -> SkillSourceState:
    path = home / ".codex" / "skills"
    if path.is_symlink():
        target = str(path.readlink())
        if path.resolve(strict=False) == expected_target.resolve(strict=False):
            return SkillSourceState("legacy-link", path, target)
        return SkillSourceState("user-managed", path, target)
    if not path.exists():
        return SkillSourceState("missing", path)
    if not path.is_dir():
        return SkillSourceState("user-managed", path)
    entries = list(path.iterdir())
    if not entries:
        return SkillSourceState("user-managed", path)
    if any(entry.name != ".system" for entry in entries):
        return SkillSourceState("user-managed", path)
    system = entries[0]
    if not system.is_symlink() or system.resolve(strict=False) != (
        expected_target / ".system"
    ).resolve(strict=False):
        return SkillSourceState("user-managed", path)
    return SkillSourceState("system-only", path)


def _cutover_backup_path(path: Path) -> Path:
    return path.with_name(f".{path.name}.manifest-cutover")


def _cutover_pending_path(path: Path) -> Path:
    return path.with_name(f".{path.name}.manifest-cutover.pending")


def _begin_transition(path: Path, target: str = "") -> None:
    """Mark a transition in flight before the first of its two renames.

    The recorded target binds the marker to one specific transition, so a
    stale marker left by unrelated cleanup cannot be consumed to resurrect a
    link the user deliberately removed.
    """
    _cutover_pending_path(path).write_text(target, encoding="utf-8")
    _fsync_dir(path.parent)


def _pending_target(path: Path) -> str | None:
    try:
        return _cutover_pending_path(path).read_text(encoding="utf-8")
    except OSError:
        return None


def _end_transition(path: Path) -> None:
    _cutover_pending_path(path).unlink(missing_ok=True)
    _fsync_dir(path.parent)


def _fsync_dir(directory: Path) -> None:
    descriptor = os.open(directory, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def resume_interrupted_cutover(home: Path) -> bool:
    """Undo a cutover or restore that died between its two rename syscalls.

    Neither direction of the symlink<->directory swap is atomic, so a SIGKILL
    or power loss in the gap leaves ``~/.codex/skills`` absent entirely -- the
    prior link survives only under the deterministic backup name. Without this,
    ``inspect_codex_skill_source`` reports ``missing`` forever and every later
    prepare/restore raises instead of recovering, leaving Codex with no skills
    until a human renames the backup by hand.

    A backup on its own is NOT evidence of a crash: it legitimately persists
    between apply and commit. Acting on that alone would resurrect a link a
    user had since deleted on purpose. The pending marker, written before the
    first rename and cleared after the last, is what distinguishes an
    interrupted transition from an ordinary uncommitted one.

    Returns True when an interrupted transition was rolled back.
    """
    path = home / ".codex" / "skills"
    backup = _cutover_backup_path(path)
    pending = _cutover_pending_path(path)
    if not pending.exists() or not backup.is_symlink():
        return False
    if path.is_symlink():
        return False
    if path.exists():
        # A crash after mkdir but before the transition finished leaves a
        # half-built directory. Gating purely on absence stranded the marker
        # forever and left every later prepare raising `user-managed`. Roll the
        # partial directory back, but only when it is ours: empty, or holding
        # nothing but the .system link this cutover creates.
        if not path.is_dir():
            return False
        # Only reclaim a directory this cutover built. The marker records the
        # target it was heading for; requiring it to match the backup's own
        # target keeps an unrelated stale marker from authorising the deletion
        # of a `.system` link the user created themselves.
        recorded = _pending_target(path)
        if recorded and recorded != str(backup.readlink()):
            return False
        entries = {item.name for item in path.iterdir()}
        if entries - {".system"}:
            return False
        system = path / ".system"
        if system.is_dir() and not system.is_symlink():
            return False
        if system.is_symlink() or system.exists():
            system.unlink()
        path.rmdir()
    backup.rename(path)
    _end_transition(path)
    return True


def cutover_codex_skills(home: Path, expected_target: Path) -> OwnedEntry:
    entry = prepare_codex_skill_cutover(home, expected_target)
    if entry.previous_checksum is not None:
        apply_codex_skill_cutover(entry, expected_target)
    return entry


def prepare_codex_skill_cutover(home: Path, expected_target: Path) -> OwnedEntry:
    """Return durable prior-state evidence before changing the skills source."""
    resume_interrupted_cutover(home)
    state = inspect_codex_skill_source(home, expected_target)
    if state.kind == "system-only":
        return OwnedEntry(
            "codex-skill-source",
            "codex-shared-skills",
            "manifest",
            str(state.path),
            None,
        )
    if state.kind != "legacy-link":
        raise SkillCutoverError(
            f"Codex skills source is {state.kind}, not a Manifest-owned link"
        )
    system_source = expected_target / ".system"
    if not system_source.is_dir():
        raise SkillCutoverError("Manifest system skills source is missing")
    prior = json.dumps(
        {"prior_target": state.target, "system_target": str(system_source)},
        separators=(",", ":"),
    )
    return OwnedEntry(
        "codex-skill-source", "codex-shared-skills", "manifest", str(state.path), prior
    )


def apply_codex_skill_cutover(entry: OwnedEntry, expected_target: Path) -> None:
    """Apply a prepared cutover only while the recorded legacy link remains."""
    if not entry.target_path or not entry.previous_checksum:
        raise SkillCutoverError("prepared Codex skill cutover is incomplete")
    path = Path(entry.target_path)
    try:
        target = json.loads(entry.previous_checksum)["prior_target"]
    except (json.JSONDecodeError, KeyError, TypeError) as error:
        raise SkillCutoverError("prepared Codex skill cutover is invalid") from error
    home = path.parents[1]
    state = inspect_codex_skill_source(home, expected_target)
    if state.kind != "legacy-link" or state.target != target:
        raise SkillCutoverError("Codex skills changed after cutover preparation")
    system_source = expected_target / ".system"
    if not system_source.is_dir():
        raise SkillCutoverError("Manifest system skills source is missing")
    backup = path.with_name(f".{path.name}.manifest-cutover")
    if backup.exists() or backup.is_symlink():
        raise SkillCutoverError("an unfinished Codex skill cutover already exists")
    _begin_transition(path, target)
    try:
        path.rename(backup)
    except BaseException:
        # Nothing moved, so clear the marker rather than leaving an inert
        # in-flight signal behind; restore's first mutation is inside its try
        # for the same reason.
        _end_transition(path)
        raise
    try:
        path.mkdir(mode=0o700)
        (path / ".system").symlink_to(system_source)
        _fsync_dir(path.parent)
        _end_transition(path)
    except Exception:
        if path.exists() and path.is_dir():
            link = path / ".system"
            if link.is_symlink():
                link.unlink()
            path.rmdir()
        if backup.exists() or backup.is_symlink():
            backup.rename(path)
        _end_transition(path)
        raise


def commit_codex_skill_cutover(entry: OwnedEntry) -> None:
    """Discard the retained prior link only after the receipt is durable."""
    if not entry.target_path or not entry.previous_checksum:
        return
    path = Path(entry.target_path)
    backup = path.with_name(f".{path.name}.manifest-cutover")
    if not backup.exists() and not backup.is_symlink():
        try:
            metadata = json.loads(entry.previous_checksum)
            system_target = metadata.get("system_target")
        except (json.JSONDecodeError, TypeError):
            system_target = None
        system = path / ".system"
        if (
            path.is_dir()
            and {item.name for item in path.iterdir()} == {".system"}
            and system.is_symlink()
            and (
                not isinstance(system_target, str)
                or system.resolve(strict=False)
                == Path(system_target).resolve(strict=False)
            )
        ):
            return
        raise SkillCutoverError(
            "Codex cutover backup is absent but committed state is not exact"
        )
    if not backup.is_symlink():
        raise SkillCutoverError("Codex cutover backup is missing before commit")
    backup.unlink()
    descriptor = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _relink_prior(path: Path, backup: Path, target: str) -> None:
    """Put the prior skills link back, from the backup or from its target."""
    if backup.is_symlink():
        backup.rename(path)
    else:
        path.symlink_to(target)


def _restore_is_resumable(path: Path, target: str) -> bool:
    """Is this the wreckage of our own interrupted restore?

    Three crash shapes leave a marker we can finish from:
      * the path gone entirely (died after rmdir),
      * an empty directory (died after .system was unlinked, before rmdir),
      * the prior link already back (died after relinking, before the marker
        was cleared) -- the work is done and only the marker needs clearing.
        Without this last case a retry sees a link it considers user-managed
        and fails an operation that had actually succeeded.
    Anything the user has since put there is not ours to clear.
    """
    if not path.exists() and not path.is_symlink():
        return True
    if path.is_symlink():
        return str(path.readlink()) == target
    if not path.is_dir():
        return False
    return not any(path.iterdir())


def _finish_interrupted_restore(path: Path, target: str) -> bool:
    """Complete a restore that died mid-transition. True if it was finished.

    Only this function knows the prior target (it comes from the receipt), and
    resume_interrupted_cutover cannot help once commit has removed the backup
    symlink. Without this, the leftovers of our own crash read as external
    tampering and the operation could never be retried.
    """
    if _pending_target(path) != target or not _restore_is_resumable(path, target):
        return False
    if path.is_symlink():
        # Already relinked; only the marker outlived the crash.
        _end_transition(path)
        return True
    if path.is_dir():
        # Crashed between unlinking .system and rmdir: an empty shell dir.
        # It can be repopulated between the emptiness check and here, so
        # report that as our own typed error rather than a bare OSError.
        try:
            path.rmdir()
        except OSError as error:
            # Usually ENOTEMPTY (repopulated in the window above), but EACCES
            # and a vanished directory land here too -- name the real errno
            # rather than asserting a cause we did not check.
            raise SkillCutoverError(
                f"could not remove the Codex skills directory {path}: {error}"
            ) from error
    _relink_prior(path, _cutover_backup_path(path), target)
    _end_transition(path)
    return True


def restore_codex_skills(entry: OwnedEntry) -> None:
    if (
        entry.kind != "codex-skill-source"
        or entry.identifier != "codex-shared-skills"
        or not entry.target_path
    ):
        raise SkillCutoverError("receipt does not authorize Codex skill restoration")
    path = Path(entry.target_path)
    try:
        prior = json.loads(entry.previous_checksum or "")
        target = prior["prior_target"]
    except (json.JSONDecodeError, KeyError, TypeError) as error:
        raise SkillCutoverError("receipt lacks the prior Codex skill target") from error
    expected_target = Path(target)
    if not expected_target.is_absolute():
        expected_target = path.parent / expected_target
    resume_interrupted_cutover(path.parents[1])
    if _finish_interrupted_restore(path, target):
        return
    if (
        inspect_codex_skill_source(path.parents[1], expected_target).kind
        != "system-only"
    ):
        raise SkillCutoverError("Codex skills changed after Manifest cutover")
    backup = path.with_name(f".{path.name}.manifest-cutover")
    if backup.exists() and not backup.is_symlink():
        raise SkillCutoverError("Codex cutover backup became unsafe")
    system = path / ".system"
    if system.is_symlink():
        system.unlink()
    # Same two-rename gap as apply, in the other direction: a crash between
    # rmdir and the link recreation leaves the path absent, so mark it in
    # flight. The backup is usually already gone here (commit deletes it), so
    # resume_interrupted_cutover cannot help -- only this function knows the
    # prior target. Recreate the link on failure, and clear the marker only
    # once the link is genuinely back.
    _begin_transition(path, target)
    try:
        path.rmdir()
        _relink_prior(path, backup, target)
    except BaseException:
        if not path.exists() and not path.is_symlink():
            with suppress(OSError):
                _relink_prior(path, backup, target)
        # Clear the marker ONLY if the link is genuinely back. `path.exists()`
        # is NOT that test: it is also true for the leftover directory a failed
        # rmdir leaves behind, and clearing on that strands the tree with no
        # skills and no signal that a later run should restore it.
        #
        # This deliberately does NOT reuse _restore_is_resumable, despite the
        # overlapping symlink case: that helper answers "can a later run finish
        # this?" and so returns True for an ABSENT path and an empty directory.
        # Here those mean both relink attempts failed, and clearing the marker
        # is the one thing we must not do. The two questions look alike and are
        # opposites at exactly the states that matter -- keep them apart.
        if path.is_symlink() and str(path.readlink()) == target:
            _end_transition(path)
        raise
    _end_transition(path)

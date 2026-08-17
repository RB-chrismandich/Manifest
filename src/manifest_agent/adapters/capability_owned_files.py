"""Capability lifecycle responsibility mixin."""

from __future__ import annotations

import hashlib
import os
import secrets
import stat
from collections.abc import Mapping
from contextlib import suppress
from pathlib import Path

from manifest_agent.adapters.capability_fs import _exchange_directory_entries
from manifest_agent.codex_plugin_backup import (
    OwnedFileBackup,
    read_owned_file_backup,
)


def _recover_quarantined_owned_file(
    parent_descriptor: int,
    path: Path,
    quarantine: str,
    error: BaseException,
) -> None:
    """Put the quarantined prior content back, or name where it survived.

    Always raises. The rename into quarantine already committed, so the caller
    looks removed; if the slot was re-occupied concurrently the content cannot
    be swapped back and would otherwise be stranded under a random name that
    nothing ever looks for.
    """
    restored = False
    # Widened past FileNotFoundError deliberately: any probe/rename failure
    # here (EACCES, ENOSPC, read-only remount) is incidental to the ORIGINAL
    # error the caller is trying to report. Letting it escape would replace the
    # real reason with a cleanup-step artifact, unchained. Treat every failure
    # as "could not confirm or restore" and fall through to the decision below.
    try:
        os.stat(path.name, dir_fd=parent_descriptor, follow_symlinks=False)
    except FileNotFoundError:
        with suppress(OSError):
            os.rename(
                quarantine,
                path.name,
                src_dir_fd=parent_descriptor,
                dst_dir_fd=parent_descriptor,
            )
            restored = True
    # This probe is incidental to the ORIGINAL `error` the caller is reporting;
    # letting its own failure escape would replace the real reason with a
    # cleanup artifact, unchained. `restored` stays False, so the decision
    # below still runs and `error` is what the caller ultimately sees.
    # constitution: exempt C-ERR -- swallowing the probe preserves the real cause.
    except OSError:
        pass
    # The raise must stay OUTSIDE the suppress block: `error` may itself be a
    # FileNotFoundError, and suppress would swallow the re-raise and fall
    # through to the "could not roll back" branch below -- reporting stranded
    # content for a slot that was actually restored.
    if restored or not isinstance(error, (OSError, ValueError)):
        raise error
    try:
        os.stat(quarantine, dir_fd=parent_descriptor, follow_symlinks=False)
    except OSError:
        raise error from None
    raise ValueError(
        f"owned file changed concurrently: {path}; prior content was "
        f"retained as {path.parent / quarantine}"
    ) from error


def _revert_published_exchange(
    parent_descriptor: int,
    path: Path,
    temporary: str,
    cause: BaseException | None,
) -> None:
    """Undo a committed exchange, or say plainly that the undo failed.

    The exchange is atomic, but this revert is a second call that can itself
    fail if a concurrent actor touched either entry. Re-raising the revert's
    own error would report a failed write while the unverified content stayed
    live at `path` -- the caller would have no way to learn that. Name that
    state explicitly instead.
    """
    try:
        _exchange_directory_entries(
            parent_descriptor, path.name, parent_descriptor, temporary
        )
    except OSError as revert_error:
        raise ValueError(
            f"owned file left in an unverified published state: {path}; "
            "the replacement content is live and could not be rolled back"
        ) from (cause or revert_error)


class OwnedFileObservationMixin:
    """Observe and validate exact adapter-owned file state."""

    @staticmethod
    def _observable_owned_file(row: Mapping[str, object]) -> dict[str, object]:
        return {key: value for key, value in row.items() if key != "restore"}

    def _observe_owned_file(self, path: Path) -> dict[str, object]:
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
        try:
            descriptor = os.open(path, flags)
        except FileNotFoundError:
            return {"path": str(path), "type": "missing"}
        except OSError as error:
            raise ValueError(f"owned path is unsafe: {path}") from error
        try:
            metadata = os.fstat(descriptor)
            if not stat.S_ISREG(metadata.st_mode):
                raise ValueError(f"owned path is not a regular file: {path}")
            digest = hashlib.sha256()
            for chunk in iter(lambda: os.read(descriptor, 64 * 1024), b""):
                digest.update(chunk)
            return {
                "path": str(path),
                "type": "file",
                "mode": stat.S_IMODE(metadata.st_mode),
                "digest": digest.hexdigest(),
            }
        finally:
            os.close(descriptor)

    def _require_owned_file_state(
        self, path: Path, expected: Mapping[str, object]
    ) -> None:
        if self._observable_owned_file(
            self._observe_owned_file(path)
        ) != self._observable_owned_file(expected):
            raise ValueError(f"owned rollback final state is not exact: {path}")

    def _conditional_owned_file_transition(
        self,
        path: Path,
        expected_current: Mapping[str, object],
        desired: Mapping[str, object],
    ) -> None:
        """Apply one file transition through a conditional link/quarantine/exchange."""
        path.parent.mkdir(parents=True, exist_ok=True)
        parent_flags = (
            os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
        )
        parent_descriptor = os.open(path.parent, parent_flags)
        try:
            current_descriptor = self._open_owned_file_at(parent_descriptor, path.name)
            try:
                observed = self._observe_owned_file_descriptor(path, current_descriptor)
                if self._observable_owned_file(observed) != self._observable_owned_file(
                    expected_current
                ):
                    raise ValueError(f"owned file changed concurrently: {path}")
                self._conditional_owned_file_mutation(
                    parent_descriptor, path, expected_current, desired
                )
                os.fsync(parent_descriptor)
            finally:
                if current_descriptor is not None:
                    os.close(current_descriptor)
        finally:
            os.close(parent_descriptor)
        self._require_owned_file_state(path, desired)


class OwnedFileMutationMixin:
    """Apply descriptor-relative owned-file transitions."""

    def _conditional_owned_file_mutation(
        self,
        parent_descriptor: int,
        path: Path,
        expected_current: Mapping[str, object],
        desired: Mapping[str, object],
    ) -> None:
        desired_type = desired.get("type")
        current_type = expected_current.get("type")
        if desired_type == "missing":
            self._remove_owned_file(
                parent_descriptor, path, expected_current, current_type
            )
            return
        self._restore_owned_file(
            parent_descriptor, path, expected_current, desired, current_type
        )

    def _remove_owned_file(
        self, parent_descriptor, path, expected_current, current_type
    ):
        if current_type == "missing":
            self._owned_file_transition_boundary(path)
            try:
                os.stat(
                    path.name,
                    dir_fd=parent_descriptor,
                    follow_symlinks=False,
                )
            except FileNotFoundError:
                return
            raise ValueError(f"owned file changed concurrently: {path}")
        quarantine = f".{path.name}.manifest-remove-{secrets.token_hex(16)}"
        self._owned_file_transition_boundary(path)
        os.rename(
            path.name,
            quarantine,
            src_dir_fd=parent_descriptor,
            dst_dir_fd=parent_descriptor,
        )
        try:
            captured = self._open_owned_file_at(parent_descriptor, quarantine)
            try:
                observed = self._observe_owned_file_descriptor(path, captured)
            finally:
                if captured is not None:
                    os.close(captured)
            if self._observable_owned_file(observed) != self._observable_owned_file(
                expected_current
            ):
                os.rename(
                    quarantine,
                    path.name,
                    src_dir_fd=parent_descriptor,
                    dst_dir_fd=parent_descriptor,
                )
                raise ValueError(f"owned file changed concurrently: {path}")
            os.unlink(quarantine, dir_fd=parent_descriptor)
        except BaseException as error:
            _recover_quarantined_owned_file(parent_descriptor, path, quarantine, error)

    def _restore_owned_file(
        self, parent_descriptor, path, expected_current, desired, current_type
    ):
        desired_type = desired.get("type")
        restore = desired.get("restore")
        mode = desired.get("mode")
        if (
            desired_type != "file"
            or not isinstance(restore, dict)
            or not isinstance(restore.get("archive"), dict)
            or not isinstance(mode, int)
        ):
            raise ValueError(f"owned rollback backup is incomplete: {path}")
        content = read_owned_file_backup(
            OwnedFileBackup.from_dict(restore["archive"]), self._env
        )
        temporary = f".{path.name}.manifest-write-{secrets.token_hex(16)}"
        descriptor = os.open(
            temporary,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
            mode,
            dir_fd=parent_descriptor,
        )
        try:
            os.fchmod(descriptor, mode)
            with os.fdopen(descriptor, "wb") as stream:
                descriptor = -1
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
            self._publish_owned_file(
                parent_descriptor,
                path,
                temporary,
                expected_current,
                current_type,
            )
        finally:
            if descriptor >= 0:
                os.close(descriptor)
            with suppress(FileNotFoundError):
                os.unlink(temporary, dir_fd=parent_descriptor)

    def _publish_owned_file(
        self, parent_descriptor, path, temporary, expected_current, current_type
    ):
        self._owned_file_transition_boundary(path)
        if current_type == "missing":
            os.link(
                temporary,
                path.name,
                src_dir_fd=parent_descriptor,
                dst_dir_fd=parent_descriptor,
                follow_symlinks=False,
            )
            os.unlink(temporary, dir_fd=parent_descriptor)
            return
        _exchange_directory_entries(
            parent_descriptor, path.name, parent_descriptor, temporary
        )
        # The exchange is already committed here, so EVERY failure below has to
        # swap back. _open_owned_file_at raises (ValueError for a non-regular
        # entry, OSError ELOOP for a symlink under O_NOFOLLOW) when the prior
        # entry was concurrently replaced -- exactly the case this verification
        # exists to catch. Reverting only on the value mismatch left that path
        # reporting BLOCKED while the target file stayed overwritten.
        try:
            captured = self._open_owned_file_at(parent_descriptor, temporary)
            try:
                observed = self._observe_owned_file_descriptor(path, captured)
            finally:
                if captured is not None:
                    os.close(captured)
            changed = self._observable_owned_file(
                observed
            ) != self._observable_owned_file(expected_current)
        except (OSError, ValueError) as error:
            _revert_published_exchange(parent_descriptor, path, temporary, error)
            raise
        if changed:
            _revert_published_exchange(parent_descriptor, path, temporary, None)
            raise ValueError(f"owned file changed concurrently: {path}")
        os.unlink(temporary, dir_fd=parent_descriptor)

    @staticmethod
    def _open_owned_file_at(parent_descriptor: int, name: str) -> int | None:
        try:
            descriptor = os.open(
                name,
                os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0),
                dir_fd=parent_descriptor,
            )
        except FileNotFoundError:
            return None
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode):
            os.close(descriptor)
            raise ValueError("owned path is not a regular file")
        return descriptor

    @staticmethod
    def _observe_owned_file_descriptor(
        path: Path, descriptor: int | None
    ) -> dict[str, object]:
        if descriptor is None:
            return {"path": str(path), "type": "missing"}
        metadata = os.fstat(descriptor)
        digest = hashlib.sha256()
        os.lseek(descriptor, 0, os.SEEK_SET)
        for chunk in iter(lambda: os.read(descriptor, 64 * 1024), b""):
            digest.update(chunk)
        return {
            "path": str(path),
            "type": "file",
            "mode": stat.S_IMODE(metadata.st_mode),
            "digest": digest.hexdigest(),
        }

    @staticmethod
    def _require_same_owned_file_identity(
        parent_descriptor: int,
        name: str,
        current_descriptor: int | None,
        path: Path,
    ) -> None:
        try:
            current = os.stat(name, dir_fd=parent_descriptor, follow_symlinks=False)
        except FileNotFoundError:
            if current_descriptor is None:
                return
            raise ValueError(f"owned file changed concurrently: {path}") from None
        if current_descriptor is None:
            raise ValueError(f"owned file changed concurrently: {path}")
        opened = os.fstat(current_descriptor)
        if (current.st_dev, current.st_ino) != (opened.st_dev, opened.st_ino):
            raise ValueError(f"owned file changed concurrently: {path}")

    def _owned_file_transition_boundary(self, path: Path) -> None:
        """Test seam immediately before the final descriptor-relative mutation."""
        del path


class OwnedFileMixin(OwnedFileObservationMixin, OwnedFileMutationMixin):
    """Compose observation and mutation behavior for owned files."""

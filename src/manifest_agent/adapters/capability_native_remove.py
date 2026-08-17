"""Capability lifecycle responsibility mixin."""

from __future__ import annotations

import os
import secrets
import shutil
from collections.abc import Sequence
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path

from manifest_agent.adapters.capability_fs import _exchange_directory_entries
from manifest_agent.codex_plugin_backup import (
    plugin_tree_sha256,
)
from manifest_agent.models import (
    AdapterPluginState,
    DesiredState,
)
from manifest_agent.process import redact_text


@dataclass
class _NativeRemovalState:
    moved: bool = False


class NativeRemoveMixin:
    """Capability lifecycle methods grouped by one mutation responsibility."""

    def _conditional_native_remove(
        self,
        expected: AdapterPluginState,
        desired: DesiredState,
        command_argv: Sequence[str],
    ) -> str | None:
        """Exchange the exact native tree with an authenticated placeholder."""
        observed = self._exact_reconcile_row(desired, expected)
        if observed.installed_path is None or observed.installed_sha256 is None:
            return self._conditional_pathless_native_remove(
                observed, desired, command_argv
            )
        installed = Path(observed.installed_path)
        if not installed.is_absolute() or installed.name in {"", ".", ".."}:
            raise ValueError(f"native removal path is unsafe for {expected.identifier}")
        parent_flags = (
            os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
        )
        parent_descriptor = os.open(installed.parent, parent_flags)
        quarantine_name = f".{installed.name}.manifest-remove-{secrets.token_hex(16)}"
        quarantined = installed.parent / quarantine_name
        placeholder_descriptor = -1
        state = _NativeRemovalState()
        try:
            os.mkdir(quarantine_name, 0o700, dir_fd=parent_descriptor)
            placeholder_descriptor = os.open(
                quarantine_name,
                parent_flags,
                dir_fd=parent_descriptor,
            )
            self._exchange_native_quarantine(
                parent_descriptor,
                installed.name,
                quarantine_name,
                quarantined,
                observed.installed_sha256,
                placeholder_descriptor,
                expected.identifier,
            )
            state.moved = True
            command = self._run_native_remove_command(command_argv)
            return self._finish_native_remove(
                parent_descriptor,
                installed.name,
                quarantine_name,
                quarantined,
                placeholder_descriptor,
                expected.identifier,
                command.returncode,
                state,
            )
        finally:
            self._cleanup_native_remove(
                parent_descriptor,
                installed.name,
                quarantine_name,
                placeholder_descriptor,
                state.moved,
            )

    def _finish_native_remove(
        self,
        parent_descriptor,
        installed_name,
        quarantine_name,
        quarantined,
        placeholder_descriptor,
        identifier,
        returncode,
        state,
    ):
        if returncode != 0:
            self._restore_native_quarantine(
                parent_descriptor,
                installed_name,
                quarantine_name,
                placeholder_descriptor,
            )
            state.moved = False
            return redact_text(
                f"exact rollback removal exited {returncode} for {identifier}"
            )
        if not self._remove_native_placeholder(
            parent_descriptor, installed_name, placeholder_descriptor
        ):
            shutil.rmtree(quarantined)
            state.moved = False
            os.fsync(parent_descriptor)
            raise ValueError(
                f"native removal path changed concurrently for {identifier}"
            )
        shutil.rmtree(quarantined)
        state.moved = False
        os.fsync(parent_descriptor)
        return None

    def _exchange_native_quarantine(
        self,
        parent_descriptor,
        installed_name,
        quarantine_name,
        quarantined,
        expected_digest,
        placeholder_descriptor,
        identifier,
    ):
        self._native_mutation_boundary(identifier)
        _exchange_directory_entries(
            parent_descriptor,
            installed_name,
            parent_descriptor,
            quarantine_name,
        )
        if plugin_tree_sha256(quarantined) == expected_digest:
            return
        self._restore_native_quarantine(
            parent_descriptor,
            installed_name,
            quarantine_name,
            placeholder_descriptor,
        )
        raise ValueError(
            f"native state changed at the final mutation boundary for {identifier}"
        )

    def _run_native_remove_command(self, command_argv):
        try:
            return self.runner.run(command_argv, env=self._env)
        except Exception as error:
            raise ValueError(f"exact rollback removal failed: {error}") from error

    def _cleanup_native_remove(
        self,
        parent_descriptor,
        installed_name,
        quarantine_name,
        placeholder_descriptor,
        moved,
    ):
        if moved:
            self._restore_native_quarantine(
                parent_descriptor,
                installed_name,
                quarantine_name,
                placeholder_descriptor,
            )
        if placeholder_descriptor >= 0:
            os.close(placeholder_descriptor)
        with suppress(FileNotFoundError):
            os.rmdir(quarantine_name, dir_fd=parent_descriptor)
        os.close(parent_descriptor)

    def _conditional_pathless_native_remove(
        self,
        expected: AdapterPluginState,
        desired: DesiredState,
        command_argv: Sequence[str],
    ) -> str | None:
        """Require a native adapter to supply an atomic compare-and-remove primitive."""
        del desired, command_argv
        raise ValueError(
            f"native removal has no explicit conditional pathless seam for "
            f"{expected.identifier}"
        )

    def _exact_reconcile_row(
        self, desired: DesiredState, expected: AdapterPluginState
    ) -> AdapterPluginState:
        observer = getattr(self, "_native_reconcile_inventory", None)
        if observer is None:
            raise ValueError("exact native reconciliation observation is unavailable")
        observed = tuple(
            observer(
                desired,
                capture_backups=False,
                identifiers={expected.identifier},
            )
        )
        if (
            len(observed) != 1
            or observed[0].identifier != expected.identifier
            or self._reconcile_plugin_payload(observed[0])
            != self._reconcile_plugin_payload(expected)
        ):
            raise ValueError("native state changed at the mutation boundary")
        return observed[0]

    @staticmethod
    def _restore_native_quarantine(
        parent_descriptor: int,
        installed_name: str,
        quarantine_name: str,
        placeholder_descriptor: int,
    ) -> None:
        try:
            installed = os.stat(
                installed_name, dir_fd=parent_descriptor, follow_symlinks=False
            )
        except FileNotFoundError:
            os.rename(
                quarantine_name,
                installed_name,
                src_dir_fd=parent_descriptor,
                dst_dir_fd=parent_descriptor,
            )
            os.fsync(parent_descriptor)
            return
        placeholder = os.fstat(placeholder_descriptor)
        if (installed.st_dev, installed.st_ino) == (
            placeholder.st_dev,
            placeholder.st_ino,
        ):
            _exchange_directory_entries(
                parent_descriptor,
                installed_name,
                parent_descriptor,
                quarantine_name,
            )
            os.rmdir(quarantine_name, dir_fd=parent_descriptor)
            os.fsync(parent_descriptor)
            return
        raise ValueError("native removal rollback path changed concurrently")

    @staticmethod
    def _remove_native_placeholder(
        parent_descriptor: int, installed_name: str, placeholder_descriptor: int
    ) -> bool:
        try:
            installed = os.stat(
                installed_name, dir_fd=parent_descriptor, follow_symlinks=False
            )
        except FileNotFoundError:
            return True
        placeholder = os.fstat(placeholder_descriptor)
        if (installed.st_dev, installed.st_ino) != (
            placeholder.st_dev,
            placeholder.st_ino,
        ):
            return False
        os.rmdir(installed_name, dir_fd=parent_descriptor)
        return True

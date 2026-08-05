"""Coordinator mutation lock and atomic-receipt interruption behavior."""

from __future__ import annotations

import multiprocessing
from pathlib import Path

import pytest

import manifest_agent.state as state
from manifest_agent.models import HarnessReceipt, InstallationReceipt
from manifest_agent.state import StateError, installation_lock, write_receipt_atomic


def _receipt() -> InstallationReceipt:
    return InstallationReceipt(
        schema_version=1,
        coordinator_version="test",
        release_version="1.0.0",
        source_commit="a" * 40,
        source_dirty=False,
        archive_sha256="b" * 64,
        bundle_checksums={"manifest-docs": "c" * 64},
        selected_optional=(),
        harnesses={
            "claude": HarnessReceipt(
                "claude", "test", "1", (), (), {}, True
            )
        },
    )


def _hold_lifecycle_lock(
    lock_path: str, entered: multiprocessing.synchronize.Event, release: multiprocessing.synchronize.Event, result: multiprocessing.queues.Queue
) -> None:
    """Run one lifecycle-shaped operation in a separate process."""
    try:
        with installation_lock(Path(lock_path)):
            result.put("READY")
            entered.set()
            release.wait(timeout=10)
    except StateError:
        result.put("BLOCKED")


def test_second_concurrent_operation_cannot_acquire_machine_lock(tmp_path: Path) -> None:
    lock_path = tmp_path / "state/install.lock"

    with (
        installation_lock(lock_path),
        pytest.raises(StateError, match="already in progress"),
        installation_lock(lock_path),
    ):
        pass


@pytest.mark.parametrize("operation", ("install", "migrate", "reconcile-apply"))
def test_concurrent_lifecycle_operations_have_one_process_lock_winner(
    tmp_path: Path, operation: str
) -> None:
    """Install, migration, and repair share the same inter-process lock."""
    context = multiprocessing.get_context("fork")
    entered = context.Event()
    release = context.Event()
    results = context.Queue()
    lock_path = tmp_path / "state/install.lock"
    first = context.Process(
        target=_hold_lifecycle_lock,
        args=(str(lock_path), entered, release, results),
    )
    first.start()
    assert entered.wait(timeout=5), f"{operation} worker did not acquire lock"
    second = context.Process(
        target=_hold_lifecycle_lock,
        args=(str(lock_path), context.Event(), context.Event(), results),
    )
    second.start()
    second.join(timeout=5)
    assert second.exitcode == 0
    assert results.get(timeout=2) == "READY"
    assert results.get(timeout=2) == "BLOCKED"
    release.set()
    first.join(timeout=5)
    assert first.exitcode == 0


def test_interrupted_replace_leaves_prior_receipt_and_removes_temp_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    destination = tmp_path / "state/installation.json"
    destination.parent.mkdir(parents=True)
    destination.write_bytes(b'{"previous": true}\n')

    def interrupted_replace(source: Path, target: Path) -> None:
        del source, target
        raise OSError("simulated interruption before replace")

    monkeypatch.setattr(state.os, "replace", interrupted_replace)
    with pytest.raises(StateError, match="write receipt atomically"):
        write_receipt_atomic(destination, _receipt())

    assert destination.read_bytes() == b'{"previous": true}\n'
    assert not list(destination.parent.glob(".installation.json.*.tmp"))

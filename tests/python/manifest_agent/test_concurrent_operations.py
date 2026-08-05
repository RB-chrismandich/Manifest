"""Coordinator mutation lock and atomic-receipt interruption behavior."""

from __future__ import annotations

import multiprocessing
import os
from contextlib import contextmanager
from pathlib import Path

import pytest

import manifest_agent.state as state
from manifest_agent.adapters.base import Detection
from manifest_agent.models import (
    HarnessReceipt,
    HarnessResult,
    InstallationReceipt,
    MarketplaceSource,
    MarketplaceSourceKind,
    ResultState,
)
from manifest_agent.release import ResolvedRelease
from manifest_agent.service import ManifestService
from manifest_agent.state import StateError, installation_lock, write_receipt_atomic
from tests.python.manifest_agent.test_service_install import (
    fake_contracts,
    fake_release,
)


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


class _WorkerAdapter:
    adapter_version = "test"
    name = "claude"

    def detect(self) -> Detection:
        return Detection(True, "fixture", "1.0")

    def install(self, _desired) -> HarnessResult:
        return HarnessResult("claude", ResultState.READY, (), {})

    def inspect(self, _desired) -> HarnessResult:
        return HarnessResult("claude", ResultState.READY, (), {})

    def uninstall(self, _receipt) -> HarnessResult:
        return HarnessResult("claude", ResultState.READY, (), {})

    def snapshot_paths(self, _desired) -> tuple[Path, ...]:
        return ()


@contextmanager
def _worker_lock(path: Path, entered, release, writer: Path, operation: str, hold: bool):
    with installation_lock(path):
        with writer.open("a", encoding="utf-8") as stream:
            stream.write(f"{operation}\n")
        entered.set()
        if hold:
            assert release.wait(timeout=10)
        yield path


def _service_lifecycle_worker(
    operation: str,
    root: str,
    release_root: str,
    entered,
    release,
    results,
    hold: bool,
) -> None:
    """Invoke a real service operation under the shared lifecycle lock."""
    worker_root = Path(root)
    os.environ["XDG_STATE_HOME"] = str(worker_root / "xdg-state")
    resolved = ResolvedRelease(
        "1.0.0",
        "a" * 40,
        "fixture-release",
        MarketplaceSource(MarketplaceSourceKind.LOCAL, release_root, None),
        Path(release_root),
        "https://example.invalid/Manifest",
        False,
        "b" * 64,
    )
    receipt_path = worker_root / "state" / "installation.json"
    writer = worker_root / "writers.log"
    service = ManifestService(
        source=resolved.release_root,
        harnesses=("claude",),
        adapters={"claude": _WorkerAdapter()},
        receipt_path=receipt_path,
        release_resolver=lambda _selector: resolved,
        contract_loader=lambda _root: fake_contracts(),
        capability_planner=lambda _contracts, _selected: object(),
        lock_factory=lambda path: _worker_lock(
            path, entered, release, writer, operation, hold
        ),
    )
    operation_result = {
        "install": service.install,
        "migrate": service.migrate,
        "reconcile-apply": lambda: service.reconcile(apply=True),
    }[operation]()
    results.put(operation_result.state.value)


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
    """Install, migration, and repair share the real service lifecycle lock."""
    context = multiprocessing.get_context("fork")
    entered = context.Event()
    release = context.Event()
    results = context.Queue()
    resolved = fake_release(tmp_path / "release-source")
    first = context.Process(
        target=_service_lifecycle_worker,
        args=(operation, str(tmp_path), str(resolved.release_root), entered, release, results, True),
    )
    first.start()
    assert entered.wait(timeout=5), f"{operation} worker did not acquire lock"
    second = context.Process(
        target=_service_lifecycle_worker,
        args=(operation, str(tmp_path), str(resolved.release_root), context.Event(), context.Event(), results, False),
    )
    second.start()
    second.join(timeout=5)
    assert second.exitcode == 0
    assert results.get(timeout=2) == "BLOCKED"
    release.set()
    first.join(timeout=5)
    assert first.exitcode == 0
    assert results.get(timeout=2) in {"READY", "BLOCKED"}
    assert (tmp_path / "writers.log").read_text(encoding="utf-8").splitlines() == [
        operation
    ]


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

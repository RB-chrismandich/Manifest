"""Receipt-authorized uninstall orchestration tests."""

from __future__ import annotations

from contextlib import contextmanager

import pytest

import manifest_agent.service as service_module
import manifest_agent.service_state as service_state_module
from manifest_agent.models import OwnedEntry, ResultState
from manifest_agent.state import StateError, read_receipt
from tests.python.manifest_agent.test_service_install import (
    FakeAdapter,
    harness_result,
    make_service_factory,
)


@pytest.fixture
def service_factory(tmp_path):
    return make_service_factory(tmp_path)


def test_uninstall_uses_receipt_not_directory_globs(service_factory):
    owned = OwnedEntry("plugin", "manifest-owned", "manifest")
    claude = FakeAdapter("claude", harness_result("claude", owned_entries=(owned,)))
    service = service_factory({"claude": claude}, harnesses=("claude",))
    service.install()
    claude.calls.clear()

    report = service.uninstall()

    assert report.state is ResultState.READY
    assert claude.uninstall_receipts[0].owned_entries == (owned,)
    assert all(
        entry.identifier != "foreign-plugin"
        for entry in claude.uninstall_receipts[0].owned_entries
    )
    assert read_receipt(service.receipt_path) is None


def test_uninstall_runs_in_reverse_harness_order(service_factory):
    events: list[str] = []

    class OrderedAdapter(FakeAdapter):
        def uninstall(self, receipt):
            events.append(self.name)
            return super().uninstall(receipt)

    adapters = {
        name: OrderedAdapter(name, harness_result(name)) for name in ("claude", "codex")
    }
    service = service_factory(adapters)
    service.install()
    service.uninstall()

    assert events == ["codex", "claude"]


def test_uninstall_retains_failed_harness_receipt(service_factory):
    claude = FakeAdapter("claude", harness_result("claude"))
    codex = FakeAdapter("codex", harness_result("codex"))
    service = service_factory({"claude": claude, "codex": codex})
    service.install()
    codex.result = harness_result(
        "codex", ResultState.BLOCKED, errors=("native removal failed",)
    )

    report = service.uninstall()

    assert report.state is ResultState.BLOCKED
    receipt = read_receipt(service.receipt_path)
    assert receipt is not None
    assert tuple(receipt.harnesses) == ("codex",)


def test_uninstall_only_selected_harness_preserves_other_receipts(service_factory):
    claude = FakeAdapter("claude", harness_result("claude"))
    codex = FakeAdapter("codex", harness_result("codex"))
    service = service_factory({"claude": claude, "codex": codex})
    service.install()
    service.harnesses = ("claude",)

    report = service.uninstall()

    assert report.state is ResultState.READY
    receipt = read_receipt(service.receipt_path)
    assert receipt is not None
    assert tuple(receipt.harnesses) == ("codex",)
    assert "uninstall" not in codex.calls


def test_uninstall_harness_all_blocks_for_missing_cli(service_factory):
    claude = FakeAdapter("claude", harness_result("claude"))
    codex = FakeAdapter("codex", harness_result("codex"))
    service = service_factory({"claude": claude, "codex": codex})
    service.install()
    service.harnesses = ("all",)
    codex.detection.present = False
    codex.detection.executable = None
    codex.detection.version = None
    codex.detection.reason = "codex CLI not present"

    report = service.uninstall()

    assert report.state is ResultState.BLOCKED
    receipt = read_receipt(service.receipt_path)
    assert receipt is not None
    assert tuple(receipt.harnesses) == ("codex",)


def test_uninstall_locks_before_reading_receipt(service_factory, monkeypatch):
    claude = FakeAdapter("claude", harness_result("claude"))
    service = service_factory({"claude": claude}, harnesses=("claude",))
    service.install()
    events = []
    real_read = service_module.read_receipt

    @contextmanager
    def recording_lock(path=None):
        events.append("lock")
        yield path

    def recording_read(path=None):
        events.append("read")
        return real_read(path)

    service.lock_factory = recording_lock
    monkeypatch.setattr(service_module, "read_receipt", recording_read)

    service.uninstall()

    assert events[:2] == ["lock", "read"]


def test_uninstall_persists_each_success_before_later_adapter(service_factory):
    observed_receipt_keys = []
    codex = FakeAdapter("codex", harness_result("codex"))

    class FailingClaude(FakeAdapter):
        def uninstall(self, receipt):
            current = read_receipt(service.receipt_path)
            assert current is not None
            observed_receipt_keys.append(tuple(current.harnesses))
            return harness_result(
                "claude", ResultState.BLOCKED, errors=("removal failed",)
            )

    claude = FailingClaude("claude", harness_result("claude"))
    service = service_factory({"claude": claude, "codex": codex})
    service.install()

    report = service.uninstall()

    assert report.state is ResultState.BLOCKED
    assert observed_receipt_keys == [("claude",)]


def test_uninstall_retries_progress_write_before_next_removal(
    service_factory, monkeypatch
):
    writes = []
    real_write = service_state_module.write_receipt_atomic
    codex = FakeAdapter("codex", harness_result("codex"))

    class ObservingClaude(FakeAdapter):
        def uninstall(self, receipt):
            current = read_receipt(service.receipt_path)
            assert current is not None
            assert tuple(current.harnesses) == ("claude",)
            return harness_result(
                "claude", ResultState.BLOCKED, errors=("removal failed",)
            )

    claude = ObservingClaude("claude", harness_result("claude"))
    service = service_factory({"claude": claude, "codex": codex})
    service.install()

    def flaky_write(path, receipt):
        writes.append(tuple(receipt.harnesses))
        if len(writes) == 1:
            raise StateError("transient write failure")
        return real_write(path, receipt)

    monkeypatch.setattr(service_state_module, "write_receipt_atomic", flaky_write)

    report = service.uninstall()

    assert report.state is ResultState.BLOCKED
    assert writes[:2] == [("claude",), ("claude",)]

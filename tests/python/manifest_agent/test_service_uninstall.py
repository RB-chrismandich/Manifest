"""Receipt-authorized uninstall orchestration tests."""

from __future__ import annotations

import pytest

from manifest_agent.models import OwnedEntry, ResultState
from manifest_agent.state import read_receipt
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

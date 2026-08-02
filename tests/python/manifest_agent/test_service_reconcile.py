"""Read-only reconcile and selective repair tests."""

from __future__ import annotations

from contextlib import contextmanager

import pytest

import manifest_agent.service as service_module
from manifest_agent.models import ResultState
from manifest_agent.state import read_receipt
from tests.python.manifest_agent.test_service_install import (
    FakeAdapter,
    harness_result,
    make_service_factory,
)


@pytest.fixture
def service_factory(tmp_path):
    return make_service_factory(tmp_path)


def test_reconcile_is_read_only_by_default(service_factory):
    claude = FakeAdapter("claude", harness_result("claude"))
    service = service_factory({"claude": claude}, harnesses=("claude",))
    service.install()
    claude.calls.clear()

    report = service.reconcile(apply=False)

    assert report.state is ResultState.READY
    assert service.runner.calls == []
    assert claude.calls == ["detect", "inspect"]


def test_reconcile_apply_repairs_only_drifted_or_degraded(service_factory):
    claude = FakeAdapter("claude", harness_result("claude"))
    codex = FakeAdapter("codex", harness_result("codex"))
    service = service_factory({"claude": claude, "codex": codex})
    service.install()
    claude.calls.clear()
    codex.calls.clear()
    codex.inspection = harness_result("codex", ResultState.DRIFTED)

    service.reconcile(apply=True)

    assert claude.calls == ["detect", "inspect"]
    assert codex.calls == ["detect", "inspect", "install", "inspect"]


def test_reconcile_apply_never_repairs_blocked_harness(service_factory):
    claude = FakeAdapter("claude", harness_result("claude"))
    service = service_factory({"claude": claude}, harnesses=("claude",))
    service.install()
    claude.calls.clear()
    claude.inspection = harness_result(
        "claude", ResultState.BLOCKED, errors=("authentication required",)
    )

    report = service.reconcile(apply=True)

    assert report.state is ResultState.BLOCKED
    assert claude.calls == ["detect", "inspect"]


def test_reconcile_identity_mismatch_is_drift_and_updates_receipt_on_apply(
    service_factory,
):
    claude = FakeAdapter("claude", harness_result("claude"))
    service = service_factory({"claude": claude}, harnesses=("claude",))
    service.install()
    receipt = read_receipt(service.receipt_path)
    assert receipt is not None
    old_resolver = service.release_resolver
    old_release = old_resolver(service.source)
    service.release_resolver = lambda selector: type(old_release)(
        "1.0.1",
        "c" * 40,
        "new-release",
        old_release.marketplace_source,
        old_release.release_root,
        old_release.repository_url,
        False,
        "d" * 64,
    )
    claude.calls.clear()

    report = service.reconcile(apply=False)

    assert report.harnesses["claude"].state is ResultState.DRIFTED
    assert "install" not in claude.calls


def test_reconcile_default_only_inspects_receipt_owned_harnesses(service_factory):
    claude = FakeAdapter("claude", harness_result("claude"))
    codex = FakeAdapter("codex", harness_result("codex"))
    service = service_factory({"claude": claude, "codex": codex}, harnesses=("codex",))
    service.install()
    service.harnesses = ()
    claude.calls.clear()
    codex.calls.clear()

    report = service.reconcile(apply=False)

    assert tuple(report.harnesses) == ("codex",)
    assert claude.calls == []
    assert codex.calls == ["detect", "inspect"]


def test_reconcile_apply_does_not_acquire_explicit_unowned_harness(
    service_factory,
):
    claude = FakeAdapter("claude", harness_result("claude"))
    codex = FakeAdapter("codex", harness_result("codex"))
    service = service_factory({"claude": claude, "codex": codex}, harnesses=("codex",))
    service.install()
    service.harnesses = ("claude",)
    claude.inspection = harness_result("claude", ResultState.DRIFTED)
    claude.calls.clear()

    report = service.reconcile(apply=True)

    assert report.harnesses["claude"].state is ResultState.DRIFTED
    assert claude.calls == ["detect", "inspect"]
    receipt = read_receipt(service.receipt_path)
    assert receipt is not None
    assert tuple(receipt.harnesses) == ("codex",)


def test_reconcile_reports_missing_receipt_owned_cli_as_blocked(service_factory):
    codex = FakeAdapter("codex", harness_result("codex"))
    service = service_factory({"codex": codex}, harnesses=("codex",))
    service.install()
    service.harnesses = ()
    codex.detection.present = False
    codex.detection.executable = None
    codex.detection.version = None
    codex.detection.reason = "codex CLI not present"

    report = service.reconcile(apply=False)

    assert report.state is ResultState.BLOCKED
    assert report.harnesses["codex"].state is ResultState.BLOCKED
    assert report.notes == ()


def test_reconcile_apply_locks_before_reading_receipt(service_factory, monkeypatch):
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

    service.reconcile(apply=True)

    assert events[:2] == ["lock", "read"]

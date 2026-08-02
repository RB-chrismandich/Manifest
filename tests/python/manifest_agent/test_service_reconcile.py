"""Read-only reconcile and selective repair tests."""

from __future__ import annotations

import pytest

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

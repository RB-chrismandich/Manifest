"""Read-only reconcile and selective repair tests."""

from __future__ import annotations

import json
from contextlib import contextmanager
from dataclasses import replace

import pytest

import manifest_agent.service as service_module
from manifest_agent.models import CatalogPlugin, HarnessResult, ResultState
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


def test_reconcile_reports_and_repairs_owned_adhd_diagnostic(
    service_factory, tmp_path, monkeypatch
):
    class DiagnosticAdapter(FakeAdapter):
        def probe_adhd_hook(self, desired):
            del desired
            self.calls.append("probe")
            return HarnessResult(
                "codex",
                ResultState.READY,
                (),
                {"addon:manifest-i-have-adhd:session-start": "verified"},
            )

    codex = DiagnosticAdapter("codex", harness_result("codex"))
    service = service_factory({"codex": codex}, harnesses=("codex",))
    assert service.install().state is ResultState.READY
    desired, error = service._desired_state()
    assert error is None and desired is not None
    desired = replace(
        desired,
        catalog_plugins=(
            *desired.catalog_plugins,
            CatalogPlugin(
                "manifest-i-have-adhd", "0.1.0", "./plugins/manifest-i-have-adhd"
            ),
        ),
    )
    service._desired_state = lambda receipt_release=None: (desired, None)
    state = tmp_path / "runtime-state"
    diagnostic = state / "manifest/diagnostics/manifest-i-have-adhd.json"
    diagnostic.parent.mkdir(parents=True)
    diagnostic.write_text(
        json.dumps(
            [
                {
                    "plugin": "manifest-i-have-adhd",
                    "version": "0.1.0",
                    "harness": "native",
                    "reason": "missing-guidance",
                }
            ]
        )
    )
    monkeypatch.setenv("XDG_STATE_HOME", str(state))
    codex.calls.clear()

    observed = service.reconcile(apply=False)
    repaired = service.reconcile(apply=True)

    assert observed.harnesses["codex"].state is ResultState.DEGRADED
    assert repaired.state is ResultState.READY
    assert "probe" in codex.calls
    assert not diagnostic.exists()


def test_reconcile_apply_unowned_v2_target_does_not_rewrite_v1_receipt(
    service_factory,
):
    claude = FakeAdapter("claude", harness_result("claude"))
    codex = FakeAdapter("codex", harness_result("codex"))
    service = service_factory({"claude": claude, "codex": codex}, harnesses=("codex",))
    service.install()
    before = service.receipt_path.read_bytes()
    previous = read_receipt(service.receipt_path)
    assert previous is not None
    old_release = service.release_resolver(service.source)
    service.release_resolver = lambda selector: type(old_release)(
        "2.0.0",
        "c" * 40,
        "v2",
        old_release.marketplace_source,
        old_release.release_root,
        old_release.repository_url,
        False,
        "d" * 64,
    )
    service.harnesses = ("claude",)
    claude.calls.clear()

    report = service.reconcile(apply=True)

    assert report.state is ResultState.DRIFTED
    assert claude.calls == ["detect", "inspect"]
    assert service.receipt_path.read_bytes() == before
    assert read_receipt(service.receipt_path) == previous


def test_reconcile_apply_blocks_partial_owned_release_identity_change(
    service_factory,
):
    claude = FakeAdapter("claude", harness_result("claude"))
    codex = FakeAdapter("codex", harness_result("codex"))
    service = service_factory({"claude": claude, "codex": codex})
    service.install()
    before = service.receipt_path.read_bytes()
    old_release = service.release_resolver(service.source)
    service.release_resolver = lambda selector: type(old_release)(
        "2.0.0",
        "c" * 40,
        "v2",
        old_release.marketplace_source,
        old_release.release_root,
        old_release.repository_url,
        False,
        "d" * 64,
    )
    service.harnesses = ("claude",)
    claude.calls.clear()
    codex.calls.clear()

    report = service.reconcile(apply=True)

    assert report.state is ResultState.BLOCKED
    assert any("full reconcile or migration" in error for error in report.errors)
    assert "install" not in claude.calls
    assert codex.calls == []
    assert service.receipt_path.read_bytes() == before


def test_reconcile_apply_partial_same_identity_preserves_other_receipt(
    service_factory,
):
    class RepairingAdapter(FakeAdapter):
        def install(self, desired):
            self.inspection = harness_result(self.name)
            return super().install(desired)

    claude = RepairingAdapter("claude", harness_result("claude"))
    codex = FakeAdapter("codex", harness_result("codex"))
    service = service_factory({"claude": claude, "codex": codex})
    service.install()
    before = read_receipt(service.receipt_path)
    assert before is not None
    service.harnesses = ("claude",)
    claude.inspection = harness_result("claude", ResultState.DRIFTED)

    report = service.reconcile(apply=True)

    assert report.state is ResultState.READY
    after = read_receipt(service.receipt_path)
    assert after is not None
    assert after.release_version == before.release_version
    assert after.source_commit == before.source_commit
    assert after.bundle_checksums == before.bundle_checksums
    assert after.harnesses["codex"] == before.harnesses["codex"]
    assert after.harnesses["claude"].verified is True


def test_reconcile_apply_full_scope_can_advance_release_identity(service_factory):
    claude = FakeAdapter("claude", harness_result("claude"))
    codex = FakeAdapter("codex", harness_result("codex"))
    service = service_factory({"claude": claude, "codex": codex})
    service.install()
    old_release = service.release_resolver(service.source)
    service.release_resolver = lambda selector: type(old_release)(
        "2.0.0",
        "c" * 40,
        "v2",
        old_release.marketplace_source,
        old_release.release_root,
        old_release.repository_url,
        False,
        "d" * 64,
    )
    service.harnesses = ()
    claude.calls.clear()
    codex.calls.clear()

    report = service.reconcile(apply=True)

    assert report.state is ResultState.READY
    assert "install" in claude.calls
    assert "install" in codex.calls
    receipt = read_receipt(service.receipt_path)
    assert receipt is not None
    assert receipt.release_version == "2.0.0"
    assert receipt.source_commit == "c" * 40
    assert all(harness.verified for harness in receipt.harnesses.values())

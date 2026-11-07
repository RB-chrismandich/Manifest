"""Guards preventing receipt rewrites while a bootstrap-sync journal is pending."""

from __future__ import annotations

from pathlib import Path

import pytest

from manifest_agent.bootstrap_sync import (
    HarnessMutationCheckpoint,
    ReconciliationSaga,
    _journal_path,
    _serialize_handle,
    _write_journal,
)
from manifest_agent.models import ResultState
from manifest_agent.state import read_receipt, receipt_digest
from tests.python.manifest_agent.test_service_install import (
    FakeAdapter,
    harness_result,
    make_service_factory,
)


@pytest.fixture
def service_factory(tmp_path: Path):
    """Create isolated ManifestService instances rooted in tmp_path."""
    return make_service_factory(tmp_path)


def _run_mutation(service, operation: str):
    if operation == "install":
        return service.install()
    if operation == "update":
        return service.reconcile(apply=True)
    if operation == "uninstall":
        return service.uninstall()
    raise AssertionError(f"unknown operation: {operation}")


@pytest.mark.parametrize("operation", ("install", "update", "uninstall"))
def test_lifecycle_mutations_refuse_pending_non_empty_bootstrap_journal(
    service_factory, operation: str
) -> None:
    """Install, update, and uninstall must block when a non-empty journal exists."""
    claude = FakeAdapter("claude", harness_result("claude"))
    codex = FakeAdapter("codex", harness_result("codex"))
    service = service_factory({"claude": claude, "codex": codex})
    assert service.install().state is ResultState.READY
    previous = read_receipt(service.receipt_path)
    assert previous is not None
    desired, error = service._desired_state()
    assert error is None and desired is not None
    handle = claude.prepare_reconcile(previous.harnesses["claude"], desired, desired)
    journal = _journal_path(service.receipt_path)
    _write_journal(
        journal,
        ReconciliationSaga(
            "prepared",
            "codex",
            harness_mutations=(
                HarnessMutationCheckpoint(
                    "claude", "prepared", _serialize_handle(handle)
                ),
            ),
            prior_receipt_digest=receipt_digest(previous),
            target_identity="a" * 64,
        ),
    )
    codex.inspection = harness_result("codex", ResultState.DRIFTED)
    receipt_before = service.receipt_path.read_bytes()
    journal_before = journal.read_bytes()
    claude.calls.clear()
    codex.calls.clear()

    result = _run_mutation(service, operation)

    assert result.state is ResultState.BLOCKED
    assert any("manifest bootstrap-sync" in err for err in result.errors)
    assert service.receipt_path.read_bytes() == receipt_before
    assert journal.read_bytes() == journal_before
    assert "install" not in claude.calls
    assert "install" not in codex.calls
    assert "uninstall" not in claude.calls
    assert "uninstall" not in codex.calls


@pytest.mark.parametrize("operation", ("install", "update", "uninstall"))
def test_empty_prepared_bootstrap_journal_does_not_block_lifecycle_mutations(
    service_factory, operation: str
) -> None:
    """An empty prepared bootstrap journal must not block install, update, or uninstall."""

    class HealingAdapter(FakeAdapter):
        def install(self, desired):
            self.inspection = self.result
            return super().install(desired)

    claude = FakeAdapter("claude", harness_result("claude"))
    codex = HealingAdapter("codex", harness_result("codex"))
    service = service_factory({"claude": claude, "codex": codex})
    assert service.install().state is ResultState.READY
    previous = read_receipt(service.receipt_path)
    assert previous is not None
    journal = _journal_path(service.receipt_path)
    _write_journal(
        journal,
        ReconciliationSaga(
            "prepared",
            "codex",
            prior_receipt_digest=receipt_digest(previous),
            target_identity="a" * 64,
        ),
    )
    if operation == "update":
        codex.inspection = harness_result("codex", ResultState.DRIFTED)

    result = _run_mutation(service, operation)

    assert result.state is ResultState.READY, result.errors


def test_first_install_refuses_pending_non_empty_journal_without_prior_receipt(
    service_factory,
) -> None:
    """First-install crash journal must also block plain install from writing a receipt."""
    codex = FakeAdapter("codex", harness_result("codex"))
    service = service_factory({"codex": codex}, harnesses=("codex",))
    journal = _journal_path(service.receipt_path)
    journal.parent.mkdir(parents=True, exist_ok=True)
    _write_journal(
        journal,
        ReconciliationSaga(
            "cutover-complete",
            "codex",
            cutover_entry={
                "kind": "codex-skill-source",
                "identifier": "codex-shared-skills",
                "ownership_marker": "manifest",
                "target_path": "/tmp/skills",
                "previous_checksum": '{"prior_target":"/tmp/source"}',
            },
            target_identity="a" * 64,
        ),
    )
    codex.calls.clear()

    result = service.install()

    assert result.state is ResultState.BLOCKED
    assert any("manifest bootstrap-sync" in err for err in result.errors)
    assert not service.receipt_path.exists()
    assert "install" not in codex.calls

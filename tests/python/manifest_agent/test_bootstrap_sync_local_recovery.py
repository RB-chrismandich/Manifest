"""Receipt-pinned local checkout saga recovery tests."""

from __future__ import annotations

import subprocess
from dataclasses import replace
from pathlib import Path

import pytest

import manifest_agent.bootstrap_sync as bootstrap_module
from manifest_agent.bootstrap_sync import (
    HarnessMutationCheckpoint,
    ReconciliationSaga,
    _serialize_handle,
    _write_journal,
)
from manifest_agent.models import ResultState
from manifest_agent.state import read_receipt, receipt_digest, write_receipt_atomic
from tests.python.manifest_agent._bootstrap_sync_helpers import legacy_skill_home
from tests.python.manifest_agent._bootstrap_sync_local_helpers import (
    _installed_local_service,
)
from tests.python.manifest_agent.test_service_install import make_service_factory


@pytest.fixture
def service_factory(tmp_path: Path):
    return make_service_factory(tmp_path)


@pytest.mark.parametrize(
    "identity_drift",
    [
        "none",
        "release_version",
        "source_commit",
        "source_dirty",
        "archive_sha256",
        "selected_optional",
    ],
)
@pytest.mark.parametrize("mutation_harness", ["codex", "claude"])
def test_local_commit_move_recovers_verified_mutation_before_reapplying(
    mutation_harness: str,
    identity_drift: str,
    service_factory,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    case = _prepare_local_recovery(
        mutation_harness, identity_drift, service_factory, tmp_path, monkeypatch
    )
    service, previous, desired, adapter, journal, journal_before = case

    result = service.bootstrap_sync()
    receipt = read_receipt(service.receipt_path)

    if identity_drift != "none":
        _assert_recovery_rejected(result, service, previous, journal, journal_before)
        return
    _assert_recovery_completed(result, receipt, desired, adapter, journal)


def _prepare_local_recovery(
    mutation_harness, identity_drift, service_factory, tmp_path, monkeypatch
):
    service, repo, claude, codex = _installed_local_service(
        service_factory, tmp_path, monkeypatch
    )
    previous = _receipt_with_legacy_checksums(service, identity_drift)
    prior_desired, error = service._desired_state()
    assert error is None and prior_desired is not None
    _advance_local_source(repo)
    reconstructed_prior, error = service._desired_state(
        prior_desired.release_version,
        exact_release=True,
        source_commit=prior_desired.source_commit,
        source_checkout=service.source,
    )
    assert error is None and reconstructed_prior is not None
    desired, error = service._desired_state()
    assert error is None and desired is not None
    assert desired.source_commit != previous.source_commit
    adapter = {"codex": codex, "claude": claude}[mutation_harness]
    rollback_prior = []
    original_rollback = adapter.rollback_reconcile

    def record_rollback(handle, prior):
        rollback_prior.append(
            (prior.release_version, prior.source_commit, Path(prior.release_root))
        )
        return original_rollback(handle, prior)

    adapter.rollback_reconcile = record_rollback
    journal, journal_before = _record_verified_mutation(
        service, previous, prior_desired, desired, adapter, mutation_harness
    )
    service.harnesses = ("codex",)
    legacy_skill_home(tmp_path, monkeypatch)
    adapter.calls.clear()
    adapter.rollback_prior = rollback_prior
    adapter.expected_prior = (
        reconstructed_prior.release_version,
        reconstructed_prior.source_commit,
        Path(reconstructed_prior.release_root),
    )
    return service, previous, desired, adapter, journal, journal_before


def _receipt_with_legacy_checksums(service, identity_drift):
    previous = read_receipt(service.receipt_path)
    assert previous is not None
    legacy_checksums = dict(previous.bundle_checksums)
    legacy_checksums["manifest-workspace"] = "0" * 64
    fields = {"bundle_checksums": legacy_checksums}
    if identity_drift != "none":
        fields[identity_drift] = {
            "release_version": f"local-{'f' * 12}",
            "source_commit": "f" * 40,
            "source_dirty": True,
            "archive_sha256": "f" * 64,
            "selected_optional": ("fixture-only",),
        }[identity_drift]
    write_receipt_atomic(service.receipt_path, replace(previous, **fields))
    receipt = read_receipt(service.receipt_path)
    assert receipt is not None
    return receipt


def _advance_local_source(repo: Path) -> None:
    (repo / "plugins" / "manifest-workspace" / "payload.txt").write_text(
        "new committed release\n", encoding="utf-8"
    )
    for args in (
        ("add", "plugins/manifest-workspace/payload.txt"),
        ("commit", "-m", "advance local release"),
    ):
        subprocess.run(
            ("git", "-C", str(repo), *args),
            check=True,
            capture_output=True,
        )


def _record_verified_mutation(
    service, previous, prior_desired, desired, adapter, mutation_harness
):
    handle = adapter.prepare_reconcile(
        previous.harnesses[mutation_harness], prior_desired, desired
    )
    journal = bootstrap_module._journal_path(service.receipt_path)
    _write_journal(
        journal,
        ReconciliationSaga(
            "harness-convergence",
            "codex",
            harness_mutations=(
                HarnessMutationCheckpoint(
                    mutation_harness, "verified", _serialize_handle(handle)
                ),
            ),
            prior_receipt_digest=receipt_digest(previous),
            target_identity=bootstrap_module._target_identity(desired),
        ),
    )
    return journal, journal.read_text(encoding="utf-8")


def _assert_recovery_rejected(result, service, previous, journal, journal_before):
    error = result.harnesses["codex"].errors[0]
    assert result.state is ResultState.BLOCKED
    assert "prior release is unavailable for cross-harness compensation:" in error
    assert journal.read_text(encoding="utf-8") == journal_before
    assert read_receipt(service.receipt_path) == previous


def _assert_recovery_completed(result, receipt, desired, adapter, journal):
    assert result.state is ResultState.READY, result.errors
    reapply_events = ("prepare", "apply", "install")
    reapply_index = min(
        (
            adapter.calls.index(event)
            for event in reapply_events
            if event in adapter.calls
        ),
        default=None,
    )
    assert reapply_index is not None
    assert adapter.calls.index("rollback") < reapply_index
    assert receipt is not None and receipt.source_commit == desired.source_commit
    assert not journal.exists()
    assert all(
        item.state is not ResultState.BLOCKED for item in result.harnesses.values()
    )
    if adapter.name == "claude":
        assert adapter.rollback_prior == [adapter.expected_prior]

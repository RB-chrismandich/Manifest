"""A journal bound to a pre-retirement receipt survives the receipt's pruning."""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

import pytest

import manifest_agent.service as service_module
from manifest_agent.bootstrap_sync import (
    HarnessMutationCheckpoint,
    ReconciliationSaga,
    _journal_path,
    _read_journal,
    _serialize_handle,
    _write_journal,
    pending_bootstrap_journal_error,
)
from manifest_agent.models import AdapterMutationHandle, ResultState
from manifest_agent.ownership import graphify_retirement_transaction_proof
from manifest_agent.service_state import bundle_checksums
from manifest_agent.state import (
    StateError,
    _decode_receipt,
    read_receipt,
    read_retired_graphify_transaction,
    receipt_digest,
    retired_graphify_transaction_path,
    retired_receipt_rebinding,
    write_receipt_atomic,
)
from tests.python.manifest_agent.test_retired_harnesses import (
    _GEMINI_RECORD,
    _add_record,
    _raw_harnesses,
)
from tests.python.manifest_agent.test_service_install import (
    FakeAdapter,
    _write_legacy_graphify_receipt,
    harness_result,
    make_service_factory,
)
from tests.python.manifest_agent.test_state import SAMPLE_RECEIPT

_TARGET_IDENTITY = "a" * 64


def _receipt_naming_gemini(tmp_path: Path) -> tuple[Path, str]:
    """Write a receipt that names gemini; return its path and as-written digest."""
    path = tmp_path / "installation.json"
    write_receipt_atomic(path, SAMPLE_RECEIPT)
    _add_record(path, "gemini", _GEMINI_RECORD)
    rebinding = retired_receipt_rebinding(path)
    assert rebinding is not None
    written, read = rebinding
    assert written != read
    assert read == receipt_digest(SAMPLE_RECEIPT)
    return path, written


def test_receipt_without_retired_records_has_no_rebinding(tmp_path: Path) -> None:
    path = tmp_path / "installation.json"
    write_receipt_atomic(path, SAMPLE_RECEIPT)

    assert retired_receipt_rebinding(path) is None
    assert retired_receipt_rebinding(tmp_path / "absent.json") is None


def test_journal_bound_to_the_unpruned_receipt_is_rebound(tmp_path: Path) -> None:
    path, written = _receipt_naming_gemini(tmp_path)
    journal = _journal_path(path)
    _write_journal(
        journal,
        ReconciliationSaga(
            "committed",
            "codex",
            prior_receipt_digest=written,
            target_identity=_TARGET_IDENTITY,
            target_receipt_digest=written,
        ),
    )
    observed = receipt_digest(read_receipt(path))

    saga = _read_journal(journal, expected_prior_receipt_digest=observed)

    assert saga is not None
    assert saga.prior_receipt_digest == observed
    assert saga.target_receipt_digest == observed
    error = pending_bootstrap_journal_error(path)
    assert error is None or "invalid" not in error


def _checkpoint(harness: str, phase: str) -> HarnessMutationCheckpoint:
    handle = AdapterMutationHandle(1, harness, "1", _TARGET_IDENTITY, (), ())
    return HarnessMutationCheckpoint(harness, phase, _serialize_handle(handle))


def test_retired_harness_participant_is_tombstoned_on_load(tmp_path: Path) -> None:
    """Its adapter is gone, so it must not block the other participants."""
    path, written = _receipt_naming_gemini(tmp_path)
    journal = _journal_path(path)
    _write_journal(
        journal,
        ReconciliationSaga(
            "harness-prepared",
            "codex",
            harness_mutations=(
                _checkpoint("gemini", "prepared"),
                _checkpoint("claude", "prepared"),
            ),
            prior_receipt_digest=written,
            target_identity=_TARGET_IDENTITY,
        ),
    )

    saga = _read_journal(journal)

    assert saga is not None
    assert {item.harness: item.phase for item in saga.harness_mutations} == {
        "gemini": "tombstoned",
        "claude": "prepared",
    }


def test_journal_bound_to_an_unrelated_receipt_keeps_its_digests(
    tmp_path: Path,
) -> None:
    path, _written = _receipt_naming_gemini(tmp_path)
    journal = _journal_path(path)
    unrelated = "b" * 64
    _write_journal(
        journal,
        ReconciliationSaga(
            "committed",
            "codex",
            prior_receipt_digest=unrelated,
            target_identity=_TARGET_IDENTITY,
            target_receipt_digest=unrelated,
        ),
    )

    saga = _read_journal(journal)

    assert saga is not None
    assert saga.prior_receipt_digest == unrelated
    assert saga.target_receipt_digest == unrelated
    assert json.loads(journal.read_text(encoding="utf-8"))["prior_receipt_digest"] == (
        unrelated
    )


def _graphify_journal_naming(service, name: str) -> Path:
    """Write a signed Graphify retirement journal whose receipts name `name`."""
    _write_legacy_graphify_receipt(service)
    _add_record(service.receipt_path, name, {**_GEMINI_RECORD, "harness": name})
    written = _decode_receipt(
        json.loads(service.receipt_path.read_text(encoding="utf-8"))
    )
    desired, error = service._desired_state()
    assert error is None and desired is not None
    target = service_module._retired_graphify_target(
        written, desired, bundle_checksums(desired)
    )
    digest = receipt_digest(written)
    proof = graphify_retirement_transaction_proof(
        "cleanup-complete",
        digest,
        written,
        target,
        key_path=service.receipt_path.parent / "ownership.key",
    )
    journal = retired_graphify_transaction_path(service.receipt_path)
    journal.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "phase": "cleanup-complete",
                "legacy_receipt_digest": digest,
                "legacy_receipt": asdict(written),
                "target_receipt": asdict(target),
                "ownership_proof": proof,
            }
        ),
        encoding="utf-8",
    )
    return journal


def test_graphify_journal_naming_a_retired_harness_still_recovers(
    tmp_path: Path,
) -> None:
    service_factory = make_service_factory(tmp_path)
    claude = FakeAdapter("claude", harness_result("claude", plugin_ids=()))
    service = service_factory({"claude": claude}, harnesses=("claude",))
    journal = _graphify_journal_naming(service, "gemini")

    report = service.install()

    assert report.state is ResultState.READY, report.errors
    assert service.runner.calls == []
    assert not journal.exists()
    after = read_receipt(service.receipt_path)
    assert after is not None
    assert set(after.harnesses) == {"claude"}
    assert _raw_harnesses(service.receipt_path) == {"claude"}


def test_graphify_journal_naming_an_unknown_harness_is_still_rejected(
    tmp_path: Path,
) -> None:
    service_factory = make_service_factory(tmp_path)
    claude = FakeAdapter("claude", harness_result("claude"))
    service = service_factory({"claude": claude}, harnesses=("claude",))
    journal = _graphify_journal_naming(service, "bogus")

    with pytest.raises(StateError):
        read_retired_graphify_transaction(journal)

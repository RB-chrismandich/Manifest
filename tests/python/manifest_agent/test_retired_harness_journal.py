"""A journal bound to a pre-retirement receipt survives the receipt's pruning."""

from __future__ import annotations

import json
from pathlib import Path

from manifest_agent.bootstrap_sync import (
    HarnessMutationCheckpoint,
    ReconciliationSaga,
    _journal_path,
    _read_journal,
    _serialize_handle,
    _write_journal,
    pending_bootstrap_journal_error,
)
from manifest_agent.models import AdapterMutationHandle
from manifest_agent.state import (
    read_receipt,
    receipt_digest,
    retired_receipt_rebinding,
    write_receipt_atomic,
)
from tests.python.manifest_agent.test_retired_harnesses import (
    _GEMINI_RECORD,
    _add_record,
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

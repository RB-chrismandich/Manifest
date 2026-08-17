"""Named saga assertions shared by the bootstrap-sync suites."""

from pathlib import Path

import manifest_agent.bootstrap_sync as bootstrap_module
from manifest_agent.codex_plugin_backup import (
    plugin_tree_sha256,
)
from manifest_agent.contracts import DOMAIN_BUNDLES
from manifest_agent.ownership import owned_file_ownership
from manifest_agent.state import read_receipt


def _assert_exact_prior_restored(adapter, installed: Path) -> None:
    rows, error = adapter._list_installed_manifest_rows()
    assert error is None and rows is not None
    assert set(rows) == {
        *(f"{name}@manifest" for name in DOMAIN_BUNDLES),
        "manifest-retired@manifest",
    }
    assert rows["manifest-retired@manifest"]["version"] == "0.1.0"
    assert rows["manifest-retired@manifest"]["enabled"] is True
    assert Path(rows["manifest-retired@manifest"]["source"]["path"]) == installed
    assert (installed / "payload.txt").read_text(encoding="utf-8") == "exact prior\n"
    assert plugin_tree_sha256(installed)


def assert_codex_applied_after_removal(journal: Path) -> None:
    """The crashed journal must show codex applied WITH the removal recorded.

    Both halves matter: `applied` alone would not prove the removal reached the
    durable record, and a recorded removal under an earlier phase would mean the
    restart could not trust it.
    """
    crashed = bootstrap_module._read_journal(journal)
    assert crashed is not None
    codex = next(item for item in crashed.harness_mutations if item.harness == "codex")
    assert codex.phase == "applied"
    handle = bootstrap_module._deserialize_handle(codex.handle)
    assert any(item.retirement_phase == "removed" for item in handle.prior_inventory)


def assert_claude_compensated_to_prepared_archive(recorded, claude) -> None:
    """The compensation must have used the archive captured at prepare time.

    A `verified` checkpoint carrying the prepared backup proves the durable
    record referenced the live archive, and the `tombstoned` checkpoint proves
    that record was retired rather than abandoned mid-compensation.
    """
    checkpoints = [
        checkpoint
        for saga in recorded
        for checkpoint in saga.harness_mutations
        if checkpoint.harness == "claude"
    ]
    assert any(
        checkpoint.phase == "verified"
        and bootstrap_module._deserialize_handle(checkpoint.handle).prior_owned_files[
            0
        ]["restore"]["archive"]
        == claude.prepared_backup.to_dict()
        for checkpoint in checkpoints
    )
    assert any(checkpoint.phase == "tombstoned" for checkpoint in checkpoints)
    assert recorded[-1].phase == "retired"


def assert_retry_after_rollback_landed(service, claude, desired) -> None:
    """A run following a completed rollback must apply again and promote.

    `apply == 2` with `rollback == 1` is the whole claim: the retry re-prepared
    from the restored prior instead of resuming a stale handle, and it did not
    roll back a second time.
    """
    assert claude.calls.count("apply") == 2
    assert claude.calls.count("rollback") == 1
    assert not bootstrap_module._journal_path(service.receipt_path).exists()
    receipt = read_receipt(service.receipt_path)
    assert receipt is not None
    assert receipt.release_version == desired.release_version


def assert_journal_references_live_archive(journal_path: Path, expected_backup) -> None:
    """The prepared journal must cite the archive captured from the live file.

    A handle rebuilt from the receipt would cite whatever the receipt recorded,
    which is exactly the staleness these tests exist to rule out.
    """
    live_journal = bootstrap_module._read_journal(journal_path)
    assert live_journal is not None and live_journal.phase == "receipt-prepared"
    mutation = next(
        item for item in live_journal.harness_mutations if item.harness == "claude"
    )
    handle = bootstrap_module._deserialize_handle(mutation.handle)
    assert (
        handle.prior_owned_files[0]["restore"]["archive"] == expected_backup.to_dict()
    )


def assert_receipt_owns_archive(service, expected_backup):
    """The promoted receipt still authenticates the same archive reference."""
    persisted = read_receipt(service.receipt_path)
    assert persisted is not None
    entry = next(
        item
        for item in persisted.harnesses["claude"].owned_entries
        if item.identifier == "example-owned-file"
    )
    _prior, current, errors = owned_file_ownership(
        entry, key_path=service.receipt_path.parent / "ownership.key"
    )
    assert not errors and current is not None
    assert current["restore"]["archive"] == expected_backup.to_dict()
    return persisted

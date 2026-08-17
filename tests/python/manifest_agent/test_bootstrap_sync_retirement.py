"""Retiring a plugin the prior release owned, across crash windows."""

from pathlib import Path

import pytest

import manifest_agent.bootstrap_sync as bootstrap_module
from manifest_agent.bootstrap_sync import (
    _read_journal,
)
from manifest_agent.models import (
    ResultState,
)
from tests.python.manifest_agent._bootstrap_sync_asserts import (
    _assert_exact_prior_restored,
    assert_codex_applied_after_removal,
)
from tests.python.manifest_agent._bootstrap_sync_helpers import (
    _retirement_service,
    journal_crash_after_removal,
    journal_stop_at_codex_tombstone,
    legacy_skill_home,
    record_prepared_handles,
    stub_codex_convergence,
)
from tests.python.manifest_agent.test_service_install import make_service_factory


@pytest.fixture
def service_factory(tmp_path: Path):
    return make_service_factory(tmp_path)


def test_retirement_exception_before_final_applied_checkpoint_restores_exact_prior(
    service_factory, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    service, adapter, runner, installed, _desired, journal = _retirement_service(
        service_factory, tmp_path
    )
    real_write = bootstrap_module._write_journal
    injected = False

    def fail_after_removed(path, saga):
        nonlocal injected
        real_write(path, saga)
        codex = next(
            (item for item in saga.harness_mutations if item.harness == "codex"),
            None,
        )
        if codex is None or injected:
            return
        handle = bootstrap_module._deserialize_handle(codex.handle)
        if any(item.retirement_phase == "removed" for item in handle.prior_inventory):
            injected = True
            assert codex.phase in {"applying", "applied"}
            raise RuntimeError("injected post-removal failure")

    monkeypatch.setattr(bootstrap_module, "_write_journal", fail_after_removed)

    result = service.bootstrap_sync()

    assert result.state is ResultState.BLOCKED
    assert injected is True
    assert any(command[1:3] == ("plugin", "remove") for command in runner.log)
    _assert_exact_prior_restored(adapter, installed)
    assert not journal.exists()


def test_restart_after_retirement_crash_restores_prior_and_checkpoints_rollback(
    service_factory, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    legacy_skill_home(tmp_path, monkeypatch)
    service, adapter, _runner, installed, _desired, journal = _retirement_service(
        service_factory, tmp_path
    )
    real_write = bootstrap_module._write_journal

    monkeypatch.setattr(
        bootstrap_module, "_write_journal", journal_crash_after_removal(real_write)
    )
    with pytest.raises(SystemExit, match="post-removal crash"):
        service.bootstrap_sync()

    assert not installed.exists()
    assert_codex_applied_after_removal(journal)

    monkeypatch.setattr(
        bootstrap_module,
        "_write_journal",
        journal_stop_at_codex_tombstone(real_write),
    )
    restarted = service.bootstrap_sync()

    assert restarted.state is ResultState.BLOCKED
    _assert_exact_prior_restored(adapter, installed)
    rolled_back = _read_journal(journal)
    assert rolled_back is not None
    tombstoned_codex = next(
        item for item in rolled_back.harness_mutations if item.harness == "codex"
    )
    assert tombstoned_codex.phase == "tombstoned"
    restored_handle = bootstrap_module._deserialize_handle(tombstoned_codex.handle)
    assert restored_handle.prior_marketplace == adapter._observed_marketplace_identity()
    backup = next(
        item.rollback_data
        for item in restored_handle.prior_inventory
        if item.identifier == "manifest-retired@manifest"
    )
    assert backup is not None
    assert Path(backup["archive_path"]).exists()

    prepared = record_prepared_handles(adapter)
    stub_codex_convergence(adapter)
    monkeypatch.setattr(bootstrap_module, "_write_journal", real_write)
    third = service.bootstrap_sync()

    assert third.state is ResultState.READY
    assert len(prepared) == 1
    assert not journal.exists()
    assert not installed.exists()
    assert not Path(backup["archive_path"]).exists()

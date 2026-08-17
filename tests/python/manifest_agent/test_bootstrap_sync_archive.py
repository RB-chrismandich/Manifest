"""Owned-file archive authenticity across receipt failure and retirement."""

from pathlib import Path

import pytest

import manifest_agent.bootstrap_sync as bootstrap_module
from manifest_agent.codex_plugin_backup import (
    read_owned_file_backup,
)
from manifest_agent.models import (
    ResultState,
)
from manifest_agent.ownership import owned_file_entry
from manifest_agent.state import read_receipt
from tests.python.manifest_agent._bootstrap_sync_asserts import (
    assert_claude_compensated_to_prepared_archive,
    assert_journal_references_live_archive,
    assert_receipt_owns_archive,
    assert_retry_after_rollback_landed,
)
from tests.python.manifest_agent._bootstrap_sync_fakes import (
    ArchiveRollbackAdapter,
    LiveReferenceAdapter,
)
from tests.python.manifest_agent._bootstrap_sync_helpers import (
    bump_release,
    fail_receipt_directory_fsync,
    link_legacy_skills,
    owned_file_saga_service,
    owned_file_scenario,
    recording_journal_writer,
    retire_owned_entry,
)
from tests.python.manifest_agent.test_service_install import (
    FakeAdapter,
    harness_result,
    make_service_factory,
)


@pytest.fixture
def service_factory(tmp_path: Path):
    return make_service_factory(tmp_path)


def test_authenticated_owned_archive_reference_survives_receipt_failure_restart_and_retirement(
    service_factory, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from manifest_agent import state as state_module

    (
        env,
        home,
        state_home,
        target,
        prior,
        installed,
        _prior_backup,
        installed_backup,
    ) = owned_file_scenario(tmp_path, b"manifest target\n")
    entry = owned_file_entry("example-owned-file", target, prior, installed, env=env)

    claude = LiveReferenceAdapter(entry, env)
    codex = FakeAdapter("codex", harness_result("codex"))
    service = service_factory(
        {"claude": claude, "codex": codex}, harnesses=("claude", "codex")
    )
    service.receipt_path = state_home / "manifest/installation.json"
    assert service.install().state is ResultState.READY
    bump_release(service)
    service.harnesses = ("codex",)
    link_legacy_skills(home, monkeypatch)
    restore_receipt_durability = fail_receipt_directory_fsync(
        monkeypatch, state_module, service
    )

    first = service.bootstrap_sync()

    assert first.state is ResultState.BLOCKED
    journal_path = bootstrap_module._journal_path(service.receipt_path)
    assert_journal_references_live_archive(journal_path, installed_backup)
    assert read_owned_file_backup(installed_backup, env) == b"manifest target\n"

    restore_receipt_durability()
    restarted = service.bootstrap_sync()

    assert restarted.state is ResultState.READY
    assert not journal_path.exists()
    persisted = assert_receipt_owns_archive(service, installed_backup)
    assert read_owned_file_backup(installed_backup, env) == b"manifest target\n"

    retire_owned_entry(service, persisted)
    # Collection is conservative, but the archive is now free of live authority.
    assert read_owned_file_backup(installed_backup, env) == b"manifest target\n"


def test_prior_visible_receipt_failure_compensates_archive_and_retires_journal(
    service_factory, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (
        env,
        home,
        state_home,
        target,
        prior,
        installed,
        _prior_backup,
        _installed_backup,
    ) = owned_file_scenario(tmp_path, b"release one\n")
    link_legacy_skills(home, monkeypatch)

    claude = ArchiveRollbackAdapter(target, env)

    (
        service,
        _codex,
        desired,
        _prior_desired,
        authoritative_prior,
    ) = owned_file_saga_service(
        service_factory, state_home, target, prior, installed, claude
    )
    recorded = recording_journal_writer(monkeypatch)
    real_write_receipt = bootstrap_module.write_receipt_atomic

    def fail_before_receipt_rename(path, receipt):
        del path, receipt
        raise OSError("injected prior-visible receipt failure")

    monkeypatch.setattr(
        bootstrap_module, "write_receipt_atomic", fail_before_receipt_rename
    )

    result = service.bootstrap_sync()

    assert result.state is ResultState.BLOCKED
    assert read_receipt(service.receipt_path) == authoritative_prior
    assert target.read_bytes() == b"release one\n"
    assert claude.calls.count("apply") == 1
    assert claude.calls.count("rollback") == 1
    assert_claude_compensated_to_prepared_archive(recorded, claude)
    assert not bootstrap_module._journal_path(service.receipt_path).exists()
    assert read_owned_file_backup(claude.prepared_backup, env) == b"release one\n"

    # A rolled-back run must leave no handle behind that poisons the next one:
    # retiring the journal is only half the contract, the other half is that a
    # third run re-prepares from the restored prior and actually lands.
    monkeypatch.setattr(bootstrap_module, "write_receipt_atomic", real_write_receipt)

    retried = service.bootstrap_sync()

    assert retried.state is ResultState.READY, retried.errors
    assert_retry_after_rollback_landed(service, claude, desired)

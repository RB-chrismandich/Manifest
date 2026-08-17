"""Codex native reconciliation observation tests."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

import manifest_agent.adapters.codex as codex_module
import manifest_agent.bootstrap_sync as bootstrap_sync_module
from manifest_agent.models import (
    DesiredState,
    ResultState,
)
from tests.python.manifest_agent._codex_adapter_test_support import (
    QueueRunner,
    _prepare_prior_only_handle,
    command,
    marketplace_json,
    plugin_remove_json,
)
from tests.python.manifest_agent._codex_adapter_test_support import (
    desired as desired,
)


def test_codex_reconcile_retires_prior_only_plugin_before_target_install(
    tmp_path: Path, desired: DesiredState, monkeypatch: pytest.MonkeyPatch
) -> None:
    adapter, handle, prior_row, _installed = _prepare_prior_only_handle(
        tmp_path, desired
    )
    adapter.runner = QueueRunner(
        [
            command(stdout=marketplace_json(str(tmp_path), tmp_path)),
            command(stdout=json.dumps({"installed": [prior_row]})),
            command(stdout=json.dumps({"installed": [prior_row]})),
            command(stdout=plugin_remove_json("manifest-retired")),
            command(stdout=json.dumps({"installed": []})),
        ]
    )
    checkpoints = []
    installed_after_retirement = []

    def install(_desired, *, marketplace_preverified=False):
        installed_after_retirement.append(marketplace_preverified)
        return codex_module.HarnessResult("codex", ResultState.READY, (), {})

    monkeypatch.setattr(adapter, "install_with_checkpoints", install)

    result = adapter.apply_reconcile(handle, desired, checkpoints.append)

    assert result.state is ResultState.READY
    assert [
        checkpoint.prior_inventory[0].retirement_phase for checkpoint in checkpoints
    ] == ["removal-prepared", "removed"]
    assert installed_after_retirement == [True]
    assert [row[1:3] for row in adapter.runner.log].count(["plugin", "remove"]) == 1
    journal = tmp_path / "retirement-journal.json"
    bootstrap_sync_module._write_journal(
        journal,
        bootstrap_sync_module.ReconciliationSaga(
            "codex-retirement",
            "codex",
            harness_mutations=(
                bootstrap_sync_module.HarnessMutationCheckpoint(
                    "codex",
                    "prepared",
                    bootstrap_sync_module._serialize_handle(checkpoints[-1]),
                ),
            ),
            prior_receipt_digest=bootstrap_sync_module.NO_PRIOR_RECEIPT_V1,
            target_identity=bootstrap_sync_module._target_identity(desired),
        ),
    )
    restored = bootstrap_sync_module._read_journal(journal)
    assert restored is not None
    restored_handle = bootstrap_sync_module._deserialize_handle(
        restored.harness_mutations[0].handle
    )
    assert restored_handle.prior_inventory[0].retirement_phase == "removed"


def test_codex_reconcile_resumes_crash_immediately_after_prior_only_removal(
    tmp_path: Path, desired: DesiredState, monkeypatch: pytest.MonkeyPatch
) -> None:
    adapter, handle, prior_row, installed = _prepare_prior_only_handle(
        tmp_path, desired
    )

    class CrashAfterRemovalRunner(QueueRunner):
        def run(self, argv, *, env=None):
            result = super().run(argv, env=env)
            if list(argv)[1:3] == ["plugin", "remove"]:
                shutil.rmtree(installed)
                raise SystemExit("injected crash after native removal")
            return result

    adapter.runner = CrashAfterRemovalRunner(
        [
            command(stdout=marketplace_json(str(tmp_path), tmp_path)),
            command(stdout=json.dumps({"installed": [prior_row]})),
            command(stdout=json.dumps({"installed": [prior_row]})),
            command(stdout=plugin_remove_json("manifest-retired")),
        ]
    )
    checkpoints = []

    with pytest.raises(SystemExit, match="injected crash"):
        adapter.apply_reconcile(handle, desired, checkpoints.append)

    prepared = checkpoints[-1]
    assert prepared.prior_inventory[0].retirement_phase == "removal-prepared"
    assert prepared.prior_inventory[0].rollback_data is not None
    adapter.runner = QueueRunner(
        [
            command(stdout=marketplace_json(str(tmp_path), tmp_path)),
            command(stdout=json.dumps({"installed": []})),
            command(stdout=json.dumps({"installed": []})),
        ]
    )
    resumed = []
    monkeypatch.setattr(
        adapter,
        "install_with_checkpoints",
        lambda _desired, *, marketplace_preverified=False: (
            resumed.append(marketplace_preverified)
            or codex_module.HarnessResult("codex", ResultState.READY, (), {})
        ),
    )

    result = adapter.apply_reconcile(prepared, desired, checkpoints.append)

    assert result.state is ResultState.READY
    assert checkpoints[-1].prior_inventory[0].retirement_phase == "removed"
    assert resumed == [True]


def test_codex_reconcile_blocks_absent_prior_only_without_retirement_checkpoint(
    tmp_path: Path, desired: DesiredState, monkeypatch: pytest.MonkeyPatch
) -> None:
    adapter, handle, _prior_row, installed = _prepare_prior_only_handle(
        tmp_path, desired
    )
    shutil.rmtree(installed)
    adapter.runner = QueueRunner(
        [
            command(stdout=marketplace_json(str(tmp_path), tmp_path)),
            command(stdout=json.dumps({"installed": []})),
        ]
    )
    resumed = False

    def install(_desired, *, marketplace_preverified=False):
        del _desired, marketplace_preverified
        nonlocal resumed
        resumed = True
        return codex_module.HarnessResult("codex", ResultState.READY, (), {})

    monkeypatch.setattr(adapter, "install_with_checkpoints", install)

    result = adapter.apply_reconcile(handle, desired)

    assert result.state is ResultState.BLOCKED
    assert resumed is False


def test_codex_reconcile_blocks_absent_prior_only_without_retained_backup(
    tmp_path: Path, desired: DesiredState, monkeypatch: pytest.MonkeyPatch
) -> None:
    adapter, handle, _prior_row, installed = _prepare_prior_only_handle(
        tmp_path, desired
    )
    handle = codex_module._with_retirement_phase(
        handle, "manifest-retired@manifest", "removal-prepared"
    )
    backup = handle.prior_inventory[0].rollback_data
    assert backup is not None
    Path(backup["archive_path"]).unlink()
    shutil.rmtree(installed)
    adapter.runner = QueueRunner(
        [
            command(stdout=marketplace_json(str(tmp_path), tmp_path)),
            command(stdout=json.dumps({"installed": []})),
        ]
    )
    monkeypatch.setattr(
        adapter,
        "install_with_checkpoints",
        lambda *_args, **_kwargs: pytest.fail("unverified retirement resumed"),
    )

    result = adapter.apply_reconcile(handle, desired)

    assert result.state is ResultState.BLOCKED


def test_codex_reconcile_rollback_restores_retired_prior_only_plugin(
    tmp_path: Path, desired: DesiredState
) -> None:
    adapter, handle, prior_row, installed = _prepare_prior_only_handle(
        tmp_path, desired
    )
    handle = codex_module._with_retirement_phase(
        handle, "manifest-retired@manifest", "removed"
    )
    shutil.rmtree(installed)
    adapter.runner = QueueRunner(
        [
            command(stdout=json.dumps({"installed": []})),
            command(stdout=marketplace_json(str(tmp_path), tmp_path)),
            command(stdout=json.dumps({"installed": [prior_row]})),
        ]
    )

    result = adapter.rollback_reconcile(handle, desired)

    assert result.state is ResultState.READY
    assert (installed / "payload.txt").read_text(encoding="utf-8") == (
        "retired release\n"
    )

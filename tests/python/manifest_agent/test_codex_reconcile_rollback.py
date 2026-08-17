"""Codex native reconciliation rollback tests."""

from __future__ import annotations

import json
import shutil
from dataclasses import replace
from pathlib import Path

import pytest

import manifest_agent.adapters.codex as codex_module
import manifest_agent.bootstrap_sync as bootstrap_sync_module
from manifest_agent.adapters.codex import CodexAdapter
from manifest_agent.contracts import (
    DOMAIN_BUNDLES,
)
from manifest_agent.models import (
    AdapterMutationHandle,
    AdapterPluginState,
    CatalogPlugin,
    DesiredState,
    HarnessReceipt,
    ResultState,
)
from tests.python.manifest_agent._codex_adapter_test_support import (
    QueueRunner,
    _prepare_reconcile_handle,
    command,
    installed_json,
    marketplace_json,
    plugin_remove_json,
)
from tests.python.manifest_agent._codex_adapter_test_support import (
    desired as desired,
)


def _journal_round_trip(
    tmp_path: Path, desired: DesiredState, handle: AdapterMutationHandle
) -> AdapterMutationHandle:
    journal = tmp_path / "bootstrap-sync.json"
    bootstrap_sync_module._write_journal(
        journal,
        bootstrap_sync_module.ReconciliationSaga(
            "codex-applied",
            "codex",
            harness_mutations=(
                bootstrap_sync_module.HarnessMutationCheckpoint(
                    "codex",
                    "applied",
                    bootstrap_sync_module._serialize_handle(handle),
                ),
            ),
            prior_receipt_digest=bootstrap_sync_module.NO_PRIOR_RECEIPT_V1,
            target_identity=bootstrap_sync_module._target_identity(desired),
        ),
    )
    restarted_saga = bootstrap_sync_module._read_journal(journal)
    assert restarted_saga is not None
    return bootstrap_sync_module._deserialize_handle(
        restarted_saga.harness_mutations[0].handle
    )


def test_codex_reconcile_abort_restores_replacement_and_target_only_additions(
    tmp_path: Path, desired: DesiredState
) -> None:
    adapter, handle, prior_row = _prepare_reconcile_handle(tmp_path, desired)
    installed = tmp_path / "native-cache/manifest-workspace"
    handle = _journal_round_trip(tmp_path, desired, handle)

    replacement_rows = json.loads(installed_json(desired))["installed"]
    shutil.rmtree(installed)
    removal_names = tuple(reversed(DOMAIN_BUNDLES))
    final_prior = {"installed": [prior_row]}
    rollback_runner = QueueRunner(
        [
            command(stdout=json.dumps({"installed": replacement_rows})),
            *(command(stdout=plugin_remove_json(name)) for name in removal_names),
            command(stdout=marketplace_json(str(tmp_path), tmp_path)),
            command(stdout=json.dumps(final_prior)),
        ]
    )
    adapter.runner = rollback_runner

    result = adapter.rollback_reconcile(handle, desired)

    assert result.state is ResultState.READY
    assert (installed / "payload.txt").read_text(encoding="utf-8") == "prior release\n"
    assert [row[3] for row in rollback_runner.log[1 : 1 + len(removal_names)]] == [
        f"{name}@manifest" for name in removal_names
    ]

    restart_runner = QueueRunner(
        [
            command(stdout=json.dumps(final_prior)),
            command(stdout=marketplace_json(str(tmp_path), tmp_path)),
            command(stdout=json.dumps(final_prior)),
        ]
    )
    adapter.runner = restart_runner

    restarted = adapter.rollback_reconcile(handle, desired)

    assert restarted.state is ResultState.READY
    assert not any(row[1:3] == ["plugin", "remove"] for row in restart_runner.log)


def _prepare_same_version_drift(
    tmp_path: Path, desired: DesiredState
) -> tuple[CodexAdapter, AdapterMutationHandle, DesiredState]:
    installed = tmp_path / "native-cache/manifest-workspace"
    installed.mkdir(parents=True)
    (installed / "payload.txt").write_text("prior content\n", encoding="utf-8")
    prior_row: dict[str, object] = {
        "pluginId": "manifest-workspace@manifest",
        "version": "0.2.0",
        "enabled": True,
        "installed": True,
        "installedPath": str(installed),
        "source": {"path": str(installed)},
    }
    scoped = replace(
        desired,
        catalog_plugins=(
            CatalogPlugin(
                "manifest-workspace", "0.2.0", "./plugins/manifest-workspace"
            ),
        ),
    )
    adapter = CodexAdapter(
        runner=QueueRunner(
            [
                command(stdout=marketplace_json(str(tmp_path), tmp_path)),
                command(stdout=json.dumps({"installed": [prior_row]})),
            ]
        ),
        which=lambda name: name,
        env={"XDG_STATE_HOME": str(tmp_path / "state")},
    )
    handle = adapter.prepare_reconcile(
        HarnessReceipt(
            "codex",
            "1",
            "prior",
            ("manifest-workspace@manifest",),
            (),
            {},
            True,
        ),
        scoped,
        scoped,
    )
    adapter.runner = QueueRunner(
        [
            command(stdout=marketplace_json(str(tmp_path), tmp_path)),
            command(stdout=json.dumps({"installed": [prior_row]})),
        ]
    )
    return adapter, handle, scoped


def test_codex_reconcile_refreshes_marketplace_for_same_version_content_drift(
    tmp_path: Path, desired: DesiredState, monkeypatch: pytest.MonkeyPatch
) -> None:
    adapter, handle, scoped = _prepare_same_version_drift(tmp_path, desired)
    preverified_values: list[bool] = []

    def install(
        _desired: DesiredState, *, marketplace_preverified: bool = False
    ) -> codex_module.HarnessResult:
        del _desired
        preverified_values.append(marketplace_preverified)
        return codex_module.HarnessResult("codex", ResultState.READY, (), {})

    monkeypatch.setattr(adapter, "install_with_checkpoints", install)

    result = adapter.apply_reconcile(handle, scoped)

    assert result.state is ResultState.READY
    assert preverified_values == [False]


def test_codex_reconcile_rollback_preserves_accumulated_failures(
    desired: DesiredState,
) -> None:
    replacement_id = "manifest-workspace@manifest"
    target_only_id = "manifest-target-only@manifest"
    prior = AdapterPluginState(replacement_id, "0.1.0", True)
    target_replacement = AdapterPluginState(replacement_id, "0.2.0", True)
    target_only = AdapterPluginState(target_only_id, "0.2.0", True)
    handle = AdapterMutationHandle(
        1,
        "codex",
        "1",
        "target",
        (prior,),
        (target_replacement, target_only),
    )
    rows = {
        "installed": [
            {
                "pluginId": target_only_id,
                "version": "0.2.0",
                "enabled": True,
            },
            {
                "pluginId": replacement_id,
                "version": "unexpected",
                "enabled": True,
            },
        ]
    }
    adapter = CodexAdapter(
        runner=QueueRunner(
            [
                command(stdout=json.dumps(rows)),
                command(returncode=1, stderr="remove failed"),
            ]
        ),
        which=lambda name: name,
    )

    result = adapter.rollback_reconcile(handle, desired)

    errors = " ".join(result.errors)
    assert result.state is ResultState.BLOCKED
    assert "remove failed" in errors
    assert f"lacks a backup for {replacement_id}" in errors

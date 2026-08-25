"""Codex native reconciliation tests."""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

import manifest_agent.adapters.codex as codex_module
from manifest_agent.adapters.codex import CodexAdapter
from manifest_agent.contracts import (
    DOMAIN_BUNDLES,
)
from manifest_agent.models import (
    DesiredState,
    HarnessReceipt,
    OwnedEntry,
    ResultState,
)
from tests.python.manifest_agent._codex_adapter_test_support import (
    QueueRunner,
    _catalog_entry,
    _prepare_reconcile_handle,
    _receipt,
    command,
    installed_json,
    marketplace_json,
    mcp_list_json,
)
from tests.python.manifest_agent._codex_adapter_test_support import (
    desired as desired,
)


def test_codex_inspect_rejects_unrecognized_manifest_extra(
    tmp_path: Path, desired: DesiredState
) -> None:
    adapter = CodexAdapter(
        runner=QueueRunner(
            [
                command(stdout=marketplace_json(str(tmp_path), tmp_path)),
                command(stdout=installed_json(desired, extra=True)),
            ]
        ),
        which=lambda name: name,
    )

    result = adapter.inspect(desired)

    assert result.state is ResultState.DRIFTED
    assert "unrecognized Manifest plugin: adversarial-design-loop@manifest" in (
        result.errors
    )


def test_codex_prepare_reconcile_rejects_unrecognized_manifest_extra(
    tmp_path: Path, desired: DesiredState
) -> None:
    plugin_ids = tuple(f"{name}@manifest" for name in DOMAIN_BUNDLES)
    adapter = CodexAdapter(
        runner=QueueRunner(
            [
                command(stdout=marketplace_json(str(tmp_path), tmp_path)),
                command(stdout=installed_json(desired, extra=True)),
            ]
        ),
        which=lambda name: name,
    )

    with pytest.raises(ValueError, match="unrecognized Manifest plugins"):
        adapter.prepare_reconcile(
            HarnessReceipt("codex", "1", "prior", plugin_ids, (), {}, True),
            desired,
            desired,
        )


def test_codex_prepared_reconcile_blocks_target_plugin_with_prior_marketplace(
    tmp_path: Path, desired: DesiredState, monkeypatch: pytest.MonkeyPatch
) -> None:
    adapter, handle, _prior_row = _prepare_reconcile_handle(
        tmp_path, desired, marketplace_present=False
    )
    target_row = json.loads(installed_json(desired, names=(DOMAIN_BUNDLES[0],)))[
        "installed"
    ][0]
    adapter.runner = QueueRunner(
        [
            command(stdout='{"marketplaces":[]}'),
            command(stdout=json.dumps({"installed": [target_row]})),
        ]
    )
    monkeypatch.setattr(
        adapter,
        "install_with_checkpoints",
        lambda *_args, **_kwargs: pytest.fail("mixed state resumed"),
    )

    result = adapter.apply_reconcile(handle, desired)

    assert result.state is ResultState.BLOCKED
    assert "state is mixed" in " ".join(result.errors)


def test_codex_prepared_reconcile_accepts_exact_target_without_mutation(
    tmp_path: Path, desired: DesiredState
) -> None:
    adapter, handle, _prior_row = _prepare_reconcile_handle(tmp_path, desired)
    target = installed_json(desired)
    adapter.runner = QueueRunner(
        [
            command(stdout=marketplace_json(str(tmp_path), tmp_path)),
            command(stdout=target),
            command(stdout=marketplace_json(str(tmp_path), tmp_path)),
            command(stdout=target),
            command(stdout=mcp_list_json()),
        ]
    )

    result = adapter.apply_reconcile(handle, desired)

    assert result.state is ResultState.READY
    assert not any(
        row[1:3] in (["plugin", "add"], ["plugin", "remove"])
        or row[1:4] == ["plugin", "marketplace", "add"]
        for row in adapter.runner.log
    )


def test_codex_prepared_reconcile_resumes_authorized_partial_without_marketplace_replay(
    tmp_path: Path, desired: DesiredState, monkeypatch: pytest.MonkeyPatch
) -> None:
    adapter, handle, _prior_row = _prepare_reconcile_handle(tmp_path, desired)
    first_target = json.loads(installed_json(desired, names=(DOMAIN_BUNDLES[0],)))[
        "installed"
    ][0]
    adapter.runner = QueueRunner(
        [
            command(stdout=marketplace_json(str(tmp_path), tmp_path)),
            command(stdout=json.dumps({"installed": [first_target]})),
        ]
    )
    observed: list[bool] = []

    def resume(_desired, *, marketplace_preverified=False):
        observed.append(marketplace_preverified)
        return codex_module.HarnessResult("codex", ResultState.READY, (), {})

    monkeypatch.setattr(adapter, "install_with_checkpoints", resume)

    result = adapter.apply_reconcile(handle, desired)

    assert result.state is ResultState.READY
    assert observed == [True]


@pytest.mark.parametrize(
    ("observed_marketplace", "marketplace_preverified"),
    (("prior", False), ("target", True)),
)
def test_codex_prepared_reconcile_observes_safe_retry_and_marketplace_crash(
    tmp_path: Path,
    desired: DesiredState,
    monkeypatch: pytest.MonkeyPatch,
    observed_marketplace: str,
    marketplace_preverified: bool,
) -> None:
    adapter, handle, prior_row = _prepare_reconcile_handle(
        tmp_path, desired, marketplace_present=False
    )
    marketplace = (
        '{"marketplaces":[]}'
        if observed_marketplace == "prior"
        else marketplace_json(str(tmp_path), tmp_path)
    )
    adapter.runner = QueueRunner(
        [
            command(stdout=marketplace),
            command(stdout=json.dumps({"installed": [prior_row]})),
        ]
    )
    observed: list[bool] = []

    def resume(_desired, *, marketplace_preverified=False):
        observed.append(marketplace_preverified)
        return codex_module.HarnessResult("codex", ResultState.READY, (), {})

    monkeypatch.setattr(adapter, "install_with_checkpoints", resume)

    result = adapter.apply_reconcile(handle, desired)

    assert result.state is ResultState.READY
    assert observed == [marketplace_preverified]


def test_codex_prepared_reconcile_blocks_later_plugin_replacement(
    tmp_path: Path, desired: DesiredState, monkeypatch: pytest.MonkeyPatch
) -> None:
    adapter, handle, prior_row = _prepare_reconcile_handle(tmp_path, desired)
    installed = Path(prior_row["source"]["path"])
    (installed / "payload.txt").write_text("user replacement\n", encoding="utf-8")
    adapter.runner = QueueRunner(
        [
            command(stdout=marketplace_json(str(tmp_path), tmp_path)),
            command(stdout=json.dumps({"installed": [prior_row]})),
        ]
    )
    resumed = False

    def unexpected_resume(_desired, *, marketplace_preverified=False):
        nonlocal resumed
        resumed = True
        return codex_module.HarnessResult("codex", ResultState.READY, (), {})

    monkeypatch.setattr(adapter, "install_with_checkpoints", unexpected_resume)

    result = adapter.apply_reconcile(handle, desired)

    assert result.state is ResultState.BLOCKED
    assert "changed after prepared reconciliation" in " ".join(result.errors)
    assert resumed is False


def test_codex_uninstall_blocks_replaced_marketplace_source_before_mutation(
    tmp_path: Path,
) -> None:
    environment = {"XDG_STATE_HOME": str(tmp_path)}
    receipt = _receipt(
        tmp_path,
        "codex",
        "1",
        "0.146",
        (),
        (
            OwnedEntry("marketplace", "manifest", "manifest"),
            _catalog_entry((), tmp_path),
        ),
        {},
        True,
    )
    runner = QueueRunner(
        [
            command(
                stdout=marketplace_json(
                    str(tmp_path / "user-replacement"),
                    tmp_path / "user-replacement",
                )
            ),
        ]
    )

    result = CodexAdapter(
        runner=runner, which=lambda name: name, env=environment
    ).uninstall(receipt)

    assert result.state is ResultState.BLOCKED
    assert "source was replaced" in " ".join(result.errors)
    assert not any(
        row[1:4] == ["plugin", "marketplace", "remove"] for row in runner.log
    )


def test_codex_uninstall_rejects_forged_restoration_metadata_before_saga(
    tmp_path: Path,
) -> None:
    config = tmp_path / ".codex/config.toml"
    config.parent.mkdir()
    config.write_text(
        '[plugins."i-have-adhd@i-have-adhd"]\nenabled = false\n',
        encoding="utf-8",
    )
    restoration = OwnedEntry(
        "plugin-enabled-state",
        "i-have-adhd@i-have-adhd",
        "manifest",
        str(config),
        json.dumps(
            {"previous": True, "current": False, "written_sha256": "0" * 64},
            sort_keys=True,
            separators=(",", ":"),
        ),
    )
    receipt = _receipt(
        tmp_path,
        "codex",
        "1",
        "0.146",
        (),
        (restoration, _catalog_entry((), tmp_path)),
        {},
        True,
    )
    forged = replace(
        receipt,
        owned_entries=tuple(
            replace(entry, previous_checksum='{"previous":false}')
            if entry.kind == "plugin-enabled-state"
            else entry
            for entry in receipt.owned_entries
        ),
    )
    runner = QueueRunner([])

    result = CodexAdapter(
        runner=runner,
        which=lambda name: name,
        env={"XDG_STATE_HOME": str(tmp_path)},
    ).uninstall(forged)

    assert result.state is ResultState.BLOCKED
    assert "full Codex ownership" in " ".join(result.errors)
    assert runner.log == []

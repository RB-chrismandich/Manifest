"""PR #1054 review regressions: checkout drift, recovery catalog, restore capture."""

import json
from pathlib import Path

import pytest

from manifest_agent.adapters.omp_identity import (
    MARKETPLACE_KIND,
    PLUGIN_KIND,
    decode_identity,
)
from manifest_agent.adapters.omp_inventory import OmpInventoryError
from manifest_agent.adapters.omp_source import owned_marketplace_matches
from manifest_agent.models import ResultState
from manifest_agent.ownership import omp_receipt_ownership_errors
from manifest_agent.service_state import with_prior_harness_receipts
from manifest_agent.state import read_receipt
from tests.python.manifest_agent._omp_native_fixture import (
    make_adapter,
    make_desired,
    make_service,
)
from tests.python.manifest_agent.test_omp_native_lifecycle import (
    owned,
    setup_install,
)


def _marketplace_source(service):
    entry = next(
        entry
        for entry in owned(service).owned_entries
        if entry.kind == MARKETPLACE_KIND
    )
    return decode_identity(entry)["source"]


def test_checkout_edit_does_not_block_uninstall_ownership(tmp_path: Path):
    desired, _adapter, _runner, service = setup_install(tmp_path)
    skill = desired.release_root / "plugins/manifest-i-have-adhd/skills"
    skill_file = next(skill.glob("*/SKILL.md"))
    skill_file.write_text(skill_file.read_text() + "\nlocal edit\n")

    assert (
        omp_receipt_ownership_errors(
            owned(service), key_path=service.receipt_path.parent / "ownership.key"
        )
        == ()
    )
    assert service.uninstall().state is ResultState.READY


def test_edited_recovery_catalog_is_rejected_before_registry_change(tmp_path: Path):
    desired, adapter, runner, _service = setup_install(tmp_path)
    catalog = desired.release_root / ".claude-plugin/marketplace.json"
    catalog_obj = json.loads(catalog.read_text())
    catalog_obj["description"] = "locally edited"
    catalog.write_text(json.dumps(catalog_obj))
    mutations_before = len(runner.mutations)

    replacement = make_desired(tmp_path / "release2", version="1.0.1")
    next_service = make_service(tmp_path, adapter, replacement)
    report = next_service.reconcile(apply=True)

    assert report.state is not ResultState.READY
    assert not any(
        "remove" in command for command in runner.mutations[mutations_before:]
    )


def test_shadow_inspect_ignores_real_home_project_inventory(tmp_path: Path):
    real_home = tmp_path / "home"
    checkout = real_home / "project"
    (real_home / ".omp" / "plugins").mkdir(parents=True)
    checkout.mkdir(parents=True)
    desired = make_desired(tmp_path / "release")
    adapter, _runner = make_adapter(tmp_path)
    adapter._env = {**adapter._env, "HOME": str(real_home)}
    adapter._cwd = checkout.resolve(strict=True)

    report = adapter.shadow_inspect(desired, tmp_path / "shadow-home")
    assert not any("project inventory" in error for error in report.errors)


def test_deleted_checkout_does_not_block_uninstall_ownership(tmp_path: Path):
    import shutil

    desired, _adapter, _runner, service = setup_install(tmp_path)
    shutil.rmtree(desired.release_root)

    assert (
        omp_receipt_ownership_errors(
            owned(service), key_path=service.receipt_path.parent / "ownership.key"
        )
        == ()
    )
    assert service.uninstall().state is ResultState.READY


def test_shadow_home_nested_under_real_home_ignores_real_project_inventory(
    tmp_path: Path,
):
    real_home = tmp_path / "home"
    (real_home / ".omp" / "plugins").mkdir(parents=True)
    desired = make_desired(tmp_path / "release")
    adapter, _runner = make_adapter(tmp_path)
    adapter._env = {**adapter._env, "HOME": str(real_home)}
    adapter._cwd = (real_home / "project").resolve(strict=False)
    (real_home / "project").mkdir()

    report = adapter.shadow_inspect(desired, real_home / "shadow")
    assert not any("project inventory" in error for error in report.errors)


def test_same_version_source_edit_is_not_reported_ready(tmp_path):
    desired, _adapter, _runner, service = setup_install(tmp_path)
    skill = next(desired.bundle_path("manifest-i-have-adhd").glob("skills/*/SKILL.md"))
    skill.write_text(skill.read_text() + "\nEdited in place.\n")
    result = service.reconcile(apply=True)
    assert result.state is not ResultState.READY


def test_post_install_capture_failure_keeps_original_command_error(tmp_path):
    """A snapshot failure in the install finally must not mask the command error."""
    from manifest_agent.adapters.omp_inventory import OmpInventoryError

    desired = make_desired(tmp_path / "release")
    adapter, _runner = make_adapter(tmp_path)
    make_service(tmp_path, adapter, desired)
    original_command = adapter._command
    original_snapshot = adapter._snapshot
    state = {"failed_once": False, "fail_next_snapshot": False}

    def failing_command(argv, **kwargs):
        if argv[1] == "plugin" and not state["failed_once"]:
            state["failed_once"] = True
            state["fail_next_snapshot"] = True
            raise OmpInventoryError("OMP native command failed: exit 1: boom")
        return original_command(argv, **kwargs)

    def flaky_snapshot():
        if state["fail_next_snapshot"]:
            state["fail_next_snapshot"] = False
            raise OSError("snapshot unreadable after mutation")
        return original_snapshot()

    adapter._command = failing_command
    adapter._snapshot = flaky_snapshot

    result = adapter.install(desired)

    assert state["failed_once"]
    assert result.state is ResultState.BLOCKED
    assert any("boom" in error for error in result.errors), result.errors


def test_marketplace_identity_failure_keeps_original_command_error(
    tmp_path, monkeypatch
):
    """Identity validation in the marketplace finally must not mask the command error."""
    from manifest_agent.adapters import omp_lifecycle
    from manifest_agent.adapters.omp_inventory import OmpInventoryError

    desired = make_desired(tmp_path / "release")
    adapter, _runner = make_adapter(tmp_path)
    make_service(tmp_path, adapter, desired)
    original_command = adapter._command
    state = {"failed_once": False}

    def failing_marketplace_add(argv, **kwargs):
        if argv[1:3] == ("plugin", "marketplace") and not state["failed_once"]:
            state["failed_once"] = True
            original_command(argv, **kwargs)
            raise OmpInventoryError("OMP native command failed: exit 1: boom")
        return original_command(argv, **kwargs)

    def rejecting_identity(*_args, **_kwargs):
        raise ValueError("marketplace source unexpected")

    adapter._command = failing_marketplace_add
    monkeypatch.setattr(omp_lifecycle, "marketplace_identity", rejecting_identity)

    result = adapter.install(desired)

    assert state["failed_once"]
    assert result.state is ResultState.BLOCKED
    assert any("boom" in error for error in result.errors), result.errors
    assert any("post-install capture failed" in error for error in result.errors), (
        result.errors
    )


def test_foreign_marketplace_source_blocks_plugin_install(tmp_path, monkeypatch):
    """A created marketplace with an unexpected source must not receive plugin installs."""
    from manifest_agent.adapters import omp_lifecycle

    desired = make_desired(tmp_path / "release")
    adapter, _runner = make_adapter(tmp_path)
    make_service(tmp_path, adapter, desired)
    original_command = adapter._command
    plugin_mutations = []

    def recording_command(argv, **kwargs):
        if argv[1] == "plugin" and argv[2] in ("install", "upgrade"):
            plugin_mutations.append(tuple(argv))
        return original_command(argv, **kwargs)

    def foreign_identity(*_args, **_kwargs):
        return {"source": "/elsewhere"}

    adapter._command = recording_command
    monkeypatch.setattr(omp_lifecycle, "marketplace_identity", foreign_identity)

    result = adapter.install(desired)

    assert result.state is ResultState.BLOCKED
    assert any("unexpected source" in error for error in result.errors), result.errors
    assert plugin_mutations == [], plugin_mutations


def test_failed_restore_add_is_reported_as_restore_diagnostic(
    tmp_path: Path, monkeypatch
):
    """When the forward add and the restore add both fail, the restore failure must be reported."""
    from manifest_agent.adapters.omp_identity import MARKETPLACE_KIND, decode_identity
    from manifest_agent.adapters.omp_inventory import OMP_MARKETPLACE, OmpInventoryError
    from manifest_agent.adapters.omp_source import OmpSourceMixin

    desired, adapter, _runner, service = setup_install(tmp_path)
    entries = {(e.kind, e.identifier): e for e in owned(service).owned_entries}
    root, markets, registry, runtime, cli = adapter._snapshot()
    expected = decode_identity(entries[(MARKETPLACE_KIND, OMP_MARKETPLACE)])
    prior = tmp_path / "prior-source"
    (prior / ".claude-plugin").mkdir(parents=True)
    (prior / ".claude-plugin" / "marketplace.json").write_bytes(
        (Path(expected["path"]) / "marketplace.json").read_bytes()
    )
    markets = {
        **markets,
        OMP_MARKETPLACE: {**markets[OMP_MARKETPLACE], "sourceUri": str(prior)},
    }
    snapshot = (root, markets, registry, runtime, cli)
    add_calls = []
    real_command = adapter._command

    def fake_command(argv, **kwargs):
        if tuple(argv[:4]) == ("omp", "plugin", "marketplace", "add"):
            add_calls.append(tuple(argv))
            if len(add_calls) == 1:
                raise OSError("forward add boom")
            raise OmpInventoryError("restore add boom")
        return real_command(argv, **kwargs)

    monkeypatch.setattr(adapter, "_command", fake_command)
    try:
        OmpSourceMixin._replace_source(adapter, desired, snapshot, entries)
    except OmpInventoryError as error:
        message = str(error)
    else:
        raise AssertionError("source replacement must fail")
    assert len(add_calls) == 2, add_calls
    assert "restore diagnostic" in message and "restore add boom" in message, message


def test_snapshot_failure_after_source_replacement_is_not_stuck(tmp_path: Path):
    """A failed capture after source replacement must not strand the receipt."""
    _desired, adapter, runner, _service = setup_install(tmp_path, git=True)
    target = make_desired(tmp_path / "next", "1.0.1", git=True)
    update = make_service(tmp_path, adapter, target)
    armed = []

    def arm(command, _root):
        if command[1:4] == ("plugin", "marketplace", "add") and not armed:
            armed.append(command)
            runner.fail(("omp", "plugin", "list", "--json"))

    runner.callback = arm
    first = update.reconcile(apply=True)
    runner.callback = None
    assert armed, "source replacement add never ran"
    assert first.state is not ResultState.READY

    second = update.reconcile(apply=True)
    assert second.state is ResultState.READY, second.errors
    live_source = adapter._snapshot()[1]["manifest"]["sourceUri"]
    assert live_source == str(target.release_root.resolve())
    assert _marketplace_source(update) == live_source
    assert update.reconcile().state is ResultState.READY


def _stranded_replacement(tmp_path):
    """Leave a signed pending source intent by failing capture after replacement."""
    _desired, adapter, runner, service = setup_install(tmp_path, git=True)
    old_source = _marketplace_source(service)
    target = make_desired(tmp_path / "next", "1.0.1", git=True)
    update = make_service(tmp_path, adapter, target)
    armed = []

    def arm(command, _root):
        if command[1:4] == ("plugin", "marketplace", "add") and not armed:
            armed.append(command)
            runner.fail(("omp", "plugin", "list", "--json"))

    runner.callback = arm
    assert update.reconcile(apply=True).state is not ResultState.READY
    runner.callback = None
    assert armed and _marketplace_source(update) == old_source
    return adapter, update, target, old_source


def _assert_pending_refused(adapter, update, target, old_source):
    desired = with_prior_harness_receipts(target, read_receipt(update.receipt_path))
    prior = adapter._prior_receipt(desired)
    entries = adapter._authenticated_entries(prior)
    assert not owned_marketplace_matches(adapter, adapter._snapshot(), entries)
    with pytest.raises(OmpInventoryError, match="changed after signing"):
        adapter._preflight(desired, prior)
    assert update.reconcile(apply=True).state is not ResultState.READY
    assert _marketplace_source(update) == old_source


def test_pending_source_refuses_live_source_other_than_intent(tmp_path: Path):
    adapter, update, target, old_source = _stranded_replacement(tmp_path)
    other = make_desired(tmp_path / "other", "1.0.1", git=True)
    adapter._command(("omp", "plugin", "marketplace", "remove", "manifest"))
    adapter._command(
        ("omp", "plugin", "marketplace", "add", str(other.release_root.resolve()))
    )
    _assert_pending_refused(adapter, update, target, old_source)


def test_pending_source_refuses_catalog_other_than_intent(tmp_path: Path):
    adapter, update, target, old_source = _stranded_replacement(tmp_path)
    catalog = (
        adapter._native_root() / "plugins/cache/marketplaces/manifest/marketplace.json"
    )
    document = json.loads(catalog.read_text())
    document["description"] = "tampered after replacement"
    catalog.write_text(json.dumps(document))
    _assert_pending_refused(adapter, update, target, old_source)


def test_pending_source_refuses_owned_plugin_non_source_drift(tmp_path: Path):
    adapter, update, target, old_source = _stranded_replacement(tmp_path)
    plugin = next(
        entry for entry in owned(update).owned_entries if entry.kind == PLUGIN_KIND
    )
    (Path(plugin.target_path) / "drift.txt").write_text("not from the release")
    _assert_pending_refused(adapter, update, target, old_source)

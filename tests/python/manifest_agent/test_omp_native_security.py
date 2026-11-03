"""Behavioral no-adoption, exact authority, CAS, and recovery-tree regressions."""

import json
from dataclasses import replace
from pathlib import Path

import pytest

from manifest_agent.adapters.omp_identity import MARKETPLACE_KIND, PLUGIN_KIND
from manifest_agent.adapters.omp_inventory import directory_sha256
from manifest_agent.models import ResultState
from manifest_agent.state import read_receipt
from tests.python.manifest_agent._omp_native_fixture import (
    get_json,
    make_adapter,
    make_desired,
    make_service,
    put_json,
)
from tests.python.manifest_agent.test_omp_native_lifecycle import (
    owned,
    setup_install,
    trees,
)


def plugin_entry(service, name="manifest-docs"):
    return next(
        entry
        for entry in owned(service).owned_entries
        if entry.kind == PLUGIN_KIND and entry.identifier == f"{name}@manifest"
    )


def test_post_receipt_inside_cache_sentinel_blocks_all_removal(tmp_path):
    _desired, _adapter, runner, service = setup_install(tmp_path)
    cache = Path(plugin_entry(service).target_path)
    sentinel = cache / "user-sentinel"
    sentinel.write_bytes(b"unowned content\n")
    before = tuple(runner.mutations)
    result = service.uninstall()
    assert result.state is ResultState.BLOCKED
    assert tuple(runner.mutations) == before
    assert sentinel.read_bytes() == b"unowned content\n"
    assert read_receipt(service.receipt_path) is not None


@pytest.mark.parametrize("field", ["version", "source", "runtime", "settings", "link"])
def test_live_native_identity_changes_never_authorize_removal(tmp_path, field):
    _desired, adapter, runner, service = setup_install(tmp_path)
    root = adapter._native_root()
    if field == "version":
        path = root / "plugins/installed_plugins.json"
        document = get_json(path, {})
        document["plugins"]["manifest-docs@manifest"][0]["version"] = "9.9.9"
    elif field == "source":
        path = root / "marketplaces.json"
        document = get_json(path, {})
        document["marketplaces"][0]["sourceUri"] = str(tmp_path / "foreign")
    elif field in {"runtime", "settings"}:
        path = root / "plugins/omp-plugins.lock.json"
        document = get_json(path, {})
        if field == "runtime":
            document["plugins"]["@manifest/manifest-docs"]["enabledFeatures"] = ["user"]
        else:
            document["settings"]["@manifest/manifest-docs"] = {"retain": "user"}
    else:
        path = root / "plugins/node_modules/@manifest/manifest-docs"
        path.unlink()
        path.symlink_to(tmp_path)
        document = None
    if document is not None:
        put_json(path, document)
    before = tuple(runner.mutations)
    assert service.uninstall().state is ResultState.BLOCKED
    assert tuple(runner.mutations) == before
    assert service.receipt_path.exists()


def test_unsigned_and_tampered_direct_adapter_receipts_cannot_mutate(tmp_path):
    _desired, adapter, runner, service = setup_install(tmp_path)
    receipt = owned(service)
    unsigned = replace(
        receipt,
        owned_entries=tuple(
            entry for entry in receipt.owned_entries if entry.kind != "omp-receipt-auth"
        ),
    )
    before = tuple(runner.mutations)
    assert adapter.uninstall(unsigned).state is ResultState.BLOCKED
    altered = replace(plugin_entry(service), target_path=str(tmp_path / "outside"))
    tampered = replace(
        receipt,
        owned_entries=tuple(
            altered if entry == plugin_entry(service) else entry
            for entry in receipt.owned_entries
        ),
    )
    assert adapter.uninstall(tampered).state is ResultState.BLOCKED
    assert tuple(runner.mutations) == before


def test_custom_receipt_parent_authority_is_bound_not_guessed(tmp_path):
    desired, adapter, runner, service = setup_install(tmp_path)
    receipt = owned(service)
    assert (service.receipt_path.parent / "ownership.key").is_file()
    assert not (tmp_path / "state/manifest/ownership.key").exists()
    other, _unused = make_adapter(tmp_path, runner)
    before = tuple(runner.mutations)
    assert other.uninstall(receipt).state is ResultState.BLOCKED
    assert tuple(runner.mutations) == before
    assert (
        adapter.install(replace(desired, prior_harness_receipts=(receipt,))).state
        is ResultState.READY
    )


def test_mutation_boundary_cache_edit_is_refused_without_resigning(tmp_path):
    desired, adapter, runner, service = setup_install(tmp_path)
    receipt = owned(service)
    cache = Path(plugin_entry(service).target_path)

    def mutate(identifier):
        if identifier == "manifest-docs@manifest":
            (cache / "concurrent-user-file").write_bytes(b"keep\n")

    adapter._native_mutation_boundary = mutate
    before = tuple(runner.mutations)
    result = service.uninstall()
    assert result.state is ResultState.BLOCKED
    assert not any(
        command
        == ("omp", "plugin", "uninstall", "manifest-docs@manifest", "--scope", "user")
        for command in runner.mutations[len(before) :]
    )
    assert (cache / "concurrent-user-file").read_bytes() == b"keep\n"
    assert owned(service).owned_entries == receipt.owned_entries
    assert adapter.inspect(desired).native_inspection is not None


def test_boundary_source_registration_change_is_not_recovered_as_owned(tmp_path):
    _desired, adapter, runner, _service = setup_install(tmp_path)
    target = make_desired(tmp_path / "next", "1.0.1")
    registry_path = adapter._native_root() / "marketplaces.json"

    def mutate(identifier):
        if identifier == "manifest":
            document = get_json(registry_path, {})
            document["marketplaces"][0]["sourceUri"] = str(tmp_path / "foreign")
            put_json(registry_path, document)

    adapter._native_mutation_boundary = mutate
    before = tuple(runner.mutations)
    update = make_service(tmp_path, adapter, target)
    assert update.reconcile(apply=True).state is ResultState.BLOCKED
    assert tuple(runner.mutations) == before
    assert get_json(registry_path, {})["marketplaces"][0]["sourceUri"] == str(
        tmp_path / "foreign"
    )


def test_restoration_collision_retains_real_recovery_tree_and_concurrent_data(tmp_path):
    _desired, adapter, runner, service = setup_install(tmp_path)
    cache = Path(plugin_entry(service).target_path)
    digest = directory_sha256(cache)
    injected = False

    def occupy(command, root):
        nonlocal injected
        if command[1:4] == ("plugin", "uninstall", "manifest-docs@manifest"):
            injected = True
            cache.mkdir()
            (cache / "concurrent-user-file").write_bytes(b"keep\n")

    runner.callback = occupy
    result = service.uninstall()
    assert injected
    assert result.state is ResultState.BLOCKED
    assert any("recovery retained" in error for error in result.harnesses["omp"].errors)
    recoveries = tuple(cache.parent.glob(f".{cache.name}.manifest-preserve-*"))
    assert len(recoveries) == 1
    assert directory_sha256(recoveries[0]) == digest
    assert (cache / "concurrent-user-file").read_bytes() == b"keep\n"
    assert service.receipt_path.exists()
    assert adapter._snapshot()[0] == tmp_path / "home/.omp"


def test_target_cache_collision_rejects_upgrade_before_source_mutation(tmp_path):
    _desired, adapter, runner, service = setup_install(tmp_path)
    target = make_desired(tmp_path / "next", "1.0.1")
    collision = (
        adapter._native_root()
        / "plugins/cache/plugins/manifest___manifest-docs___1.0.1"
    )
    collision.mkdir()
    (collision / "user").write_bytes(b"keep\n")
    before = tuple(runner.mutations)
    result = make_service(tmp_path, adapter, target).reconcile(apply=True)
    assert result.state is ResultState.BLOCKED
    assert tuple(runner.mutations) == before
    assert (collision / "user").read_bytes() == b"keep\n"
    assert read_receipt(service.receipt_path).release_version == "1.0.0"


def test_same_version_changed_source_is_rejected_before_registration_change(tmp_path):
    _desired, adapter, runner, _service = setup_install(tmp_path)
    target = make_desired(tmp_path / "next")
    (target.bundle_path("manifest-docs") / "user-visible-content").write_text("changed\n")
    before = tuple(runner.mutations)
    result = make_service(tmp_path, adapter, target).reconcile(apply=True)
    assert result.state is ResultState.BLOCKED
    assert tuple(runner.mutations) == before
    assert any("same-version" in error for error in result.harnesses["omp"].errors)


def test_foreign_same_marketplace_reference_preserves_catalog_on_removal(tmp_path):
    _desired, adapter, runner, service = setup_install(tmp_path)
    path = adapter._native_root() / "plugins/installed_plugins.json"
    registry = get_json(path, {})
    registry["plugins"]["foreign@manifest"] = [
        {"scope": "user", "version": "1", "installPath": "/foreign"}
    ]
    put_json(path, registry)
    result = service.uninstall()
    assert result.state is ResultState.READY
    assert result.harnesses["omp"].warnings
    assert "manifest" in adapter._snapshot()[1]
    assert not any(command[2:4] == ("marketplace", "remove") for command in runner.mutations)


def test_foreign_reference_blocks_owned_source_rebind_before_mutation(tmp_path):
    _desired, adapter, runner, _service = setup_install(tmp_path)
    path = adapter._native_root() / "plugins/installed_plugins.json"
    registry = get_json(path, {})
    registry["plugins"]["foreign@manifest"] = [
        {"scope": "user", "version": "1", "installPath": "/foreign"}
    ]
    put_json(path, registry)
    target = make_desired(tmp_path / "next", "1.0.1")
    before = tuple(runner.mutations)
    result = make_service(tmp_path, adapter, target).reconcile(apply=True)
    assert result.state is ResultState.BLOCKED
    assert tuple(runner.mutations) == before


def test_symlinked_native_cache_and_initialized_xdg_layout_refuse_mutation(tmp_path):
    desired = make_desired(tmp_path / "release")
    adapter, runner = make_adapter(tmp_path)
    root = adapter._native_root()
    root.mkdir()
    (root / "plugins").symlink_to(tmp_path / "foreign")
    assert adapter.install(desired).state is ResultState.BLOCKED
    assert not runner.mutations
    (root / "plugins").unlink()
    xdg = tmp_path / "data"
    (xdg / "omp").mkdir(parents=True)
    adapter._env["XDG_DATA_HOME"] = str(xdg)
    assert adapter.inspect(desired).state is ResultState.BLOCKED
    assert not runner.mutations


def test_signed_record_path_escape_is_rejected_even_with_correct_full_auth(tmp_path):
    _desired, adapter, runner, service = setup_install(tmp_path)
    receipt = owned(service)
    entry = plugin_entry(service)
    identity = json.loads(entry.previous_checksum)
    identity["path"] = str(tmp_path / "foreign")
    forged = replace(
        entry, target_path=identity["path"], previous_checksum=json.dumps(identity)
    )
    receipt = replace(
        receipt,
        owned_entries=tuple(
            forged if item == entry else item for item in receipt.owned_entries
        ),
    )
    receipt = adapter.authenticate_provisional_receipt(receipt)
    before = tuple(runner.mutations)
    assert adapter.uninstall(receipt).state is ResultState.BLOCKED
    assert tuple(runner.mutations) == before
    assert any(entry.kind == MARKETPLACE_KIND for entry in owned(service).owned_entries)
    assert trees(owned(service))

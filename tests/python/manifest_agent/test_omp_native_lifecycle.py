"""Production OmpAdapter and ManifestService lifecycle against stateful native IO."""

from dataclasses import replace
from pathlib import Path

import pytest

from manifest_agent.adapters.omp_identity import (
    MARKETPLACE_KIND,
    PLUGIN_KIND,
    decode_identity,
)
from manifest_agent.adapters.omp_inventory import directory_sha256
from manifest_agent.models import ResultState
from manifest_agent.ownership import omp_receipt_ownership_errors
from manifest_agent.state import read_receipt
from tests.python.manifest_agent._omp_native_fixture import (
    get_json,
    make_adapter,
    make_desired,
    make_service,
    put_json,
    with_receipt,
)


def setup_install(tmp_path, *, git=False, automatic=False):
    desired = make_desired(tmp_path / "release", git=git)
    adapter, runner = make_adapter(tmp_path)
    service = make_service(tmp_path, adapter, desired, automatic=automatic)
    result = service.install()
    assert result.state is ResultState.READY
    return desired, adapter, runner, service


def owned(service):
    return read_receipt(service.receipt_path).harnesses["omp"]


def trees(receipt):
    return {
        Path(entry.target_path): directory_sha256(Path(entry.target_path))
        for entry in receipt.owned_entries
        if entry.kind in {MARKETPLACE_KIND, PLUGIN_KIND}
    }


@pytest.mark.parametrize("automatic", [False, True])
def test_explicit_and_conservative_automatic_selection(tmp_path, automatic):
    _desired, _adapter, runner, service = setup_install(tmp_path, automatic=automatic)
    receipt = owned(service)
    assert len(receipt.plugin_ids) == 9
    assert receipt.verified
    assert any(command == ("/native/omp", "--version") for command in runner.calls)
    assert all(context[1] == tmp_path for context in runner.contexts)
    assert omp_receipt_ownership_errors(
        receipt, key_path=service.receipt_path.parent / "ownership.key"
    ) == ()
    assert not (tmp_path / "home/.claude").exists()


def test_immutable_git_provenance_uses_verified_local_release_root(tmp_path):
    desired, _adapter, runner, service = setup_install(tmp_path, git=True)
    assert (
        "omp",
        "plugin",
        "marketplace",
        "add",
        str(desired.release_root),
    ) in runner.mutations
    assert not any(
        desired.marketplace_source.source in command for command in runner.calls
    )
    identity = next(
        decode_identity(entry)
        for entry in owned(service).owned_entries
        if entry.kind == MARKETPLACE_KIND
    )
    assert identity["source"] == str(desired.release_root)
    assert read_receipt(service.receipt_path).source_commit == desired.source_commit


def test_initial_install_never_adopts_existing_unowned_native_plugin(tmp_path):
    desired = make_desired(tmp_path / "release")
    adapter, runner = make_adapter(tmp_path)
    adapter._command(("omp", "plugin", "marketplace", "add", str(desired.release_root)))
    adapter._command(
        ("omp", "plugin", "install", "manifest-docs@manifest", "--scope", "user")
    )
    before = adapter._identity(adapter._snapshot(), "manifest-docs@manifest")
    service = make_service(tmp_path, adapter, desired)
    result = service.install()
    assert result.state is ResultState.BLOCKED
    receipt = owned(service)
    assert "manifest-docs@manifest" not in receipt.plugin_ids
    assert len(receipt.plugin_ids) == 8
    assert not any(entry.kind == MARKETPLACE_KIND for entry in receipt.owned_entries)
    assert adapter._identity(adapter._snapshot(), "manifest-docs@manifest") == before
    assert service.uninstall().state is ResultState.READY
    assert adapter._identity(adapter._snapshot(), "manifest-docs@manifest") == before
    assert "manifest" in adapter._snapshot()[1]
    assert not any(command[2] == "upgrade" for command in runner.mutations)


def test_differing_unowned_marketplace_is_not_removed_or_replaced(tmp_path):
    desired = make_desired(tmp_path / "desired")
    other = make_desired(tmp_path / "other")
    adapter, runner = make_adapter(tmp_path)
    adapter._command(("omp", "plugin", "marketplace", "add", str(other.release_root)))
    before = tuple(runner.mutations)
    result = make_service(tmp_path, adapter, desired).install()
    assert result.state is ResultState.BLOCKED
    assert tuple(runner.mutations) == before
    assert adapter._snapshot()[1]["manifest"]["sourceUri"] == str(other.release_root)


def test_partial_native_install_records_creations_and_repairs_missing_packages(tmp_path):
    desired = make_desired(tmp_path / "release")
    adapter, runner = make_adapter(tmp_path)
    runner.fail(("omp", "plugin", "install", "manifest-docs@manifest", "--scope", "user"))
    service = make_service(tmp_path, adapter, desired)
    result = service.install()
    assert result.state is ResultState.BLOCKED
    partial = owned(service)
    assert not partial.verified
    assert partial.errors
    assert len(partial.plugin_ids) == 8
    assert any(entry.kind == MARKETPLACE_KIND for entry in partial.owned_entries)
    assert omp_receipt_ownership_errors(
        partial, key_path=service.receipt_path.parent / "ownership.key"
    ) == ()
    assert service.reconcile(apply=True).state is ResultState.READY
    repaired = owned(service)
    assert repaired.verified
    assert len(repaired.plugin_ids) == 9
    assert service.uninstall().state is ResultState.READY


def test_native_command_failure_after_creation_preserves_partial_authority(tmp_path):
    desired = make_desired(tmp_path / "release")
    adapter, runner = make_adapter(tmp_path)
    runner.fail(
        ("omp", "plugin", "install", "manifest-docs@manifest", "--scope", "user"),
        after=True,
    )
    service = make_service(tmp_path, adapter, desired)
    assert service.install().state is ResultState.BLOCKED
    receipt = owned(service)
    assert "manifest-docs@manifest" in receipt.plugin_ids
    assert not receipt.verified
    assert service.uninstall().state is ResultState.READY


def test_owned_upgrade_replaces_receipt_identity_and_preserves_every_old_cache(tmp_path):
    desired, adapter, runner, service = setup_install(tmp_path, git=True)
    prior = owned(service)
    old_trees = trees(prior)
    target = make_desired(tmp_path / "next", "1.0.1", git=True)
    update = make_service(tmp_path, adapter, target)
    assert update.reconcile().state is ResultState.DRIFTED
    assert update.reconcile(apply=True).state is ResultState.READY
    current = owned(update)
    assert current.verified
    identities = [
        decode_identity(entry)
        for entry in current.owned_entries
        if entry.kind == PLUGIN_KIND
    ]
    assert {item["version"] for item in identities} == {"1.0.1", "0.2.4"}
    assert all(item["source"] == str(target.release_root) for item in identities)
    old_packages = {
        path: digest
        for path, digest in old_trees.items()
        if "cache/plugins" in str(path)
    }
    assert {path: directory_sha256(path) for path in old_packages} == old_packages
    assert read_receipt(update.receipt_path).release_version == "1.0.1"
    assert len([command for command in runner.mutations if command[2] == "upgrade"]) == 8
    new_trees = trees(current)
    assert update.uninstall().state is ResultState.READY
    assert {path: directory_sha256(path) for path in new_trees} == new_trees
    assert not adapter._snapshot()[2]
    assert not adapter._snapshot()[3]["plugins"]
    assert desired.release_version == "1.0.0"


def test_partial_upgrade_persists_new_native_proofs_without_false_release_commit(tmp_path):
    _desired, adapter, runner, service = setup_install(tmp_path)
    prior = owned(service)
    target = make_desired(tmp_path / "next", "1.0.1")
    runner.fail(("omp", "plugin", "upgrade", "manifest-docs@manifest", "--scope", "user"))
    update = make_service(tmp_path, adapter, target)
    assert update.reconcile(apply=True).state is ResultState.BLOCKED
    partial = read_receipt(update.receipt_path)
    assert partial.release_version == "1.0.0"
    assert not partial.harnesses["omp"].verified
    identities = {
        entry.identifier: decode_identity(entry)
        for entry in partial.harnesses["omp"].owned_entries
        if entry.kind == PLUGIN_KIND
    }
    assert identities["manifest-docs@manifest"]["version"] == "1.0.0"
    assert identities["manifest-workspace@manifest"]["version"] == "1.0.1"
    assert identities["manifest-workspace@manifest"]["source"] == str(target.release_root)
    assert partial.harnesses["omp"].owned_entries != prior.owned_entries
    assert update.reconcile(apply=True).state is ResultState.READY
    assert owned(update).verified
    assert update.uninstall().state is ResultState.READY


def test_source_replacement_native_failure_restores_prior_registration(tmp_path):
    desired, adapter, runner, service = setup_install(tmp_path)
    target = make_desired(tmp_path / "next", "1.0.1")
    runner.fail(("omp", "plugin", "marketplace", "add", str(target.release_root)))
    before = trees(owned(service))
    update = make_service(tmp_path, adapter, target)
    assert update.reconcile(apply=True).state is ResultState.BLOCKED
    assert adapter._snapshot()[1]["manifest"]["sourceUri"] == str(desired.release_root)
    assert {path: directory_sha256(path) for path in before} == before
    assert update.uninstall().state is ResultState.READY


def test_foreign_native_rows_settings_and_outside_sentinels_survive_unregister(tmp_path):
    _desired, adapter, _runner, service = setup_install(tmp_path)
    root = adapter._native_root()
    registry_path = root / "plugins/installed_plugins.json"
    lock_path = root / "plugins/omp-plugins.lock.json"
    registry = get_json(registry_path, {})
    registry["plugins"]["foreign@elsewhere"] = [
        {"scope": "user", "version": "4", "installPath": "/foreign"}
    ]
    put_json(registry_path, registry)
    lock = get_json(lock_path, {})
    lock["plugins"]["foreign"] = {"version": "4", "enabled": False}
    lock["settings"]["foreign"] = {"retain": True}
    put_json(lock_path, lock)
    sentinel = root / "plugins/cache/foreign-sentinel"
    sentinel.write_bytes(b"user data\n")
    caches = trees(owned(service))
    assert service.uninstall().state is ResultState.READY
    assert sentinel.read_bytes() == b"user data\n"
    after = adapter._snapshot()
    assert after[2]["foreign@elsewhere"] == registry["plugins"]["foreign@elsewhere"]
    assert after[3]["settings"]["foreign"] == {"retain": True}
    assert after[3]["plugins"]["foreign"]["enabled"] is False
    assert {path: directory_sha256(path) for path in caches} == caches


def test_native_uninstall_failure_restores_cache_and_can_resume_owned_cleanup(tmp_path):
    _desired, adapter, runner, service = setup_install(tmp_path)
    caches = trees(owned(service))
    runner.fail(
        ("omp", "plugin", "uninstall", "manifest-docs@manifest", "--scope", "user"),
        after=True,
    )
    result = service.uninstall()
    assert result.state is ResultState.BLOCKED
    assert service.receipt_path.exists()
    assert {path: directory_sha256(path) for path in caches} == caches
    assert service.uninstall().state is ResultState.READY
    assert not adapter._snapshot()[2]


def test_marketplace_unregister_failure_after_mutation_can_resume_without_cache_loss(
    tmp_path,
):
    _desired, adapter, runner, service = setup_install(tmp_path)
    receipt = read_receipt(service.receipt_path)
    caches = trees(receipt.harnesses["omp"])
    sentinel = adapter._native_root() / "plugins/cache/foreign-sentinel"
    sentinel.write_bytes(b"keep user cache data\n")
    runner.fail(("omp", "plugin", "marketplace", "remove", "manifest"), after=True)
    assert service.uninstall().state is ResultState.BLOCKED
    assert read_receipt(service.receipt_path) == receipt
    assert not adapter._snapshot()[1]
    assert not adapter._snapshot()[2]
    assert not adapter._snapshot()[3]["plugins"]
    assert {path: directory_sha256(path) for path in caches} == caches
    before = tuple(runner.mutations)

    assert service.uninstall().state is ResultState.READY
    assert tuple(runner.mutations) == before
    assert not service.receipt_path.exists()
    after = adapter._snapshot()
    assert not after[1]
    assert not after[2]
    assert not after[3]["plugins"]
    assert {path: directory_sha256(path) for path in caches} == caches
    assert sentinel.read_bytes() == b"keep user cache data\n"


@pytest.mark.parametrize(
    "change", ["marketplace-cache", "plugin-cache", "registration", "native-root"]
)
def test_marketplace_unregister_retry_refuses_changed_authenticated_state(tmp_path, change):
    _desired, adapter, runner, service = setup_install(tmp_path)
    receipt = read_receipt(service.receipt_path)
    native = receipt.harnesses["omp"]
    caches = trees(native)
    root = adapter._native_root()
    market = dict(adapter._snapshot()[1]["manifest"])
    runner.fail(("omp", "plugin", "marketplace", "remove", "manifest"), after=True)
    assert service.uninstall().state is ResultState.BLOCKED
    if change in {"marketplace-cache", "plugin-cache"}:
        kind = MARKETPLACE_KIND if change == "marketplace-cache" else PLUGIN_KIND
        entry = next(item for item in native.owned_entries if item.kind == kind)
        (Path(entry.target_path) / "user-data").write_bytes(b"keep changed cache\n")
    elif change == "registration":
        market["sourceUri"] = str(tmp_path / "foreign")
        put_json(root / "marketplaces.json", {"version": 1, "marketplaces": [market]})
    else:
        adapter._env = {**adapter._env, "HOME": str(tmp_path / "other-home")}
    retained = {path: directory_sha256(path) for path in caches}
    before = tuple(runner.mutations)

    assert service.uninstall().state is ResultState.BLOCKED
    assert tuple(runner.mutations) == before
    assert read_receipt(service.receipt_path) == receipt
    assert {path: directory_sha256(path) for path in caches} == retained


@pytest.mark.parametrize("change", ["foreign-registration", "runtime", "link"])
def test_marketplace_unregister_retry_refuses_stale_native_plugin_state(tmp_path, change):
    _desired, adapter, runner, service = setup_install(tmp_path)
    receipt = read_receipt(service.receipt_path)
    native = receipt.harnesses["omp"]
    caches = trees(native)
    root = adapter._native_root()
    plugin = next(
        decode_identity(entry)
        for entry in native.owned_entries
        if entry.kind == PLUGIN_KIND and entry.identifier == "manifest-docs@manifest"
    )
    runner.fail(("omp", "plugin", "marketplace", "remove", "manifest"), after=True)
    assert service.uninstall().state is ResultState.BLOCKED
    if change == "foreign-registration":
        put_json(
            root / "plugins/installed_plugins.json",
            {
                "version": 2,
                "plugins": {
                    "foreign@manifest": [
                        {"scope": "user", "version": "4", "installPath": "/foreign"}
                    ]
                },
            },
        )
    elif change == "runtime":
        path = root / "plugins/omp-plugins.lock.json"
        lock = get_json(path, {})
        lock["plugins"][plugin["runtime_name"]] = {"version": "1.0.0", "enabled": True}
        put_json(path, lock)
    else:
        Path(plugin["link_path"]).symlink_to(plugin["path"])
    before = tuple(runner.mutations)
    inventory = adapter._snapshot()[1:]

    assert service.uninstall().state is ResultState.BLOCKED
    assert tuple(runner.mutations) == before
    assert read_receipt(service.receipt_path) == receipt
    assert adapter._snapshot()[1:] == inventory
    assert {path: directory_sha256(path) for path in caches} == caches
    if change == "link":
        assert Path(plugin["link_path"]).readlink() == Path(plugin["path"])


def test_owned_disabled_package_upgrade_preserves_native_disabled_state(tmp_path):
    desired, adapter, _runner, service = setup_install(tmp_path)
    # Disabled state existed before this exact authorized receipt was issued.
    root = adapter._native_root()
    registry_path = root / "plugins/installed_plugins.json"
    lock_path = root / "plugins/omp-plugins.lock.json"
    registry = get_json(registry_path, {})
    registry["plugins"]["manifest-docs@manifest"][0]["enabled"] = False
    put_json(registry_path, registry)
    lock = get_json(lock_path, {})
    lock["plugins"]["@manifest/manifest-docs"]["enabled"] = False
    put_json(lock_path, lock)
    from manifest_agent.adapters.omp_identity import identity_entry
    from manifest_agent.state import write_receipt_atomic

    receipt = read_receipt(service.receipt_path)
    prior = receipt.harnesses["omp"]
    current = adapter._identity(adapter._snapshot(), "manifest-docs@manifest")
    entries = tuple(
        entry
        for entry in prior.owned_entries
        if entry.identifier != "manifest-docs@manifest"
        and entry.kind != "omp-receipt-auth"
    )
    updated = replace(
        prior,
        owned_entries=(
            *entries,
            identity_entry(PLUGIN_KIND, "manifest-docs@manifest", current),
        ),
    )
    updated = adapter.authenticate_provisional_receipt(updated)
    write_receipt_atomic(
        service.receipt_path, replace(receipt, harnesses={"omp": updated})
    )
    target = make_desired(tmp_path / "next", "1.0.1")
    result = adapter.install(with_receipt(target, owned(service)))
    assert result.state is ResultState.DRIFTED
    assert adapter._snapshot()[3]["plugins"]["@manifest/manifest-docs"]["enabled"] is False
    assert adapter.inspect(desired).state is not ResultState.READY


def test_durable_transaction_rejection_happens_before_any_native_mutation(tmp_path):
    desired, adapter, runner, service = setup_install(tmp_path)
    target = make_desired(tmp_path / "next", "1.0.1")
    before = tuple(runner.mutations)
    with pytest.raises(ValueError, match="no mutation performed"):
        adapter.prepare_reconcile(owned(service), desired, target)
    assert tuple(runner.mutations) == before
    assert adapter.inspect(desired).state is ResultState.READY

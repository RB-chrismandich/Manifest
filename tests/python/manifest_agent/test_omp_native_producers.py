"""Actual service, migration, shadow, and mutation-boundary ownership producers."""

from dataclasses import dataclass, field, replace
from pathlib import Path

from manifest_agent.adapters.omp import OmpAdapter
from manifest_agent.adapters.omp_identity import (
    MARKETPLACE_KIND,
    PLUGIN_KIND,
    decode_identity,
)
from manifest_agent.adapters.omp_inventory import directory_sha256
from manifest_agent.migration import (
    LegacyInventoryEntry,
    MigrationService,
    OwnershipProof,
)
from manifest_agent.models import DesiredState, HarnessReceipt, ResultState
from manifest_agent.ownership import omp_receipt_ownership_errors
from manifest_agent.paths import xdg_paths
from manifest_agent.service import ManifestService
from manifest_agent.service_state import bundle_checksums
from manifest_agent.state import _decode_harness, read_receipt
from tests.python.manifest_agent._omp_native_fixture import (
    NativeRunner,
    get_json,
    make_adapter,
    make_desired,
    make_service,
    put_json,
)


def migration_for(tmp_path, service):
    home = tmp_path / "home"
    return MigrationService.from_manifest_service(
        service,
        paths=xdg_paths({"HOME": str(home)}),
        home=home,
    )


def test_actual_service_populates_source_integrity_and_prior_context(tmp_path):
    desired = make_desired(tmp_path / "release")
    adapter, _runner = make_adapter(tmp_path)
    service = make_service(tmp_path, adapter, desired)
    selected, error = service._desired_state()
    assert error is None
    assert dict(selected.source_bundle_checksums) == bundle_checksums(selected)
    assert len(selected.source_bundle_checksums) == 9
    assert selected.source_catalog_sha256 == desired.source_catalog_sha256
    assert service.install().state is ResultState.READY
    receipt = read_receipt(service.receipt_path).harnesses["omp"]
    observed = []
    original = adapter.inspect

    def inspect(state):
        observed.append(state.prior_harness_receipts)
        return original(state)

    adapter.inspect = inspect
    assert service.reconcile().state is ResultState.READY
    assert observed and all(receipt in receipts for receipts in observed)


def test_actual_source_catalog_allows_unowned_marketplace_only_entries(tmp_path):
    desired = make_desired(tmp_path / "release")
    delegate = desired.release_root / "plugins/manifest-delegate"
    put_json(
        delegate / ".claude-plugin/plugin.json",
        {"name": "manifest-delegate", "version": "0.1.0"},
    )
    catalog_path = desired.release_root / ".claude-plugin/marketplace.json"
    catalog = get_json(catalog_path, {})
    catalog["plugins"].append(
        {
            "name": "manifest-delegate",
            "version": "0.1.0",
            "source": "./plugins/manifest-delegate",
        }
    )
    put_json(catalog_path, catalog)
    adapter, runner = make_adapter(tmp_path)
    service = make_service(tmp_path, adapter, desired)
    assert service.install().state is ResultState.READY
    receipt = read_receipt(service.receipt_path).harnesses["omp"]
    assert len(receipt.plugin_ids) == 9
    assert "manifest-delegate@manifest" not in receipt.plugin_ids
    assert not any("manifest-delegate@manifest" in command for command in runner.calls)
    assert len(adapter._snapshot()[1]) == 1


def test_changed_validated_source_is_rejected_before_initial_creation(tmp_path):
    desired = make_desired(tmp_path / "release")
    adapter, runner = make_adapter(tmp_path)
    (desired.bundle_path("manifest-docs") / "changed").write_text("user change\n")
    result = adapter.install(desired)
    assert result.state is ResultState.BLOCKED
    assert result.native_inspection.inventory_errors
    assert not runner.mutations
    assert not adapter._snapshot()[1]


def test_target_source_change_at_owned_mutation_boundary_never_unregisters(tmp_path):
    initial = make_desired(tmp_path / "release")
    adapter, runner = make_adapter(tmp_path)
    service = make_service(tmp_path, adapter, initial)
    assert service.install().state is ResultState.READY
    target = make_desired(tmp_path / "next", "1.0.1")
    before = tuple(runner.mutations)

    def change(identifier):
        if identifier == "manifest":
            (target.bundle_path("manifest-docs") / "changed").write_text("keep\n")

    adapter._native_mutation_boundary = change
    result = make_service(tmp_path, adapter, target).reconcile(apply=True)
    assert result.state is ResultState.BLOCKED
    assert tuple(runner.mutations) == before
    assert adapter._snapshot()[1]["manifest"]["sourceUri"] == str(initial.release_root)
    assert (target.bundle_path("manifest-docs") / "changed").read_text() == "keep\n"


def test_actual_migration_commits_full_creation_authority_and_isolates_shadow_key(
    tmp_path,
):
    desired = make_desired(tmp_path / "release")
    adapter, _runner = make_adapter(tmp_path)
    service = make_service(tmp_path, adapter, desired)
    migration = migration_for(tmp_path, service)
    state, error = service._desired_state()
    assert error is None
    result = migration.migrate(state)
    assert result.state is ResultState.READY
    receipt = read_receipt(service.receipt_path)
    assert receipt.migration_complete
    native = receipt.harnesses["omp"]
    assert len(native.plugin_ids) == 9
    assert sum(entry.kind == PLUGIN_KIND for entry in native.owned_entries) == 9
    assert sum(entry.kind == MARKETPLACE_KIND for entry in native.owned_entries) == 1
    assert not omp_receipt_ownership_errors(
        native, key_path=service.receipt_path.parent / "ownership.key"
    )
    shadow = migration.paths.state / "migration-shadows/omp"
    shadow_path = shadow / ".local/state/manifest/installation.json"
    shadow_native = read_receipt(shadow_path).harnesses["omp"]
    assert not omp_receipt_ownership_errors(
        shadow_native, key_path=shadow_path.parent / "ownership.key"
    )
    assert omp_receipt_ownership_errors(
        shadow_native, key_path=service.receipt_path.parent / "ownership.key"
    )
    assert adapter._ownership_key_path == service.receipt_path.parent / "ownership.key"
    assert service.uninstall().state is ResultState.READY
    assert get_json(shadow / ".omp/plugins/installed_plugins.json", {})["plugins"]


@dataclass
class _MigrationRetry:
    desired: DesiredState
    adapter: OmpAdapter
    runner: NativeRunner
    service: ManifestService
    migration: MigrationService
    state: DesiredState
    install: tuple[str, ...]
    hub: Path
    sentinel: Path
    legacy: Path
    pending: HarnessReceipt | None = None
    caches: dict[Path, str] = field(default_factory=dict)
    disabled: Path | None = None


def _new_migration_retry(tmp_path: Path) -> _MigrationRetry:
    desired = make_desired(tmp_path / "release")
    adapter, runner = make_adapter(tmp_path)
    service = make_service(tmp_path, adapter, desired)
    migration = migration_for(tmp_path, service)
    hub = tmp_path / "home/.manifest/skills"
    hub.mkdir(parents=True)
    sentinel = hub / "user-data"
    sentinel.write_bytes(b"keep legacy user data\n")
    legacy = tmp_path / "home/.omp/agent/skills"
    legacy.parent.mkdir(parents=True)
    legacy.symlink_to(hub)
    migration.inventory = replace(
        migration.inventory,
        entries=(
            *migration.inventory.entries,
            LegacyInventoryEntry(
                "omp-shared-skills",
                "skills",
                "~/.omp/agent/skills",
                ("omp",),
                "bundle-owned",
                "native-plugin-managers",
                OwnershipProof("symlink-target", "~/.manifest/skills"),
                "disable",
                "restore-symlink",
                "test_omp_native_producers.py",
            ),
        ),
    )
    original_event = migration._event
    install = ("omp", "plugin", "install", "manifest-docs@manifest", "--scope", "user")
    failed = False

    def event(name: str) -> None:
        nonlocal failed
        original_event(name)
        if name == "native-install" and not failed:
            runner.fail(install)
            failed = True

    migration._event = event
    state, error = service._desired_state()
    assert error is None
    assert state is not None
    return _MigrationRetry(
        desired,
        adapter,
        runner,
        service,
        migration,
        state,
        install,
        hub,
        sentinel,
        legacy,
    )


def _assert_initial_partial(context: _MigrationRetry) -> None:
    assert context.migration.migrate(context.state).state is ResultState.BLOCKED
    assert not context.service.receipt_path.exists()
    journal = get_json(context.migration.state_path, {})["harnesses"]["omp"]
    assert journal["phase"] == "legacy-disabled"
    pending = _decode_harness(journal["native_receipt"])
    assert not pending.verified
    assert len(pending.plugin_ids) == 8
    assert not omp_receipt_ownership_errors(
        pending, key_path=context.service.receipt_path.parent / "ownership.key"
    )
    caches = {
        Path(entry.target_path): decode_identity(entry)["tree_sha256"]
        for entry in pending.owned_entries
        if entry.kind in {MARKETPLACE_KIND, PLUGIN_KIND}
    }
    assert len(caches) == 9
    assert {path: directory_sha256(path) for path in caches} == caches
    record = next(
        item for item in journal["entries"] if item["id"] == "omp-shared-skills"
    )
    disabled = Path(record["disabled_path"])
    assert not context.legacy.is_symlink()
    assert disabled.is_symlink()
    assert disabled.resolve() == context.hub
    assert "manifest" in context.adapter._snapshot()[1]
    assert len(context.adapter._snapshot()[2]) == 8
    context.pending = pending
    context.caches = caches
    context.disabled = disabled


def _assert_exact_prior_refusal(context: _MigrationRetry) -> None:
    assert context.pending is not None and context.disabled is not None
    changed = context.desired.bundle_path("manifest-docs") / "changed"
    changed.write_bytes(b"changed source\n")
    before = tuple(context.runner.mutations)
    assert context.migration.migrate(context.state).state is ResultState.BLOCKED
    assert tuple(context.runner.mutations) == before
    refused = get_json(context.migration.state_path, {})["harnesses"]["omp"]
    refused_receipt = _decode_harness(refused["native_receipt"])
    assert refused["phase"] == "legacy-disabled"
    assert not refused_receipt.verified
    assert context.adapter._authenticated_entries(
        refused_receipt
    ) == context.adapter._authenticated_entries(context.pending)
    assert not omp_receipt_ownership_errors(
        refused_receipt,
        key_path=context.service.receipt_path.parent / "ownership.key",
    )
    assert changed.read_bytes() == b"changed source\n"
    assert context.disabled.is_symlink()
    assert not context.legacy.is_symlink()
    assert {path: directory_sha256(path) for path in context.caches} == context.caches
    changed.unlink()


def _assert_retry_after_creation_failure(context: _MigrationRetry) -> None:
    assert context.disabled is not None
    context.runner.fail(context.install, after=True)
    assert context.migration.migrate(context.state).state is ResultState.BLOCKED
    retried = get_json(context.migration.state_path, {})["harnesses"]["omp"]
    retried_receipt = _decode_harness(retried["native_receipt"])
    assert retried["phase"] == "legacy-disabled"
    assert not retried_receipt.verified
    assert len(retried_receipt.plugin_ids) == 9
    assert not omp_receipt_ownership_errors(
        retried_receipt,
        key_path=context.service.receipt_path.parent / "ownership.key",
    )
    assert not context.service.receipt_path.exists()
    assert context.disabled.is_symlink()
    assert not context.legacy.is_symlink()
    assert {path: directory_sha256(path) for path in context.caches} == context.caches


def _assert_successful_native_retry(context: _MigrationRetry) -> None:
    assert context.disabled is not None
    assert context.migration.migrate(context.state).state is ResultState.READY
    committed = read_receipt(context.service.receipt_path)
    assert committed.migration_complete
    assert committed.harnesses["omp"].verified
    assert len(committed.harnesses["omp"].plugin_ids) == 9
    assert not omp_receipt_ownership_errors(
        committed.harnesses["omp"],
        key_path=context.service.receipt_path.parent / "ownership.key",
    )
    assert (
        get_json(context.migration.state_path, {})["harnesses"]["omp"]["phase"]
        == "committed"
    )
    assert not context.legacy.is_symlink()
    assert not context.disabled.is_symlink()
    assert context.sentinel.read_bytes() == b"keep legacy user data\n"
    assert {path: directory_sha256(path) for path in context.caches} == context.caches
    assert not any(
        command[2] == "uninstall" or command[1:4] == ("plugin", "marketplace", "remove")
        for command in context.runner.mutations
    )


def test_actual_migration_retains_signed_partial_creation_for_native_retry(
    tmp_path: Path,
) -> None:
    context = _new_migration_retry(tmp_path)
    _assert_initial_partial(context)
    _assert_exact_prior_refusal(context)
    _assert_retry_after_creation_failure(context)
    _assert_successful_native_retry(context)


def test_shadow_partial_receipts_support_retry_without_actual_authority_adoption(
    tmp_path,
):
    desired = make_desired(tmp_path / "release")
    adapter, runner = make_adapter(tmp_path)
    service = make_service(tmp_path, adapter, desired)
    actual_key = adapter._ownership_key_path
    shadow = tmp_path / "shadow"
    runner.fail(
        ("omp", "plugin", "install", "manifest-docs@manifest", "--scope", "user")
    )
    assert adapter.shadow_install(desired, shadow).state is ResultState.BLOCKED
    partial = read_receipt(shadow / ".local/state/manifest/installation.json")
    assert len(partial.harnesses["omp"].plugin_ids) == 8
    assert not partial.harnesses["omp"].verified
    assert adapter.shadow_install(desired, shadow).state is ResultState.READY
    assert adapter.shadow_inspect(desired, shadow).state is ResultState.READY
    assert adapter._ownership_key_path == actual_key
    assert not service.receipt_path.exists()
    assert not adapter._snapshot()[2]


def test_missing_service_source_fingerprints_cannot_claim_native_convergence(tmp_path):
    desired = make_desired(tmp_path / "release")
    adapter, runner = make_adapter(tmp_path)
    unsupported = replace(
        desired, source_bundle_checksums=(), source_catalog_sha256=None
    )
    assert adapter.install(unsupported).state is ResultState.BLOCKED
    assert not runner.mutations


def test_marketplace_creation_failure_retains_authority_for_real_reconcile(tmp_path):
    desired = make_desired(tmp_path / "release")
    adapter, runner = make_adapter(tmp_path)
    runner.fail(
        ("omp", "plugin", "marketplace", "add", str(desired.release_root)),
        after=True,
    )
    service = make_service(tmp_path, adapter, desired)
    assert service.install().state is ResultState.BLOCKED
    partial = read_receipt(service.receipt_path).harnesses["omp"]
    assert not partial.verified
    assert not partial.plugin_ids
    assert any(entry.kind == MARKETPLACE_KIND for entry in partial.owned_entries)
    assert not omp_receipt_ownership_errors(
        partial, key_path=service.receipt_path.parent / "ownership.key"
    )
    assert service.reconcile(apply=True).state is ResultState.READY
    assert len(read_receipt(service.receipt_path).harnesses["omp"].plugin_ids) == 9


def test_created_native_row_without_runtime_link_keeps_cleanup_authority(tmp_path):
    desired = make_desired(tmp_path / "release")
    adapter, runner = make_adapter(tmp_path)

    def lose_runtime(command, root):
        if command[1:4] == ("plugin", "install", "manifest-docs@manifest"):
            path = root / "plugins/omp-plugins.lock.json"
            lock = get_json(path, {})
            lock["plugins"].pop("@manifest/manifest-docs")
            put_json(path, lock)
            (root / "plugins/node_modules/@manifest/manifest-docs").unlink()

    runner.callback = lose_runtime
    service = make_service(tmp_path, adapter, desired)
    assert service.install().state is ResultState.BLOCKED
    partial = read_receipt(service.receipt_path).harnesses["omp"]
    assert "manifest-docs@manifest" in partial.plugin_ids
    assert len(partial.plugin_ids) == 9
    assert not partial.verified
    assert not omp_receipt_ownership_errors(
        partial, key_path=service.receipt_path.parent / "ownership.key"
    )
    assert service.uninstall().state is ResultState.READY

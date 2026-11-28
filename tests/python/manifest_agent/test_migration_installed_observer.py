"""Migration publishes real archived, locked observer transactions before handoff."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path

import pytest

import manifest_agent.observer_runtime as runtime
from manifest_agent.checks import toolchain_materialize as materializer
from manifest_agent.checks.toolchain_provision import provision
from manifest_agent.migration import MigrationService
from manifest_agent.models import InstallationReceipt, ResultState
from manifest_agent.observer_runtime_identity import (
    digest,
    generation_paths,
    resolve_observer_runtime,
    runtime_roots,
)
from manifest_agent.paths import xdg_paths
from manifest_agent.service_state import bundle_checksums, with_source_fingerprints
from manifest_agent.state import installation_lock, read_receipt, write_receipt_atomic
from tests.python.manifest_agent._installed_observer_fixtures import (
    _installed_release_state,
    inventory,
)
from tests.python.manifest_agent._observer_locked_cache import offline_materializer_run
from tests.python.manifest_agent.test_migration import (
    MigrationAdapter,
    _legacy_home,
    _service,
)


def test_observer_is_prepared_before_migration_snapshot(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    import manifest_agent.migration as migration_module

    events: list[str] = []
    home, _link = _legacy_home(tmp_path)
    service = _service(tmp_path, MigrationAdapter(events))
    migration = MigrationService.from_manifest_service(
        service, paths=xdg_paths({"HOME": str(home)}), home=home, event_log=events
    )

    class Observer:
        def __init__(self, desired, receipt_path):
            del desired, receipt_path

        def __enter__(self):
            events.append("observer-ready")
            return self

        def __exit__(self, *_):
            return False

        def persist(self, receipt):
            write_receipt_atomic(service.receipt_path, receipt)
            events.append("observer-persist")

    monkeypatch.setattr(migration_module, "ObserverTransaction", Observer)
    monkeypatch.setattr(migration_module, "requires_observer", lambda desired: True)

    desired, error = service._desired_state()
    assert error is None and desired is not None
    assert migration.migrate(desired).state is ResultState.READY
    assert events.index("observer-ready") < events.index("snapshot-legacy")
    assert events.index("observer-persist") < events.index("commit-receipt")
    assert read_receipt(service.receipt_path).migration_complete


@pytest.fixture(scope="module")
def archived_migration_release(tmp_path_factory):
    # Build/extract the actual candidate archive, but deliberately do not use
    # installed_observer's already-provisioned generation.
    return _installed_release_state(tmp_path_factory.mktemp("migration-release"))


def _use_locked_provision(project, monkeypatch):
    lock = json.loads((project / "uv-toolchain.lock.json").read_bytes())
    pin = lock["tools"]["uv"]["platforms"][runtime.platform_id()]
    archive = Path(os.environ["MANIFEST_TEST_UV_ARCHIVE"]).read_bytes()
    assert digest(archive) == pin["sha256"]

    def fetch(url):
        assert url == pin["url"], "migration acquired outside the locked UV fixture"
        return archive

    def locked_provision(*args, **kwargs):
        return provision(*args, **kwargs, fetcher=fetch)

    monkeypatch.setattr(runtime, "provision", locked_provision)
    monkeypatch.setattr(
        materializer, "_run", offline_materializer_run(materializer._run)
    )


@pytest.fixture
def archived_migration(archived_migration_release, tmp_path, monkeypatch):
    _source, release_env, _release, archived = archived_migration_release
    env = dict(release_env)
    home, link = _legacy_home(tmp_path)
    env["HOME"] = str(home)
    for name in ("CACHE", "DATA", "STATE", "CONFIG"):
        env[f"XDG_{name}_HOME"] = str(tmp_path / name.lower())
    for name, value in env.items():
        monkeypatch.setenv(name, value)
    for name in (
        "PYTHONPATH",
        "PYTHONHOME",
        "PYTHONDONTWRITEBYTECODE",
        "PYTHONPYCACHEPREFIX",
    ):
        monkeypatch.delenv(name, raising=False)
    desired = replace(archived, requested_harnesses=("claude",))
    _use_locked_provision(desired.release_root / runtime.PROJECT, monkeypatch)
    events = []
    adapter = MigrationAdapter(events)
    held = []

    @contextmanager
    def locked(path):
        with installation_lock(path):
            held.append(path)
            try:
                yield path
            finally:
                held.pop()

    migration = MigrationService(
        adapters={"claude": adapter},
        receipt_path=tmp_path / "authority/installation.json",
        paths=xdg_paths(env),
        lock_factory=locked,
        harness_order=("claude",),
        home=home,
        event_log=events,
    )
    prepare = runtime.prepare_observer_runtime

    def prepare_locked(selected, *, receipt_path):
        assert held == [receipt_path.parent / "install.lock"]
        assert "snapshot-legacy" not in events
        assert "disable-legacy" not in events
        binding = prepare(selected, receipt_path=receipt_path)
        events.append("observer-ready")
        return binding

    monkeypatch.setattr(runtime, "prepare_observer_runtime", prepare_locked)
    assert all(not root.exists() for root in runtime_roots(env))
    return migration, desired, env, link, events, adapter


def _assert_installed_runtime(migration, desired, env):
    receipt = read_receipt(migration.receipt_path)
    assert receipt is not None and receipt.migration_complete
    assert receipt.bundle_checksums == bundle_checksums(desired)
    backup = Path(receipt.migration_backup)
    assert (backup / "recovery.json").is_file()
    assert (backup / "restore.py").stat().st_mode & 0o777 == 0o700
    interpreter = resolve_observer_runtime(
        desired.bundle_path("manifest-workspace"),
        receipt_path=migration.receipt_path,
        environ=env,
    )
    result = subprocess.run(
        [
            str(interpreter),
            "-I",
            "-B",
            "-c",
            "import pathlib, sys, manifest_agent; "
            "assert pathlib.Path(manifest_agent.__file__).resolve().is_relative_to(pathlib.Path(sys.prefix)); "
            "from manifest_agent.cli import observe_native; assert callable(observe_native)",
        ],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    binding = runtime._binding(desired)
    provider = runtime._provider(
        desired.release_root / runtime.PROJECT, binding.platform
    )
    generation, record = generation_paths(binding, provider, env)
    assert interpreter.is_relative_to(generation)
    assert record.is_file()
    return generation, record


def _prior_receipt(desired):
    # Valid arbitrary prior bundle bindings must not be overwritten on failure,
    # nor mistaken for a completed migration of the requested bytes.
    return InstallationReceipt(
        1,
        "prior",
        desired.release_version,
        desired.source_commit,
        False,
        desired.archive_sha256,
        {"manifest-workspace": "a" * 64},
        (),
        {},
        None,
    )


@pytest.mark.parametrize("resumed", (False, True))
def test_archived_migration_publishes_receipt_and_working_runtime(
    archived_migration, resumed
):
    migration, desired, env, link, events, _adapter = archived_migration
    write_receipt_atomic(migration.receipt_path, _prior_receipt(desired))
    if resumed:
        state = migration._load_or_snapshot(("claude",), desired)
        state["harnesses"]["claude"]["phase"] = "shadow-installed"
        migration._write_state(state)
        events.clear()
    assert link.is_symlink()

    result = migration.migrate(desired)

    assert result.state is ResultState.READY, result
    assert events[0] == "observer-ready"
    assert events.index("observer-ready") < events.index("disable-legacy")
    if not resumed:
        assert events.index("observer-ready") < events.index("snapshot-legacy")
    assert events[-1] == "commit-receipt"
    generation, record = _assert_installed_runtime(migration, desired, env)
    before = (
        migration.receipt_path.read_bytes(),
        inventory(generation),
        record.read_bytes(),
    )
    events.clear()
    assert migration.migrate(desired).state is ResultState.READY
    assert events == ["observer-ready"]
    assert (
        migration.receipt_path.read_bytes(),
        inventory(generation),
        record.read_bytes(),
    ) == before


def test_archived_failed_setup_keeps_legacy_and_arbitrary_prior_receipt(
    archived_migration, monkeypatch
):
    migration, desired, env, link, events, _adapter = archived_migration
    write_receipt_atomic(migration.receipt_path, _prior_receipt(desired))
    before = migration.receipt_path.read_bytes()
    target = link.readlink()
    smoke = runtime._smoke

    def fail_smoke(*args):
        assert link.is_symlink() and link.readlink() == target
        assert not migration.state_path.exists()
        assert migration.receipt_path.read_bytes() == before
        raise RuntimeError("injected archived observer setup failure")

    monkeypatch.setattr(runtime, "_smoke", fail_smoke)
    result = migration.migrate(desired)
    assert result.state is ResultState.BLOCKED
    assert events == []
    assert not migration.state_path.exists()
    assert link.is_symlink() and link.readlink() == target
    assert migration.receipt_path.read_bytes() == before
    monkeypatch.setattr(runtime, "_smoke", smoke)
    assert migration.migrate(desired).state is ResultState.READY
    _assert_installed_runtime(migration, desired, env)


def test_completed_migration_rejects_different_bundle_before_preparation(
    archived_migration, tmp_path
):
    migration, desired, env, _link, events, _adapter = archived_migration
    assert migration.migrate(desired).state is ResultState.READY
    generation, record = _assert_installed_runtime(migration, desired, env)
    before_receipt = migration.receipt_path.read_bytes()
    before_runtime = (inventory(generation), record.read_bytes())
    before_roots = [inventory(root) for root in runtime_roots(env)]
    changed_root = tmp_path / "different-release"
    shutil.copytree(desired.release_root, changed_root, symlinks=True)
    bundle = changed_root / "plugins/manifest-workspace"
    (bundle / "different-content.txt").write_text(
        "same release identifiers, different bytes\n"
    )
    changed = with_source_fingerprints(
        replace(desired, release_root=changed_root, source=str(changed_root))
    )
    assert changed.source_commit == desired.source_commit
    assert changed.archive_sha256 == desired.archive_sha256
    assert bundle_checksums(changed) != bundle_checksums(desired)
    events.clear()

    result = migration.migrate(changed)

    assert result.state is ResultState.BLOCKED
    assert events == [], "rejected bundle must never reach runtime preparation"
    assert migration.receipt_path.read_bytes() == before_receipt
    assert [inventory(root) for root in runtime_roots(env)] == before_roots
    assert (inventory(generation), record.read_bytes()) == before_runtime
    _assert_installed_runtime(migration, desired, env)


def test_failed_replacement_preserves_old_binding_and_retries_real_transaction(
    archived_migration, tmp_path, monkeypatch
):
    migration, desired, env, link, events, _adapter = archived_migration
    original_target = link.readlink()
    assert migration.migrate(desired).state is ResultState.READY
    old_generation, old_record = _assert_installed_runtime(migration, desired, env)
    old_runtime = (inventory(old_generation), old_record.read_bytes())
    # Resume an incomplete handoff with a genuine prior observer selection.
    prior = replace(read_receipt(migration.receipt_path), migration_backup=None)
    write_receipt_atomic(migration.receipt_path, prior)
    prior_bytes = migration.receipt_path.read_bytes()
    link.symlink_to(original_target)
    state = migration._read_state()
    state["harnesses"]["claude"]["phase"] = "shadow-installed"
    migration._write_state(state)
    state_bytes = migration.state_path.read_bytes()
    changed_root = tmp_path / "replacement-release"
    shutil.copytree(desired.release_root, changed_root, symlinks=True)
    (changed_root / "plugins/manifest-workspace/replacement.txt").write_text(
        "different observer binding for a resumed migration\n"
    )
    changed = with_source_fingerprints(
        replace(desired, release_root=changed_root, source=str(changed_root))
    )
    smoke = runtime._smoke

    def fail_smoke(*args):
        assert link.is_symlink() and link.readlink() == original_target
        assert migration.receipt_path.read_bytes() == prior_bytes
        raise RuntimeError("injected replacement runtime setup failure")

    monkeypatch.setattr(runtime, "_smoke", fail_smoke)
    events.clear()
    result = migration.migrate(changed)
    assert result.state is ResultState.BLOCKED
    assert events == []
    assert migration.state_path.read_bytes() == state_bytes
    assert migration.receipt_path.read_bytes() == prior_bytes
    assert link.is_symlink() and link.readlink() == original_target
    assert (inventory(old_generation), old_record.read_bytes()) == old_runtime
    assert resolve_observer_runtime(
        desired.bundle_path("manifest-workspace"),
        receipt_path=migration.receipt_path,
        environ=env,
    ).is_relative_to(old_generation)
    monkeypatch.setattr(runtime, "_smoke", smoke)
    assert migration.migrate(changed).state is ResultState.READY
    assert events[0] == "observer-ready"
    assert events.index("observer-ready") < events.index("disable-legacy")
    new_generation, _new_record = _assert_installed_runtime(migration, changed, env)
    assert new_generation != old_generation
    assert (inventory(old_generation), old_record.read_bytes()) == old_runtime

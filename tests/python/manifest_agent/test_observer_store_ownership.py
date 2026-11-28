"""Signed store ownership survives provider transfer and interrupted processes."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from manifest_agent.observer_runtime import (
    STORE_DOMAIN,
    _claim_store,
    _finish_store,
    _release_store,
    _store_owner,
)
from manifest_agent.observer_runtime_identity import read_signed


@pytest.mark.parametrize("xdg_name", ["XDG_DATA_HOME", "XDG_STATE_HOME"])
@pytest.mark.parametrize(
    "location", ["release", "source", "bundle", "symlinked-bundle"]
)
def test_observer_rejects_xdg_inside_protected_tree_without_mutation(
    tmp_path, monkeypatch, xdg_name, location
):
    import manifest_agent.observer_runtime as runtime

    release = tmp_path / "release"
    source = tmp_path / "source"
    bundle = release / "plugins" / "bundle"
    for root in (release, source, bundle):
        root.mkdir(parents=True)
        (root / "sentinel").write_text(root.name)
    if location == "release":
        target = release
    elif location == "source":
        target = source
    elif location == "bundle":
        target = bundle
    else:
        target = tmp_path / "bundle-alias"
        target.symlink_to(bundle, target_is_directory=True)

    desired = type("Desired", (), {})()
    desired.release_root = release
    desired.source = str(source)
    desired.all_contracts = (type("Contract", (), {"name": "bundle"})(),)
    desired.bundle_path = lambda name: bundle
    xdg = target / "xdg"
    before = {
        str(path): (path.lstat().st_mode, path.read_text() if path.is_file() else None)
        for root in (release, source)
        for path in (root, *root.rglob("*"))
    }
    if target.is_symlink():
        before[str(target)] = (target.lstat().st_mode, str(target.readlink()))
    monkeypatch.setenv(xdg_name, str(xdg))

    with pytest.raises(runtime.ObserverRuntimeError):
        runtime.prepare_observer_runtime(
            desired, receipt_path=tmp_path / "receipt.json"
        )

    after = {
        str(path): (path.lstat().st_mode, path.read_text() if path.is_file() else None)
        for root in (release, source)
        for path in (root, *root.rglob("*"))
    }
    if target.is_symlink():
        after[str(target)] = (target.lstat().st_mode, str(target.readlink()))
    assert after == before
    assert not xdg.exists()


@pytest.mark.parametrize("cwd_location", ["home", "xdg-data"])
def test_observer_location_checks_allow_user_home_cwds(
    tmp_path, monkeypatch, cwd_location
):
    import manifest_agent.observer_runtime as runtime
    import manifest_agent.observer_runtime_identity as identity
    from manifest_agent.observer_runtime_identity import ObserverBinding

    home = tmp_path / "home"
    release = tmp_path / "release"
    bundle = release / "plugins" / "manifest-workspace"
    project = release / runtime.PROJECT
    project.mkdir(parents=True)
    bundle.mkdir(parents=True, exist_ok=True)
    (project / "uv-toolchain.lock.json").write_text("{}")
    (project / "uv.lock").write_text("locked observer dependencies")
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.delenv("XDG_DATA_HOME", raising=False)
    monkeypatch.delenv("XDG_STATE_HOME", raising=False)
    data_root = home / ".local" / "share"
    cwd = home if cwd_location == "home" else data_root
    cwd.mkdir(parents=True, exist_ok=True)
    monkeypatch.chdir(cwd)

    desired = type("Desired", (), {})()
    desired.release_root = release
    desired.source = "https://example.invalid/archive"
    desired.all_contracts = ()
    binding = ObserverBinding("a", "b", "c", "d", identity.platform_id())
    monkeypatch.setattr(runtime, "_binding", lambda _: binding)
    desired.bundle_path = lambda name: bundle
    provider = {"path": str(home / "python")}
    monkeypatch.setattr(runtime, "_provider", lambda *_: provider)
    monkeypatch.setattr(runtime, "_source_unchanged", lambda _: None)

    class ProvisionBoundary(Exception):
        pass

    def stop_provision(*args, **kwargs):
        raise ProvisionBoundary

    monkeypatch.setattr(runtime, "provision", stop_provision)
    with pytest.raises(ProvisionBoundary):
        runtime.prepare_observer_runtime(
            desired, receipt_path=tmp_path / "receipt.json"
        )
    _assert_missing_runtime_is_read_only(runtime, identity, bundle, tmp_path)


def _assert_missing_runtime_is_read_only(runtime, identity, bundle, tmp_path):
    data, state = identity.runtime_roots(os.environ)
    assert state.is_dir()
    receipt = tmp_path / "installed.json"
    receipt.write_text(
        json.dumps(
            {
                "source_commit": "a",
                "archive_sha256": "b",
                "bundle_checksums": {
                    "manifest-workspace": identity.bundle_tree_sha256(bundle)
                },
            }
        )
    )
    store = data / "toolchains" / identity.digest(b"{}") / identity.platform_id()
    assert not store.exists()
    with pytest.raises(ValueError, match="observer runtime is missing"):
        identity.resolve_observer_runtime(
            bundle, receipt_path=receipt, environ=os.environ
        )
    assert not store.exists()


@pytest.mark.parametrize(
    "location",
    [
        "data",
        "state",
        "symlinked-data",
        "symlinked-state",
        "store",
    ],
)
def test_launcher_rejects_bundle_containment_without_writes(tmp_path, location):
    import manifest_agent.observer_runtime_identity as identity

    bundle = tmp_path / "bundle"
    project = bundle / "runtime/observer"
    project.mkdir(parents=True)
    (project / "uv.lock").write_text("locked observer dependencies")
    (project / "uv-toolchain.lock.json").write_text("{}")
    environ = {
        "HOME": str(tmp_path / "home"),
        "XDG_DATA_HOME": str(tmp_path / "data"),
        "XDG_STATE_HOME": str(tmp_path / "state"),
    }
    if location == "store":
        data, _ = identity.runtime_roots(environ)
        data.mkdir(parents=True)
        (data / "toolchains").symlink_to(bundle, target_is_directory=True)
    else:
        target = bundle
        if location.startswith("symlinked-"):
            target = tmp_path / "alias"
            target.symlink_to(bundle, target_is_directory=True)
        name = "XDG_DATA_HOME" if location.endswith("data") else "XDG_STATE_HOME"
        environ[name] = str(target / "xdg")
    receipt = tmp_path / "receipt.json"
    receipt.write_text(
        json.dumps(
            {
                "source_commit": "a",
                "archive_sha256": "b",
                "bundle_checksums": {
                    "manifest-workspace": identity.bundle_tree_sha256(bundle)
                },
            }
        )
    )

    def snapshot():
        return {
            str(path.relative_to(tmp_path)): (
                path.lstat().st_mode,
                str(path.readlink())
                if path.is_symlink()
                else path.read_bytes()
                if path.is_file()
                else None,
            )
            for path in tmp_path.rglob("*")
        }

    before = snapshot()
    with pytest.raises(identity.ObserverRuntimeError, match="must not resolve inside"):
        identity.resolve_observer_runtime(bundle, receipt_path=receipt, environ=environ)
    assert snapshot() == before


FIRST = "a" * 64 + "/" + "b" * 64
SECOND = "a" * 64 + "/" + "c" * 64


@pytest.fixture
def authority(tmp_path):
    key = tmp_path / "ownership.key"
    key.write_bytes(os.urandom(32))
    key.chmod(0o600)
    return key


@pytest.mark.parametrize("signed_shape", [False, True])
def test_unsigned_store_is_never_adopted_or_removed(tmp_path, authority, signed_shape):
    store = tmp_path / "toolchain"
    store.mkdir()
    payload = store / "foreign"
    payload.write_text("must survive")
    marker = store / ".observer-owner.json"
    marker.write_text(
        json.dumps(
            {
                "kind": "observer-toolchain-v1",
                "owners": [FIRST],
                **({"proof": "0" * 64} if signed_shape else {}),
            }
        )
    )
    before = {p.name: p.read_bytes() for p in store.iterdir()}
    for operation in (_claim_store, _release_store):
        with pytest.raises(ValueError):
            operation(store, FIRST, authority)
        assert {p.name: p.read_bytes() for p in store.iterdir()} == before


def test_marker_transfer_and_cleanup_are_bound_to_current_provider(tmp_path, authority):
    store = tmp_path / "toolchain"
    assert _claim_store(store, FIRST, authority)
    (store / "artifact").write_text("verified provider bytes")
    _finish_store(store, FIRST, authority)
    assert not _claim_store(store, SECOND, authority)
    assert _store_owner(store, authority)["phase"] == "ready"
    _finish_store(store, FIRST, authority)
    _finish_store(store, SECOND, authority)
    _release_store(store, FIRST, authority)
    assert _store_owner(store, authority)["owners"] == [SECOND]
    assert (store / "artifact").read_text() == "verified provider bytes"
    _release_store(store, SECOND, authority)
    assert not store.exists()


def test_ready_store_attestation_rejects_mutation(tmp_path, authority):
    store = tmp_path / "toolchain"
    _claim_store(store, FIRST, authority)
    artifact = store / "artifact"
    artifact.write_text("trusted")
    _finish_store(store, FIRST, authority)
    artifact.write_text("changed")
    for operation in (_claim_store, _release_store):
        with pytest.raises(ValueError, match="attestation changed"):
            operation(store, SECOND, authority)
    assert artifact.read_text() == "changed"


def test_hard_interruption_cannot_transfer_another_providers_marker(
    tmp_path, authority
):
    store = tmp_path / "toolchain"
    _claim_store(store, FIRST, authority)
    _finish_store(store, FIRST, authority)
    code = (
        "import os, sys; from pathlib import Path; "
        "from manifest_agent.observer_runtime import _claim_store; "
        "_claim_store(Path(sys.argv[1]), sys.argv[2], Path(sys.argv[3])); os._exit(73)"
    )
    child = subprocess.run(
        [sys.executable, "-B", "-c", code, str(store), SECOND, str(authority)],
        env={
            **os.environ,
            "PYTHONPATH": str(Path(__file__).resolve().parents[3] / "src"),
        },
        capture_output=True,
        text=True,
        check=False,
    )
    assert child.returncode == 73, child.stderr
    marker = read_signed(store / ".observer-owner.json", authority, domain=STORE_DOMAIN)
    assert marker["phase"] == "ready"
    assert marker["active_owner"] is None
    _release_store(store, SECOND, authority)
    assert _store_owner(store, authority)["owners"] == [FIRST]
    _release_store(store, FIRST, authority)
    assert not store.exists()


def test_failed_shared_generation_never_resigns_changed_store(tmp_path, authority):
    store = tmp_path / "toolchain"
    _claim_store(store, FIRST, authority)
    artifact = store / "artifact"
    artifact.write_text("trusted")
    _finish_store(store, FIRST, authority)
    _claim_store(store, SECOND, authority)
    marker = (store / ".observer-owner.json").read_bytes()
    artifact.write_text("foreign changed bytes")
    for operation in (_finish_store, _release_store):
        with pytest.raises(ValueError, match="attestation changed"):
            operation(store, SECOND, authority)
    assert (store / ".observer-owner.json").read_bytes() == marker
    assert artifact.read_text() == "foreign changed bytes"


def test_hard_exit_before_store_marker_cannot_permanently_block_provision(
    tmp_path, authority
):
    from manifest_agent._observer_store import _recover_store_stage

    store = tmp_path / "toolchain"
    code = """
import os, sys
from pathlib import Path
import manifest_agent._observer_store as store
store._write_signed = lambda *a: os._exit(73)
store._claim_store(Path(sys.argv[1]), sys.argv[2], Path(sys.argv[3]))
"""
    result = subprocess.run(
        [sys.executable, "-B", "-c", code, str(store), FIRST, str(authority)],
        env={
            **os.environ,
            "PYTHONPATH": str(Path(__file__).resolve().parents[3] / "src"),
        },
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 73, result.stderr
    orphans = tuple(tmp_path.glob(".*.pending.*"))
    assert len(orphans) == 1
    _recover_store_stage(store, FIRST, authority)
    assert orphans[0].is_dir(), "unsigned staging path must never be claimed or deleted"
    assert _claim_store(store, FIRST, authority)
    _finish_store(store, FIRST, authority)
    _release_store(store, FIRST, authority)
    assert not store.exists()
    assert orphans[0].is_dir()


def test_observer_authority_is_global_private_and_never_recreated(
    tmp_path, monkeypatch
):
    import manifest_agent.observer_runtime as runtime
    from manifest_agent.observer_runtime_identity import (
        authority as read_authority,
    )
    from manifest_agent.observer_runtime_identity import (
        observer_key_path,
    )

    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    first = tmp_path / "first/installation.json"
    second = tmp_path / "second/installation.json"
    first.parent.mkdir()
    first.write_text("legacy installation without observer state")
    key = runtime._observer_authority(first)
    original = read_authority(key)
    assert key == observer_key_path(os.environ)
    assert len(original) == 32 and key.stat().st_mode & 0o777 == 0o600
    assert runtime._observer_authority(second) == key
    assert read_authority(key) == original
    (key.parent / "records").mkdir()
    key.unlink()
    with pytest.raises(Exception, match=r"authority|key|secret|missing|No such file"):
        runtime._observer_authority(second)
    assert not key.exists()


def test_partial_store_retirement_resumes_only_unchanged_survivors(
    tmp_path, authority, monkeypatch
):
    import manifest_agent._observer_store as stores

    store = tmp_path / "toolchain"
    _claim_store(store, FIRST, authority)
    (store / "first").write_text("one")
    (store / "second").write_text("two")
    _finish_store(store, FIRST, authority)
    remove = stores._remove_tree_at

    def interrupted(parent, name, *, expected_inode=None, files):
        (store / "first").unlink()
        raise RuntimeError("interrupted deletion")

    monkeypatch.setattr(stores, "_remove_tree_at", interrupted)
    with pytest.raises(RuntimeError, match="interrupted"):
        _release_store(store, FIRST, authority)
    monkeypatch.setattr(stores, "_remove_tree_at", remove)
    (store / "second").write_text("modified")
    with pytest.raises(ValueError, match="surviving files changed"):
        _release_store(store, FIRST, authority)
    (store / "second").write_text("two")
    _release_store(store, FIRST, authority)
    assert not store.exists()
    assert not store.with_name(".toolchain.retiring.json").exists()


def test_materializing_store_preserves_unsigned_contents_and_allows_new_claim(
    tmp_path, authority
):
    store = tmp_path / "toolchain"
    _claim_store(store, FIRST, authority)
    (store / "foreign").write_bytes(b"must survive")
    with pytest.warns(RuntimeWarning, match="incomplete store preserved"):
        _release_store(store, FIRST, authority)
    assert not store.exists()
    retained = next(tmp_path.glob(".toolchain.*.retained"))
    assert (retained / "foreign").read_bytes() == b"must survive"
    evidence = read_signed(
        retained.with_suffix(".retained.json"),
        authority,
        domain=STORE_DOMAIN + "-retained",
    )
    assert evidence["status"] == "retained-unresolved"
    assert evidence["marker"]["phase"] == "materializing"
    assert "files" not in evidence
    _claim_store(store, FIRST, authority)
    _finish_store(store, FIRST, authority)
    _release_store(store, FIRST, authority)
    assert not store.exists()
    assert (retained / "foreign").read_bytes() == b"must survive"


def test_ready_store_rechecks_inventory_at_deletion_not_just_before(
    tmp_path, authority, monkeypatch
):
    import manifest_agent._observer_store as stores

    store = tmp_path / "toolchain"
    _claim_store(store, FIRST, authority)
    (store / "artifact").write_bytes(b"verified")
    _finish_store(store, FIRST, authority)
    remove = stores._remove_tree_at

    def late_contents(parent, name, *, expected_inode, files):
        (store / "unknown").mkdir()
        (store / "unknown/sentinel").write_bytes(b"must survive")
        return remove(parent, name, expected_inode=expected_inode, files=files)

    monkeypatch.setattr(stores, "_remove_tree_at", late_contents)
    with pytest.raises(ValueError, match="unowned contents"):
        _release_store(store, FIRST, authority)
    assert (store / "unknown/sentinel").read_bytes() == b"must survive"
    assert store.with_name(".toolchain.retiring.json").exists()


def test_empty_store_cleanup_recovery_retains_late_unsigned_survivors(
    tmp_path, authority, monkeypatch
):
    import manifest_agent._observer_store as stores

    store = tmp_path / "toolchain"
    _claim_store(store, FIRST, authority)
    remove = stores._remove_tree_at

    def interrupted(parent, name, *, expected_inode, files):
        (store / ".observer-owner.json").unlink()
        (store / "sentinel").write_bytes(b"must survive")
        raise RuntimeError("interrupted empty-store cleanup")

    monkeypatch.setattr(stores, "_remove_tree_at", interrupted)
    with pytest.raises(RuntimeError, match="interrupted empty-store"):
        _release_store(store, FIRST, authority)
    assert store.with_name(".toolchain.retiring.json").exists()
    monkeypatch.setattr(stores, "_remove_tree_at", remove)
    with pytest.warns(RuntimeWarning, match="incomplete store preserved"):
        _release_store(store, FIRST, authority)
    retained = next(tmp_path.glob(".toolchain.*.retained"))
    assert (retained / "sentinel").read_bytes() == b"must survive"
    assert not store.exists()
    assert not store.with_name(".toolchain.retiring.json").exists()
    _claim_store(store, FIRST, authority)
    _finish_store(store, FIRST, authority)
    _release_store(store, FIRST, authority)
    assert (retained / "sentinel").read_bytes() == b"must survive"

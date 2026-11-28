"""Retirement authorizes matching inventory entries at the deletion boundary."""

from __future__ import annotations

import os
import stat
from dataclasses import asdict

import pytest

from manifest_agent import _observer_cleanup as cleanup
from manifest_agent import observer_runtime_identity as identity
from manifest_agent.observer_runtime_identity import digest


@pytest.mark.parametrize("change", ["bytes", "mode", "literal-link"])
def test_changed_entry_is_preserved_after_directory_enumeration(
    tmp_path, monkeypatch, change
):
    root = tmp_path / "generation"
    root.mkdir()
    payload = root / "payload"
    payload.write_bytes(b"authorized")
    payload.chmod(0o600)
    alias = root / "alias"
    alias.symlink_to("payload")
    files = {
        ".": {"kind": "directory", "mode": stat.S_IMODE(root.stat().st_mode)},
        "payload": {"kind": "file", "mode": 0o600, "sha256": digest(b"authorized")},
        "alias": {
            "kind": "symlink",
            "mode": stat.S_IMODE(alias.lstat().st_mode),
            "target": "payload",
        },
    }
    target = "alias" if change == "literal-link" else "payload"
    remove = cleanup._remove_entry

    def changed(parent, name, relative, inventory):
        if name == target:
            if change == "bytes":
                payload.write_bytes(b"changed")
            elif change == "mode":
                payload.chmod(0o644)
            else:
                alias.unlink()
                alias.symlink_to("missing")
        return remove(parent, name, relative, inventory)

    monkeypatch.setattr(cleanup, "_remove_entry", changed)
    parent = os.open(tmp_path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    info = root.stat()
    try:
        with pytest.raises(ValueError, match="surviving files changed"):
            cleanup._remove_tree_at(
                parent,
                root.name,
                expected_inode=[info.st_dev, info.st_ino],
                files=files,
            )
    finally:
        os.close(parent)
    if change == "literal-link":
        assert str(alias.readlink()) == "missing"
    elif change == "bytes":
        assert payload.read_bytes() == b"changed"
    else:
        assert stat.S_IMODE(payload.stat().st_mode) == 0o644


def test_late_directory_is_not_recursively_removed_after_final_enumeration(
    tmp_path, monkeypatch
):
    root = tmp_path / "generation"
    root.mkdir()
    files = {".": {"kind": "directory", "mode": stat.S_IMODE(root.stat().st_mode)}}
    rmdir = os.rmdir

    def late_directory(name, *, dir_fd=None):
        if name == root.name and dir_fd is not None:
            (root / "unknown").mkdir()
            (root / "unknown/sentinel").write_bytes(b"must survive")
        return rmdir(name, dir_fd=dir_fd)

    monkeypatch.setattr(os, "rmdir", late_directory)
    parent = os.open(tmp_path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    info = root.stat()
    try:
        with pytest.raises(ValueError, match="gained unowned contents"):
            cleanup._remove_tree_at(
                parent,
                root.name,
                expected_inode=[info.st_dev, info.st_ino],
                files=files,
            )
    finally:
        os.close(parent)
    assert (root / "unknown/sentinel").read_bytes() == b"must survive"


def test_retained_store_is_not_readopted_by_later_cleanup(tmp_path, monkeypatch):
    from manifest_agent import _observer_store as stores
    from manifest_agent.observer_runtime_identity import runtime_roots

    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    key = tmp_path / "key"
    key.write_bytes(os.urandom(32))
    key.chmod(0o600)
    data, _ = runtime_roots(os.environ)
    store = data / "toolchains" / ("a" * 64) / "test-platform"
    owner = "b" * 64 + "/" + "c" * 64
    stores._claim_store(store, owner, key)
    (store / "sentinel").write_bytes(b"must survive")
    with pytest.warns(RuntimeWarning, match="incomplete store preserved"):
        stores._release_store(store, owner, key)
    retained = next(store.parent.glob(".test-platform.*.retained"))
    stores._cleanup_stores(key)
    stores._claim_store(store, owner, key)
    stores._finish_store(store, owner, key)
    stores._cleanup_stores(key)
    assert not store.exists()
    assert (retained / "sentinel").read_bytes() == b"must survive"


def test_legacy_materializing_intent_does_not_authorize_its_fresh_inventory(tmp_path):
    from manifest_agent import _observer_store as stores

    key = tmp_path / "key"
    key.write_bytes(os.urandom(32))
    key.chmod(0o600)
    store = tmp_path / "toolchain"
    owner = "b" * 64 + "/" + "c" * 64
    stores._claim_store(store, owner, key)
    (store / "sentinel").write_bytes(b"must survive")
    intent = store.with_name(".toolchain.retiring.json")
    stores._write_signed(
        intent,
        {
            "path": str(store),
            "inode": stores._inode(store),
            "files": stores._store_inventory(store),
            "marker": (store / ".observer-owner.json").read_bytes().hex(),
        },
        key,
        stores.STORE_DOMAIN + "-retirement",
    )
    with pytest.warns(RuntimeWarning, match="incomplete store preserved"):
        assert stores._recover_store_retirement(store, key)
    retained = next(tmp_path.glob(".toolchain.*.retained"))
    assert (retained / "sentinel").read_bytes() == b"must survive"
    assert not store.exists() and not intent.exists()


@pytest.fixture
def linux_observer_inventory(tmp_path, monkeypatch):
    """The actual UV Linux alias layout, without provisioning a test runtime."""
    base = tmp_path.resolve()
    monkeypatch.setenv("XDG_DATA_HOME", str(base / "data"))
    monkeypatch.setenv("XDG_STATE_HOME", str(base / "state"))
    executable = base / "provider"
    executable.write_bytes(b"pinned external provider")
    provider = {
        "path": str(executable),
        "implementation": "cpython",
        "version": "3.14.10",
        "build": "fixture",
        "exe_sha256": digest(executable.read_bytes()),
    }
    binding = identity.ObserverBinding(
        "a" * 40, "b" * 64, "c" * 64, "d" * 64, "linux-x64"
    )
    root, record_path = identity.generation_paths(binding, provider, os.environ)
    (root / "bin").mkdir(parents=True)
    (root / "bin/python").symlink_to(executable)
    (root / "lib").mkdir()
    (root / "lib/payload").write_bytes(b"attested library bytes")
    (root / "lib64").symlink_to("lib")
    files = identity.environment_inventory(root, provider)
    key = identity.observer_key_path(os.environ)
    key.parent.mkdir(parents=True)
    key.write_bytes(os.urandom(32))
    key.chmod(0o600)
    record = identity.sign(
        {
            "schema_version": 1,
            "binding": asdict(binding),
            "provider": provider,
            "files": files,
            "environment_sha256": digest(identity.canonical(files)),
        },
        key,
    )
    record_path.parent.mkdir(parents=True)
    record_path.write_bytes(identity.canonical(record))
    return root, binding, record_path, key


def test_linux_lib64_alias_is_literal_and_fully_attested(linux_observer_inventory):
    root, binding, record_path, key = linux_observer_inventory
    record = identity.read_signed(record_path, key)
    identity.validate_record(record, binding, root)
    files = record["files"]
    assert files["lib64"] == {
        "kind": "symlink",
        "target": "lib",
        "mode": stat.S_IMODE((root / "lib64").lstat().st_mode),
    }
    assert files["lib/payload"]["sha256"] == digest(b"attested library bytes")
    assert "lib64/payload" not in files
    assert identity.retirement_inventory(root, record["provider"]) == files
    (root / "lib/payload").write_bytes(b"modified")
    with pytest.raises(ValueError, match="attestation changed"):
        identity.validate_record(record, binding, root)


@pytest.mark.parametrize(
    "target", ["./lib", "lib/", "lib/../lib", "../lib", "/lib", "other"]
)
def test_linux_lib64_rejects_every_other_literal_target(
    linux_observer_inventory, target
):
    root, _, record_path, key = linux_observer_inventory
    provider = identity.read_signed(record_path, key)["provider"]
    alias = root / "lib64"
    alias.unlink()
    os.symlink(target, alias)
    for inventory in (identity.environment_inventory, identity.retirement_inventory):
        with pytest.raises(ValueError, match="unexpected observer symlink: lib64"):
            inventory(root, provider)


@pytest.mark.parametrize("relative", ["lib32", "nested/lib64"])
def test_linux_lib64_exception_does_not_authorize_other_aliases(
    linux_observer_inventory, relative
):
    root, _, record_path, key = linux_observer_inventory
    provider = identity.read_signed(record_path, key)["provider"]
    alias = root / relative
    alias.parent.mkdir(exist_ok=True)
    alias.symlink_to("lib")
    for inventory in (identity.environment_inventory, identity.retirement_inventory):
        with pytest.raises(ValueError, match="unexpected observer symlink"):
            inventory(root, provider)


@pytest.mark.parametrize("escape", [False, True])
def test_linux_lib64_cannot_follow_an_indirect_or_escaping_directory(
    linux_observer_inventory, escape
):
    root, _, record_path, key = linux_observer_inventory
    provider = identity.read_signed(record_path, key)["provider"]
    target = root.parent / "external-lib" if escape else root / "actual-lib"
    (root / "lib").rename(target)
    (root / "lib").symlink_to(target if escape else "actual-lib")
    for inventory in (identity.environment_inventory, identity.retirement_inventory):
        with pytest.raises(ValueError, match="unexpected observer symlink: lib"):
            inventory(root, provider)


def test_linux_lib64_requires_a_live_directory_not_a_regular_file(
    linux_observer_inventory,
):
    root, binding, record_path, key = linux_observer_inventory
    record = identity.read_signed(record_path, key)
    (root / "lib/payload").unlink()
    (root / "lib").rmdir()
    (root / "lib").write_bytes(b"not a directory")
    with pytest.raises(ValueError, match="lib64 target is not a regular directory"):
        identity.validate_record(record, binding, root)


def test_signed_lib64_retirement_resumes_after_target_directory_is_gone(
    linux_observer_inventory,
):
    from manifest_agent import observer_runtime_transactions as transactions

    root, binding, record_path, key = linux_observer_inventory
    record = identity.read_signed(record_path, key)
    state = identity.runtime_roots(os.environ)[1]
    intent = state / "retirements" / (digest(str(record_path).encode()) + ".json")
    intent.parent.mkdir()
    pending = identity.sign(
        {
            "record": record,
            "inode": [root.stat().st_dev, root.stat().st_ino],
            "receipt": str(state / "retired-receipt.json"),
        },
        key,
        domain=transactions.RETIREMENT_DOMAIN,
    )
    intent.write_bytes(identity.canonical(pending))
    (root / "lib/payload").unlink()
    (root / "lib").rmdir()
    assert (root / "lib64").is_symlink() and not (root / "lib64").exists()
    with pytest.raises(FileNotFoundError):
        identity.validate_record(record, binding, root)
    surviving = identity.retirement_inventory(root, record["provider"])
    assert surviving["lib64"] == record["files"]["lib64"]
    assert all(record["files"].get(name) == row for name, row in surviving.items())
    # A changed survivor is still refused, even with an authentic retirement.
    (root / "lib64").unlink()
    os.symlink("./lib", root / "lib64")
    with pytest.raises(ValueError, match="unexpected observer symlink: lib64"):
        transactions._recover_retirements(key)
    assert root.exists() and record_path.exists() and intent.exists()
    (root / "lib64").unlink()
    (root / "lib64").symlink_to("lib")
    transactions._recover_retirements(key)
    assert not root.exists() and not record_path.exists() and not intent.exists()

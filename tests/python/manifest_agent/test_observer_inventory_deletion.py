"""Retirement authorizes matching inventory entries at the deletion boundary."""

from __future__ import annotations

import os
import stat

import pytest

from manifest_agent import _observer_cleanup as cleanup
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

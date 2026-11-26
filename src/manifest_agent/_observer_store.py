"""Authenticated observer toolchain-store ownership and generation transfer."""

from __future__ import annotations

import os
import re
import stat
import tempfile
from pathlib import Path

from manifest_agent.checks.toolchain_provision_store import _remove_tree_at
from manifest_agent.observer_runtime_identity import (
    ObserverRuntimeError,
    canonical,
    digest,
    forbidden_root,
    read_regular,
    read_signed,
    runtime_roots,
    sign,
)
from manifest_agent.state import _write_private_json_atomic

STORE_DOMAIN = "manifest-observer-store-v1"


def _write_signed(path: Path, document: dict, key: Path, domain: str) -> None:
    _write_private_json_atomic(path, sign(document, key, domain=domain))


def _safe_parents(path: Path) -> None:
    for ancestor in reversed((path, *path.parents)):
        if ancestor.is_symlink():
            raise ValueError("observer path has a symlink ancestor")
        ancestor.mkdir(mode=0o700, exist_ok=True)


def _inode(path: Path) -> list[int]:
    info = path.stat(follow_symlinks=False)
    return [info.st_dev, info.st_ino]


def _store_path(project: Path, platform: str, *protected: Path) -> Path:
    data, _ = runtime_roots(os.environ)
    store = (
        data
        / "toolchains"
        / digest(read_regular(project / "uv-toolchain.lock.json"))
        / platform
    )
    if violated := forbidden_root(store, *protected):
        raise ObserverRuntimeError(
            f"observer runtime must not resolve inside {violated}"
        )
    return store


def _store_owner(store: Path, key: Path, *, logical_path: Path | None = None) -> dict:
    if store.is_symlink():
        raise ValueError("observer toolchain is a symlink")
    marker = read_signed(store / ".observer-owner.json", key, domain=STORE_DOMAIN)
    if (
        marker.get("kind") != "observer-toolchain-v1"
        or marker.get("path") != str(logical_path or store)
        or marker.get("inode") != _inode(store)
        or not isinstance(marker.get("owners"), list)
    ):
        raise ValueError("observer toolchain ownership is invalid")
    if any(
        not isinstance(owner, str)
        or re.fullmatch(r"[0-9a-f]{64}/[0-9a-f]{64}", owner) is None
        for owner in marker["owners"]
    ):
        raise ValueError("observer store contains an invalid generation owner")
    if marker.get("phase") == "ready":
        if marker.get("attestation") != _store_digest(store):
            raise ValueError("observer toolchain store attestation changed")
    elif (
        marker.get("phase") != "materializing"
        or marker.get("active_owner") not in marker["owners"]
    ):
        raise ValueError("observer toolchain generation ownership is invalid")
    return marker


def _store_inventory(store: Path) -> dict:
    inventory = {}
    for path in sorted(store.rglob("*")):
        if path == store / ".observer-owner.json":
            continue
        mode = path.lstat().st_mode
        row = {"mode": stat.S_IMODE(mode)}
        if path.is_symlink():
            if not path.resolve().is_relative_to(store.resolve()):
                raise ValueError("observer store symlink escapes its root")
            row.update(kind="symlink", target=path.readlink().as_posix())
        elif path.is_dir():
            row.update(kind="directory")
        elif path.is_file():
            row.update(kind="file", sha256=digest(read_regular(path)))
        else:
            raise ValueError("observer store contains a special file")
        inventory[path.relative_to(store).as_posix()] = row
    return inventory


def _store_digest(store: Path) -> str:
    return digest(canonical(_store_inventory(store)))


def _store_stage(store: Path, owner: str) -> Path:
    return store.with_name(f".{store.name}.{digest(owner.encode())}.pending")


def _recover_store_stage(store: Path, owner: str, key: Path) -> None:
    # Random unpublished directories cannot block future provisioning. Only a
    # directory carrying a verified inode-bound marker is eligible for cleanup.
    for stage in store.parent.glob(_store_stage(store, owner).name + "*"):
        if not (stage / ".observer-owner.json").exists():
            continue
        marker = _store_owner(stage, key, logical_path=store)
        if marker["owners"] != [owner] or marker.get("active_owner") != owner:
            raise ValueError("observer store stage belongs to another generation")
        parent = os.open(stage.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            if _inode(stage) != marker["inode"]:
                raise ValueError("observer store stage changed before cleanup")
            _remove_tree_at(parent, stage.name, expected_inode=marker["inode"])
        finally:
            os.close(parent)


def _claim_store(store: Path, owner: str, key: Path) -> bool:
    _safe_parents(store.parent)
    _recover_store_retirement(store, key)
    if store.exists() or store.is_symlink():
        marker = _store_owner(store, key)
        if marker["phase"] != "ready":
            raise ValueError("observer toolchain has an unfinished provider generation")
        if owner not in marker["owners"]:
            marker["owners"].append(owner)
        # Reuse never suspends the prior attestation: a failed new generation
        # cannot bless changed bytes on behalf of surviving owners.
        _write_signed(store / ".observer-owner.json", marker, key, STORE_DOMAIN)
        return False
    stage = Path(
        tempfile.mkdtemp(prefix=_store_stage(store, owner).name + ".", dir=store.parent)
    )
    marker = {
        "kind": "observer-toolchain-v1",
        "path": str(store),
        "inode": _inode(stage),
        "owners": [owner],
        "phase": "materializing",
        "active_owner": owner,
    }
    try:
        _write_signed(stage / ".observer-owner.json", marker, key, STORE_DOMAIN)
        # The public path appears atomically with its authenticated owner.
        # An existing destination is never replaced, even if it is empty.
        if store.exists() or store.is_symlink():
            raise ValueError("observer store appeared during publication")
        stage.rename(store)
    except BaseException:
        parent = os.open(stage.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            if stage.exists() and _inode(stage) == marker["inode"]:
                _remove_tree_at(parent, stage.name, expected_inode=marker["inode"])
        finally:
            os.close(parent)
        raise
    return True


def _finish_store(store: Path, owner: str, key: Path) -> None:
    marker = _store_owner(store, key)
    if marker["phase"] == "ready":
        if owner not in marker["owners"]:
            raise ValueError("observer marker does not include this generation")
        return
    if marker.get("active_owner") != owner:
        raise ValueError("observer marker transfer changed provider generation")
    marker.update(phase="ready", active_owner=None, attestation=_store_digest(store))
    _write_signed(store / ".observer-owner.json", marker, key, STORE_DOMAIN)


def _recover_store_retirement(store: Path, key: Path) -> bool:
    intent = store.with_name(f".{store.name}.retiring.json")
    if not intent.exists():
        return False
    pending = read_signed(intent, key, domain=STORE_DOMAIN + "-retirement")
    if pending["path"] != str(store):
        raise ValueError("observer store retirement path changed")
    if store.exists() or store.is_symlink():
        if store.is_symlink() or _inode(store) != pending["inode"]:
            raise ValueError("observer store retirement root changed")
        if any(
            pending["files"].get(name) != row
            for name, row in _store_inventory(store).items()
        ):
            raise ValueError("observer store retirement surviving files changed")
        marker = store / ".observer-owner.json"
        if marker.exists() and read_regular(marker).hex() != pending["marker"]:
            raise ValueError("observer store retirement marker changed")
        parent = os.open(store.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            _remove_tree_at(parent, store.name, expected_inode=pending["inode"])
            os.fsync(parent)
        finally:
            os.close(parent)
    intent.unlink()
    parent = os.open(intent.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(parent)
    finally:
        os.close(parent)
    return True


def _release_store(store: Path, owner: str, key: Path) -> None:
    if _recover_store_retirement(store, key):
        return
    if not store.exists():
        return
    marker = _store_owner(store, key)
    if owner not in marker["owners"]:
        raise ValueError("observer toolchain marker belongs to another generation")
    if marker["phase"] == "materializing" and marker["active_owner"] != owner:
        raise ValueError("observer cleanup cannot retire another provider generation")
    marker["owners"].remove(owner)
    if marker["owners"]:
        # _store_owner already checked the original ready attestation. A shared
        # store must never be re-attested during rollback.
        if marker["phase"] != "ready":
            raise ValueError("cannot retire unfinished shared observer toolchain")
        marker.update(active_owner=None)
        _write_signed(store / ".observer-owner.json", marker, key, STORE_DOMAIN)
        return
    intent = store.with_name(f".{store.name}.retiring.json")
    _write_signed(
        intent,
        {
            "path": str(store),
            "inode": marker["inode"],
            "files": _store_inventory(store),
            "marker": read_regular(store / ".observer-owner.json").hex(),
        },
        key,
        STORE_DOMAIN + "-retirement",
    )
    _recover_store_retirement(store, key)


def _cleanup_stores(key: Path) -> None:
    data, state = runtime_roots(os.environ)
    referenced = set()
    for path in (state / "references").glob("*.json"):
        reference = read_signed(path, key, domain="manifest-observer-reference-v1")
        referenced.update(reference["bindings"])
    records = state / "records"
    for intent in sorted((data / "toolchains").glob("*/.*.retiring.json")):
        store = intent.with_name(intent.name[1 : -len(".retiring.json")])
        _recover_store_retirement(store, key)
    for marker_path in sorted((data / "toolchains").glob("*/*/.observer-owner.json")):
        marker = _store_owner(marker_path.parent, key)
        for owner in tuple(marker["owners"]):
            binding_id, provider_id = owner.split("/")
            if (
                binding_id not in referenced
                and not (records / binding_id / f"{provider_id}.json").exists()
            ):
                _release_store(marker_path.parent, owner, key)

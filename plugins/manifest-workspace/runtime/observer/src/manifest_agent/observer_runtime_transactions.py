"""Authenticated observer references, recovery, and retirement."""

from __future__ import annotations

import errno
import os
import re
import warnings
from pathlib import Path

from manifest_agent._observer_cleanup import _remove_tree_at
from manifest_agent._observer_store import (
    _cleanup_stores,
    _inode,
    _recover_store_retirement,
    _recover_store_stage,
    _release_store,
    _safe_parents,
    _store_owner,
    _write_signed,
)
from manifest_agent.observer_runtime_identity import (
    ObserverBinding,
    canonical,
    digest,
    generation_paths,
    observer_key_path,
    read_signed,
    retirement_inventory,
    runtime_roots,
    validate_record,
)
from manifest_agent.state import installation_lock, read_receipt

PENDING_DOMAIN = "manifest-observer-pending-v1"
REFERENCE_DOMAIN = "manifest-observer-reference-v1"
RETIREMENT_DOMAIN = "manifest-observer-retirement-v1"


def _pending_path(receipt: Path) -> Path:
    return receipt.with_name(f".{receipt.name}.observer-pending.json")


def _reference_path(receipt: Path) -> Path:
    _, state = runtime_roots(os.environ)
    return state / "references" / (digest(str(receipt.absolute()).encode()) + ".json")


def _reference(receipt: Path, binding: ObserverBinding, key: Path) -> None:
    path = _reference_path(receipt)
    record = (
        read_signed(path, key, domain=REFERENCE_DOMAIN)
        if path.exists() or path.is_symlink()
        else {"receipt": str(receipt.absolute()), "bindings": []}
    )
    if record["receipt"] != str(receipt.absolute()):
        raise ValueError("observer reference belongs to another receipt")
    if binding.id not in record["bindings"]:
        record["bindings"].append(binding.id)
    record.pop("retiring", None)
    _safe_parents(path.parent)
    _write_signed(path, record, key, REFERENCE_DOMAIN)


def _referenced(binding: ObserverBinding, excluding: Path, key: Path) -> bool:
    _, state = runtime_roots(os.environ)
    for path in (state / "references").glob("*.json"):
        reference_record = read_signed(path, key, domain=REFERENCE_DOMAIN)
        target = Path(reference_record["receipt"])
        if (
            target == excluding.absolute()
            or binding.id not in reference_record["bindings"]
        ):
            continue
        # References also protect prepared or ambiguously published generations.
        return True
    return False


def _retain_pending_stage(pending: dict, key: Path) -> None:
    """Keep unresolved staging evidence independently of the next transaction."""
    evidence = (
        runtime_roots(os.environ)[1]
        / "retained"
        / (digest(canonical(pending)) + ".json")
    )
    _safe_parents(evidence.parent)
    _write_signed(
        evidence,
        {
            "status": "retained-unresolved",
            "pending": pending,
            "reason": "stage contents have no independently authenticated inventory",
        },
        key,
        PENDING_DOMAIN + "-retained",
    )
    warnings.warn(
        f"observer incomplete stage preserved: {pending['stage']}; unresolved evidence: {evidence}",
        RuntimeWarning,
        stacklevel=2,
    )


def _recover_pending_stage(root: Path, pending: dict, key: Path) -> None:
    stage = root.parent / pending["stage"]
    if (
        re.fullmatch(
            re.escape(f".{root.name}.{pending['pid']}")
            + r"(?:\.[0-9a-f]{32})?\.staging",
            stage.name,
        )
        is None
    ):
        raise ValueError("observer pending stage identity mismatch")
    if stage.exists() or stage.is_symlink():
        if stage.is_symlink() or _inode(stage) != pending["inode"]:
            raise ValueError("observer pending stage was replaced")
        parent = os.open(stage.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            # A signed creation inode is not authority over descendants.
            # rmdir is deliberately nonrecursive, including after a crash.
            try:
                os.rmdir(stage.name, dir_fd=parent)
            except OSError as error:
                if error.errno not in (errno.ENOTEMPTY, errno.EEXIST):
                    raise
                _retain_pending_stage(pending, key)
        finally:
            os.close(parent)


def _recover(receipt: Path, key: Path) -> None:
    pending_file = _pending_path(receipt)
    if not pending_file.exists() and not pending_file.is_symlink():
        return
    pending = read_signed(pending_file, key, domain=PENDING_DOMAIN)
    if pending["receipt"] != str(receipt.absolute()):
        raise ValueError("observer pending transaction belongs to another receipt")
    binding = ObserverBinding(**pending["binding"])
    if (
        pending["owner"] != f"{binding.id}/{digest(canonical(pending['provider']))}"
        or re.fullmatch(r"[0-9a-f]{64}", pending["store_lock_sha256"]) is None
    ):
        raise ValueError("observer pending provider generation is invalid")
    root, record_path = generation_paths(binding, pending["provider"], os.environ)
    data, _ = runtime_roots(os.environ)
    store = data / "toolchains" / pending["store_lock_sha256"] / binding.platform
    _recover_store_stage(store, pending["owner"], key)
    _recover_store_retirement(store, key)
    _recover_pending_stage(root, pending, key)
    if (root.exists() or root.is_symlink()) and not record_path.exists():
        if store.exists():
            marker = _store_owner(store, key)
            if pending["owner"] in marker["owners"]:
                _release_store(store, pending["owner"], key)
        pending_file.unlink()
        raise ValueError(
            "unowned observer generation appeared; preserved without adoption"
        )
    if root.exists():
        record = read_signed(record_path, key)
        validate_record(record, binding, root)
    else:
        if record_path.exists():
            record = read_signed(record_path, key)
            if (
                record["binding"] != pending["binding"]
                or record["provider"] != pending["provider"]
            ):
                raise ValueError("observer pending record changed generation")
            record_path.unlink()
        if store.exists():
            marker = _store_owner(store, key)
            if pending["owner"] in marker["owners"]:
                _release_store(store, pending["owner"], key)
    pending_file.unlink()


def _sync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _retire_generation(path: Path, record: dict, key: Path, *, receipt: Path) -> None:
    binding = ObserverBinding(**record["binding"])
    root, expected = generation_paths(binding, record["provider"], os.environ)
    if path != expected:
        raise ValueError("observer cleanup record path differs from identity")
    validate_record(record, binding, root)
    intent = (
        runtime_roots(os.environ)[1]
        / "retirements"
        / (digest(str(path).encode()) + ".json")
    )
    _safe_parents(intent.parent)
    _write_signed(
        intent,
        {"record": record, "inode": _inode(root), "receipt": str(receipt.absolute())},
        key,
        RETIREMENT_DOMAIN,
    )
    reference_path = _reference_path(receipt)
    reference = read_signed(reference_path, key, domain=REFERENCE_DOMAIN)
    reference["bindings"].remove(binding.id)
    _write_signed(reference_path, reference, key, REFERENCE_DOMAIN)
    _recover_retirements(key)


def _recover_retirements(key: Path) -> None:
    """Resume only authenticated deletion; surviving bytes must still match."""
    state = runtime_roots(os.environ)[1]
    for intent in sorted((state / "retirements").glob("*.json")):
        pending = read_signed(intent, key, domain=RETIREMENT_DOMAIN)
        record = pending["record"]
        binding = ObserverBinding(**record["binding"])
        root, path = generation_paths(binding, record["provider"], os.environ)
        if intent.name != digest(str(path).encode()) + ".json":
            raise ValueError("observer retirement identity changed")
        # A reference may have been added after an interrupted retirement.
        protected = False
        for reference_path in (state / "references").glob("*.json"):
            reference = read_signed(reference_path, key, domain=REFERENCE_DOMAIN)
            if binding.id not in reference["bindings"]:
                continue
            target = Path(reference["receipt"])
            selected = read_receipt(target)
            selected_binding = selected is not None and (
                selected.source_commit == binding.source_commit
                and selected.archive_sha256 == binding.archive_sha256
                and selected.bundle_checksums.get("manifest-workspace")
                == binding.bundle_sha256
            )
            if str(target) == pending["receipt"] and not selected_binding:
                reference["bindings"].remove(binding.id)
                _write_signed(reference_path, reference, key, REFERENCE_DOMAIN)
            else:
                protected = True
        if protected:
            continue
        if root.exists() or root.is_symlink():
            if root.is_symlink() or _inode(root) != pending["inode"]:
                raise ValueError("observer retirement root was replaced")
            surviving = retirement_inventory(root, record["provider"])
            if any(record["files"].get(name) != row for name, row in surviving.items()):
                raise ValueError("observer retirement surviving files changed")
            parent = os.open(root.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            try:
                _remove_tree_at(
                    parent,
                    root.name,
                    expected_inode=pending["inode"],
                    files=record["files"],
                )
                os.fsync(parent)
            finally:
                os.close(parent)
        if path.exists() or path.is_symlink():
            if read_signed(path, key) != record:
                raise ValueError("observer retirement record changed")
            path.unlink()
            _sync_directory(path.parent)
        intent.unlink()
        _sync_directory(intent.parent)


def queue_observer_cleanup(receipt_path: Path) -> None:
    """Durably authenticate cleanup before the service retires its receipt."""
    path = _reference_path(receipt_path)
    if path.exists() or path.is_symlink():
        key = observer_key_path(os.environ)
        reference = read_signed(path, key, domain=REFERENCE_DOMAIN)
        if reference["receipt"] != str(receipt_path.absolute()):
            raise ValueError("observer cleanup receipt identity changed")
        reference["retiring"] = True
        _write_signed(path, reference, key, REFERENCE_DOMAIN)


def _remove_observer(receipt_path: Path) -> None:
    """Retire this receipt's reference before authenticated resumable cleanup."""
    selected = read_receipt(receipt_path)
    if selected is not None and selected.harnesses:
        raise ValueError("observer cleanup refused: receipt still selects a runtime")
    if receipt_path.parent.exists():
        _sync_directory(receipt_path.parent)
    _, state = runtime_roots(os.environ)
    key = observer_key_path(os.environ)
    records = state / "records"
    reference_path = _reference_path(receipt_path)
    if not records.exists() or (
        not reference_path.exists() and not reference_path.is_symlink()
    ):
        if key.exists():
            _recover_retirements(key)
            _cleanup_stores(key)
        return
    reference = read_signed(reference_path, key, domain=REFERENCE_DOMAIN)
    if reference["receipt"] != str(receipt_path.absolute()):
        raise ValueError("observer cleanup reference belongs to another receipt")
    candidates = []
    for path in sorted(records.glob("*/*.json")):
        record = read_signed(path, key)
        binding = ObserverBinding(**record["binding"])
        if binding.id in reference["bindings"] and not _referenced(
            binding, receipt_path, key
        ):
            root, expected = generation_paths(binding, record["provider"], os.environ)
            if path != expected:
                raise ValueError("observer cleanup record path differs from identity")
            validate_record(record, binding, root)
            candidates.append((path, record))
    # Queue every retirement before dropping the reference. No live receipt
    # may select this runtime when the service invokes this cleanup.
    for path, record in candidates:
        root, _ = generation_paths(
            ObserverBinding(**record["binding"]), record["provider"], os.environ
        )
        intent = state / "retirements" / (digest(str(path).encode()) + ".json")
        _safe_parents(intent.parent)
        _write_signed(
            intent,
            {
                "record": record,
                "inode": _inode(root),
                "receipt": str(receipt_path.absolute()),
            },
            key,
            RETIREMENT_DOMAIN,
        )
    reference_path.unlink()
    _sync_directory(reference_path.parent)
    _recover_retirements(key)
    _cleanup_stores(key)


def remove_observer(receipt_path: Path) -> None:
    _, state = runtime_roots(os.environ)
    if not state.exists():
        return
    with installation_lock(state / "observer.lock"):
        _remove_observer(receipt_path)

"""Secret-backed ownership authority for coordinator-created capabilities."""

from __future__ import annotations

import fcntl
import hashlib
import hmac
import json
import os
import secrets
import stat
import tempfile
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import asdict
from pathlib import Path

from manifest_agent.capability_identity import capability_identity
from manifest_agent.models import HarnessReceipt, OwnedEntry
from manifest_agent.paths import xdg_paths

_MARKER = "manifest"
_OWNED_STATUS = "installed-by-manifest"
_CAPABILITY_KINDS = frozenset({"executable", "mcp"})
_RETIRED_EXECUTABLE_IDENTITIES = frozenset({"graphify"})
_SECRET_BYTES = 32
_PROOF_VERSION = "manifest-capability-ownership-v1"
_RETIREMENT_PROOF_VERSION = "manifest-graphify-retirement-v1"


class OwnershipError(RuntimeError):
    """Ownership authority is missing, corrupt, unsafe, or unavailable."""


def ownership_key_path(env: Mapping[str, str] | None = None) -> Path:
    """Return the private XDG authority path, never a receipt path."""
    return xdg_paths(env).state / "ownership.key"


def owned_capability_entry(
    kind: str,
    identifier: str,
    target_path: str | None = None,
    *,
    env: Mapping[str, str] | None = None,
    key_path: Path | None = None,
) -> OwnedEntry:
    """Issue one owned entry using private authority outside the receipt."""
    authority = key_path or ownership_key_path(env)
    secret = _load_or_create_secret(authority)
    proof = _ownership_proof(secret, kind, identifier, target_path)
    return OwnedEntry(kind, identifier, _MARKER, target_path, proof)


def capability_ownership_errors(
    receipt: HarnessReceipt,
    *,
    expected_cursor_path: Path | None = None,
    env: Mapping[str, str] | None = None,
    key_path: Path | None = None,
) -> tuple[str, ...]:
    """Validate bidirectional ownership facts without creating authority."""
    relevant_entries = tuple(
        entry for entry in receipt.owned_entries if entry.kind in _CAPABILITY_KINDS
    )
    expected_identities = {
        identity
        for identity, status in receipt.capabilities.items()
        if status == _OWNED_STATUS and identity.partition(":")[0] in _CAPABILITY_KINDS
    }
    if not relevant_entries and not expected_identities:
        return ()
    try:
        secret = _load_secret(key_path or ownership_key_path(env))
    except OwnershipError as error:
        return (str(error),)

    errors: list[str] = []
    owned_identities: set[str] = set()
    for entry in relevant_entries:
        identity = f"{entry.kind}:{entry.identifier}"
        if identity in owned_identities:
            errors.append(f"receipt repeats owned capability {identity}")
            continue
        owned_identities.add(identity)
        errors.extend(
            _entry_errors(
                receipt,
                entry,
                secret,
                expected_cursor_path=expected_cursor_path,
            )
        )
    for identity in sorted(expected_identities - owned_identities):
        errors.append(f"receipt lacks ownership metadata for {identity}")
    return tuple(errors)


def graphify_retirement_transaction_proof(
    phase: str,
    legacy_receipt_digest: str,
    legacy_receipt,
    target_receipt,
    *,
    key_path: Path,
) -> str:
    """Sign a Graphify retirement transition with the existing ownership authority."""
    secret = _load_secret(key_path)
    return _retirement_proof(
        secret,
        phase,
        legacy_receipt_digest,
        legacy_receipt,
        target_receipt,
    )


def graphify_retirement_transaction_errors(
    phase: str,
    legacy_receipt_digest: str,
    legacy_receipt,
    target_receipt,
    ownership_proof: str,
    *,
    key_path: Path,
) -> tuple[str, ...]:
    """Return authority errors for a receipt-bound Graphify transaction."""
    try:
        expected = graphify_retirement_transaction_proof(
            phase,
            legacy_receipt_digest,
            legacy_receipt,
            target_receipt,
            key_path=key_path,
        )
    except OwnershipError as error:
        return (str(error),)
    if not isinstance(ownership_proof, str) or not hmac.compare_digest(
        ownership_proof, expected
    ):
        return ("retired Graphify transaction ownership proof does not match",)
    return ()


def _entry_errors(
    receipt: HarnessReceipt,
    entry: OwnedEntry,
    secret: bytes,
    *,
    expected_cursor_path: Path | None,
) -> list[str]:
    identity = f"{entry.kind}:{entry.identifier}"
    errors: list[str] = []
    try:
        canonical_identity = _canonical_identity(entry.kind, entry.identifier)
    except ValueError as error:
        return [f"receipt contains {error}"]
    if identity != canonical_identity or entry.ownership_marker != _MARKER:
        errors.append(f"receipt has invalid ownership metadata for {identity}")
    if receipt.capabilities.get(identity) != _OWNED_STATUS:
        errors.append(
            f"receipt lacks Manifest-created capability evidence for {identity}"
        )
    errors.extend(
        _target_errors(
            receipt.harness, entry, expected_cursor_path=expected_cursor_path
        )
    )
    expected_proof = _ownership_proof(
        secret, entry.kind, entry.identifier, entry.target_path
    )
    if not isinstance(entry.previous_checksum, str) or not hmac.compare_digest(
        entry.previous_checksum, expected_proof
    ):
        errors.append(f"receipt ownership proof does not match {identity}")
    return errors


def _target_errors(
    harness: str, entry: OwnedEntry, *, expected_cursor_path: Path | None
) -> list[str]:
    identity = f"{entry.kind}:{entry.identifier}"
    if entry.kind == "executable" or harness != "cursor":
        return (
            [] if entry.target_path is None else [f"invalid target path for {identity}"]
        )
    if entry.target_path is None:
        return [f"missing Cursor target path for {identity}"]
    target = Path(entry.target_path)
    if expected_cursor_path is not None:
        if target != expected_cursor_path:
            return [f"Cursor target path does not match {identity}"]
    elif not target.is_absolute() or target.parts[-2:] != (".cursor", "mcp.json"):
        return [f"invalid Cursor target path for {identity}"]
    return []


def _ownership_proof(
    secret: bytes, kind: str, identifier: str, target_path: str | None
) -> str:
    identity = _canonical_identity(kind, identifier)
    payload = json.dumps(
        {
            "capability": identity,
            "identifier": identifier,
            "kind": kind,
            "ownership_marker": _MARKER,
            "proof_version": _PROOF_VERSION,
            "status": _OWNED_STATUS,
            "target_path": target_path,
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return hmac.new(secret, payload, hashlib.sha256).hexdigest()


def _retirement_proof(
    secret: bytes,
    phase: str,
    legacy_receipt_digest: str,
    legacy_receipt,
    target_receipt,
) -> str:
    payload = json.dumps(
        {
            "legacy_receipt": asdict(legacy_receipt),
            "legacy_receipt_digest": legacy_receipt_digest,
            "phase": phase,
            "proof_version": _RETIREMENT_PROOF_VERSION,
            "target_receipt": asdict(target_receipt),
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return hmac.new(secret, payload, hashlib.sha256).hexdigest()


def _canonical_identity(kind: str, identifier: str) -> str:
    """Accept receipt-proven retired tools only long enough to remove them."""
    if kind == "executable" and identifier in _RETIRED_EXECUTABLE_IDENTITIES:
        return f"executable:{identifier}"
    return capability_identity(kind, identifier)


def _load_or_create_secret(path: Path) -> bytes:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with _authority_lock(path.parent / "ownership.lock"):
        if path.exists():
            return _load_secret(path)
        secret = secrets.token_bytes(_SECRET_BYTES)
        _write_secret_atomic(path, secret)
        return secret


def _load_secret(path: Path) -> bytes:
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except FileNotFoundError as error:
        raise OwnershipError("ownership authority is missing") from error
    except OSError as error:
        raise OwnershipError("ownership authority is unavailable") from error
    try:
        metadata = os.fstat(descriptor)
        if (
            not stat.S_ISREG(metadata.st_mode)
            or stat.S_IMODE(metadata.st_mode) != 0o600
        ):
            raise OwnershipError("ownership authority permissions are unsafe")
        secret = os.read(descriptor, _SECRET_BYTES + 1)
    finally:
        os.close(descriptor)
    if len(secret) != _SECRET_BYTES:
        raise OwnershipError("ownership authority is corrupt")
    return secret


@contextmanager
def _authority_lock(path: Path) -> Iterator[None]:
    flags = os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags, 0o600)
    except OSError as error:
        raise OwnershipError("ownership authority lock is unavailable") from error
    try:
        os.fchmod(descriptor, 0o600)
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        yield
    finally:
        fcntl.flock(descriptor, fcntl.LOCK_UN)
        os.close(descriptor)


def _write_secret_atomic(path: Path, secret: bytes) -> None:
    descriptor, name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temporary = Path(name)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "wb") as stream:
            descriptor = -1
            stream.write(secret)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        directory = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    except OSError as error:
        raise OwnershipError("ownership authority could not be persisted") from error
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        temporary.unlink(missing_ok=True)

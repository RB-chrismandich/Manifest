"""Secret-backed ownership authority for coordinator-created capabilities."""

from __future__ import annotations

import fcntl
import hashlib
import hmac
import json
import os
import re
import secrets
import stat
import tempfile
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import asdict, replace
from pathlib import Path

from manifest_agent.capability_identity import capability_identity
from manifest_agent.codex_plugin_backup import (
    OwnedFileBackup,
    owned_file_backup_root,
    verify_owned_file_backup,
)
from manifest_agent.models import HarnessReceipt, OwnedEntry
from manifest_agent.paths import xdg_paths

_MARKER = "manifest"
_OWNED_STATUS = "installed-by-manifest"
_CAPABILITY_KINDS = frozenset({"executable", "mcp"})
_RETIRED_EXECUTABLE_IDENTITIES = frozenset({"graphify"})
_SECRET_BYTES = 32
_PROOF_VERSION = "manifest-capability-ownership-v1"
_RETIREMENT_PROOF_VERSION = "manifest-graphify-retirement-v1"
_CODEX_CATALOG_PROOF_VERSION = "manifest-codex-catalog-ownership-v1"
_CODEX_RECEIPT_PROOF_VERSION = "manifest-codex-receipt-ownership-v1"
_BOOTSTRAP_JOURNAL_PROOF_VERSION = "manifest-bootstrap-journal-v1"
_OWNED_FILE_PROOF_VERSION = "manifest-owned-file-v1"


class OwnershipError(RuntimeError):
    """Ownership authority is missing, corrupt, unsafe, or unavailable."""


def ensure_bootstrap_journal_authority(
    key_path: Path, *, receipt_exists: bool, journal_exists: bool
) -> None:
    """Create first-install authority only when no durable state exists."""
    if receipt_exists or journal_exists:
        _load_secret(key_path)
    else:
        _load_or_create_secret(key_path)


def bootstrap_journal_proof(document: Mapping[str, object], *, key_path: Path) -> str:
    """Authenticate one complete receipt-bound bootstrap transaction."""
    secret = _load_secret(key_path)
    payload = json.dumps(
        {
            "journal": dict(document),
            "proof_version": _BOOTSTRAP_JOURNAL_PROOF_VERSION,
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return hmac.new(secret, payload, hashlib.sha256).hexdigest()


def bootstrap_journal_errors(
    document: Mapping[str, object], proof: object, *, key_path: Path
) -> tuple[str, ...]:
    """Validate journal authority before any recovery or native mutation."""
    try:
        expected = bootstrap_journal_proof(document, key_path=key_path)
    except OwnershipError as error:
        return (str(error),)
    if not isinstance(proof, str) or not hmac.compare_digest(proof, expected):
        return ("bootstrap reconciliation journal ownership proof does not match",)
    return ()


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


def owned_file_entry(
    identifier: str,
    target_path: Path,
    prior: Mapping[str, object],
    installed: Mapping[str, object],
    *,
    env: Mapping[str, str] | None = None,
    key_path: Path | None = None,
) -> OwnedEntry:
    """Issue authenticated authority to restore one exact prior regular file."""
    authority = key_path or ownership_key_path(env)
    secret = _load_or_create_secret(authority)
    document = {
        "installed": dict(installed),
        "prior": dict(prior),
        "proof_version": _OWNED_FILE_PROOF_VERSION,
    }
    proof = _owned_file_proof(secret, identifier, str(target_path), document)
    return OwnedEntry(
        "owned-file",
        identifier,
        _MARKER,
        str(target_path),
        json.dumps(
            {**document, "proof": proof},
            sort_keys=True,
            separators=(",", ":"),
        ),
    )


def owned_file_ownership(
    entry: OwnedEntry,
    *,
    env: Mapping[str, str] | None = None,
    key_path: Path | None = None,
) -> tuple[dict[str, object] | None, dict[str, object] | None, tuple[str, ...]]:
    """Validate an owned-file receipt without creating or replacing authority."""
    try:
        document = json.loads(entry.previous_checksum or "")
        proof = document.pop("proof")
    except (json.JSONDecodeError, KeyError, TypeError):
        return None, None, ("receipt owned-file proof is invalid",)
    if (
        entry.kind != "owned-file"
        or entry.ownership_marker != _MARKER
        or not entry.identifier
        or not isinstance(entry.target_path, str)
        or not Path(entry.target_path).is_absolute()
        or set(document) != {"installed", "prior", "proof_version"}
        or document.get("proof_version") != _OWNED_FILE_PROOF_VERSION
        or not isinstance(document.get("prior"), dict)
        or not isinstance(document.get("installed"), dict)
    ):
        return None, None, ("receipt owned-file metadata is invalid",)
    prior = document["prior"]
    installed = document["installed"]
    errors = [
        *(_owned_file_row_errors(prior, require_archive=prior.get("type") == "file")),
        *(_owned_file_row_errors(installed, require_archive=True)),
    ]
    if (
        prior.get("path") != entry.target_path
        or installed.get("path") != entry.target_path
    ):
        errors.append("receipt owned-file target path does not match")
    if errors:
        return None, None, tuple(errors)
    try:
        secret = _load_secret(key_path or ownership_key_path(env))
    except OwnershipError as error:
        return None, None, (str(error),)
    expected = _owned_file_proof(secret, entry.identifier, entry.target_path, document)
    if not isinstance(proof, str) or not hmac.compare_digest(proof, expected):
        return None, None, ("receipt owned-file proof does not match",)
    try:
        for row in (prior, installed):
            restore = row.get("restore")
            if isinstance(restore, dict) and isinstance(restore.get("archive"), dict):
                verify_owned_file_backup(
                    OwnedFileBackup.from_dict(restore["archive"]),
                    env,
                    root=(
                        owned_file_backup_root(env)
                        if key_path is None
                        else key_path.parent / "owned-file-backups"
                    ),
                )
    except Exception:
        return None, None, ("receipt owned-file archive is invalid",)
    return dict(prior), dict(installed), ()


def advance_owned_file_entry(
    previous: OwnedEntry,
    current: OwnedEntry,
    *,
    env: Mapping[str, str] | None = None,
    key_path: Path | None = None,
) -> OwnedEntry:
    """Advance installed bytes while preserving original uninstall authority."""
    prior, _old_installed, previous_errors = owned_file_ownership(
        previous, env=env, key_path=key_path
    )
    _immediate_prior, installed, current_errors = owned_file_ownership(
        current, env=env, key_path=key_path
    )
    errors = (*previous_errors, *current_errors)
    if errors or prior is None or installed is None:
        raise OwnershipError("; ".join(errors) or "owned-file receipt is invalid")
    if (
        previous.identifier != current.identifier
        or previous.target_path != current.target_path
    ):
        raise OwnershipError("owned-file receipt identity changed")
    return owned_file_entry(
        previous.identifier,
        Path(previous.target_path or ""),
        prior,
        installed,
        env=env,
        key_path=key_path,
    )


def owned_codex_catalog_entry(
    catalog: list[dict[str, str]],
    *,
    marketplace: Mapping[str, object] | None = None,
    env: Mapping[str, str] | None = None,
    key_path: Path | None = None,
) -> OwnedEntry:
    """Authenticate the exact destructive Codex catalog with private authority."""
    authority = key_path or ownership_key_path(env)
    secret = _load_or_create_secret(authority)
    canonical_catalog = json.dumps(
        catalog, sort_keys=True, separators=(",", ":")
    ).encode()
    identifier = hashlib.sha256(canonical_catalog).hexdigest()
    marketplace_identity = dict(
        marketplace
        or {
            "identifier": "manifest",
            "source_kind": "local",
            "source": "/manifest",
            "immutable_ref": None,
            "checkout_root": "/manifest",
        }
    )
    if _marketplace_identity_errors(marketplace_identity):
        raise OwnershipError("Codex marketplace ownership identity is invalid")
    proof = _codex_catalog_proof(secret, identifier, catalog, marketplace_identity)
    document = json.dumps(
        {
            "catalog": catalog,
            "marketplace": marketplace_identity,
            "proof": proof,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return OwnedEntry("codex-catalog", identifier, _MARKER, None, document)


def codex_catalog_ownership(
    entry: OwnedEntry,
    *,
    env: Mapping[str, str] | None = None,
    key_path: Path | None = None,
) -> tuple[list[dict[str, str]] | None, tuple[str, ...]]:
    """Return an authenticated catalog or stable ownership errors."""
    try:
        document = json.loads(entry.previous_checksum or "")
        catalog = document["catalog"]
        marketplace = document["marketplace"]
        proof = document["proof"]
        canonical_catalog = json.dumps(
            catalog, sort_keys=True, separators=(",", ":")
        ).encode()
    except (json.JSONDecodeError, KeyError, TypeError):
        return None, ("receipt Codex catalog ownership proof is invalid",)
    if (
        entry.kind != "codex-catalog"
        or entry.ownership_marker != _MARKER
        or entry.target_path is not None
        or not isinstance(catalog, list)
        or any(
            not isinstance(row, dict)
            or set(row) != {"name", "source", "version"}
            or not all(isinstance(row[key], str) and row[key] for key in row)
            for row in catalog
        )
        or entry.identifier != hashlib.sha256(canonical_catalog).hexdigest()
        or not isinstance(marketplace, dict)
        or _marketplace_identity_errors(marketplace)
    ):
        return None, ("receipt Codex catalog ownership metadata is invalid",)
    try:
        secret = _load_secret(key_path or ownership_key_path(env))
    except OwnershipError as error:
        return None, (str(error),)
    expected = _codex_catalog_proof(secret, entry.identifier, catalog, marketplace)
    if not isinstance(proof, str) or not hmac.compare_digest(proof, expected):
        return None, ("receipt Codex catalog ownership proof does not match",)
    return catalog, ()


def codex_marketplace_ownership(
    entry: OwnedEntry,
    *,
    env: Mapping[str, str] | None = None,
    key_path: Path | None = None,
) -> tuple[dict[str, object] | None, tuple[str, ...]]:
    """Return the exact authenticated marketplace identity from a catalog entry."""
    catalog, errors = codex_catalog_ownership(entry, env=env, key_path=key_path)
    if errors or catalog is None:
        return None, errors
    try:
        document = json.loads(entry.previous_checksum or "")
        marketplace = document["marketplace"]
    except (json.JSONDecodeError, KeyError, TypeError):
        return None, ("receipt Codex marketplace ownership proof is invalid",)
    if not isinstance(marketplace, dict) or _marketplace_identity_errors(marketplace):
        return None, ("receipt Codex marketplace ownership metadata is invalid",)
    return marketplace, ()


def authenticate_codex_receipt(
    receipt: HarnessReceipt,
    *,
    env: Mapping[str, str] | None = None,
    key_path: Path | None = None,
) -> HarnessReceipt:
    """HMAC-bind every destructive field of a finalized Codex receipt."""
    if receipt.harness != "codex":
        return receipt
    unsigned = replace(
        receipt,
        owned_entries=tuple(
            entry
            for entry in receipt.owned_entries
            if entry.kind != "codex-receipt-auth"
        ),
    )
    authority = key_path or ownership_key_path(env)
    secret = _load_or_create_secret(authority)
    proof = _codex_receipt_proof(secret, unsigned)
    entry = OwnedEntry(
        "codex-receipt-auth",
        hashlib.sha256(_canonical_receipt(unsigned)).hexdigest(),
        _MARKER,
        None,
        proof,
    )
    return replace(unsigned, owned_entries=(*unsigned.owned_entries, entry))


def codex_receipt_ownership_errors(
    receipt: HarnessReceipt,
    *,
    env: Mapping[str, str] | None = None,
    key_path: Path | None = None,
) -> tuple[str, ...]:
    """Verify the full Codex receipt before any destructive recovery or uninstall."""
    entries = tuple(
        entry for entry in receipt.owned_entries if entry.kind == "codex-receipt-auth"
    )
    if receipt.harness != "codex" or len(entries) != 1:
        # A receipt written before Codex receipt authentication existed carries
        # no proof at all. Failing closed is deliberate -- an unauthenticated
        # receipt must never authorise removal -- so name the remediation
        # rather than leaving the operator with an opaque corruption message.
        if receipt.harness == "codex" and not entries:
            return (
                "receipt lacks one full Codex ownership proof: it predates Codex "
                "receipt authentication. Re-run `manifest install` to write an "
                "authenticated receipt, or remove the installation receipt to "
                "start from a clean state.",
            )
        return ("receipt lacks one full Codex ownership proof",)
    entry = entries[0]
    unsigned = replace(
        receipt,
        owned_entries=tuple(
            item for item in receipt.owned_entries if item.kind != entry.kind
        ),
    )
    canonical = _canonical_receipt(unsigned)
    if (
        entry.ownership_marker != _MARKER
        or entry.target_path is not None
        or entry.identifier != hashlib.sha256(canonical).hexdigest()
        or not isinstance(entry.previous_checksum, str)
    ):
        return ("receipt full Codex ownership metadata is invalid",)
    try:
        secret = _load_secret(key_path or ownership_key_path(env))
    except OwnershipError as error:
        return (str(error),)
    expected = _codex_receipt_proof(secret, unsigned)
    if not hmac.compare_digest(entry.previous_checksum, expected):
        return ("receipt full Codex ownership proof does not match",)
    return ()


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


def _owned_file_proof(
    secret: bytes,
    identifier: str,
    target_path: str,
    document: Mapping[str, object],
) -> str:
    payload = json.dumps(
        {
            **dict(document),
            "identifier": identifier,
            "ownership_marker": _MARKER,
            "target_path": target_path,
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return hmac.new(secret, payload, hashlib.sha256).hexdigest()


def _owned_file_row_errors(
    row: Mapping[str, object], *, require_archive: bool
) -> tuple[str, ...]:
    kind = row.get("type")
    if kind == "missing":
        return (
            ()
            if set(row) == {"path", "type"} and not require_archive
            else ("receipt owned-file missing state is invalid",)
        )
    restore = row.get("restore")
    if (
        kind != "file"
        or not isinstance(row.get("path"), str)
        or not isinstance(row.get("mode"), int)
        or not isinstance(row.get("digest"), str)
        or len(row["digest"]) != 64
        or not isinstance(restore, dict)
        or not isinstance(restore.get("archive"), dict)
    ):
        return ("receipt owned-file state is invalid",)
    try:
        backup = OwnedFileBackup.from_dict(restore["archive"])
    except Exception:
        return ("receipt owned-file archive metadata is invalid",)
    if backup.archive_sha256 != row["digest"]:
        return ("receipt owned-file digest does not match archive",)
    return ()


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


def _codex_catalog_proof(
    secret: bytes,
    identifier: str,
    catalog: list[dict[str, str]],
    marketplace: Mapping[str, object],
) -> str:
    payload = json.dumps(
        {
            "catalog": catalog,
            "catalog_identifier": identifier,
            "marketplace": dict(marketplace),
            "proof_version": _CODEX_CATALOG_PROOF_VERSION,
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return hmac.new(secret, payload, hashlib.sha256).hexdigest()


def _marketplace_identity_errors(value: Mapping[str, object]) -> tuple[str, ...]:
    if set(value) != {
        "identifier",
        "source_kind",
        "source",
        "immutable_ref",
        "checkout_root",
    }:
        return ("invalid fields",)
    if value.get("identifier") != "manifest":
        return ("invalid identifier",)
    kind = value.get("source_kind")
    source = value.get("source")
    checkout_root = value.get("checkout_root")
    immutable_ref = value.get("immutable_ref")
    if kind not in {"local", "git"}:
        return ("invalid source kind",)
    if not isinstance(source, str) or not source:
        return ("invalid source",)
    if not isinstance(checkout_root, str) or not checkout_root:
        return ("invalid checkout root",)
    if kind == "local" and immutable_ref is not None:
        return ("unexpected local ref",)
    if kind == "git" and (
        not isinstance(immutable_ref, str)
        or re.fullmatch(r"[0-9a-fA-F]{40}(?:[0-9a-fA-F]{24})?", immutable_ref) is None
    ):
        return ("invalid immutable ref",)
    return ()


def _canonical_receipt(receipt: HarnessReceipt) -> bytes:
    return json.dumps(asdict(receipt), sort_keys=True, separators=(",", ":")).encode()


def _codex_receipt_proof(secret: bytes, receipt: HarnessReceipt) -> str:
    payload = json.dumps(
        {
            "proof_version": _CODEX_RECEIPT_PROOF_VERSION,
            "receipt": asdict(receipt),
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

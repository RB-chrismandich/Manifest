"""XDG locking and secret-free atomic installation receipts."""

import fcntl
import hashlib
import json
import os
import re
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any

from manifest_agent.models import HarnessReceipt, InstallationReceipt, OwnedEntry
from manifest_agent.ownership import (
    authenticate_codex_receipt,
    capability_ownership_errors,
    codex_catalog_ownership,
    codex_receipt_ownership_errors,
    owned_file_ownership,
)
from manifest_agent.paths import xdg_paths
from manifest_agent.process import contains_credential_material

_CREDENTIAL_KEY = re.compile(
    r"(?:^|[._-])(?:authorization|credential|password|private[_-]?key|secret|token|"
    r"api[_-]?key|access[_-]?key)(?:$|[._-])",
    re.I,
)
_FULL_COMMIT = re.compile(r"^[0-9a-fA-F]{40}(?:[0-9a-fA-F]{24})?$")
_SHA256 = re.compile(r"^[0-9a-fA-F]{64}$")
_RETIREMENT_PHASES = frozenset({"prepared", "cleanup-complete"})
_SUPPORTED_HARNESSES = frozenset(
    {"claude", "codex", "gemini", "cursor", "antigravity", "devin"}
)
_NON_SUCCESS_CAPABILITY_VALUES = frozenset(
    {
        "blocked",
        "degraded",
        "drifted",
        "failed",
        "not-installed",
        "not_installed",
        "skipped",
        "unavailable",
        "unsupported",
    }
)


class StateError(RuntimeError):
    """Durable state is unsafe, malformed, unavailable, or concurrently locked."""


@dataclass(frozen=True)
class RetiredGraphifyTransaction:
    """Crash-recoverable state for the one-time legacy Graphify cleanup."""

    phase: str
    legacy_receipt_digest: str
    legacy_receipt: InstallationReceipt
    target_receipt: InstallationReceipt
    ownership_proof: str


def _receipt_path(path: Path | None) -> Path:
    return path if path is not None else xdg_paths().state / "installation.json"


@contextmanager
def installation_lock(path: Path | None = None) -> Iterator[Path]:
    """Hold the coordinator's exclusive, nonblocking XDG installation lock."""
    lock_path = path if path is not None else xdg_paths().state / "install.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    descriptor = os.open(lock_path, os.O_RDWR | os.O_CREAT, 0o600)
    os.fchmod(descriptor, 0o600)
    try:
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise StateError(
                "another Manifest installation is already in progress"
            ) from error
        yield lock_path
    finally:
        try:
            fcntl.flock(descriptor, fcntl.LOCK_UN)
        finally:
            os.close(descriptor)


def write_receipt_atomic(
    path: Path | InstallationReceipt,
    receipt: InstallationReceipt | None = None,
) -> None:
    """Validate and atomically persist a private installation receipt."""
    if receipt is None:
        if not isinstance(path, InstallationReceipt):
            raise TypeError("receipt is required")
        receipt = path
        destination = _receipt_path(None)
    else:
        if not isinstance(path, Path):
            raise TypeError("receipt path must be a Path")
        destination = path
    if not isinstance(receipt, InstallationReceipt):
        raise TypeError("receipt must be an InstallationReceipt")

    receipt = receipt_for_persistence(destination, receipt)

    document = asdict(receipt)
    _assert_secret_free(document)
    _validate_receipt(receipt, ownership_key_path=destination.parent / "ownership.key")
    payload = (json.dumps(document, indent=2, sort_keys=True) + "\n").encode()
    destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)

    descriptor = -1
    temporary: Path | None = None
    try:
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{destination.name}.", suffix=".tmp", dir=destination.parent
        )
        temporary = Path(temporary_name)
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "wb") as stream:
            descriptor = -1
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, destination)
        temporary = None
        _fsync_directory(destination.parent)
    except OSError as error:
        raise StateError("unable to write receipt atomically") from error
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def receipt_for_persistence(
    destination: Path, receipt: InstallationReceipt
) -> InstallationReceipt:
    """Return the exact ownership-authenticated receipt bytes will represent."""
    codex = receipt.harnesses.get("codex")
    if codex is None:
        return receipt
    return replace(
        receipt,
        harnesses={
            **receipt.harnesses,
            "codex": authenticate_codex_receipt(
                codex, key_path=destination.parent / "ownership.key"
            ),
        },
    )


def read_receipt(path: Path | None = None) -> InstallationReceipt | None:
    """Read and strictly reconstruct a secret-free installation receipt."""
    source = _receipt_path(path)
    if not source.exists():
        return None
    try:
        document = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise StateError("unable to read installation receipt") from error
    _assert_secret_free(document)
    try:
        receipt = _decode_receipt(document)
    except (KeyError, TypeError, ValueError) as error:
        raise StateError("installation receipt has an invalid schema") from error
    _validate_receipt(receipt, ownership_key_path=source.parent / "ownership.key")
    return receipt


def retired_graphify_transaction_path(receipt_path: Path) -> Path:
    """Return the private journal path paired with one installation receipt."""
    return receipt_path.with_name(f".{receipt_path.name}.retired-graphify.json")


def receipt_digest(receipt: InstallationReceipt) -> str:
    """Return a stable identity for a validated legacy receipt."""
    payload = json.dumps(
        asdict(receipt), sort_keys=True, separators=(",", ":")
    ).encode()
    return hashlib.sha256(payload).hexdigest()


def read_retired_graphify_transaction(
    path: Path,
) -> RetiredGraphifyTransaction | None:
    """Read a validated Graphify retirement journal without changing state."""
    if not path.exists():
        return None
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
        _assert_secret_free(document)
        transaction = _decode_retired_graphify_transaction(document)
    except (
        OSError,
        UnicodeError,
        json.JSONDecodeError,
        KeyError,
        TypeError,
        ValueError,
    ) as error:
        raise StateError("unable to read retired Graphify transaction") from error
    _validate_receipt(
        transaction.legacy_receipt, ownership_key_path=path.parent / "ownership.key"
    )
    _validate_receipt(
        transaction.target_receipt, ownership_key_path=path.parent / "ownership.key"
    )
    return transaction


def write_retired_graphify_transaction_atomic(
    path: Path, transaction: RetiredGraphifyTransaction
) -> None:
    """Durably record the cleanup phase before advancing a native mutation."""
    if transaction.phase not in _RETIREMENT_PHASES:
        raise StateError("retired Graphify transaction has an invalid phase")
    if not _SHA256.fullmatch(transaction.legacy_receipt_digest):
        raise StateError("retired Graphify transaction has an invalid receipt digest")
    if not _SHA256.fullmatch(transaction.ownership_proof):
        raise StateError("retired Graphify transaction has an invalid ownership proof")
    _validate_receipt(
        transaction.legacy_receipt, ownership_key_path=path.parent / "ownership.key"
    )
    _validate_receipt(
        transaction.target_receipt, ownership_key_path=path.parent / "ownership.key"
    )
    document = {
        "schema_version": 1,
        "phase": transaction.phase,
        "legacy_receipt_digest": transaction.legacy_receipt_digest,
        "legacy_receipt": asdict(transaction.legacy_receipt),
        "target_receipt": asdict(transaction.target_receipt),
        "ownership_proof": transaction.ownership_proof,
    }
    _assert_secret_free(document)
    _write_private_json_atomic(path, document)


def clear_retired_graphify_transaction(path: Path) -> None:
    """Remove the completed private cleanup journal."""
    try:
        path.unlink(missing_ok=True)
        if path.parent.exists():
            _fsync_directory(path.parent)
    except OSError as error:
        raise StateError("unable to clear retired Graphify transaction") from error


def _fsync_directory(directory: Path) -> None:
    descriptor = os.open(directory, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _write_private_json_atomic(path: Path, document: dict[str, Any]) -> None:
    payload = (json.dumps(document, indent=2, sort_keys=True) + "\n").encode()
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    descriptor = -1
    temporary: Path | None = None
    try:
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
        )
        temporary = Path(temporary_name)
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "wb") as stream:
            descriptor = -1
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        temporary = None
        _fsync_directory(path.parent)
    except OSError as error:
        raise StateError("unable to write private state atomically") from error
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def _assert_secret_free(value: Any, *, key: str | None = None) -> None:
    if key is not None and _CREDENTIAL_KEY.search(key):
        raise StateError("receipt contains credential material")
    if isinstance(value, dict):
        for child_key, child_value in value.items():
            if not isinstance(child_key, str):
                raise StateError("installation receipt keys must be strings")
            _assert_secret_free(child_value, key=child_key)
    elif isinstance(value, (list, tuple)):
        for child in value:
            _assert_secret_free(child)
    elif isinstance(value, str) and contains_credential_material(value):
        raise StateError("receipt contains credential material")


def _validate_receipt(
    receipt: InstallationReceipt, *, ownership_key_path: Path
) -> None:
    if receipt.schema_version != 1:
        raise StateError("unsupported installation receipt schema version")
    if not _FULL_COMMIT.fullmatch(receipt.source_commit):
        raise StateError("installation receipt source commit must be a full SHA")
    if not _SHA256.fullmatch(receipt.archive_sha256):
        raise StateError("installation receipt archive SHA-256 is invalid")
    if any(
        not name or not _SHA256.fullmatch(checksum)
        for name, checksum in receipt.bundle_checksums.items()
    ):
        raise StateError("installation receipt bundle checksum is invalid")
    unknown_harnesses = set(receipt.harnesses) - _SUPPORTED_HARNESSES
    if unknown_harnesses:
        raise StateError(
            "unsupported receipt harness: " + ", ".join(sorted(unknown_harnesses))
        )
    for name, harness in receipt.harnesses.items():
        if name != harness.harness:
            raise StateError("receipt harness key does not match its identity")
        if not harness.verified and not harness.errors:
            raise StateError("an unverified harness must record an explicit error")
        if not harness.verified and any(
            value.strip().lower() not in _NON_SUCCESS_CAPABILITY_VALUES
            for value in harness.capabilities.values()
        ):
            raise StateError(
                "an unverified harness must use explicit non-success capabilities"
            )
        ownership_errors = capability_ownership_errors(
            harness, key_path=ownership_key_path
        )
        ownership_errors = (
            *ownership_errors,
            *_special_owned_entry_errors(harness, ownership_key_path),
        )
        if ownership_errors:
            raise StateError("; ".join(ownership_errors))


def _special_owned_entry_errors(
    receipt: HarnessReceipt, ownership_key_path: Path
) -> tuple[str, ...]:
    errors: list[str] = []
    if receipt.harness == "codex":
        errors.extend(
            codex_receipt_ownership_errors(receipt, key_path=ownership_key_path)
        )
    for entry in receipt.owned_entries:
        if entry.kind == "codex-skill-source":
            if (
                receipt.harness != "codex"
                or entry.identifier != "codex-shared-skills"
                or entry.ownership_marker != "manifest"
                or not entry.target_path
                or Path(entry.target_path).name != "skills"
                or Path(entry.target_path).parent.name != ".codex"
            ):
                errors.append("invalid Codex skill-source ownership entry")
        elif entry.kind == "plugin-enabled-state" and (
            receipt.harness != "codex"
            or entry.identifier != "i-have-adhd@i-have-adhd"
            or entry.ownership_marker != "manifest"
            or not entry.target_path
            or Path(entry.target_path).name != "config.toml"
            or Path(entry.target_path).parent.name != ".codex"
        ):
            errors.append("invalid Codex plugin enabled-state ownership entry")
        elif entry.kind == "codex-catalog":
            _catalog, catalog_errors = codex_catalog_ownership(
                entry, key_path=ownership_key_path
            )
            if receipt.harness != "codex" or catalog_errors:
                errors.append("invalid Codex catalog ownership entry")
        elif entry.kind == "codex-receipt-auth" and (
            receipt.harness != "codex"
            or entry.ownership_marker != "manifest"
            or entry.target_path is not None
        ):
            errors.append("invalid full Codex ownership entry")
        elif entry.kind == "owned-file":
            _prior, _installed, file_errors = owned_file_ownership(
                entry, key_path=ownership_key_path
            )
            if file_errors:
                errors.extend(file_errors)
    return tuple(errors)


def _decode_receipt(value: Any) -> InstallationReceipt:
    document = _object(
        value,
        {
            "schema_version",
            "coordinator_version",
            "release_version",
            "source_commit",
            "source_dirty",
            "archive_sha256",
            "bundle_checksums",
            "selected_optional",
            "harnesses",
            "migration_backup",
        },
    )
    harness_values = _object(document["harnesses"])
    harnesses = {name: _decode_harness(item) for name, item in harness_values.items()}
    bundle_checksums = _string_map(document["bundle_checksums"])
    migration_backup = document["migration_backup"]
    if migration_backup is not None and not isinstance(migration_backup, str):
        raise TypeError("migration_backup must be a string or null")
    return InstallationReceipt(
        schema_version=_integer(document["schema_version"]),
        coordinator_version=_string(document["coordinator_version"]),
        release_version=_string(document["release_version"]),
        source_commit=_string(document["source_commit"]),
        source_dirty=_boolean(document["source_dirty"]),
        archive_sha256=_string(document["archive_sha256"]),
        bundle_checksums=bundle_checksums,
        selected_optional=_string_tuple(document["selected_optional"]),
        harnesses=harnesses,
        migration_backup=migration_backup,
    )


def _decode_retired_graphify_transaction(value: Any) -> RetiredGraphifyTransaction:
    """Strictly reconstruct a receipt-bound Graphify retirement journal."""
    document = _object(
        value,
        {
            "schema_version",
            "phase",
            "legacy_receipt_digest",
            "legacy_receipt",
            "target_receipt",
            "ownership_proof",
        },
    )
    if _integer(document["schema_version"]) != 1:
        raise ValueError("unsupported retired Graphify transaction schema version")
    phase = _string(document["phase"])
    if phase not in _RETIREMENT_PHASES:
        raise ValueError("invalid retired Graphify transaction phase")
    legacy_receipt_digest = _string(document["legacy_receipt_digest"])
    if not _SHA256.fullmatch(legacy_receipt_digest):
        raise ValueError("invalid retired Graphify transaction receipt digest")
    ownership_proof = _string(document["ownership_proof"])
    if not _SHA256.fullmatch(ownership_proof):
        raise ValueError("invalid retired Graphify transaction ownership proof")
    return RetiredGraphifyTransaction(
        phase=phase,
        legacy_receipt_digest=legacy_receipt_digest,
        legacy_receipt=_decode_receipt(document["legacy_receipt"]),
        target_receipt=_decode_receipt(document["target_receipt"]),
        ownership_proof=ownership_proof,
    )


def _decode_harness(value: Any) -> HarnessReceipt:
    document = _object(
        value,
        {
            "harness",
            "adapter_version",
            "native_version",
            "plugin_ids",
            "owned_entries",
            "capabilities",
            "verified",
            "errors",
        },
    )
    entries = tuple(
        _decode_owned_entry(item) for item in _array(document["owned_entries"])
    )
    return HarnessReceipt(
        harness=_string(document["harness"]),
        adapter_version=_string(document["adapter_version"]),
        native_version=_string(document["native_version"]),
        plugin_ids=_string_tuple(document["plugin_ids"]),
        owned_entries=entries,
        capabilities=_string_map(document["capabilities"]),
        verified=_boolean(document["verified"]),
        errors=_string_tuple(document["errors"]),
    )


def _decode_owned_entry(value: Any) -> OwnedEntry:
    document = _object(
        value,
        {"kind", "identifier", "ownership_marker", "target_path", "previous_checksum"},
    )
    target_path = document["target_path"]
    previous_checksum = document["previous_checksum"]
    if target_path is not None and not isinstance(target_path, str):
        raise TypeError("target_path must be a string or null")
    if previous_checksum is not None and not isinstance(previous_checksum, str):
        raise TypeError("previous_checksum must be a string or null")
    return OwnedEntry(
        kind=_string(document["kind"]),
        identifier=_string(document["identifier"]),
        ownership_marker=_string(document["ownership_marker"]),
        target_path=target_path,
        previous_checksum=previous_checksum,
    )


def _object(value: Any, keys: set[str] | None = None) -> dict[str, Any]:
    if not isinstance(value, dict) or any(not isinstance(key, str) for key in value):
        raise TypeError("expected object")
    if keys is not None and set(value) != keys:
        raise ValueError("object keys do not match schema")
    return value


def _array(value: Any) -> list[Any]:
    if not isinstance(value, list):
        raise TypeError("expected array")
    return value


def _string(value: Any) -> str:
    if not isinstance(value, str):
        raise TypeError("expected string")
    return value


def _boolean(value: Any) -> bool:
    if not isinstance(value, bool):
        raise TypeError("expected boolean")
    return value


def _integer(value: Any) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise TypeError("expected integer")
    return value


def _string_tuple(value: Any) -> tuple[str, ...]:
    return tuple(_string(item) for item in _array(value))


def _string_map(value: Any) -> dict[str, str]:
    return {key: _string(item) for key, item in _object(value).items()}

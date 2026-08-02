"""Deterministic receipt linkage for coordinator-created capabilities."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from manifest_agent.capabilities import load_mcp_catalog
from manifest_agent.models import HarnessReceipt, OwnedEntry

_MARKER = "manifest"
_OWNED_STATUS = "installed-by-manifest"
_CAPABILITY_KINDS = frozenset({"executable", "mcp"})


def owned_capability_entry(
    kind: str, identifier: str, target_path: str | None = None
) -> OwnedEntry:
    """Create an owned entry linked to its canonical capability result."""
    checksum = capability_ownership_checksum(kind, identifier, target_path)
    return OwnedEntry(kind, identifier, _MARKER, target_path, checksum)


def capability_ownership_checksum(
    kind: str, identifier: str, target_path: str | None
) -> str:
    """Hash the exact non-secret metadata that authorizes later removal."""
    identity = _capability_identity(kind, identifier)
    payload = json.dumps(
        {
            "capability": identity,
            "identifier": identifier,
            "kind": kind,
            "ownership_marker": _MARKER,
            "status": _OWNED_STATUS,
            "target_path": target_path,
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return hashlib.sha256(payload).hexdigest()


def capability_ownership_errors(
    receipt: HarnessReceipt, *, expected_cursor_path: Path | None = None
) -> tuple[str, ...]:
    """Validate bidirectional ownership facts before destructive cleanup."""
    errors: list[str] = []
    owned_identities: set[str] = set()
    for entry in receipt.owned_entries:
        if entry.kind not in _CAPABILITY_KINDS:
            continue
        identity = f"{entry.kind}:{entry.identifier}"
        if identity in owned_identities:
            errors.append(f"receipt repeats owned capability {identity}")
            continue
        owned_identities.add(identity)
        errors.extend(
            _entry_errors(receipt, entry, expected_cursor_path=expected_cursor_path)
        )

    expected_identities = {
        identity
        for identity, status in receipt.capabilities.items()
        if status == _OWNED_STATUS and identity.partition(":")[0] in _CAPABILITY_KINDS
    }
    for identity in sorted(expected_identities - owned_identities):
        errors.append(f"receipt lacks ownership metadata for {identity}")
    return tuple(errors)


def _entry_errors(
    receipt: HarnessReceipt,
    entry: OwnedEntry,
    *,
    expected_cursor_path: Path | None,
) -> list[str]:
    identity = f"{entry.kind}:{entry.identifier}"
    errors: list[str] = []
    try:
        canonical_identity = _capability_identity(entry.kind, entry.identifier)
    except ValueError as error:
        return [str(error)]
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
    expected_checksum = capability_ownership_checksum(
        entry.kind, entry.identifier, entry.target_path
    )
    if entry.previous_checksum != expected_checksum:
        errors.append(f"receipt ownership checksum does not match {identity}")
    return errors


def _target_errors(
    harness: str, entry: OwnedEntry, *, expected_cursor_path: Path | None
) -> list[str]:
    identity = f"{entry.kind}:{entry.identifier}"
    if entry.kind == "executable":
        return (
            [] if entry.target_path is None else [f"invalid target path for {identity}"]
        )
    if harness != "cursor":
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


def _capability_identity(kind: str, identifier: str) -> str:
    if kind == "executable" and identifier == "graphify":
        return "executable:graphify"
    if kind == "mcp" and identifier in load_mcp_catalog():
        return f"mcp:{identifier}"
    raise ValueError(
        f"receipt contains unsupported owned capability {kind}:{identifier}"
    )

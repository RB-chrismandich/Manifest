"""Exact, secret-free OMP identities carried by the full receipt HMAC."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from manifest_agent.adapters.omp_inventory import (
    OMP_MARKETPLACE,
    OmpInventoryError,
    cache_directory_name,
    directory_sha256,
    document_sha256,
    plugin_path,
    read_object,
    regular_chain,
    runtime_name,
)
from manifest_agent.models import HarnessReceipt, OwnedEntry

PLUGIN_KIND = "omp-native-plugin"
MARKETPLACE_KIND = "omp-native-marketplace"
IDENTITY_KINDS = frozenset({PLUGIN_KIND, MARKETPLACE_KIND})


def marketplace_identity(root: Path, row: Mapping[str, Any]) -> dict[str, Any]:
    path = root / "plugins/cache/marketplaces" / OMP_MARKETPLACE
    if row.get("name") != OMP_MARKETPLACE or row.get("catalogPath") != str(
        path / "marketplace.json"
    ):
        raise OmpInventoryError("OMP marketplace catalog path or name is unsafe")
    if row.get("sourceType") != "local" or not isinstance(row.get("sourceUri"), str):
        raise OmpInventoryError("OMP marketplace source is unsupported")
    source = Path(row["sourceUri"])
    if not source.is_absolute():
        raise OmpInventoryError("OMP marketplace source is not absolute")
    return {
        "native_root": str(root),
        "scope": "user",
        "path": str(path),
        "tree_sha256": directory_sha256(path),
        "row_sha256": document_sha256(row),
        "source": str(source),
    }


def plugin_identity(
    root: Path,
    plugin_id: str,
    cli: list[Mapping[str, Any]],
    rows: list[Mapping[str, Any]],
    runtime: Mapping[str, Any],
    marketplace: Mapping[str, Any],
) -> dict[str, Any] | None:
    fallback = plugin_id.partition("@")[0]
    if not rows and not cli:
        source_path = Path(marketplace["sourceUri"]) / "plugins" / fallback
        name = runtime_name(source_path, fallback)
        link = root / "plugins/node_modules" / name
        if name in runtime["plugins"] or link.exists() or link.is_symlink():
            raise OmpInventoryError(f"{plugin_id}: runtime-only inventory conflict")
        return None
    if len(rows) != 1 or rows != cli or rows[0].get("scope") != "user":
        raise OmpInventoryError(f"{plugin_id}: ambiguous or inconsistent native rows")
    path = plugin_path(root, plugin_id, rows[0])
    name = runtime_name(path, fallback)
    link = root / "plugins/node_modules" / name
    regular_chain(link.parent)
    if link.exists() and not link.is_symlink():
        raise OmpInventoryError(f"{plugin_id}: runtime link is user-owned")
    target = str(link.readlink()) if link.is_symlink() else None
    if target is not None and link.resolve(strict=True) != path:
        raise OmpInventoryError(f"{plugin_id}: runtime link points outside its cache")
    # Precise missing runtime/link state authenticates partial recovery, never READY.
    lock_row = runtime["plugins"].get(name)
    return {
        "native_root": str(root),
        "scope": "user",
        "path": str(path),
        "version": rows[0]["version"],
        "runtime_name": name,
        "link_path": str(link),
        "link_target": target,
        "runtime_sha256": document_sha256(lock_row),
        "settings_sha256": document_sha256(runtime.get("settings", {}).get(name)),
        "row_sha256": document_sha256(rows[0]),
        "source": marketplace["sourceUri"],
        "tree_sha256": directory_sha256(path),
        "source_tree_sha256": _source_tree_sha256(
            Path(marketplace["sourceUri"]) / "plugins" / fallback
        ),
    }


def _source_tree_sha256(source: Path) -> str | None:
    """Checkout digest for target validation; None once the checkout is gone."""
    if not source.exists():
        return None
    return directory_sha256(source)


OWNERSHIP_UNSTABLE_FIELDS = frozenset({"source_tree_sha256"})


def ownership_fields(identity: Mapping[str, Any]) -> dict[str, Any]:
    """Installed-ownership view; checkout source drift is target validation only."""
    return {
        key: value
        for key, value in identity.items()
        if key not in OWNERSHIP_UNSTABLE_FIELDS
    }


def identity_entry(
    kind: str, identifier: str, identity: Mapping[str, Any]
) -> OwnedEntry:
    return OwnedEntry(
        kind,
        identifier,
        "manifest",
        str(identity["path"]),
        json.dumps(dict(identity), sort_keys=True, separators=(",", ":")),
    )


def decode_identity(entry: OwnedEntry) -> dict[str, Any]:
    try:
        value = json.loads(entry.previous_checksum or "")
    except (TypeError, json.JSONDecodeError) as error:
        raise OmpInventoryError("OMP receipt native identity is malformed") from error
    common = {"native_root", "scope", "path", "source", "tree_sha256", "row_sha256"}
    fields = (
        common
        if entry.kind == MARKETPLACE_KIND
        else common
        | {
            "version",
            "runtime_name",
            "link_path",
            "link_target",
            "runtime_sha256",
            "settings_sha256",
            "source_tree_sha256",
        }
    )
    if not isinstance(value, dict) or set(value) != fields:
        raise OmpInventoryError("OMP receipt native identity has an invalid schema")
    if entry.kind not in IDENTITY_KINDS or entry.ownership_marker != "manifest":
        raise OmpInventoryError("OMP receipt native ownership marker is invalid")
    if value["scope"] != "user" or entry.target_path != value["path"]:
        raise OmpInventoryError("OMP receipt native path/scope identity is invalid")
    for key, item in value.items():
        if key == "link_target" and item is None:
            continue
        if not isinstance(item, str) or not item:
            raise OmpInventoryError(
                "OMP receipt native identity contains invalid values"
            )
        if key.endswith("sha256") and (
            len(item) != 64 or any(char not in "0123456789abcdef" for char in item)
        ):
            raise OmpInventoryError("OMP receipt native identity digest is invalid")
    _validate_identity_location(entry, value)
    return value


def _validate_identity_location(entry: OwnedEntry, value: Mapping[str, Any]) -> None:
    root = Path(value["native_root"])
    if not root.is_absolute() or root.name != ".omp" or ".." in root.parts:
        raise OmpInventoryError("OMP receipt native root is unsafe")
    if not Path(value["source"]).is_absolute():
        raise OmpInventoryError("OMP receipt native source is unsafe")
    if entry.kind == MARKETPLACE_KIND:
        if (
            entry.identifier != OMP_MARKETPLACE
            or Path(value["path"]) != root / "plugins/cache/marketplaces/manifest"
        ):
            raise OmpInventoryError("OMP receipt marketplace identity is unsafe")
        return
    name, separator, marketplace = entry.identifier.partition("@")
    if not separator or marketplace != OMP_MARKETPLACE:
        raise OmpInventoryError("OMP receipt plugin identity is unsafe")
    expected = (
        root
        / "plugins/cache/plugins"
        / cache_directory_name(name, marketplace, value["version"])
    )
    if Path(value["path"]) != expected:
        raise OmpInventoryError("OMP receipt plugin path is unsafe")
    runtime = value["runtime_name"]
    link = root / "plugins/node_modules" / runtime
    if (
        ".." in Path(runtime).parts
        or Path(runtime).is_absolute()
        or str(link) != value["link_path"]
    ):
        raise OmpInventoryError("OMP receipt runtime link identity is unsafe")


def receipt_entries(
    receipt: HarnessReceipt | None,
) -> dict[tuple[str, str], OwnedEntry]:
    entries = {}
    if receipt is None:
        return entries
    for entry in receipt.owned_entries:
        if entry.kind == "omp-receipt-auth":
            continue
        if entry.kind not in IDENTITY_KINDS:
            raise OmpInventoryError(
                "OMP receipt contains unsupported ownership entries"
            )
        decode_identity(entry)
        key = (entry.kind, entry.identifier)
        if key in entries:
            raise OmpInventoryError("OMP receipt repeats a native identity")
        entries[key] = entry
    ids = tuple(
        sorted(identifier for kind, identifier in entries if kind == PLUGIN_KIND)
    )
    if tuple(sorted(receipt.plugin_ids)) != ids:
        raise OmpInventoryError(
            "OMP receipt plugin IDs disagree with owned native identities"
        )
    return entries


def desired_catalog(desired) -> dict[str, Any]:
    from manifest_agent.catalog import load_catalog
    from manifest_agent.contracts import DOMAIN_BUNDLES
    from manifest_agent.service_state import bundle_checksums

    if tuple(contract.name for contract in desired.contracts) != DOMAIN_BUNDLES:
        raise OmpInventoryError(
            "OMP desired state must contain exact canonical domains"
        )
    root = desired.release_root.resolve(strict=True)
    catalog_path = root / ".claude-plugin/marketplace.json"
    document = read_object(catalog_path, "desired marketplace catalog")
    if document is None or document.get("name") != OMP_MARKETPLACE:
        raise OmpInventoryError("desired OMP marketplace name is invalid")
    plugins = load_catalog(catalog_path)
    actual = {plugin.name: plugin.version for plugin in plugins}
    expected = {contract.name: contract.version for contract in desired.all_contracts}
    if any(actual.get(name) != version for name, version in expected.items()):
        raise OmpInventoryError(
            "desired OMP catalog does not match validated contracts"
        )

    if (
        not desired.source_bundle_checksums
        or dict(desired.source_bundle_checksums) != bundle_checksums(desired)
        or desired.source_catalog_sha256
        != hashlib.sha256(catalog_path.read_bytes()).hexdigest()
    ):
        raise OmpInventoryError(
            "OMP target source bytes differ from validated desired state"
        )
    return document


def catalog_versions(document: Mapping[str, Any]) -> dict[str, tuple[str, str]]:
    rows = document.get("plugins")
    if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
        raise OmpInventoryError("OMP native marketplace catalog is malformed")
    result = {}
    for row in rows:
        name, version, source = row.get("name"), row.get("version"), row.get("source")
        if (
            not all(isinstance(item, str) and item for item in (name, version, source))
            or name in result
        ):
            raise OmpInventoryError(
                "OMP native marketplace plugin identity is malformed"
            )
        result[name] = (version, source)
    return result

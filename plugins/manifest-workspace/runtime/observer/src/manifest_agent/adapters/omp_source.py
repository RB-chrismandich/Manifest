"""Exact-prior preflight and native local marketplace source replacement."""

from pathlib import Path

from manifest_agent.adapters.omp_identity import (
    MARKETPLACE_KIND,
    PLUGIN_KIND,
    catalog_versions,
    decode_identity,
    desired_catalog,
    identity_entry,
    marketplace_identity,
    ownership_fields,
    pending_source,
)
from manifest_agent.adapters.omp_inventory import (
    OMP_MARKETPLACE,
    OmpInventoryError,
    cache_directory_name,
    directory_sha256,
    document_sha256,
    read_object,
    regular_chain,
)


def _authorize_source_replacement(changed, entries, registry):
    if changed and (MARKETPLACE_KIND, OMP_MARKETPLACE) not in entries:
        raise OmpInventoryError("refusing replacement of an unowned OMP marketplace")
    owned_ids = {identifier for kind, identifier in entries if kind == PLUGIN_KIND}
    if changed and any(
        plugin_id.endswith("@manifest") and rows and plugin_id not in owned_ids
        for plugin_id, rows in registry.items()
    ):
        raise OmpInventoryError(
            "OMP source replacement is referenced by foreign/unowned packages"
        )


def _plugin_identity_conflict(plugin_id, identity, previous):
    current = None if identity is None else ownership_fields(identity)
    if previous is not None and current != ownership_fields(decode_identity(previous)):
        raise OmpInventoryError(
            f"{plugin_id}: native identity changed after signing; refusing repair"
        )
    if previous is None and identity is not None:
        return f"{plugin_id}: existing unowned plugin will not be adopted"
    return None


def _require_installed_source(plugin_id, identity, previous, bundle):
    """Compare the digest signed at install; the live checkout may have changed."""
    signed = identity if previous is None else decode_identity(previous)
    installed = signed["source_tree_sha256"]
    if installed is not None and installed != directory_sha256(bundle):
        raise OmpInventoryError(
            f"{plugin_id}: same-version source changed in place; "
            "cannot be force-overwritten"
        )


def _require_prior_source_catalog(row, expected):
    source = read_object(
        Path(row["sourceUri"]) / ".claude-plugin/marketplace.json",
        "prior source catalog",
    )
    if source is None:
        raise OmpInventoryError(
            "OMP prior source is unavailable for source replacement recovery"
        )
    # Recovery re-adds the mutable checkout; it must match the native catalog
    # that the signed marketplace identity already authenticates.
    cached = read_object(
        Path(expected["path"]) / "marketplace.json",
        "authenticated marketplace catalog",
    )
    if cached != source:
        raise OmpInventoryError(
            "OMP prior source catalog differs from the authenticated native catalog"
        )


def owned_marketplace_matches(adapter, snapshot, entries):
    """True when the live marketplace is the signed one; may finish a write-ahead."""
    owned_market = entries.get((MARKETPLACE_KIND, OMP_MARKETPLACE))
    if owned_market is None:
        return True
    row = snapshot[1].get(OMP_MARKETPLACE)
    existing = marketplace_identity(snapshot[0], row) if row else None
    return existing == decode_identity(owned_market) or _adopt_pending_source(
        adapter, snapshot, existing, owned_market, entries
    )


def _adopt_pending_source(adapter, snapshot, existing, owned_market, entries):
    """Adopt only the exact signed write-ahead replacement target; else refuse."""
    intent = pending_source(owned_market)
    if intent is None or existing is None or existing["source"] != intent["source"]:
        return False
    if existing["native_root"] != decode_identity(owned_market)["native_root"]:
        return False
    catalog = read_object(
        Path(existing["path"]) / "marketplace.json", "native marketplace catalog"
    )
    if catalog is None or document_sha256(catalog) != intent["catalog_sha256"]:
        return False
    rebound = {}
    for kind, plugin_id in entries:
        if kind != PLUGIN_KIND:
            continue
        identity = adapter._identity(snapshot, plugin_id)
        previous = ownership_fields(decode_identity(entries[(kind, plugin_id)]))
        if (
            identity is None
            or identity["source"] != intent["source"]
            or any(
                previous[key] != identity[key] for key in previous if key != "source"
            )
        ):
            return False
        rebound[(kind, plugin_id)] = identity_entry(kind, plugin_id, identity)
    entries.update(rebound)
    entries[(MARKETPLACE_KIND, OMP_MARKETPLACE)] = identity_entry(
        MARKETPLACE_KIND, OMP_MARKETPLACE, existing
    )
    return True


class OmpSourceMixin:
    def _preflight(self, desired, prior):
        catalog = desired_catalog(desired)
        entries = self._authenticated_entries(prior)
        snapshot = self._snapshot()
        root, markets, registry, _runtime, _cli = snapshot
        row = markets.get(OMP_MARKETPLACE)
        existing = marketplace_identity(root, row) if row else None
        if not owned_marketplace_matches(self, snapshot, entries):
            raise OmpInventoryError(
                "OMP owned marketplace source/catalog changed after signing"
            )
        source = str(desired.release_root.resolve(strict=True))
        native_catalog = (
            read_object(
                Path(existing["path"]) / "marketplace.json",
                "native marketplace catalog",
            )
            if existing
            else None
        )
        changed = existing is not None and (
            existing["source"] != source
            or native_catalog is None
            or catalog_versions(native_catalog) != catalog_versions(catalog)
        )
        _authorize_source_replacement(changed, entries, registry)
        observed, conflicts = {}, {}
        for contract in desired.all_contracts:
            plugin_id = f"{contract.name}@{OMP_MARKETPLACE}"
            identity = self._identity(snapshot, plugin_id)
            previous = entries.get((PLUGIN_KIND, plugin_id))
            conflict = _plugin_identity_conflict(plugin_id, identity, previous)
            if conflict is not None:
                conflicts[plugin_id] = conflict
            target = (
                root
                / "plugins/cache/plugins"
                / cache_directory_name(contract.name, OMP_MARKETPLACE, contract.version)
            )
            regular_chain(target.parent)
            if identity is None or identity["version"] != contract.version:
                if target.exists() or target.is_symlink():
                    raise OmpInventoryError(
                        f"{plugin_id}: target cache collision; "
                        "no force overwrite permitted"
                    )
            else:
                _require_installed_source(
                    plugin_id, identity, previous, desired.bundle_path(contract.name)
                )
            observed[plugin_id] = identity
        if row is None:
            target = root / "plugins/cache/marketplaces/manifest"
            if target.exists() or target.is_symlink():
                raise OmpInventoryError("unowned OMP marketplace cache collision")
        return snapshot, entries, observed, conflicts, changed

    def _replace_source(self, desired, snapshot, entries):
        row = snapshot[1][OMP_MARKETPLACE]
        expected = decode_identity(entries[(MARKETPLACE_KIND, OMP_MARKETPLACE)])
        # Native compensation must be possible before changing the registry.
        _require_prior_source_catalog(row, expected)
        removed = [False]
        try:
            self._preserve(
                MARKETPLACE_KIND,
                OMP_MARKETPLACE,
                expected,
                ("omp", "plugin", "marketplace", "remove", OMP_MARKETPLACE),
                removed,
                desired=desired,
            )
            self._command(
                (
                    "omp",
                    "plugin",
                    "marketplace",
                    "add",
                    str(desired.release_root.resolve(strict=True)),
                ),
                desired=desired,
            )
        except (OSError, ValueError) as error:
            if not removed[0]:
                raise
            live = self._snapshot()
            created = live[1].get(OMP_MARKETPLACE)
            if created is not None:
                replacement = marketplace_identity(live[0], created)
                if replacement == expected:
                    raise OmpInventoryError(
                        "OMP source replacement failed; prior source remains intact: "
                        f"{error}"
                    ) from error
                if replacement["source"] != str(desired.release_root.resolve()):
                    raise OmpInventoryError(
                        "OMP source recovery refused a concurrent foreign registration"
                    ) from error
                self._preserve(
                    MARKETPLACE_KIND,
                    OMP_MARKETPLACE,
                    replacement,
                    ("omp", "plugin", "marketplace", "remove", OMP_MARKETPLACE),
                )
            self._restore_prior_source(entries, row, error)

    def _restore_prior_source(self, entries, row, error):
        restore_error = None
        try:
            self._command(("omp", "plugin", "marketplace", "add", row["sourceUri"]))
        except OmpInventoryError as restore:
            restore_error = restore
        detail = f"; restore diagnostic: {restore_error}" if restore_error else ""
        try:
            self._capture_owned(
                entries,
                {identifier for kind, identifier in entries if kind == PLUGIN_KIND},
                True,
                source_changed=True,
                expected_source=row["sourceUri"],
            )
        except OmpInventoryError as capture:
            raise OmpInventoryError(
                f"OMP restored source capture failed: {capture}{detail}"
            ) from capture
        raise OmpInventoryError(
            f"OMP source replacement failed; prior native source restored: {error}{detail}"
        ) from error

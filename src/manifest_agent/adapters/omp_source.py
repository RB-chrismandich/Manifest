"""Exact-prior preflight and native local marketplace source replacement."""

from pathlib import Path

from manifest_agent.adapters.omp_identity import (
    MARKETPLACE_KIND,
    PLUGIN_KIND,
    catalog_versions,
    decode_identity,
    desired_catalog,
    marketplace_identity,
)
from manifest_agent.adapters.omp_inventory import (
    OMP_MARKETPLACE,
    OmpInventoryError,
    cache_directory_name,
    directory_sha256,
    read_object,
    regular_chain,
)


class OmpSourceMixin:
    def _preflight(self, desired, prior):
        catalog = desired_catalog(desired)
        entries = self._authenticated_entries(prior)
        snapshot = self._snapshot()
        root, markets, registry, _runtime, _cli = snapshot
        row = markets.get(OMP_MARKETPLACE)
        existing = marketplace_identity(root, row) if row else None
        owned_market = entries.get((MARKETPLACE_KIND, OMP_MARKETPLACE))
        if owned_market is not None and existing != decode_identity(owned_market):
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
        if changed and owned_market is None:
            raise OmpInventoryError(
                "refusing replacement of an unowned OMP marketplace"
            )
        owned_ids = {identifier for kind, identifier in entries if kind == PLUGIN_KIND}
        if changed and any(
            plugin_id.endswith("@manifest") and rows and plugin_id not in owned_ids
            for plugin_id, rows in registry.items()
        ):
            raise OmpInventoryError(
                "OMP source replacement is referenced by foreign/unowned packages"
            )
        observed, conflicts = {}, {}
        for contract in desired.all_contracts:
            plugin_id = f"{contract.name}@{OMP_MARKETPLACE}"
            identity = self._identity(snapshot, plugin_id)
            previous = entries.get((PLUGIN_KIND, plugin_id))
            if previous is not None:
                if identity != decode_identity(previous):
                    raise OmpInventoryError(
                        f"{plugin_id}: native identity changed after signing; "
                        "refusing repair"
                    )
            elif identity is not None:
                conflicts[plugin_id] = (
                    f"{plugin_id}: existing unowned plugin will not be adopted"
                )
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
            elif changed and identity["source_tree_sha256"] != directory_sha256(
                desired.bundle_path(contract.name)
            ):
                raise OmpInventoryError(
                    f"{plugin_id}: same-version changed source "
                    "cannot be force-overwritten"
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
        if (
            read_object(
                Path(row["sourceUri"]) / ".claude-plugin/marketplace.json",
                "prior source catalog",
            )
            is None
        ):
            raise OmpInventoryError(
                "OMP prior source is unavailable for source replacement recovery"
            )
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
            self._command(
                ("omp", "plugin", "marketplace", "add", row["sourceUri"])
            )
            self._capture_owned(
                entries,
                {identifier for kind, identifier in entries if kind == PLUGIN_KIND},
                True,
                source_changed=True,
                expected_source=row["sourceUri"],
            )
            raise OmpInventoryError(
                f"OMP source replacement failed; prior native source restored: {error}"
            ) from error

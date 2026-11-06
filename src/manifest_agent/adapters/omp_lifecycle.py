"""Receipt-backed OMP install, targeted upgrade, and preserved unregister."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from manifest_agent.adapters.base import combine_results
from manifest_agent.adapters.omp_identity import (
    MARKETPLACE_KIND,
    PLUGIN_KIND,
    decode_identity,
    desired_catalog,
    identity_entry,
    marketplace_identity,
    ownership_fields,
    plugin_identity,
)
from manifest_agent.adapters.omp_inventory import (
    OMP_MARKETPLACE,
    OmpInventoryError,
    cache_directory_name,
    directory_sha256,
)
from manifest_agent.adapters.omp_preservation import preserve_native_tree
from manifest_agent.models import HarnessResult, ResultState


def _capture_marketplace(adapter, desired, entries, failures, started, *, primary):
    try:
        live = adapter._snapshot()
        created = live[1].get(OMP_MARKETPLACE)
        if not (started[0] and created is not None):
            return
        identity = marketplace_identity(live[0], created)
    except (OSError, ValueError, OmpInventoryError) as error:
        failures.append(f"{OMP_MARKETPLACE}: post-install capture failed: {error}")
        return
    if identity["source"] != str(desired.release_root.resolve()):
        message = f"{OMP_MARKETPLACE}: OMP created marketplace has unexpected source"
        if not primary:
            raise OmpInventoryError(message)
        failures.append(message)
        return
    key = (MARKETPLACE_KIND, OMP_MARKETPLACE)
    entries[key] = identity_entry(MARKETPLACE_KIND, OMP_MARKETPLACE, identity)


def _register_marketplace(adapter, desired, entries, failures):
    started = [False]
    try:
        adapter._native_mutation_boundary(OMP_MARKETPLACE)
        live = adapter._snapshot()
        target = live[0] / "plugins/cache/marketplaces/manifest"
        if OMP_MARKETPLACE in live[1] or target.exists() or target.is_symlink():
            raise OmpInventoryError(
                "OMP marketplace target appeared at mutation boundary"
            )
        adapter._command(
            (
                "omp",
                "plugin",
                "marketplace",
                "add",
                str(desired.release_root.resolve(strict=True)),
            ),
            desired=desired,
            started=started,
        )
    except BaseException:
        # The original command error stays primary; capture problems only annotate it.
        _capture_marketplace(adapter, desired, entries, failures, started, primary=True)
        raise
    _capture_marketplace(adapter, desired, entries, failures, started, primary=False)
    return (MARKETPLACE_KIND, OMP_MARKETPLACE) in entries


def _install_plugin(adapter, desired, contract, old, entries, failures):
    plugin_id = f"{contract.name}@{OMP_MARKETPLACE}"
    live = adapter._snapshot()
    if old is None and adapter._identity(live, plugin_id) is not None:
        raise OmpInventoryError(f"{plugin_id}: native row appeared concurrently")
    argv = (
        "omp",
        "plugin",
        "upgrade" if old else "install",
        plugin_id,
        "--scope",
        "user",
    )
    started = [False]
    try:
        if old is not None:
            current = decode_identity(entries[(PLUGIN_KIND, plugin_id)])
            adapter._preserve(PLUGIN_KIND, plugin_id, current, argv, started, desired)
        else:
            adapter._native_mutation_boundary(plugin_id)
            target = (
                live[0]
                / "plugins/cache/plugins"
                / cache_directory_name(contract.name, OMP_MARKETPLACE, contract.version)
            )
            if (
                target.exists()
                or target.is_symlink()
                or adapter._identity(adapter._snapshot(), plugin_id) is not None
            ):
                raise OmpInventoryError(
                    f"{plugin_id}: target appeared at mutation boundary"
                )
            adapter._command(argv, desired=desired, started=started)
    except (OSError, ValueError) as error:
        failures.append(str(error))
    finally:
        try:
            created = adapter._identity(adapter._snapshot(), plugin_id)
        except (OSError, ValueError, OmpInventoryError) as error:
            failures.append(f"{plugin_id}: post-install capture failed: {error}")
        else:
            if (
                started[0]
                and created is not None
                and created["version"] == contract.version
            ):
                entries[(PLUGIN_KIND, plugin_id)] = identity_entry(
                    PLUGIN_KIND, plugin_id, created
                )


def _authorize_uninstall(adapter, entries, snapshot):
    for (kind, identifier), entry in entries.items():
        identity = decode_identity(entry)
        if identity["native_root"] != str(snapshot[0]):
            raise OmpInventoryError("OMP receipt belongs to a different native root")
        missing = (
            kind == PLUGIN_KIND and adapter._identity(snapshot, identifier) is None
        ) or (kind == MARKETPLACE_KIND and identifier not in snapshot[1])
        if not missing:
            adapter._assert_identity(kind, identifier, identity)
            continue
        if kind == MARKETPLACE_KIND and any(
            plugin_id.endswith("@manifest") and rows
            for plugin_id, rows in snapshot[2].items()
        ):
            raise OmpInventoryError("OMP plugin references a missing marketplace")
        if kind == PLUGIN_KIND:
            link = Path(identity["link_path"])
            if (
                identity["runtime_name"] in snapshot[3]["plugins"]
                or link.exists()
                or link.is_symlink()
            ):
                raise OmpInventoryError(
                    f"{identifier}: runtime-only inventory conflict"
                )
        if directory_sha256(Path(identity["path"])) != identity["tree_sha256"]:
            raise OmpInventoryError("OMP retained cache changed after unregister")


def _unregister_plugins(adapter, entries):
    failures = []
    for (kind, identifier), entry in entries.items():
        if (
            kind != PLUGIN_KIND
            or adapter._identity(adapter._snapshot(), identifier) is None
        ):
            continue
        try:
            adapter._preserve(
                kind,
                identifier,
                decode_identity(entry),
                ("omp", "plugin", "uninstall", identifier, "--scope", "user"),
            )
            if adapter._identity(adapter._snapshot(), identifier) is not None:
                raise OmpInventoryError(
                    "OMP native unregister did not remove its registration"
                )
        except (ValueError, OSError) as error:
            failures.append(str(error))
    return failures


class OmpLifecycleMixin:
    def _identity(self, snapshot, plugin_id):
        root, markets, registry, runtime, cli = snapshot
        marketplace = markets.get(OMP_MARKETPLACE)
        if marketplace is None:
            if registry.get(plugin_id) or cli.get(plugin_id):
                raise OmpInventoryError("OMP plugin references a missing marketplace")
            return None
        return plugin_identity(
            root,
            plugin_id,
            cli.get(plugin_id, []),
            registry.get(plugin_id, []),
            runtime,
            marketplace,
        )

    def _assert_identity(self, kind, identifier, expected):
        snapshot = self._snapshot()
        if kind == MARKETPLACE_KIND:
            row = snapshot[1].get(identifier)
            actual = marketplace_identity(snapshot[0], row) if row else None
        else:
            actual = self._identity(snapshot, identifier)
        if kind == PLUGIN_KIND:
            actual = None if actual is None else ownership_fields(actual)
            expected = ownership_fields(expected)
        if actual != expected:
            raise OmpInventoryError(
                f"{identifier}: native source/row/runtime/link/content changed "
                "after ownership was signed"
            )

    def _preserve(self, kind, identifier, identity, argv, started=None, desired=None):
        def execute(command):
            if started is not None:
                started[0] = True
            return self._execute(command)

        def authorize():
            if desired is not None:
                desired_catalog(desired)
            self._assert_identity(kind, identifier, identity)

        return preserve_native_tree(
            identity,
            argv,
            authorize=authorize,
            execute=execute,
            boundary=self._native_mutation_boundary,
            identifier=identifier,
        )

    def _command(self, argv, *, desired=None, started=None):
        if desired is not None:
            desired_catalog(desired)
        if started is not None:
            started[0] = True
        command, error = self._execute(argv)
        if error is not None:
            raise OmpInventoryError("; ".join(error.errors))
        if command is None or command.returncode != 0:
            reason = (
                f"exit {command.returncode}: {command.stderr or command.stdout}"
                if command
                else "no result"
            )
            raise OmpInventoryError("OMP native command failed: " + reason)
        return command

    def install(self, desired):
        entries, failures = {}, []
        try:
            with self._native_mutation_lock():
                prior = self._prior_receipt(desired)
                snapshot, entries, observed, conflicts, changed = self._preflight(
                    desired, prior
                )
                authorized = {
                    identifier for kind, identifier in entries if kind == PLUGIN_KIND
                }
                market_owned = (MARKETPLACE_KIND, OMP_MARKETPLACE) in entries
                failures.extend(conflicts.values())
                if snapshot[1].get(OMP_MARKETPLACE) is None:
                    market_owned = _register_marketplace(
                        self, desired, entries, failures
                    )
                elif changed:
                    self._replace_source(desired, snapshot, entries)
                self._capture_owned(
                    entries,
                    authorized,
                    market_owned,
                    source_changed=changed,
                    expected_source=str(desired.release_root.resolve()),
                )
                for contract in desired.all_contracts:
                    plugin_id = f"{contract.name}@{OMP_MARKETPLACE}"
                    if plugin_id in conflicts:
                        continue
                    old = observed[plugin_id]
                    if old is not None and old["version"] == contract.version:
                        continue
                    _install_plugin(self, desired, contract, old, entries, failures)
        except (OSError, ValueError) as error:
            failures.append(str(error))
        owned = tuple(entries.values())
        provisional = HarnessResult(
            self.name, ResultState.BLOCKED, (), {}, owned_entries=owned
        )
        inspected = self.inspect(self.inspection_desired_state(desired, provisional))
        result = replace(inspected, owned_entries=owned)
        if failures:
            result = combine_results(self._blocked("; ".join(failures)), result)
        return result

    def _capture_owned(
        self,
        entries,
        authorized_ids,
        market_owned,
        *,
        source_changed=False,
        expected_source=None,
    ):
        live = self._snapshot()
        for plugin_id in sorted(authorized_ids):
            identity = self._identity(live, plugin_id)
            if identity is not None:
                previous = decode_identity(entries[(PLUGIN_KIND, plugin_id)])
                stable = set(ownership_fields(previous)) - (
                    {"source"} if source_changed else set()
                )
                if any(previous[key] != identity[key] for key in stable):
                    raise OmpInventoryError(
                        f"{plugin_id}: identity changed during source registration"
                    )
                entries[(PLUGIN_KIND, plugin_id)] = identity_entry(
                    PLUGIN_KIND, plugin_id, identity
                )
        if market_owned:
            row = live[1].get(OMP_MARKETPLACE)
            if row is not None:
                identity = marketplace_identity(live[0], row)
                previous = decode_identity(entries[(MARKETPLACE_KIND, OMP_MARKETPLACE)])
                if source_changed:
                    if identity["source"] != expected_source:
                        raise OmpInventoryError(
                            "OMP native source changed concurrently"
                        )
                elif identity != previous:
                    raise OmpInventoryError(
                        "OMP marketplace changed before receipt finalization"
                    )
                entries[(MARKETPLACE_KIND, OMP_MARKETPLACE)] = identity_entry(
                    MARKETPLACE_KIND, OMP_MARKETPLACE, identity
                )

    def migration_cleanup_requires_resume(self, receipt):
        """Keep signed creations registered: retained caches cannot be reinstalled."""
        return bool(self._authenticated_entries(receipt))

    def uninstall(self, receipt):
        try:
            entries = self._authenticated_entries(receipt)
            with self._native_mutation_lock():
                snapshot = self._snapshot()
                _authorize_uninstall(self, entries, snapshot)
                failures = _unregister_plugins(self, entries)
                if failures:
                    return self._blocked("; ".join(failures))
                marketplace = entries.get((MARKETPLACE_KIND, OMP_MARKETPLACE))
                live = self._snapshot()
                references = tuple(
                    plugin_id
                    for plugin_id, rows in live[2].items()
                    if plugin_id.endswith("@manifest") and rows
                )
                if (
                    marketplace is not None
                    and not references
                    and OMP_MARKETPLACE in live[1]
                ):
                    self._preserve(
                        MARKETPLACE_KIND,
                        OMP_MARKETPLACE,
                        decode_identity(marketplace),
                        ("omp", "plugin", "marketplace", "remove", OMP_MARKETPLACE),
                    )
                    if OMP_MARKETPLACE in self._snapshot()[1]:
                        raise OmpInventoryError(
                            "OMP native marketplace unregister did not remove "
                            "its registration"
                        )
                warnings = (
                    ("preserving OMP marketplace: foreign native references remain",)
                    if references
                    else ()
                )
                return HarnessResult(
                    self.name, ResultState.READY, (), {}, warnings=warnings
                )
        except (ValueError, OSError) as error:
            return self._blocked(str(error))

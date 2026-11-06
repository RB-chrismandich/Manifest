"""OMP native package inspection, separate from deferred activation qualification."""

from __future__ import annotations

from pathlib import Path

from manifest_agent.adapters.omp_identity import (
    MARKETPLACE_KIND,
    PLUGIN_KIND,
    catalog_versions,
    decode_identity,
    desired_catalog,
    marketplace_identity,
    ownership_fields,
)
from manifest_agent.adapters.omp_inventory import (
    OMP_MARKETPLACE,
    OmpInventoryError,
    cross_checked_plugin,
    plugin_cli_rows,
    plugin_path,
    read_installed_plugins,
    read_marketplaces,
    read_object,
    read_runtime_document,
    runtime_name,
    skill_file_path,
)
from manifest_agent.models import (
    DesiredState,
    HarnessResult,
    NativeComponentInspection,
    NativeInspection,
    NativePluginInspection,
    ResultState,
)
from manifest_agent.process import redact_text


def _inspect_marketplace(root, desired, source_catalog, row, entries):
    errors = []
    blocked = False
    if row is None:
        return ["missing required marketplace: manifest"], False
    market = marketplace_identity(root, row)
    catalog = read_object(Path(market["path"]) / "marketplace.json", "native catalog")
    if catalog is None:
        raise OmpInventoryError("OMP registered marketplace catalog is missing")
    owned = entries.get((MARKETPLACE_KIND, OMP_MARKETPLACE))
    if owned is not None and decode_identity(owned) != market:
        errors.append("OMP owned marketplace changed outside its receipt")
        blocked = True
    changed = market["source"] != str(desired.release_root.resolve()) or (
        catalog_versions(catalog) != catalog_versions(source_catalog)
    )
    if changed:
        errors.append(
            "OMP native marketplace source/catalog differs from desired release"
        )
        blocked = blocked or owned is None
    return errors, blocked


def _plugin_record(plugin_id, contract, row, root, cross, message):
    if cross is None:
        return NativePluginInspection(
            plugin_id,
            contract.name,
            OMP_MARKETPLACE,
            row.get("sourceUri") if row else None,
            "native-local-marketplace" if row else None,
            None,
            None,
            None,
            str(root),
            None,
            "inconsistent" if message else "missing",
        )
    return NativePluginInspection(
        plugin_id,
        contract.name,
        OMP_MARKETPLACE,
        row.get("sourceUri") if row else None,
        "native-local-marketplace" if row else None,
        cross["version"],
        "user",
        cross["enabled"],
        str(root),
        cross["install_path"],
        "verified" if cross["enabled"] else "disabled",
    )


def _inspect_packages(adapter, desired, snapshot, entries):
    root, markets, registry, runtime, cli = snapshot
    row = markets.get(OMP_MARKETPLACE)
    packages, paths, installed, errors = [], {}, [], []
    blocked = False
    for contract in desired.all_contracts:
        plugin_id = f"{contract.name}@{OMP_MARKETPLACE}"
        rows = registry.get(plugin_id, [])
        name = runtime_name(desired.bundle_path(contract.name), contract.name)
        if len(rows) == 1:
            name = runtime_name(plugin_path(root, plugin_id, rows[0]), contract.name)
        cross, message = cross_checked_plugin(
            plugin_id=plugin_id,
            marketplace=OMP_MARKETPLACE,
            cli_entries=cli.get(plugin_id, []),
            registry_rows=rows,
            runtime_row=runtime["plugins"].get(name),
            native_root=root,
        )
        if message is not None:
            errors.append(message)
            blocked = True
        if cross is None:
            if message is None:
                errors.append(f"missing required plugin: {plugin_id}")
        else:
            owned = entries.get((PLUGIN_KIND, plugin_id))
            if owned is not None and ownership_fields(
                decode_identity(owned)
            ) != ownership_fields(adapter._identity(snapshot, plugin_id)):
                errors.append(
                    f"{plugin_id}: native identity changed outside its receipt"
                )
                blocked = True
            if cross["version"] != contract.version:
                errors.append(
                    f"plugin {plugin_id} expected {contract.version}, "
                    f"found {cross['version']}"
                )
            if not cross["enabled"]:
                errors.append(f"plugin {plugin_id} is disabled")
            else:
                installed.append(plugin_id)
                paths[contract.name] = Path(cross["install_path"])
        packages.append(_plugin_record(plugin_id, contract, row, root, cross, message))
    return packages, paths, installed, errors, blocked


def _resolve_skill(adapter, installed, skills_root, skill):
    command, error = adapter._execute(("omp", "read", f"skill://{skill}"))
    identity_warning = (
        f"OMP skill {skill} resolver identity is absent or outside its package"
    )
    if error is not None or command is None or command.returncode != 0:
        reason = (
            "; ".join(error.errors)
            if error
            else command.stderr
            if command
            else "no result"
        )
        return None, f"OMP skill {skill} resolver failed: {reason}"
    candidate = skill_file_path(command.stdout)
    if candidate is not None:
        expected = installed / skills_root / skill / "SKILL.md"
        try:
            expected_path = expected.resolve(strict=True)
            if Path(candidate).resolve(
                strict=True
            ) == expected_path and expected_path.is_relative_to(
                installed.resolve(strict=True)
            ):
                return str(Path(candidate)), None
        except OSError:
            return None, identity_warning
    return None, identity_warning


def component_records(adapter, desired, paths):
    records = []
    warnings = ["OMP runtime/agent/MCP activation qualification is not observed"]
    for contract in desired.all_contracts:
        installed = paths.get(contract.name)
        skill_root = (
            desired.bundle_path(contract.name) / contract.components.skills_root
        )
        for pattern in contract.components.skills_include:
            for path in sorted(skill_root.glob(pattern)):
                if not path.is_file():
                    continue
                skill = path.parent.name
                resolved = None
                if installed is not None:
                    resolved, warning = _resolve_skill(
                        adapter, installed, contract.components.skills_root, skill
                    )
                    if warning is not None:
                        warnings.append(warning)
                records.append(
                    NativeComponentInspection(
                        "skill",
                        skill,
                        "resolved" if resolved else "unresolved",
                        "native-resolver",
                        resolved,
                    )
                )
        for kind in ("agents", "hooks", "runtime", "guidance"):
            for component in getattr(contract.components, kind):
                records.append(
                    NativeComponentInspection(
                        kind.rstrip("s"),
                        component.id,
                        "unsupported",
                        "not-observed",
                    )
                )
        for kind in ("mcp", "executables"):
            for identifiers in getattr(contract.capabilities, kind).values():
                for identifier in identifiers:
                    records.append(
                        NativeComponentInspection(
                            kind, identifier, "unobserved", "not-observed"
                        )
                    )
    return tuple(records), tuple(redact_text(warning) for warning in warnings)


def _blocked_inspection(name, root, error):
    diagnostic = redact_text(str(error))
    return HarnessResult(
        name,
        ResultState.BLOCKED,
        (),
        {},
        errors=(diagnostic,),
        native_inspection=NativeInspection(
            name,
            "user",
            str(root) if root else None,
            inventory_errors=(diagnostic,),
        ),
    )


class OmpInspectionMixin:
    # Shadow runs set this to their isolated home so ancestor walks never leave it.
    _project_ceiling: Path | None = None

    def _project_ancestors(self):
        for ancestor in (self._cwd, *self._cwd.parents):
            yield ancestor
            if ancestor == self._project_ceiling:
                return

    def _snapshot(self):
        root = self._native_root()
        # Native project resolution walks ancestors. Reject every project
        # registry, including malformed/empty files, instead of shadowing state.
        for ancestor in self._project_ancestors():
            project = ancestor / ".omp"
            if project == root:
                continue
            candidates = (
                project / "plugins",
                project / "marketplaces.json",
                project / ".env",
                project / "agent/.env",
            )
            if any(path.exists() or path.is_symlink() for path in candidates):
                raise OmpInventoryError(
                    "OMP project inventory is unsupported in this execution context"
                )
        profiles = root / "profiles"
        if profiles.is_symlink() or (
            profiles.exists()
            and any(
                path.is_symlink()
                or (path / "plugins").exists()
                or (path / "plugins").is_symlink()
                for path in profiles.iterdir()
            )
        ):
            raise OmpInventoryError(
                "OMP profile inventory makes shared source ownership ambiguous"
            )
        markets = read_marketplaces(root)
        registry = read_installed_plugins(root)
        runtime = read_runtime_document(root)
        command, error = self._execute(("omp", "plugin", "list", "--json"))
        if error is not None:
            raise OmpInventoryError("; ".join(error.errors))
        if command is None or command.returncode != 0:
            reason = command.stderr if command else "no result"
            raise OmpInventoryError("OMP plugin list failed: " + reason)
        rows, diagnostic = plugin_cli_rows(command.stdout)
        if diagnostic is not None:
            raise OmpInventoryError(diagnostic)
        cli = {}
        for row in rows:
            if row.get("scope", "user") != "user" or row.get("shadowedBy"):
                raise OmpInventoryError(
                    "OMP project/scope inventory conflict is unsupported"
                )
            cli[row["id"]] = row["entries"]
        if set(cli) != {key for key, entries in registry.items() if entries}:
            raise OmpInventoryError(
                "OMP CLI and installed registry package sets disagree"
            )
        return root, markets, registry, runtime, cli

    def inspect(self, desired: DesiredState) -> HarnessResult:
        root = None
        try:
            root = self._native_root()
            source_catalog = desired_catalog(desired)
            snapshot = self._snapshot()
            root, markets, _registry, _runtime, _cli = snapshot
            entries = self._authenticated_entries(self._prior_receipt(desired))
            marketplace_errors, blocked = _inspect_marketplace(
                root,
                desired,
                source_catalog,
                markets.get(OMP_MARKETPLACE),
                entries,
            )
            packages, paths, installed, package_errors, package_blocked = (
                _inspect_packages(self, desired, snapshot, entries)
            )
            errors = [*marketplace_errors, *package_errors]
            blocked = blocked or package_blocked
            components, warnings = component_records(self, desired, paths)
            errors = tuple(redact_text(error) for error in errors)
            native = NativeInspection(
                self.name,
                "user",
                str(root),
                tuple(packages),
                components,
                "not-observed",
                errors,
            )
            state = (
                ResultState.BLOCKED
                if blocked
                else ResultState.DRIFTED
                if errors
                else ResultState.READY
            )
            return HarnessResult(
                self.name,
                state,
                tuple(installed),
                {
                    "package-lifecycle": "verified" if not errors else "drifted",
                    "activation": "not-observed",
                },
                errors=errors,
                warnings=warnings,
                native_inspection=native,
            )
        except (ValueError, OSError) as error:
            return _blocked_inspection(self.name, root, error)

"""Read OMP package evidence without loading plugins or mutating receipts."""

from __future__ import annotations

import json
import re
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .components import skill_components
from .inventory import (
    OMP_MARKETPLACE,
    OmpInventoryError,
    cross_checked_plugin,
    omp_native_root,
    plugin_cli_rows,
    plugin_path,
    read_installed_plugins,
    read_marketplaces,
    read_object,
    read_runtime_document,
    regular_chain,
    runtime_name,
)
from .models import (
    NativeInspection,
    NativePluginInspection,
)


def _check_context(root: Path, cwd: Path) -> None:
    for ancestor in (cwd, *cwd.parents):
        project = ancestor / ".omp"
        if project == root:
            continue
        if any(
            path.exists() or path.is_symlink()
            for path in (
                project / "plugins",
                project / "marketplaces.json",
                project / ".env",
                project / "agent/.env",
            )
        ):
            raise OmpInventoryError("OMP project inventory is unsupported")
    profiles = root / "profiles"
    regular_chain(profiles)
    if profiles.exists() and any(
        path.is_symlink()
        or (path / "plugins").exists()
        or (path / "plugins").is_symlink()
        for path in profiles.iterdir()
    ):
        raise OmpInventoryError("OMP profile inventory is unsupported")


def _marketplace_catalog_source(root: Path) -> tuple[Path, Path, str, str]:
    market = read_marketplaces(root).get(OMP_MARKETPLACE)
    native_path = root / "plugins/cache/marketplaces/manifest/marketplace.json"
    if not market or market.get("catalogPath") != str(native_path):
        raise OmpInventoryError("OMP manifest marketplace is missing or mismatched")
    source_type = market.get("sourceType")
    source = market.get("sourceUri")
    if source_type == "local":
        if not isinstance(source, str) or not Path(source).is_absolute():
            raise OmpInventoryError(
                "OMP marketplace source is unsupported or mismatched"
            )
        source_catalog = Path(source) / ".claude-plugin/marketplace.json"
        return native_path, source_catalog, "local", "native-local-marketplace"
    if source_type == "github":
        if (
            not isinstance(source, str)
            or re.fullmatch(
                r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?/[A-Za-z0-9._-]{1,100}",
                source,
            )
            is None
        ):
            raise OmpInventoryError(
                "OMP marketplace source is unsupported or mismatched"
            )
        source_catalog = (
            root / "plugins/cache/marketplaces/manifest/.claude-plugin/marketplace.json"
        )
        return native_path, source_catalog, source, "native-github-marketplace"
    raise OmpInventoryError("OMP marketplace source is unsupported or mismatched")


def _catalog(root: Path) -> tuple[str, str, dict[str, str]]:
    path, source_catalog, source_identity, provenance = _marketplace_catalog_source(
        root
    )
    native = read_object(path, "native catalog")
    try:
        original = read_object(source_catalog, "source catalog")
    except (OmpInventoryError, OSError) as error:
        raise OmpInventoryError(
            "OMP marketplace source catalog is missing or malformed",
        ) from error
    if native is None or original is None or native != original:
        raise OmpInventoryError("OMP marketplace catalog is missing or stale")
    rows = native.get("plugins")
    if native.get("name") != OMP_MARKETPLACE or not isinstance(rows, list):
        raise OmpInventoryError("OMP marketplace catalog is malformed")
    versions = {}
    for row in rows:
        if (
            not isinstance(row, dict)
            or not isinstance(row.get("name"), str)
            or not row["name"]
            or not isinstance(row.get("version"), str)
            or not row["version"]
            or row["name"] in versions
        ):
            raise OmpInventoryError("OMP marketplace catalog package is malformed")
        versions[row["name"]] = row["version"]
    return source_identity, provenance, versions


def _list_plugins(cwd: Path) -> dict:
    try:
        command = subprocess.run(
            ["omp", "plugin", "list", "--json"],
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except (OSError, UnicodeError, subprocess.TimeoutExpired) as error:
        raise OmpInventoryError("OMP plugin list is unavailable") from error
    if command.returncode:
        # Native diagnostics may contain credentials; never echo stderr.
        raise OmpInventoryError("OMP plugin list failed")
    rows, diagnostic = plugin_cli_rows(command.stdout)
    if diagnostic:
        raise OmpInventoryError(diagnostic)
    document = json.loads(command.stdout)
    if document.get("npm") != []:
        raise OmpInventoryError("OMP npm inventory is unsupported or malformed")
    cli = {}
    for row in rows:
        if row.get("scope") != "user" or row.get("shadowedBy"):
            raise OmpInventoryError("OMP project/scope inventory is unsupported")
        cli[row["id"]] = row["entries"]
    return cli


def _list_skills(cwd: Path) -> str:
    try:
        command = subprocess.run(
            ["omp", "skill", "list", "--json"],
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except (OSError, UnicodeError, subprocess.TimeoutExpired) as error:
        raise OmpInventoryError("OMP skill inventory is unavailable") from error
    if command.returncode:
        raise OmpInventoryError("OMP skill inventory failed")
    return command.stdout


def _package(root, plugin_id, entries, rows, runtime, source, provenance, versions):
    name, separator, marketplace = plugin_id.partition("@")
    if not separator or not name or marketplace != OMP_MARKETPLACE:
        raise OmpInventoryError("OMP non-Manifest marketplace inventory is unsupported")
    runtime_id = name
    message = None
    cross = None
    try:
        if len(rows) == 1:
            path = plugin_path(root, plugin_id, rows[0])
            runtime_id = runtime_name(path, name)
        cross, message = cross_checked_plugin(
            plugin_id=plugin_id,
            marketplace=marketplace,
            cli_entries=entries,
            registry_rows=rows,
            runtime_row=runtime["plugins"].get(runtime_id),
            native_root=root,
        )
        if cross:
            metadata = read_object(
                Path(cross["install_path"]) / "package.json", "package"
            )
            if (
                metadata is None
                or metadata.get("version") != cross["version"]
                or versions.get(name) != cross["version"]
            ):
                message = (
                    f"{plugin_id}: package version is stale against catalog/metadata"
                )
    except (OmpInventoryError, OSError) as error:
        message = str(error)
    status = (
        "inconsistent"
        if message
        else "missing"
        if cross is None
        else "verified"
        if cross["enabled"]
        else "disabled"
    )
    if status == "disabled":
        message = f"{plugin_id}: package is disabled"
    record = NativePluginInspection(
        plugin_id,
        name,
        marketplace,
        source,
        provenance,
        cross["version"] if cross else None,
        "user",
        cross["enabled"] if cross else None,
        str(root),
        cross["install_path"] if cross else None,
        status,
    )
    return record, runtime_id, message


@dataclass(frozen=True)
class _NativeInputs:
    source: str
    provenance: str
    versions: dict[str, str]
    registry: dict[str, list[dict[str, Any]]]
    runtime: dict[str, Any]
    cli: dict[str, list[dict[str, Any]]]


def _read_native_inputs(root: Path, cwd: Path) -> _NativeInputs:
    _check_context(root, cwd)
    source, provenance, versions = _catalog(root)
    for relative in (
        "plugins/installed_plugins.json",
        "plugins/omp-plugins.lock.json",
    ):
        if read_object(root / relative, relative) is None:
            raise OmpInventoryError("OMP native inventory is missing")
    registry = read_installed_plugins(root)
    runtime = read_runtime_document(root)
    cli = _list_plugins(cwd)
    if set(cli) != {key for key, rows in registry.items() if rows}:
        raise OmpInventoryError("OMP CLI and installed registry package sets disagree")
    return _NativeInputs(source, provenance, versions, registry, runtime, cli)


def _external_runtime_id(root: Path, plugin_id: str, rows: list[dict]) -> str | None:
    if len(rows) != 1:
        return None
    try:
        path = plugin_path(root, plugin_id, rows[0])
        return runtime_name(path, plugin_id.partition("@")[0])
    except (OmpInventoryError, OSError):
        # Unattributed runtime entries must still fail closed.
        return None


def _inspect_packages(root: Path, inputs: _NativeInputs):
    packages, errors, runtime_ids, external_runtime_ids = [], [], set(), set()
    for plugin_id in sorted(set(inputs.cli) | set(inputs.registry)):
        if (
            re.fullmatch(
                r"[A-Za-z0-9][A-Za-z0-9._~-]*@[A-Za-z0-9][A-Za-z0-9._~-]*",
                plugin_id,
            )
            is None
        ):
            raise OmpInventoryError("OMP marketplace package identity is malformed")
        if plugin_id.partition("@")[2] != OMP_MARKETPLACE:
            if inputs.cli.get(plugin_id, []) != inputs.registry.get(plugin_id, []):
                raise OmpInventoryError(
                    "OMP CLI and installed registry package entries disagree",
                )
            external_id = _external_runtime_id(
                root, plugin_id, inputs.registry.get(plugin_id, [])
            )
            if (
                external_id is not None
                and not external_id.startswith(("@manifest/", "manifest-"))
                and external_id not in inputs.versions
            ):
                external_runtime_ids.add(external_id)
            continue
        record, runtime_id, error = _package(
            root,
            plugin_id,
            inputs.cli.get(plugin_id, []),
            inputs.registry.get(plugin_id, []),
            inputs.runtime,
            inputs.source,
            inputs.provenance,
            inputs.versions,
        )
        packages.append(record)
        runtime_ids.add(runtime_id)
        if error:
            errors.append(error)
    return packages, errors, runtime_ids, external_runtime_ids


def _observe_components(cwd: Path, packages):
    try:
        components, errors = skill_components(_list_skills(cwd), packages)
        return components, list(errors)
    except (OmpInventoryError, OSError) as error:
        return (), [str(error)]


def _verify_native_snapshot(root: Path, inputs: _NativeInputs) -> None:
    if (
        read_installed_plugins(root) != inputs.registry
        or read_runtime_document(root) != inputs.runtime
        or _catalog(root) != (inputs.source, inputs.provenance, inputs.versions)
    ):
        raise OmpInventoryError("OMP inventory changed during inspection")


def inspect_native() -> NativeInspection:
    """Observe default user inventory; absent/ambiguous evidence stays unverified."""
    root = None
    try:
        root = omp_native_root(None)
        cwd = Path.cwd()
        inputs = _read_native_inputs(root, cwd)
        packages, errors, runtime_ids, external_runtime_ids = _inspect_packages(
            root, inputs
        )
        components, component_errors = _observe_components(cwd, packages)
        errors.extend(component_errors)
        _verify_native_snapshot(root, inputs)
        # Unknown/orphaned runtime entries retain the existing stale check.
        if set(inputs.runtime["plugins"]) - runtime_ids - external_runtime_ids:
            errors.append("OMP runtime-only stale inventory is unsupported")
        return NativeInspection(
            "omp",
            "user",
            str(root),
            tuple(packages),
            components,
            "not-observed",
            tuple(errors),
        )
    except (ValueError, OSError) as error:
        return NativeInspection(
            "omp",
            "user",
            str(root) if root else None,
            inventory_errors=(str(error),),
        )


def inspection_report() -> dict:
    """JSON-compatible envelope; package agreement never claims runtime readiness."""
    document = asdict(inspect_native())
    # asdict preserves the immutable model's tuples. Both direct Python and JSON
    # consumers require the same array contract, including empty/error inventories.
    for field in ("packages", "components", "inventory_errors"):
        document[field] = list(document[field])
    return {
        "harnesses": {
            "omp": {
                "state": "DEGRADED",
                "native_inspection": document,
            }
        }
    }

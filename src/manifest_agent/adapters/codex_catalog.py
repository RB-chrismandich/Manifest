"""Codex plugin catalog validation, evidence, and ownership records."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict
from pathlib import Path
from typing import Any

from manifest_agent.adapters.base import (
    CapabilityEvidenceFailure,
    collect_native_component_evidence,
    normalize_component_identity,
)
from manifest_agent.adapters.codex_common import COMMIT, MARKETPLACE, blocked
from manifest_agent.adapters.codex_marketplace import desired_marketplace_identity
from manifest_agent.adapters.codex_mcp_inventory import McpInventoryObservation
from manifest_agent.adapters.codex_native import installed_plugin_path
from manifest_agent.capabilities import (
    CapabilityConflict,
    McpDefinition,
    load_mcp_catalog,
    merge_mcp_definitions,
)
from manifest_agent.codex_config import (
    CodexConfigError,
    observe_plugin_enabled_rollback,
    plugin_enabled_change_from_metadata,
)
from manifest_agent.codex_plugin_backup import (
    CodexPluginBackupError,
    plugin_tree_sha256,
)
from manifest_agent.codex_skill_cutover import inspect_codex_skill_source
from manifest_agent.contracts import DOMAIN_BUNDLES
from manifest_agent.models import (
    AdapterMarketplaceState,
    BundleContract,
    CapabilityTier,
    CatalogPlugin,
    DesiredState,
    HarnessReceipt,
    HarnessResult,
    MarketplaceSourceKind,
    OwnedEntry,
    ResultState,
)
from manifest_agent.ownership import (
    codex_catalog_ownership,
    codex_marketplace_ownership,
    owned_codex_catalog_entry,
)
from manifest_agent.process import redact_text


def catalog(desired: DesiredState) -> tuple[CatalogPlugin, ...]:
    """Preserve compatibility with callers constructing pre-catalog fixtures."""
    if desired.catalog_plugins:
        return desired.catalog_plugins
    return tuple(
        CatalogPlugin(contract.name, contract.version, f"./plugins/{contract.name}")
        for contract in desired.all_contracts
    )


def catalog_snapshot(desired: DesiredState) -> list[dict[str, str]]:
    return [
        {"name": item.name, "source": item.source, "version": item.version}
        for item in catalog(desired)
    ]


def desired_target_identity(desired: DesiredState) -> str:
    payload = json.dumps(
        {
            "archive_sha256": desired.archive_sha256,
            "catalog": catalog_snapshot(desired),
            "marketplace": asdict(desired_marketplace_identity(desired)),
            "release_version": desired.release_version,
            "source_commit": desired.source_commit,
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return hashlib.sha256(payload).hexdigest()


def validate_desired(desired: DesiredState) -> HarnessResult | None:
    names = tuple(contract.name for contract in desired.contracts)
    if names != DOMAIN_BUNDLES:
        return blocked("desired state must contain the exact canonical domain plugins")
    if any(not contract.version for contract in desired.all_contracts):
        return blocked("desired plugin versions must be non-empty")
    plugins = catalog(desired)
    if not plugins or len({plugin.name for plugin in plugins}) != len(plugins):
        return blocked("desired state must contain a unique plugin catalog")
    contract_versions = {
        contract.name: contract.version for contract in desired.all_contracts
    }
    for plugin in plugins:
        expected = contract_versions.get(plugin.name)
        if expected is not None and expected != plugin.version:
            return blocked(
                f"catalog version for {plugin.name} disagrees with its contract"
            )
    if not desired.marketplace_source.source:
        return blocked("desired marketplace source must be non-empty")
    if not COMMIT.fullmatch(desired.source_commit):
        return blocked("Codex marketplace source commit must be immutable")
    if (
        desired.marketplace_source.kind is MarketplaceSourceKind.GIT
        and desired.marketplace_source.ref != desired.source_commit
    ):
        return blocked("desired marketplace ref must match the release commit")
    return None


def verify_rows(
    desired: DesiredState, rows: Sequence[Mapping[str, Any]]
) -> HarnessResult:
    by_id = {
        row.get("pluginId"): row
        for row in rows
        if isinstance(row.get("pluginId"), str) and row.get("installed") is not False
    }
    installed: list[str] = []
    errors: list[str] = []
    plugins = catalog(desired)
    expected_ids = {f"{plugin.name}@{MARKETPLACE}" for plugin in plugins}
    extra_ids = sorted(
        plugin_id
        for plugin_id in by_id
        if plugin_id.endswith(f"@{MARKETPLACE}") and plugin_id not in expected_ids
    )
    errors.extend(
        f"unrecognized Manifest plugin: {plugin_id}" for plugin_id in extra_ids
    )
    for plugin in plugins:
        plugin_id = f"{plugin.name}@{MARKETPLACE}"
        row = by_id.get(plugin_id)
        if row is None:
            errors.append(f"missing required plugin: {plugin_id}")
            continue
        installed.append(plugin_id)
        version = row.get("version")
        if version != plugin.version:
            errors.append(
                redact_text(
                    f"plugin {plugin_id} expected {plugin.version}, found {version}"
                )
            )
        if row.get("enabled") is False:
            errors.append(f"plugin {plugin_id} is disabled")
    state = ResultState.READY if not errors else ResultState.DRIFTED
    return HarnessResult("codex", state, tuple(installed), {}, tuple(errors))


def row_is_ready(
    row: Mapping[str, Any], plugin: CatalogPlugin, desired: DesiredState
) -> bool:
    if row.get("version") != plugin.version or row.get("enabled") is False:
        return False
    installed = installed_plugin_path(row)
    if installed is None:
        return False
    try:
        return plugin_tree_sha256(Path(installed)) == plugin_tree_sha256(
            desired.bundle_path(plugin.name)
        )
    except CodexPluginBackupError:
        return False


def component_evidence(
    desired: DesiredState,
    rows: Sequence[Mapping[str, Any]],
    which: Callable[[str], str | None],
    *,
    served_mcp: Mapping[str, McpDefinition] | None = None,
) -> set[str]:
    """Collect Codex evidence from installed files and exact live MCP definitions."""
    roots: dict[str, Path] = {}
    mcp_servers: dict[str, tuple[str, ...]] = {}
    matching_mcp = _matching_mcp_names(served_mcp or {})
    by_id = {
        row.get("pluginId"): row for row in rows if isinstance(row.get("pluginId"), str)
    }
    for contract in desired.all_contracts:
        row = by_id.get(f"{contract.name}@{MARKETPLACE}")
        if row is None:
            continue
        root_value = installed_plugin_path(row)
        if isinstance(root_value, str):
            roots[contract.name] = Path(root_value)
        declared_and_served = tuple(
            name for name in _declared_mcp(contract) if name in matching_mcp
        )
        if declared_and_served:
            mcp_servers[contract.name] = declared_and_served
    evidence = collect_native_component_evidence(desired, roots, mcp_servers, which)
    return _add_lifecycle_evidence(desired, evidence)


def component_evidence_failures(
    desired: DesiredState, observation: McpInventoryObservation
) -> dict[str, CapabilityEvidenceFailure]:
    """Map live Codex MCP conflicts or observation failure to contract identities."""
    failures: dict[str, CapabilityEvidenceFailure] = {}
    for contract in desired.all_contracts:
        for name in _declared_mcp(contract):
            failure = _mcp_evidence_failure(name, observation)
            if failure is not None:
                identity = normalize_component_identity(contract.name, "mcp", name)
                failures[identity] = failure
    return failures


def _add_lifecycle_evidence(desired: DesiredState, evidence: set[str]) -> set[str]:
    workspace = next(
        (
            contract
            for contract in desired.all_contracts
            if contract.name == "manifest-workspace"
        ),
        None,
    )
    if workspace is None:
        return evidence
    metadata = desired.bundle_path(workspace.name) / "hooks/codex-lifecycle-events.json"
    try:
        document = json.loads(metadata.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return evidence
    events = document.get("events") if isinstance(document, Mapping) else None
    if not isinstance(events, list):
        return evidence
    expected = {
        "codex-session-start": "SessionStart",
        "codex-stop": "Stop",
        "codex-permission-request": "PermissionRequest",
    }
    observed = {
        row.get("id"): row.get("native_event")
        for row in events
        if isinstance(row, Mapping)
    }
    evidence.update(
        f"manifest-workspace:hook:{component_id}"
        for component_id, event in expected.items()
        if observed.get(component_id) == event
    )
    return evidence


def receipt_plugin_ids(
    receipt: HarnessReceipt, env: Mapping[str, str] | None = None
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    entries = tuple(
        entry for entry in receipt.owned_entries if entry.kind == "codex-catalog"
    )
    if len(entries) != 1:
        return (), ("receipt lacks one canonical Codex catalog snapshot",)
    try:
        snapshot, ownership_errors = codex_catalog_ownership(entries[0], env=env)
    except (TypeError, ValueError):
        return (), ("receipt Codex catalog snapshot is invalid",)
    if ownership_errors or snapshot is None:
        return (), ownership_errors
    authorized = tuple(f"{row['name']}@{MARKETPLACE}" for row in snapshot)
    ids: list[str] = []
    errors: list[str] = []
    for identifier in receipt.plugin_ids:
        plugin_id = (
            f"{identifier}@{MARKETPLACE}" if "@" not in identifier else identifier
        )
        _bundle, separator, marketplace = plugin_id.partition("@")
        if (
            separator != "@"
            or marketplace != MARKETPLACE
            or plugin_id not in authorized
        ):
            errors.append(f"receipt contains plugin outside its catalog: {identifier}")
        elif plugin_id not in ids:
            ids.append(plugin_id)
    if tuple(ids) != authorized:
        errors.append("receipt plugin IDs do not match its exact catalog snapshot")
    return tuple(ids), tuple(errors)


def authenticated_catalog(
    receipt: HarnessReceipt, env: Mapping[str, str] | None
) -> list[dict[str, str]] | None:
    entries = tuple(
        entry for entry in receipt.owned_entries if entry.kind == "codex-catalog"
    )
    if len(entries) != 1:
        return None
    value, errors = codex_catalog_ownership(entries[0], env=env)
    return value if not errors else None


def authenticated_marketplace(
    receipt: HarnessReceipt, env: Mapping[str, str] | None
) -> AdapterMarketplaceState | None:
    entries = tuple(
        entry for entry in receipt.owned_entries if entry.kind == "codex-catalog"
    )
    if len(entries) != 1:
        return None
    identity, errors = codex_marketplace_ownership(entries[0], env=env)
    if errors or identity is None:
        return None
    try:
        return AdapterMarketplaceState(**identity)
    except TypeError:
        return None


def observe_restoration(entry: OwnedEntry) -> str:
    """Observe a prepared owned-state restoration without mutating it."""
    if entry.kind == "codex-skill-source" and entry.target_path:
        return _observe_skill_restoration(entry)
    if entry.kind == "plugin-enabled-state" and entry.target_path:
        return _observe_enabled_restoration(entry)
    return "ambiguous"


def _observe_skill_restoration(entry: OwnedEntry) -> str:
    try:
        metadata = json.loads(entry.previous_checksum or "")
        raw_prior = metadata["prior_target"]
    except (json.JSONDecodeError, KeyError, TypeError):
        return "ambiguous"
    path = Path(entry.target_path or "")
    prior = Path(raw_prior)
    expected_prior = prior if prior.is_absolute() else path.parent / prior
    state = inspect_codex_skill_source(path.parents[1], expected_prior)
    if state.kind == "legacy-link" and state.target == raw_prior:
        return "completed"
    return "unapplied" if state.kind == "system-only" else "ambiguous"


def _observe_enabled_restoration(entry: OwnedEntry) -> str:
    try:
        metadata = json.loads(entry.previous_checksum or "")
        change = plugin_enabled_change_from_metadata(
            entry.identifier,
            metadata,
        )
        return observe_plugin_enabled_rollback(Path(entry.target_path or ""), change)
    except (CodexConfigError, json.JSONDecodeError, OSError, TypeError, ValueError):
        return "ambiguous"


def installed_manifest_ids(rows: Sequence[Mapping[str, Any]]) -> set[str]:
    return {
        identifier
        for row in rows
        if isinstance((identifier := row.get("pluginId")), str)
        and identifier.endswith(f"@{MARKETPLACE}")
        and row.get("installed") is not False
    }


def owns_marketplace(receipt: HarnessReceipt) -> bool:
    return any(
        entry.kind == "marketplace" and entry.identifier == MARKETPLACE
        for entry in receipt.owned_entries
    )


def catalog_owned_entries(
    desired: DesiredState,
    env: Mapping[str, str] | None = None,
    marketplace: AdapterMarketplaceState | None = None,
) -> tuple[OwnedEntry, ...]:
    snapshot = catalog_snapshot(desired)
    identity = marketplace or desired_marketplace_identity(desired)
    return (
        OwnedEntry("marketplace", MARKETPLACE, "manifest"),
        owned_codex_catalog_entry(snapshot, marketplace=asdict(identity), env=env),
    )


def receipt_identity(receipt: HarnessReceipt) -> str:
    payload = json.dumps(
        {
            "adapter_version": receipt.adapter_version,
            "harness": receipt.harness,
            "native_version": receipt.native_version,
            "owned_entries": [
                {
                    "identifier": item.identifier,
                    "kind": item.kind,
                    "ownership_marker": item.ownership_marker,
                    "previous_checksum": item.previous_checksum,
                    "target_path": item.target_path,
                }
                for item in receipt.owned_entries
            ],
            "plugin_ids": receipt.plugin_ids,
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return hashlib.sha256(payload).hexdigest()


def _declared_mcp(contract: BundleContract) -> tuple[str, ...]:
    """Every MCP identity this bundle declares, across all tiers."""
    return tuple(
        dict.fromkeys(
            name for tier in CapabilityTier for name in contract.capabilities.mcp[tier]
        )
    )


def _matching_mcp_names(
    served_mcp: Mapping[str, McpDefinition],
) -> frozenset[str]:
    catalog = load_mcp_catalog()
    matches: set[str] = set()
    for name, observed in served_mcp.items():
        expected = catalog.get(name)
        if expected is None:
            continue
        try:
            merge_mcp_definitions(expected, observed)
        except CapabilityConflict:
            continue
        matches.add(name)
    return frozenset(matches)


def _mcp_evidence_failure(
    name: str, observation: McpInventoryObservation
) -> CapabilityEvidenceFailure | None:
    if observation.error is not None:
        return CapabilityEvidenceFailure("observation-unavailable", observation.error)
    conflict = observation.conflicts.get(name)
    if conflict is not None:
        return CapabilityEvidenceFailure("conflicting", conflict)
    if not isinstance(observation.inventory, Mapping):
        return None
    observed = observation.inventory.get(name)
    if observed is None:
        return None
    expected = load_mcp_catalog().get(name)
    if expected is None:
        return CapabilityEvidenceFailure(
            "conflicting", f"Codex reported undeclared MCP server {name!r}"
        )
    try:
        merge_mcp_definitions(expected, observed)
    except CapabilityConflict as error:
        return CapabilityEvidenceFailure("conflicting", str(error))
    return None

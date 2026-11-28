"""Component and capability evidence collection for the Devin CLI adapter."""

from __future__ import annotations

import json
import os
from collections.abc import Collection, Mapping
from pathlib import Path
from typing import TYPE_CHECKING, Any

from manifest_agent.adapters.base import (
    NativeMcpInventory,
    normalize_component_identity,
)
from manifest_agent.adapters.component_presence import component_is_installed
from manifest_agent.capabilities import (
    CapabilityConflict,
    McpDefinition,
    load_mcp_catalog,
    merge_mcp_definitions,
)
from manifest_agent.models import BundleContract, CapabilityTier, DesiredState

if TYPE_CHECKING:
    from manifest_agent.adapters.devin import DevinAdapter

_COMPONENT_GROUPS = (
    ("agent", "agents"),
    ("hook", "hooks"),
    ("runtime", "runtime"),
    ("guidance", "guidance"),
)


def devin_config_dir(env: Mapping[str, str] | None) -> Path:
    """Resolve Devin's user config directory against XDG_CONFIG_HOME or HOME."""
    source = os.environ if env is None else env
    xdg_config = source.get("XDG_CONFIG_HOME")
    if xdg_config:
        return Path(xdg_config) / "devin"
    home = Path(source["HOME"]) if "HOME" in source else Path.home()
    return home / ".config" / "devin"


def read_devin_native_mcp_servers(
    env: Mapping[str, str] | None,
) -> dict[str, McpDefinition]:
    """Return Devin's live user-scope MCP registrations, failing closed on errors.

    ``devin mcp add --scope user`` writes into ``mcp_config.json`` under
    ``~/.config/devin`` (or ``$XDG_CONFIG_HOME/devin``), while ``config.json``
    may carry legacy or user-authored ``mcpServers`` entries. Missing,
    malformed, or disabled entries yield no evidence rather than false-green
    capabilities.
    """
    config_dir = devin_config_dir(env)
    definitions: dict[str, McpDefinition] = {}
    for filename in ("config.json", "mcp_config.json"):
        _merge_mcp_config_file(config_dir / filename, definitions)
    return definitions


def _merge_mcp_config_file(path: Path, definitions: dict[str, McpDefinition]) -> None:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return
    if not isinstance(document, Mapping):
        return
    servers = document.get("mcpServers")
    if not isinstance(servers, Mapping):
        return
    for name, raw in servers.items():
        if not isinstance(name, str) or not name:
            continue
        parsed = _parse_mcp_server_entry(name, raw)
        if parsed is None:
            definitions.pop(name, None)
        else:
            definitions[name] = parsed


def _parse_mcp_server_entry(name: str, raw: object) -> McpDefinition | None:
    if not isinstance(raw, Mapping):
        return None
    if raw.get("disabled") is True or raw.get("enabled") is False:
        return None
    transport = raw.get("transport") if "transport" in raw else raw.get("type")
    url = raw.get("url")
    if (
        transport in {"http", None}
        and isinstance(url, str)
        and url.startswith(("http://", "https://"))
        and "command" not in raw
    ):
        return McpDefinition(name=name, transport="http", url=url)
    command = raw.get("command")
    if transport in {"stdio", None} and isinstance(command, str) and command:
        return McpDefinition(
            name=name, transport="native-existing", discovery_prefixes=(name,)
        )
    return None


def _component_evidence(
    desired: DesiredState,
    installed_ids: Collection[str],
    info_rows: Mapping[str, Mapping[str, Any]],
    adapter: DevinAdapter,
) -> set[str]:
    """Collect fail-closed component and capability evidence for Devin."""
    roots = _verified_plugin_roots(desired, installed_ids, info_rows)
    served_mcp = _served_mcp_definitions(roots, info_rows, adapter)
    matching_mcp = _matching_mcp_names(served_mcp)
    evidence: set[str] = set()
    rule_path = adapter._adhd_rule_path()
    for contract in desired.all_contracts:
        _add_skill_and_executable_evidence(evidence, contract, info_rows, adapter)
        root = roots.get(contract.name)
        if root is None:
            continue
        _add_bundle_component_evidence(evidence, contract, root, rule_path)
        for server in _declared_mcp(contract):
            if server in matching_mcp:
                evidence.add(normalize_component_identity(contract.name, "mcp", server))
    return evidence


def _add_skill_and_executable_evidence(
    evidence: set[str],
    contract: BundleContract,
    info_rows: Mapping[str, Mapping[str, Any]],
    adapter: DevinAdapter,
) -> None:
    row = info_rows.get(contract.name)
    skills = row.get("skills") if row is not None else ()
    if isinstance(skills, set):
        evidence.update(
            normalize_component_identity(contract.name, "skill", skill)
            for skill in skills
        )
    for tier in CapabilityTier:
        evidence.update(
            normalize_component_identity(contract.name, "executable", executable)
            for executable in contract.capabilities.executables[tier]
            if adapter._which(executable) is not None
        )


def _add_bundle_component_evidence(
    evidence: set[str],
    contract: BundleContract,
    root: Path,
    rule_path: Path | None,
) -> None:
    declared = _declared_devin_components(root, contract.name)
    if declared is None:
        return
    rule_verified = _generated_rule_verified(root, rule_path)
    for kind, attribute in _COMPONENT_GROUPS:
        declared_pairs = declared.get(attribute, set())
        for component in getattr(contract.components, attribute):
            if (component.id, component.path) not in declared_pairs:
                continue
            if not component_is_installed(root / component.path):
                continue
            status = (component.compatibility or {}).get(
                "devin"
            ) or contract.compatibility["devin"]
            if status.mode == "generated" and not rule_verified:
                continue
            evidence.add(
                normalize_component_identity(contract.name, kind, component.id)
            )


def _declared_devin_components(
    root: Path, bundle: str
) -> dict[str, set[tuple[str, str]]] | None:
    manifest_path = root / ".devin-plugin" / "plugin.json"
    try:
        document = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None
    if not isinstance(document, Mapping) or document.get("name") != bundle:
        return None
    harnesses = document.get("harnesses")
    surface = harnesses.get("devin") if isinstance(harnesses, Mapping) else None
    if not isinstance(surface, Mapping):
        return None
    components = surface.get("components", {})
    if not isinstance(components, Mapping):
        return None
    declared: dict[str, set[tuple[str, str]]] = {}
    for attribute, entries in components.items():
        if not isinstance(attribute, str) or not isinstance(entries, list):
            continue
        declared[attribute] = {
            (entry["id"], entry["path"])
            for entry in entries
            if isinstance(entry, Mapping)
            and isinstance(entry.get("id"), str)
            and isinstance(entry.get("path"), str)
        }
    return declared


def _generated_rule_verified(root: Path, rule_path: Path | None) -> bool:
    if rule_path is None:
        return False
    generated = root / "devin" / "global-rule.md"
    try:
        return generated.read_bytes() == rule_path.read_bytes()
    except OSError:
        return False


def _verified_plugin_roots(
    desired: DesiredState,
    installed_ids: Collection[str],
    info_rows: Mapping[str, Mapping[str, Any]],
) -> dict[str, Path]:
    roots: dict[str, Path] = {}
    for contract in desired.all_contracts:
        if contract.name not in installed_ids:
            continue
        row = info_rows.get(contract.name)
        if row is None or row.get("name") != contract.name:
            continue
        source = row.get("source")
        expected = str(desired.bundle_path(contract.name))
        if not isinstance(source, str) or _resolved_path(source) != _resolved_path(
            expected
        ):
            continue
        root = Path(source)
        if root.is_dir():
            roots[contract.name] = root
    return roots


def _served_mcp_definitions(
    roots: Mapping[str, Path],
    info_rows: Mapping[str, Mapping[str, Any]],
    adapter: DevinAdapter,
) -> dict[str, McpDefinition]:
    served: dict[str, McpDefinition] = {}
    for bundle in roots:
        info_mcp = info_rows.get(bundle, {}).get("mcp_servers")
        if isinstance(info_mcp, Mapping):
            for name, definition in info_mcp.items():
                if isinstance(name, str) and isinstance(definition, McpDefinition):
                    served[name] = definition
    served.update(read_devin_native_mcp_servers(adapter._env))
    served.update(_native_mcp_definitions(adapter._native_mcp_inventory))
    return served


def _native_mcp_definitions(inventory: NativeMcpInventory) -> dict[str, McpDefinition]:
    if isinstance(inventory, Mapping):
        return dict(inventory)
    return {
        name: McpDefinition(name, "native-existing", discovery_prefixes=(name,))
        for name in inventory
    }


def _matching_mcp_names(served_mcp: Mapping[str, McpDefinition]) -> frozenset[str]:
    catalog = load_mcp_catalog()
    matches: set[str] = set()
    for name, expected in catalog.items():
        if expected.transport == "native-existing":
            if any(
                observed_name.startswith(expected.discovery_prefixes)
                for observed_name in served_mcp
            ):
                matches.add(name)
            continue
        observed = served_mcp.get(name)
        if observed is None:
            continue
        try:
            merge_mcp_definitions(expected, observed)
        except CapabilityConflict:
            continue
        matches.add(name)
    return frozenset(matches)


def _declared_mcp(contract: BundleContract) -> tuple[str, ...]:
    return tuple(
        dict.fromkeys(
            name for tier in CapabilityTier for name in contract.capabilities.mcp[tier]
        )
    )


def _resolved_path(value: str) -> str:
    return str(Path(value).expanduser().resolve(strict=False))

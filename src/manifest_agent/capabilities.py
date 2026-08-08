"""Deterministic, secret-free capability planning across domain contracts."""

from __future__ import annotations

import re
from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass
from importlib.resources import files
from types import MappingProxyType
from urllib.parse import urlsplit

import yaml

from manifest_agent.contracts import DOMAIN_BUNDLES
from manifest_agent.models import BundleContract, CapabilityTier
from manifest_agent.process import contains_credential_material

_SYSTEM_EXECUTABLES = frozenset({"bash", "git", "node", "python3"})
_CREDENTIAL_KEY = re.compile(
    r"(?:^|[._-])(?:authorization|credential|password|secret|token|api[_-]?key)"
    r"(?:$|[._-])",
    re.I,
)


class CapabilityConflict(RuntimeError):
    """Capability declarations or transport identities disagree."""


@dataclass(frozen=True)
class McpDefinition:
    """Secret-free coordinator transport metadata for one MCP identity."""

    name: str
    transport: str
    url: str | None = None
    command: tuple[str, ...] = ()
    discovery_prefixes: tuple[str, ...] = ()


@dataclass(frozen=True)
class ExecutableDefinition:
    """Reviewed user-scope acquisition recipe for one executable."""

    manager: str
    distribution: str
    version: str
    executable: str

    def as_dict(self) -> dict[str, str]:
        """Return the stable catalog representation used in reports."""
        return {
            "manager": self.manager,
            "distribution": self.distribution,
            "version": self.version,
            "executable": self.executable,
        }


@dataclass(frozen=True)
class CapabilityPlan:
    """The sorted union of all contract tiers plus explicit opt-ins."""

    required_mcp: tuple[str, ...]
    default_mcp: tuple[str, ...]
    optional_mcp: tuple[str, ...]
    required_executables: tuple[str, ...]
    default_executables: tuple[str, ...]
    optional_executables: tuple[str, ...]
    selected_optional: frozenset[str]
    mcp_definitions: Mapping[str, McpDefinition]
    executable_definitions: Mapping[str, ExecutableDefinition]

    @property
    def selected_mcp(self) -> tuple[str, ...]:
        """Return required, default, and explicitly selected optional MCPs."""
        return _selected(
            self.required_mcp,
            self.default_mcp,
            self.optional_mcp,
            self.selected_optional,
            "mcp",
        )

    @property
    def selected_executables(self) -> tuple[str, ...]:
        """Return required, default, and explicitly selected executables."""
        return _selected(
            self.required_executables,
            self.default_executables,
            self.optional_executables,
            self.selected_optional,
            "executable",
        )

    def tier(self, kind: str, name: str) -> CapabilityTier:
        """Return the one declared tier for an identity."""
        for tier, values in (
            (CapabilityTier.REQUIRED, getattr(self, f"required_{kind}")),
            (CapabilityTier.DEFAULT, getattr(self, f"default_{kind}")),
            (CapabilityTier.OPTIONAL, getattr(self, f"optional_{kind}")),
        ):
            if name in values:
                return tier
        raise KeyError(f"unknown {kind} capability {name!r}")


def load_mcp_catalog() -> Mapping[str, McpDefinition]:
    """Load and validate the packaged MCP transport catalog."""
    document = _catalog_document("mcp_catalog.yml")
    catalog: dict[str, McpDefinition] = {}
    for name, raw in sorted(document.items()):
        row = _mapping(raw, f"MCP definition {name!r}")
        _require_keys(
            row,
            {"transport", "url", "discovery_prefixes"},
            {"transport"},
            name,
        )
        url = row.get("url")
        definition = McpDefinition(
            name=name,
            transport=_string(row["transport"], f"{name}.transport"),
            url=_string(url, f"{name}.url") if url is not None else None,
            discovery_prefixes=_string_tuple(
                row.get("discovery_prefixes", ()), f"{name}.discovery_prefixes"
            ),
        )
        _validate_mcp_definition(definition)
        catalog[name] = definition
    return MappingProxyType(catalog)


def load_executable_catalog() -> Mapping[str, ExecutableDefinition]:
    """Load reviewed executable acquisition recipes."""
    document = _catalog_document("executable_catalog.yml")
    catalog: dict[str, ExecutableDefinition] = {}
    required = {"manager", "distribution", "version", "executable"}
    for name, raw in sorted(document.items()):
        row = _mapping(raw, f"executable definition {name!r}")
        _require_keys(row, required, required, name)
        definition = ExecutableDefinition(
            manager=_string(row["manager"], f"{name}.manager"),
            distribution=_string(row["distribution"], f"{name}.distribution"),
            version=_string(row["version"], f"{name}.version"),
            executable=_string(row["executable"], f"{name}.executable"),
        )
        if name != definition.executable or definition.manager != "uv-tool":
            raise CapabilityConflict(f"unsupported acquisition recipe for {name}")
        catalog[name] = definition
    if set(catalog) & _SYSTEM_EXECUTABLES:
        raise CapabilityConflict("system executables must remain check-only")
    return MappingProxyType(catalog)


def merge_mcp_definitions(*definitions: McpDefinition) -> McpDefinition:
    """Require repeated definitions of an MCP identity to be exactly equal."""
    if not definitions:
        raise ValueError("at least one MCP definition is required")
    first = definitions[0]
    _validate_mcp_definition(first)
    for definition in definitions[1:]:
        _validate_mcp_definition(definition)
        if definition.name != first.name or definition != first:
            names = sorted({item.name for item in definitions})
            identity = first.name if len(names) == 1 else "/".join(names)
            raise CapabilityConflict(f"conflicting MCP definition for {identity}")
    return first


def resolve_capabilities(
    contracts: Sequence[BundleContract], selected_optional: Collection[str]
) -> CapabilityPlan:
    """Build a deterministic union while rejecting tier/selection ambiguity."""
    names = tuple(contract.name for contract in contracts)
    if len(contracts) != len(DOMAIN_BUNDLES) or set(names) != set(DOMAIN_BUNDLES):
        raise CapabilityConflict(
            f"capability planning requires the exact {len(DOMAIN_BUNDLES)} contracts"
        )
    tiers = {
        kind: {tier: set() for tier in CapabilityTier}
        for kind in ("mcp", "executables")
    }
    optional_aliases: dict[str, set[tuple[str, str]]] = {}
    for contract in sorted(contracts, key=lambda item: item.name):
        for kind in ("mcp", "executables"):
            for tier in CapabilityTier:
                for capability in getattr(contract.capabilities, kind)[tier]:
                    _claim_tier(tiers[kind], tier, capability)
                    if tier is CapabilityTier.OPTIONAL:
                        singular = "executable" if kind == "executables" else kind
                        identity = (singular, capability)
                        for alias in (
                            capability,
                            f"{singular}:{capability}",
                            f"{contract.name}:{singular}:{capability}",
                        ):
                            optional_aliases.setdefault(alias, set()).add(identity)
    selected: set[str] = set()
    for value in selected_optional:
        matches = optional_aliases.get(value, set())
        if not matches:
            raise CapabilityConflict(f"unknown optional capability {value!r}")
        if len(matches) != 1:
            raise CapabilityConflict(f"ambiguous optional capability {value!r}")
        kind, name = next(iter(matches))
        selected.add(f"{kind}:{name}")

    mcp_catalog = load_mcp_catalog()
    declared_mcp = set().union(*tiers["mcp"].values())
    missing = sorted(declared_mcp - set(mcp_catalog))
    if missing:
        raise CapabilityConflict("missing MCP definitions: " + ", ".join(missing))
    return CapabilityPlan(
        required_mcp=_tier_values(tiers, "mcp", CapabilityTier.REQUIRED),
        default_mcp=_tier_values(tiers, "mcp", CapabilityTier.DEFAULT),
        optional_mcp=_tier_values(tiers, "mcp", CapabilityTier.OPTIONAL),
        required_executables=_tier_values(
            tiers, "executables", CapabilityTier.REQUIRED
        ),
        default_executables=_tier_values(tiers, "executables", CapabilityTier.DEFAULT),
        optional_executables=_tier_values(
            tiers, "executables", CapabilityTier.OPTIONAL
        ),
        selected_optional=frozenset(selected),
        mcp_definitions=MappingProxyType(
            {name: mcp_catalog[name] for name in sorted(declared_mcp)}
        ),
        executable_definitions=load_executable_catalog(),
    )


def _selected(required, default, optional, selected, kind):
    opted_in = (
        name for name in optional if name in selected or f"{kind}:{name}" in selected
    )
    return tuple(dict.fromkeys((*required, *default, *opted_in)))


def _tier_values(tiers, kind, tier):
    return tuple(sorted(tiers[kind][tier]))


def _claim_tier(tiers, tier, name):
    if any(name in tiers[other] for other in CapabilityTier if other is not tier):
        raise CapabilityConflict(f"capability {name!r} has conflicting tiers")
    tiers[tier].add(name)


def _catalog_document(name):
    raw = files("manifest_agent.data").joinpath(name).read_text(encoding="utf-8")
    document = yaml.safe_load(raw)
    _assert_secret_free(document)
    return _mapping(document, name)


def _assert_secret_free(value, key=None):
    if key is not None and _CREDENTIAL_KEY.search(key):
        raise CapabilityConflict("capability catalog contains credential material")
    if isinstance(value, dict):
        for child_key, child in value.items():
            if not isinstance(child_key, str):
                raise CapabilityConflict("capability catalog keys must be strings")
            _assert_secret_free(child, child_key)
    elif isinstance(value, list):
        for child in value:
            _assert_secret_free(child)
    elif isinstance(value, str) and contains_credential_material(value):
        raise CapabilityConflict("capability catalog contains credential material")


def _validate_mcp_definition(definition):
    if definition.transport == "http":
        parsed = urlsplit(definition.url or "")
        valid = parsed.scheme == "https" and parsed.netloc
        if (
            not valid
            or parsed.username is not None
            or parsed.password is not None
            or parsed.query
            or parsed.fragment
        ):
            raise CapabilityConflict(
                f"invalid HTTP MCP definition for {definition.name}"
            )
        if definition.command or definition.discovery_prefixes:
            raise CapabilityConflict(
                f"conflicting HTTP MCP fields for {definition.name}"
            )
    elif definition.transport == "native-existing":
        if definition.url or definition.command or not definition.discovery_prefixes:
            raise CapabilityConflict(
                f"invalid native MCP definition for {definition.name}"
            )
    elif definition.transport == "stdio":
        if definition.url or not definition.command or definition.discovery_prefixes:
            raise CapabilityConflict(
                f"invalid stdio MCP definition for {definition.name}"
            )
    else:
        raise CapabilityConflict(f"unknown MCP transport for {definition.name}")


def _mapping(value, location):
    if not isinstance(value, dict) or any(not isinstance(key, str) for key in value):
        raise CapabilityConflict(f"{location} must be a string-keyed mapping")
    return value


def _require_keys(row, allowed, required, location):
    if set(row) - allowed or not required <= set(row):
        raise CapabilityConflict(f"invalid catalog fields for {location}")


def _string(value, location):
    if not isinstance(value, str) or not value:
        raise CapabilityConflict(f"{location} must be a non-empty string")
    return value


def _string_tuple(value, location):
    if not isinstance(value, (list, tuple)) or any(
        not isinstance(item, str) or not item for item in value
    ):
        raise CapabilityConflict(f"{location} must be a string list")
    return tuple(value)


# Runtime functions are re-exported here to keep the Task 9 public API singular.
from manifest_agent.capability_runtime import (  # noqa: E402
    apply_capability_plan,
    remove_owned_capabilities,
)

__all__ = [
    "CapabilityConflict",
    "CapabilityPlan",
    "ExecutableDefinition",
    "McpDefinition",
    "apply_capability_plan",
    "load_executable_catalog",
    "load_mcp_catalog",
    "merge_mcp_definitions",
    "remove_owned_capabilities",
    "resolve_capabilities",
]

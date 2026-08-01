"""Validation and loading for portable Manifest bundle contracts."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from functools import lru_cache
from importlib import resources
from pathlib import Path
from types import MappingProxyType
from typing import Any

import yaml
from jsonschema import Draft202012Validator

from manifest_agent.models import BundleContract, CapabilityTier

DOMAIN_BUNDLES = (
    "manifest-code-quality",
    "manifest-docs",
    "manifest-forge",
    "manifest-graphify",
    "manifest-ops",
    "manifest-security",
    "manifest-spec-planning",
    "manifest-workspace",
    "stitch-design",
)

_COMPONENT_KINDS = ("agents", "hooks", "runtime", "guidance")
_TIER_NAMES = frozenset(tier.value for tier in CapabilityTier)


class ContractError(ValueError):
    """All contract violations found during one validation operation."""

    def __init__(self, errors: str | list[str] | tuple[str, ...]) -> None:
        self.errors = (errors,) if isinstance(errors, str) else tuple(errors)
        super().__init__("\n".join(self.errors))


@dataclass(frozen=True)
class CompatibilityStatus:
    """The native representation status for one harness."""

    mode: str
    reason: str | None = None


@dataclass(frozen=True)
class Component:
    """A portable bundle asset other than the skills tree."""

    id: str
    path: str
    compatibility: Mapping[str, CompatibilityStatus] | None = None


@dataclass(frozen=True)
class Components:
    """The complete portable component inventory for one bundle."""

    skills_root: str
    skills_include: tuple[str, ...]
    agents: tuple[Component, ...]
    hooks: tuple[Component, ...]
    runtime: tuple[Component, ...]
    guidance: tuple[Component, ...]


@dataclass(frozen=True)
class Capabilities:
    """MCP and executable declarations indexed by their install tier."""

    mcp: Mapping[CapabilityTier, tuple[str, ...]]
    executables: Mapping[CapabilityTier, tuple[str, ...]]


@dataclass(frozen=True)
class Provenance:
    """Source and generation information embedded in a portable contract."""

    repository: str
    license: str
    license_file: str
    generated_by: str


@lru_cache(maxsize=1)
def _schema_validator() -> Draft202012Validator:
    schema_path = resources.files("manifest_agent.data").joinpath(
        "manifest-capabilities.schema.json"
    )
    try:
        schema_text = schema_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        # Hatch editable installs expose ``src`` directly; the wheel contains
        # the resource above, while this keeps its single canonical source usable.
        schema_text = (
            Path(__file__).parents[2] / "schemas" / "manifest-capabilities.schema.json"
        ).read_text(encoding="utf-8")
    schema = json.loads(schema_text)
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def _format_schema_error(error: Any) -> str:
    location = ".".join(str(part) for part in error.absolute_path) or "<root>"
    path = tuple(error.absolute_path)
    if error.validator == "additionalProperties" and path in {
        ("capabilities", "mcp"),
        ("capabilities", "executables"),
    }:
        unexpected = re.findall(r"'([^']+)'", error.message)
        if unexpected:
            return f"{location}: unknown capability tier {unexpected[0]!r}"
    return f"{location}: {error.message}"


def _load_yaml(path: Path) -> Any:
    try:
        with path.open(encoding="utf-8") as contract_file:
            return yaml.safe_load(contract_file)
    except OSError as error:
        raise ContractError(f"{path}: unable to read contract: {error}") from error
    except yaml.YAMLError as error:
        raise ContractError(f"{path}: invalid YAML: {error}") from error


def _semantic_errors(document: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    capabilities = document["capabilities"]
    for capability_type in ("mcp", "executables"):
        tiers = capabilities[capability_type]
        unknown_tiers = sorted(set(tiers) - _TIER_NAMES)
        errors.extend(
            f"capabilities.{capability_type}: unknown capability tier {tier!r}"
            for tier in unknown_tiers
        )
        declared_tiers: dict[str, str] = {}
        for tier in CapabilityTier:
            for identifier in tiers[tier.value]:
                previous_tier = declared_tiers.setdefault(identifier, tier.value)
                if previous_tier != tier.value:
                    errors.append(
                        f"capabilities.{capability_type}: {identifier!r} is declared "
                        f"in both {previous_tier!r} and {tier.value!r} tiers"
                    )

    components = document["components"]
    for component_kind in _COMPONENT_KINDS:
        seen_ids: set[str] = set()
        for component in components[component_kind]:
            component_id = component["id"]
            if component_id in seen_ids:
                errors.append(
                    f"components.{component_kind}: duplicate component id {component_id!r}"
                )
            seen_ids.add(component_id)
    return errors


def _compatibility_map(
    raw_compatibility: dict[str, dict[str, str]],
) -> Mapping[str, CompatibilityStatus]:
    return MappingProxyType(
        {
            harness: CompatibilityStatus(
                mode=status["mode"], reason=status.get("reason")
            )
            for harness, status in raw_compatibility.items()
        }
    )


def _component(raw_component: dict[str, Any]) -> Component:
    raw_compatibility = raw_component.get("compatibility")
    compatibility = (
        _compatibility_map(raw_compatibility) if raw_compatibility is not None else None
    )
    return Component(
        id=raw_component["id"], path=raw_component["path"], compatibility=compatibility
    )


def _tier_map(
    raw_tiers: dict[str, list[str]],
) -> Mapping[CapabilityTier, tuple[str, ...]]:
    return MappingProxyType(
        {tier: tuple(raw_tiers[tier.value]) for tier in CapabilityTier}
    )


def _to_contract(document: dict[str, Any]) -> BundleContract:
    bundle = document["bundle"]
    raw_components = document["components"]
    components = Components(
        skills_root=raw_components["skills"]["root"],
        skills_include=tuple(raw_components["skills"]["include"]),
        agents=tuple(_component(component) for component in raw_components["agents"]),
        hooks=tuple(_component(component) for component in raw_components["hooks"]),
        runtime=tuple(_component(component) for component in raw_components["runtime"]),
        guidance=tuple(
            _component(component) for component in raw_components["guidance"]
        ),
    )
    raw_capabilities = document["capabilities"]
    capabilities = Capabilities(
        mcp=_tier_map(raw_capabilities["mcp"]),
        executables=_tier_map(raw_capabilities["executables"]),
    )
    raw_provenance = document["provenance"]
    provenance = Provenance(
        repository=raw_provenance["repository"],
        license=raw_provenance["license"],
        license_file=raw_provenance["license_file"],
        generated_by=raw_provenance["generated_by"],
    )
    return BundleContract(
        name=bundle["name"],
        version=bundle["version"],
        description=bundle["description"],
        category=bundle["category"],
        components=components,
        capabilities=capabilities,
        compatibility=_compatibility_map(document["compatibility"]),
        provenance=provenance,
    )


def load_contract(path: Path) -> BundleContract:
    """Load one portable contract after exhaustive structural validation."""
    document = _load_yaml(path)
    schema_errors = sorted(
        _schema_validator().iter_errors(document),
        key=lambda error: (tuple(map(str, error.absolute_path)), error.message),
    )
    if schema_errors:
        raise ContractError([_format_schema_error(error) for error in schema_errors])

    semantic_errors = _semantic_errors(document)
    if semantic_errors:
        raise ContractError(semantic_errors)
    return _to_contract(document)


def _inside_bundle(bundle_path: Path, declared_path: str) -> bool:
    bundle_root = bundle_path.resolve()
    try:
        (bundle_path / declared_path).resolve().relative_to(bundle_root)
    except ValueError:
        return False
    return True


def _component_path_errors(bundle_path: Path, contract: BundleContract) -> list[str]:
    errors: list[str] = []
    if not _inside_bundle(bundle_path, contract.components.skills_root):
        errors.append(
            f"{bundle_path}: components.skills.root "
            f"{contract.components.skills_root!r} escapes its bundle"
        )
    for component_kind in _COMPONENT_KINDS:
        for component in getattr(contract.components, component_kind):
            if not _inside_bundle(bundle_path, component.path):
                errors.append(
                    f"{bundle_path}: components.{component_kind} path {component.path!r} "
                    "escapes its bundle"
                )
    return errors


def load_domain_contracts(root: Path) -> tuple[BundleContract, ...]:
    """Load the exact nine portable domain contracts rooted at ``plugins``."""
    contract_paths = sorted(root.glob("*/manifest-capabilities.yml"))
    errors: list[str] = []
    contracts_by_path: list[tuple[Path, BundleContract]] = []
    for contract_path in contract_paths:
        try:
            contracts_by_path.append((contract_path, load_contract(contract_path)))
        except ContractError as error:
            errors.extend(f"{contract_path}: {detail}" for detail in error.errors)

    if len(contract_paths) != len(DOMAIN_BUNDLES):
        errors.append(
            f"expected 9 domain contracts, found {len(contract_paths)} under {root}"
        )

    names_to_paths: dict[str, list[Path]] = {}
    for contract_path, contract in contracts_by_path:
        names_to_paths.setdefault(contract.name, []).append(contract_path)
        parent_name = contract_path.parent.name
        if parent_name != contract.name:
            errors.append(
                f"{contract_path}: bundle.name {contract.name!r} does not match "
                f"bundle directory {parent_name!r}"
            )
        errors.extend(_component_path_errors(contract_path.parent, contract))

    for name, paths in sorted(names_to_paths.items()):
        if len(paths) > 1:
            errors.append(
                f"duplicate domain contract {name!r}: {', '.join(map(str, paths))}"
            )
        if name == "adversarial-design-loop":
            errors.append(
                "adversarial-design-loop is an optional addon, not a domain bundle"
            )
        elif name == "manifest-core":
            errors.append("manifest-core is not a portable domain bundle")
        elif name not in DOMAIN_BUNDLES:
            errors.append(f"unexpected domain contract {name!r}")

    found_names = set(names_to_paths)
    for name in DOMAIN_BUNDLES:
        if name not in found_names:
            errors.append(f"missing required domain contract {name!r}")

    if errors:
        raise ContractError(errors)

    contracts_by_name = {contract.name: contract for _, contract in contracts_by_path}
    return tuple(contracts_by_name[name] for name in DOMAIN_BUNDLES)

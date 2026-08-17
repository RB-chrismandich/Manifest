"""Immutable public contracts shared by coordinator layers."""

import re
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any


class ResultState(StrEnum):
    """The explicit outcome of a harness or coordinator operation."""

    READY = "READY"
    DEGRADED = "DEGRADED"
    BLOCKED = "BLOCKED"
    DRIFTED = "DRIFTED"


class CapabilityTier(StrEnum):
    """Whether a declared capability is mandatory, automatic, or opt-in."""

    REQUIRED = "required"
    DEFAULT = "default"
    OPTIONAL = "optional"


class MarketplaceSourceKind(StrEnum):
    """Whether a native marketplace is local content or an immutable Git tree."""

    LOCAL = "local"
    GIT = "git"


@dataclass(frozen=True)
class MarketplaceSource:
    """Native marketplace location separated from release acquisition metadata."""

    kind: MarketplaceSourceKind
    source: str
    ref: str | None

    def __post_init__(self) -> None:
        if not self.source:
            raise ValueError("marketplace source must be non-empty")
        if self.kind is MarketplaceSourceKind.LOCAL and self.ref is not None:
            raise ValueError("local marketplace source must not carry a Git ref")
        if self.kind is MarketplaceSourceKind.GIT and (
            self.ref is None
            or re.fullmatch(r"[0-9a-fA-F]{40}(?:[0-9a-fA-F]{24})?", self.ref) is None
        ):
            raise ValueError("Git marketplace source requires an immutable commit ref")


@dataclass(frozen=True)
class CommandResult:
    """Captured result of one argv-only native command."""

    argv: tuple[str, ...]
    returncode: int
    stdout: str
    stderr: str


@dataclass(frozen=True)
class BundleContract:
    """Validated portable metadata for one plugin bundle.

    Task 2 converts the structured contract sections into their validated model
    forms; retaining their types here keeps this stable boundary independent of
    the YAML loader.
    """

    name: str
    version: str
    description: str
    category: str
    components: Any
    capabilities: Any
    compatibility: Any
    provenance: Any


@dataclass(frozen=True)
class CatalogPlugin:
    """One immutable plugin entry from the canonical local marketplace."""

    name: str
    version: str
    source: str


@dataclass(frozen=True)
class DesiredState:
    """The verified release and requested install scope."""

    release_version: str
    source_commit: str
    source: str
    marketplace_source: MarketplaceSource
    release_root: Path
    repository_url: str
    source_dirty: bool
    archive_sha256: str
    contracts: tuple[BundleContract, ...]
    selected_optional: frozenset[str]
    requested_harnesses: tuple[str, ...]
    catalog_plugins: tuple[CatalogPlugin, ...] = ()
    addon_contracts: tuple[BundleContract, ...] = ()

    def bundle_path(self, name: str) -> Path:
        """Return a bundle path inside the resolved immutable release."""
        return self.release_root / "plugins" / name

    @property
    def all_contracts(self) -> tuple[BundleContract, ...]:
        """Every authoritative portable contract, domains first then addons."""
        return (*self.contracts, *self.addon_contracts)


@dataclass(frozen=True)
class OwnedEntry:
    """A native harness entry that the coordinator is permitted to remove."""

    kind: str
    identifier: str
    ownership_marker: str
    target_path: str | None = None
    previous_checksum: str | None = None


@dataclass(frozen=True)
class HarnessReceipt:
    """Verified installation state for one native harness."""

    harness: str
    adapter_version: str
    native_version: str
    plugin_ids: tuple[str, ...]
    owned_entries: tuple[OwnedEntry, ...]
    capabilities: dict[str, str]
    verified: bool
    errors: tuple[str, ...] = ()


@dataclass(frozen=True)
class HarnessResult:
    """An adapter operation result with errors preserved for aggregation."""

    harness: str
    state: ResultState
    installed_plugin_ids: tuple[str, ...]
    capabilities: dict[str, str]
    errors: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    owned_entries: tuple[OwnedEntry, ...] = ()


@dataclass(frozen=True)
class AdapterPluginState:
    """Versioned native plugin state authorized by a reconciliation handle."""

    identifier: str
    version: str
    enabled: bool
    rollback_data: dict[str, Any] | None = None
    installed_path: str | None = None
    installed_sha256: str | None = None
    retirement_phase: str | None = None
    source_identity: str | None = None


@dataclass(frozen=True)
class AdapterMarketplaceState:
    """Exact native marketplace identity authorized by a mutation handle."""

    identifier: str
    source_kind: str
    source: str
    immutable_ref: str | None
    checkout_root: str


@dataclass(frozen=True)
class AdapterMutationHandle:
    """Durable adapter-owned authority for one release transition."""

    schema_version: int
    harness: str
    adapter_version: str
    target_identity: str
    prior_inventory: tuple[AdapterPluginState, ...]
    target_inventory: tuple[AdapterPluginState, ...]
    prior_marketplace: AdapterMarketplaceState | None = None
    target_marketplace: AdapterMarketplaceState | None = None
    prior_cas: str | None = None
    target_cas: str | None = None
    prior_capabilities: dict[str, str] | None = None
    target_capabilities: dict[str, str] | None = None
    prior_owned_files: tuple[dict[str, Any], ...] = ()
    target_owned_files: tuple[dict[str, Any], ...] = ()


@dataclass(frozen=True)
class InstallationReceipt:
    """Secret-free durable record of a completed coordinator operation."""

    schema_version: int
    coordinator_version: str
    release_version: str
    source_commit: str
    source_dirty: bool
    archive_sha256: str
    bundle_checksums: dict[str, str]
    selected_optional: tuple[str, ...]
    harnesses: dict[str, HarnessReceipt]
    migration_backup: str | None = None

    @property
    def migration_complete(self) -> bool:
        """Whether this receipt was committed by a completed legacy handoff."""
        return self.migration_backup is not None

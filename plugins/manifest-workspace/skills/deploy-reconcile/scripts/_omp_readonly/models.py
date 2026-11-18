"""Dependency-free native inspection wire contracts."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class NativeComponentInspection:
    """Component discovery observed through a harness-native interface."""

    kind: str
    identifier: str
    status: str
    provenance: str
    resolved_path: str | None = None


@dataclass(frozen=True)
class NativePluginInspection:
    """One package identity observed in a native plugin manager."""

    package_id: str
    package_name: str
    marketplace: str | None
    source_uri: str | None
    source_provenance: str | None
    version: str | None
    scope: str | None
    enabled: bool | None
    native_root: str | None
    install_path: str | None
    status: str


@dataclass(frozen=True)
class NativeInspection:
    """Typed, secret-free native inventory for downstream coordinator consumers."""

    harness: str
    profile: str | None
    native_root: str | None
    packages: tuple[NativePluginInspection, ...] = ()
    components: tuple[NativeComponentInspection, ...] = ()
    activation: str = "not-observed"
    inventory_errors: tuple[str, ...] = ()

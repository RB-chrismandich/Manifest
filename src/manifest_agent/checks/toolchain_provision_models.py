"""Shared immutable data for toolchain provisioning."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class OfflineValidationContext:
    """Shared inputs and accumulating failures for offline-store verification."""

    lock: Mapping
    store: Path
    platform: str
    repo_root: Path
    problems: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ProvisionPlan:
    """Validated provisioning selection in required execution order."""

    context: ProvisionContext
    tools: tuple[tuple[str, Mapping], ...]
    caches: tuple[str, ...]


@dataclass(frozen=True)
class ProvisionRequest:
    """Raw public provisioning inputs before lock selection is validated."""

    lock: Mapping
    store: Path
    platform: str
    only: frozenset[str] | None
    fetcher: Fetcher | None
    repo_root: Path | None
    env: Mapping[str, str] | None
    attest_missing: bool = False


Fetcher = Callable[[str], bytes]


@dataclass(frozen=True)
class ProvisionOutcome:
    """A single bundle's provision result and optional observed evidence."""

    bundle: str
    status: str
    reason: str = ""
    digest: str | None = None
    provider: Mapping[str, str] | None = None


@dataclass(frozen=True)
class ProvisionContext:
    """The immutable arguments shared by every provisioning operation."""

    store: Path
    lock: Mapping
    platform: str
    fetcher: Fetcher = None  # type: ignore[assignment]
    repo_root: Path = field(default_factory=Path.cwd)
    env: Mapping[str, str] = field(default_factory=dict)
    attest_missing: bool = False

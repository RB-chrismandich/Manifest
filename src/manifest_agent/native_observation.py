"""Read-only native harness observation using the packaged service contract."""

from __future__ import annotations

import re
from pathlib import Path
from typing import NoReturn

from manifest_agent.catalog import load_catalog
from manifest_agent.contracts import load_addon_contracts, load_domain_contracts
from manifest_agent.models import (
    DesiredState,
    InstallationReceipt,
    MarketplaceSource,
    MarketplaceSourceKind,
)
from manifest_agent.paths import xdg_paths
from manifest_agent.release import REPOSITORY_URL
from manifest_agent.service import ManifestService
from manifest_agent.service_state import (
    diagnostic,
    report,
    with_prior_harness_receipts,
    with_source_fingerprints,
)
from manifest_agent.state import read_receipt

_VERSION = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+(?:[-+][0-9A-Za-z.-]+)?$")
_SHA256 = re.compile(r"^[0-9a-fA-F]{64}$")


def _cached_release_root(receipt: InstallationReceipt) -> Path | None:
    """Return only an already extracted release matching the receipt identity."""
    version = receipt.release_version
    checksum = receipt.archive_sha256
    if not _VERSION.fullmatch(version) or not _SHA256.fullmatch(checksum):
        return None
    cached = xdg_paths().cache / "releases" / f"{version}-{checksum[:16]}"
    if cached.is_symlink() or not cached.is_dir():
        return None
    if (cached / "plugins").is_dir():
        return cached
    try:
        children = tuple(cached.iterdir())
    except OSError:
        return None
    if (
        len(children) == 1
        and children[0].is_dir()
        and (children[0] / "plugins").is_dir()
    ):
        return children[0]
    return None


def _desired_state(
    source_root: Path,
    receipt: InstallationReceipt,
    *,
    published: bool,
) -> DesiredState:
    contracts = load_domain_contracts(source_root / "plugins")
    addons = load_addon_contracts(source_root / "plugins")
    marketplace_path = source_root / ".claude-plugin" / "marketplace.json"
    catalog = load_catalog(marketplace_path) if marketplace_path.exists() else ()
    marketplace_source = (
        MarketplaceSource(
            MarketplaceSourceKind.GIT,
            f"{REPOSITORY_URL}.git",
            receipt.source_commit,
        )
        if published
        else MarketplaceSource(MarketplaceSourceKind.LOCAL, str(source_root), None)
    )
    desired = DesiredState(
        receipt.release_version,
        receipt.source_commit,
        str(source_root),
        marketplace_source,
        source_root,
        REPOSITORY_URL,
        receipt.source_dirty,
        receipt.archive_sha256,
        tuple(contracts),
        frozenset(receipt.selected_optional),
        tuple(receipt.harnesses),
        tuple(catalog),
        tuple(addons),
    )
    return with_source_fingerprints(with_prior_harness_receipts(desired, receipt))


def _release_resolution_forbidden(_selector: str | Path) -> NoReturn:
    raise RuntimeError("native observation must not resolve a release")


def _lock_forbidden(_path: Path | None) -> NoReturn:
    raise RuntimeError("native observation must not acquire an installation lock")


def observe_native_state(
    source_root: Path | None = None,
    receipt_path: Path | None = None,
) -> dict[str, object]:
    """Inspect the receipt-selected native state using local contracts only.

    A repository caller may provide its checkout root. An installed bundle
    instead reads the exact extracted release cache named by the receipt; it
    never resolves a published release or creates/fills a cache. The service
    read path is constrained to prepared desired state, with release resolution
    and installation locking replaced by fail-closed callbacks.
    """
    target = receipt_path or xdg_paths().state / "installation.json"
    try:
        receipt = read_receipt(target)
    except Exception as error:
        return report("reconcile", {}, errors=(diagnostic(error),)).to_dict()
    if receipt is None:
        return report(
            "reconcile", {}, errors=("no installation receipt is available",)
        ).to_dict()

    published = source_root is None
    root = (
        Path(source_root) if source_root is not None else _cached_release_root(receipt)
    )
    if root is None:
        return report(
            "reconcile",
            {},
            errors=(
                "read-only native observation has no matching local release contracts",
            ),
        ).to_dict()
    try:
        desired = _desired_state(root, receipt, published=published)
        service = ManifestService(
            receipt_path=target,
            release_resolver=_release_resolution_forbidden,
            lock_factory=_lock_forbidden,
        )
        return service.observe_prepared(receipt, desired).to_dict()
    except Exception as error:
        return report("reconcile", {}, errors=(diagnostic(error),)).to_dict()

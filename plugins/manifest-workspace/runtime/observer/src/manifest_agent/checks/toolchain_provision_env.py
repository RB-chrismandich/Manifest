"""Materialization and attestation for Python and Node environments."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from pathlib import Path

from . import toolchain_env, toolchain_env_digest
from . import toolchain_materialize as materialize
from .toolchain_provision_models import ProvisionContext, ProvisionOutcome
from .toolchain_provision_store import (
    _materialize_env,
    _read_source_bytes,
    _record_env_bundle,
    _SourceUnavailable,
    staged_directory,
)


def provision_environment(
    ctx: ProvisionContext,
    bundle: str,
    entry: Mapping,
    platform_entry: Mapping,
) -> ProvisionOutcome:
    """Materialize an environment and return its observed or pinned digest."""
    try:
        source_bytes = _read_source_bytes(ctx, platform_entry["url"])
    except _SourceUnavailable as error:
        return ProvisionOutcome(bundle, "blocked", f"toolchain: {bundle} {error}")
    source_sha256 = hashlib.sha256(source_bytes).hexdigest()
    if source_sha256 != platform_entry["sha256"]:
        return ProvisionOutcome(
            bundle, "blocked", f"toolchain: {bundle} digest mismatch"
        )
    if entry["kind"] == "python-env":
        try:
            project_sha256 = materialize.python_project_metadata_digest(
                ctx.repo_root, bundle
            )
        except (OSError, ValueError, materialize.MaterializationError) as error:
            return ProvisionOutcome(
                bundle,
                "blocked",
                f"toolchain: {bundle} project metadata attestation failed: {error}",
            )
        if project_sha256 != platform_entry.get("project_sha256"):
            return ProvisionOutcome(
                bundle,
                "blocked",
                f"toolchain: {bundle} project metadata digest mismatch",
            )
    relative = f"tools/{bundle}/{source_sha256[:16]}"
    names = [Path(script).name for script in platform_entry.get("console_scripts", ())]
    attested = _materialize_attested(
        ctx, bundle, entry, platform_entry, relative, names
    )
    if isinstance(attested, ProvisionOutcome):
        return attested
    scripts, digest = attested
    env_relative = Path(relative)
    store_relative_scripts = {
        name: str(env_relative / path) for name, path in scripts.items()
    }
    _record_env_bundle(ctx, bundle, source_sha256, store_relative_scripts)
    return ProvisionOutcome(bundle, "provisioned", digest=digest)


def _observed_provider(entry: Mapping, env_root: Path) -> dict[str, str] | None:
    if entry["kind"] != "python-env":
        return None
    return toolchain_env_digest.external_python_provider(
        toolchain_env_digest.python_provider_from_env(env_root)
    ).lock_record()


def _unattested_outcome(
    ctx: ProvisionContext,
    bundle: str,
    entry: Mapping,
    env_root: Path,
    digest: str,
) -> ProvisionOutcome:
    provider = (
        _observed_provider(entry, env_root) if entry["kind"] == "python-env" else None
    )
    return ProvisionOutcome(
        bundle,
        "UNPINNED" if ctx.attest_missing else "blocked",
        f"UNPINNED: toolchain: {bundle} unattested for {ctx.platform}",
        digest=digest,
        provider=provider,
    )


def _pinned_python_provider(
    ctx: ProvisionContext,
    bundle: str,
    entry: Mapping,
    env_root: Path,
    platform_entry: Mapping,
) -> dict[str, str] | ProvisionOutcome | None:
    if entry["kind"] != "python-env":
        return None
    provider = toolchain_env_digest.external_python_provider(
        toolchain_env_digest.python_provider_from_env(env_root)
    )
    pinned = platform_entry.get("python_provider")
    if provider.matches(pinned):
        return pinned
    if pinned is None and ctx.attest_missing:
        return None
    observed = json.dumps(provider.lock_record(), sort_keys=True, separators=(",", ":"))
    state = "unpinned" if pinned is None else "does not match the lock"
    return ProvisionOutcome(
        bundle, "blocked", f"toolchain: {bundle} Python provider {state}: {observed}"
    )


def _materialize_attested(
    ctx: ProvisionContext,
    bundle: str,
    entry: Mapping,
    platform_entry: Mapping,
    relative: str,
    names: list[str],
) -> tuple[dict[str, str], str] | ProvisionOutcome:
    try:
        with staged_directory(ctx.store, relative) as transaction:
            env_root = transaction.path
            scripts = _materialize_env(ctx, bundle, entry, env_root, names)
            if entry["kind"] == "python-env":
                materialize.relocate_python_launchers(env_root, ctx.store / relative)
            missing = sorted(set(names) - set(scripts))
            if missing:
                return ProvisionOutcome(
                    bundle,
                    "blocked",
                    f"toolchain: {bundle} missing console script(s) {missing}",
                )
            pinned_provider = _pinned_python_provider(
                ctx, bundle, entry, env_root, platform_entry
            )
            if isinstance(pinned_provider, ProvisionOutcome):
                return pinned_provider
            digest = toolchain_env.distribution_set_digest(
                env_root,
                entry["kind"],
                store=ctx.store,
                checkout_root=ctx.repo_root.resolve(),
                canonical_env_root=ctx.store / relative,
                python_provider=pinned_provider,
            )
            expected_digest = platform_entry.get("exe_sha256")
            missing_provider = (
                entry["kind"] == "python-env"
                and platform_entry.get("python_provider") is None
            )
            if expected_digest is not None and digest != expected_digest:
                return ProvisionOutcome(
                    bundle,
                    "blocked",
                    f"toolchain: {bundle} digest mismatch",
                    digest=digest,
                )
            if expected_digest is None or (ctx.attest_missing and missing_provider):
                return _unattested_outcome(ctx, bundle, entry, env_root, digest)
            transaction.commit()
    except (
        OSError,
        ValueError,
        toolchain_env.UntrustedPthError,
        materialize.MaterializationError,
    ) as error:
        return ProvisionOutcome(
            bundle, "blocked", f"toolchain: {bundle} attestation failed: {error}"
        )
    return scripts, digest

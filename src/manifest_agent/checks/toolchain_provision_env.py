"""Materialization and attestation for Python and Node environments."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from pathlib import Path

from . import toolchain_env
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
            digest = toolchain_env.distribution_set_digest(
                env_root,
                entry["kind"],
                store=ctx.store,
                checkout_root=ctx.repo_root.resolve(),
                canonical_env_root=ctx.store / relative,
            )
            expected_digest = platform_entry.get("exe_sha256")
            if expected_digest is None:
                return ProvisionOutcome(
                    bundle,
                    "blocked",
                    f"toolchain: {bundle} unattested for {ctx.platform}",
                    digest=digest,
                )
            if digest != expected_digest:
                return ProvisionOutcome(
                    bundle,
                    "blocked",
                    f"toolchain: {bundle} digest mismatch",
                    digest=digest,
                )
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

"""`manifest provision`: populate the content-addressed toolchain store.

Network is permitted here, and only here -- `manifest check` never calls into
this module. Every download goes through an injectable `Fetcher` callable so
tests drive real code paths with local fixture bytes and never touch the
network (mirrors the seam `tools/project_checks/ci_context.py` uses for
`fetch_jobs`). Store writes are serialized with the same `fcntl.flock`
primitive `preparation.py` already uses, so two concurrent `manifest
provision` invocations cannot interleave a torn `manifest.json`.
"""

from __future__ import annotations

import hashlib
import urllib.parse
import urllib.request
from collections.abc import Callable, Mapping
from pathlib import Path

from . import toolchain, toolchain_npm_cache
from . import toolchain_materialize as materialize
from .toolchain_provision_env import provision_environment
from .toolchain_provision_models import (
    OfflineValidationContext,
    ProvisionContext,
    ProvisionOutcome,
    ProvisionPlan,
    ProvisionRequest,
)
from .toolchain_provision_store import (
    BinaryArtifacts,
    _record_bundle,
    archive_member_bytes,
    staged_directory,
    write_file,
)

Fetcher = Callable[[str], bytes]

_IMPLEMENTED_KINDS = frozenset({"binary", "python-env", "node-env"})
_ENV_KINDS = frozenset({"python-env", "node-env"})


_TRUSTED_DOWNLOAD_HOSTS = frozenset({"example.invalid", "github.com", "nodejs.org"})
_TRUSTED_REDIRECT_HOSTS = frozenset(
    {
        "github-releases.githubusercontent.com",
        "objects.githubusercontent.com",
        "release-assets.githubusercontent.com",
    }
)


def _safe_relative(value: str) -> bool:
    path = Path(value)
    return bool(value) and not path.is_absolute() and ".." not in path.parts


def _safe_component(value: object) -> bool:
    return (
        isinstance(value, str)
        and bool(value)
        and Path(value).name == value
        and value not in {".", ".."}
    )


def _safe_artifact_url(url: object) -> bool:
    if not isinstance(url, str):
        return False
    if url.startswith("file://"):
        return True
    parsed = urllib.parse.urlsplit(url)
    return (
        parsed.scheme == "https"
        and parsed.hostname in _TRUSTED_DOWNLOAD_HOSTS
        and parsed.port is None
        and not parsed.username
        and not parsed.password
        and not parsed.fragment
    )


def validate_lock(lock: Mapping) -> None:
    """Reject malformed lock records before touching the store."""
    from .toolchain_lock_validation import validate_lock as validate

    validate(lock)


def _valid_digest(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(char in "0123456789abcdef" for char in value)
    )


class _RejectRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        target = urllib.parse.urlsplit(newurl)
        if (
            target.scheme != "https"
            or target.hostname not in _TRUSTED_REDIRECT_HOSTS
            or target.port is not None
            or target.username
            or target.password
        ):
            raise ValueError(f"toolchain download redirect rejected: {newurl}")
        return super().redirect_request(request, fp, code, msg, headers, newurl)


def default_fetcher(url: str) -> bytes:  # pragma: no cover - exercised only live
    """Fetch a direct reviewed HTTPS artifact or a regular local test file."""
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme == "file":
        path = Path(urllib.request.url2pathname(parsed.path))
        if parsed.netloc or path.is_symlink() or not path.is_file():
            raise ValueError(f"unsafe toolchain download URL: {url}")
        return path.read_bytes()
    if not _safe_artifact_url(url) or parsed.scheme != "https":
        raise ValueError(f"unsafe toolchain download URL: {url}")
    opener = urllib.request.build_opener(_RejectRedirects)
    with opener.open(url, timeout=60) as response:
        return response.read()


def _provision_env_entry(
    ctx: ProvisionContext, bundle: str, entry: Mapping
) -> ProvisionOutcome:
    platform_entry = _platform_entry(
        entry, bundle, ctx.platform, require_exe_sha256=False
    )
    if isinstance(platform_entry, ProvisionOutcome):
        return platform_entry
    return provision_environment(ctx, bundle, entry, platform_entry)


def _platform_entry(
    entry: Mapping,
    bundle: str,
    platform: str,
    *,
    require_exe_sha256: bool = True,
) -> dict | ProvisionOutcome:
    if not isinstance(entry.get("version"), str) or not entry["version"]:
        return ProvisionOutcome(
            bundle, "blocked", f"UNPINNED: toolchain: {bundle} has no expected version"
        )
    platform_entry = entry.get("platforms", {}).get(platform)
    if (
        platform_entry is None
        or platform_entry.get("sha256") is None
        or (require_exe_sha256 and platform_entry.get("exe_sha256") is None)
    ):
        return ProvisionOutcome(
            bundle, "blocked", f"toolchain: {bundle} unattested for {platform}"
        )
    return platform_entry


def _extract_extra_executables(
    ctx: ProvisionContext,
    bundle: str,
    entry: Mapping,
    platform_entry: Mapping,
    data: bytes,
) -> dict[str, tuple[str, str]] | ProvisionOutcome:
    """Stage, verify, and replace each archive-derived extra executable."""
    extra: dict[str, tuple[str, str]] = {}
    for name, spec in (platform_entry.get("extra_executables") or {}).items():
        relative_root = f"tools/{bundle}/{entry['version']}/_{name}"
        try:
            with staged_directory(ctx.store, relative_root) as transaction:
                subtree_root = transaction.path
                target = subtree_root / spec["executable_relative"]
                materialize.extract_subtree(data, spec["path_in_archive"], subtree_root)
                if not target.is_file():
                    return ProvisionOutcome(
                        bundle,
                        "blocked",
                        f"toolchain: {bundle} extra executable {name!r} not found in archive",
                    )
                actual = toolchain.sha256_file(target)
                if actual != spec.get("exe_sha256"):
                    return ProvisionOutcome(
                        bundle, "blocked", f"toolchain: {bundle} {name} digest mismatch"
                    )
                transaction.commit()
        except (OSError, ValueError) as error:
            return ProvisionOutcome(
                bundle,
                "blocked",
                f"toolchain: {bundle} extra extraction failed: {error}",
            )
        extra[name] = (f"{relative_root}/{spec['executable_relative']}", actual)
    return extra


def _provision_binary_entry(
    ctx: ProvisionContext, bundle: str, entry: Mapping
) -> ProvisionOutcome:
    platform_entry = _platform_entry(entry, bundle, ctx.platform)
    if isinstance(platform_entry, ProvisionOutcome):
        return platform_entry
    try:
        data = ctx.fetcher(platform_entry["url"])
    except (OSError, ValueError) as error:
        return ProvisionOutcome(
            bundle, "blocked", f"toolchain: {bundle} download failed: {error}"
        )
    actual_sha = hashlib.sha256(data).hexdigest()
    if actual_sha != platform_entry["sha256"]:
        return ProvisionOutcome(
            bundle, "blocked", f"toolchain: {bundle} digest mismatch"
        )
    relative = f"tools/{bundle}/{entry['version']}/bin/{bundle}"
    exe_path = ctx.store / relative
    try:
        write_file(
            ctx.store,
            relative,
            archive_member_bytes(data, platform_entry["path_in_archive"]),
            0o755,
        )
    except (KeyError, ValueError) as error:
        return ProvisionOutcome(bundle, "blocked", f"toolchain: {bundle} {error}")
    exe_sha = toolchain.sha256_file(exe_path)
    if exe_sha != platform_entry["exe_sha256"]:
        return ProvisionOutcome(
            bundle, "blocked", f"toolchain: {bundle} digest mismatch"
        )
    extra = _extract_extra_executables(ctx, bundle, entry, platform_entry, data)
    if isinstance(extra, ProvisionOutcome):
        return extra
    _record_bundle(ctx, bundle, BinaryArtifacts(actual_sha, relative, exe_sha, extra))
    return ProvisionOutcome(bundle, "provisioned")


def import_binary(
    ctx: ProvisionContext, bundle: str, entry: Mapping, source: Path
) -> ProvisionOutcome:
    """Adopt an existing on-disk binary ONLY if its sha256 matches the lock.

    Only `binary`-kind bundles can be adopted this way: a `python-env`/
    `node-env` bundle has several console scripts, not one file to import.
    """
    if entry.get("kind") != "binary":
        return ProvisionOutcome(
            bundle,
            "blocked",
            f"toolchain: {bundle} is kind {entry.get('kind')!r}, "
            "--import only adopts binary-kind tools",
        )
    platform_entry = _platform_entry(entry, bundle, ctx.platform)
    if isinstance(platform_entry, ProvisionOutcome):
        return platform_entry
    if not source.is_file():
        return ProvisionOutcome(
            bundle, "blocked", f"toolchain: {bundle} import source missing"
        )
    actual_sha = toolchain.sha256_file(source)
    if actual_sha != platform_entry["exe_sha256"]:
        return ProvisionOutcome(
            bundle, "blocked", f"toolchain: {bundle} digest mismatch"
        )
    relative = f"tools/{bundle}/{entry['version']}/bin/{bundle}"
    try:
        write_file(ctx.store, relative, source.read_bytes(), 0o755)
    except (OSError, ValueError) as error:
        return ProvisionOutcome(
            bundle, "blocked", f"toolchain: {bundle} import failed: {error}"
        )
    # An imported executable has no archive provenance.  Do not lie by
    # equating its executable hash with the lock's source archive hash.
    _record_bundle(ctx, bundle, BinaryArtifacts(None, relative, actual_sha))
    return ProvisionOutcome(bundle, "provisioned")


def _relative_scripts(entry: Mapping, platform: str) -> list[str]:
    """Every console-script relative path a bundle's platform entry declares.

    `binary` kinds have exactly one implicit `bin/<bundle>`, plus one per
    declared `extra_executables` entry (e.g. `node`'s `bin/npm`); `python-env`
    / `node-env` kinds list every console script the registry actually uses
    under `console_scripts` (schema `toolchain.lock.schema.json`).
    """
    platform_entry = entry.get("platforms", {}).get(platform, {})
    scripts = list(platform_entry.get("console_scripts") or ["bin/{bundle}"])
    scripts.extend(
        f"bin/{name}" for name in (platform_entry.get("extra_executables") or {})
    )
    return scripts


def validate_offline(
    lock: Mapping, store: Path, platform: str, *, repo_root: Path
) -> tuple[bool, list[str]]:
    """Check the store against the lock without downloading anything."""
    validate_lock(lock)
    ctx = OfflineValidationContext(lock, store, platform, repo_root)
    _verify_tool_store(ctx)
    _verify_cache_store(ctx)
    return not ctx.problems, ctx.problems


def _verify_tool_store(ctx: OfflineValidationContext) -> None:
    for bundle, entry in ctx.lock["tools"].items():
        platform_entry = _platform_entry(entry, bundle, ctx.platform)
        if isinstance(platform_entry, ProvisionOutcome):
            ctx.problems.append(platform_entry.reason)
            continue
        for relative in _relative_scripts(entry, ctx.platform):
            outcome = toolchain.resolve(
                f"store:{bundle}/{relative.format(bundle=bundle)}",
                lock=ctx.lock,
                store=ctx.store,
                platform=ctx.platform,
                repo_root=ctx.repo_root,
            )
            if isinstance(outcome, toolchain.BlockedReason):
                ctx.problems.append(outcome.reason)


def _verify_cache_store(ctx: OfflineValidationContext) -> None:
    caches = ctx.lock.get("caches") or {}
    if not isinstance(caches, Mapping):
        ctx.problems.append("toolchain: invalid caches")
        return
    manifest = toolchain.load_store_manifest(ctx.store)
    if not isinstance(manifest, Mapping) and caches:
        ctx.problems.append("toolchain: store manifest missing or invalid")
    manifest = manifest if isinstance(manifest, Mapping) else {}
    for cache_name, cache_entry in caches.items():
        _verify_cache_record(ctx, manifest, cache_name, cache_entry)


def _verify_cache_record(
    ctx: OfflineValidationContext,
    manifest: Mapping,
    cache_name: str,
    cache_entry: object,
) -> None:
    if not isinstance(cache_entry, Mapping):
        ctx.problems.append(f"toolchain: {cache_name} cache invalid")
        return
    platforms = cache_entry.get("platforms")
    cache_platform = (
        platforms.get(ctx.platform) if isinstance(platforms, Mapping) else None
    )
    if not isinstance(cache_platform, Mapping):
        ctx.problems.append(
            f"toolchain: {cache_name} cache unattested for {ctx.platform}"
        )
        return
    expected_digest = cache_platform.get("digest")
    actual_digest = toolchain_npm_cache.index_digest(
        ctx.store / "caches" / cache_name / ctx.platform
    )
    recorded_caches = manifest.get("caches")
    recorded_cache = (
        recorded_caches.get(cache_name)
        if isinstance(recorded_caches, Mapping)
        else None
    )
    recorded_platforms = (
        recorded_cache.get("platforms") if isinstance(recorded_cache, Mapping) else None
    )
    recorded_platform = (
        recorded_platforms.get(ctx.platform)
        if isinstance(recorded_platforms, Mapping)
        else None
    )
    if (
        not _valid_digest(expected_digest)
        or actual_digest != expected_digest
        or not isinstance(recorded_platform, Mapping)
        or recorded_platform.get("digest") != expected_digest
    ):
        ctx.problems.append(
            f"toolchain: {cache_name} cache incomplete or digest mismatch"
        )


def provision(
    lock: Mapping,
    store: Path,
    *,
    platform: str,
    only: frozenset[str] | None = None,
    fetcher: Fetcher | None = None,
    repo_root: Path | None = None,
    env: Mapping[str, str] | None = None,
    attest_missing: bool = False,
) -> list[ProvisionOutcome]:
    """Provision reviewed entries, or observe missing pins in acquisition mode."""
    request = ProvisionRequest(
        lock, store, platform, only, fetcher, repo_root, env, attest_missing
    )
    plan = _plan_provision(request)
    if isinstance(plan, list):
        return plan
    outcomes = _execute_tool_plan(plan)
    outcomes.extend(_execute_cache_plan(plan))
    return outcomes


def _plan_provision(
    request: ProvisionRequest,
) -> ProvisionPlan | list[ProvisionOutcome]:
    lock = request.lock
    only = request.only
    validate_lock(lock)
    known = set(lock["tools"]) | set(lock.get("caches") or {})
    if only is not None:
        unknown = sorted(only - known)
        if unknown:
            return [
                ProvisionOutcome(name, "blocked", f"toolchain: {name} unknown to lock")
                for name in unknown
            ]
    context = ProvisionContext(
        request.store,
        lock,
        request.platform,
        request.fetcher or default_fetcher,
        (request.repo_root or Path.cwd()).resolve(strict=False),
        request.env or {},
        request.attest_missing,
    )
    tools = tuple(
        (bundle, entry)
        for bundle, entry in sorted(
            lock["tools"].items(), key=lambda item: item[1].get("kind") in _ENV_KINDS
        )
        if only is None or bundle in only
    )
    caches = tuple(
        bundle
        for bundle in (lock.get("caches") or {})
        if only is None or bundle in only
    )
    return ProvisionPlan(context, tools, caches)


def _execute_tool_plan(plan: ProvisionPlan) -> list[ProvisionOutcome]:
    outcomes: list[ProvisionOutcome] = []
    for bundle, entry in plan.tools:
        if entry.get("kind") not in _IMPLEMENTED_KINDS:
            outcomes.append(
                ProvisionOutcome(
                    bundle,
                    "blocked",
                    f"toolchain: {bundle} kind {entry.get('kind')!r} not yet provisionable",
                )
            )
            continue
        try:
            outcome = (
                _provision_env_entry(plan.context, bundle, entry)
                if entry.get("kind") in _ENV_KINDS
                else _provision_binary_entry(plan.context, bundle, entry)
            )
        except (OSError, ValueError) as error:
            outcome = ProvisionOutcome(
                bundle, "blocked", f"toolchain: {bundle} store mutation failed: {error}"
            )
        outcomes.append(outcome)
    return outcomes


def _execute_cache_plan(plan: ProvisionPlan) -> list[ProvisionOutcome]:
    return [
        ProvisionOutcome(bundle, *toolchain_npm_cache.provision(plan.context, bundle))
        for bundle in plan.caches
    ]

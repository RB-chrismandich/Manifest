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
from .toolchain_provision_models import ProvisionContext, ProvisionOutcome
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
    """Reject malformed or unpinned lock records before touching the store."""
    if lock.get("schema_version") != 1 or not isinstance(lock.get("tools"), Mapping):
        raise ValueError("invalid toolchain lock schema")
    for bundle, entry in lock["tools"].items():
        if not isinstance(bundle, str) or not toolchain._STORE_EXECUTABLE.match(
            f"store:{bundle}/bin/{bundle}"
        ):
            raise ValueError(f"invalid toolchain bundle name: {bundle!r}")
        if not isinstance(entry, Mapping) or not isinstance(
            entry.get("platforms"), Mapping
        ):
            raise ValueError(f"invalid toolchain entry: {bundle}")
        version = entry.get("version")
        if version is not None:
            version_is_safe = (
                _safe_relative(version)
                if entry.get("kind") in _ENV_KINDS
                else _safe_component(version)
            )
            if not version_is_safe:
                raise ValueError(f"invalid expected version for {bundle}")
        for platform, artifact in entry["platforms"].items():
            if not _safe_component(platform) or not isinstance(artifact, Mapping):
                raise ValueError(f"invalid platform record for {bundle}")
            if not _safe_artifact_url(artifact.get("url")):
                raise ValueError(f"invalid artifact URL for {bundle}/{platform}")
            if not _safe_relative(str(artifact.get("path_in_archive", ""))):
                raise ValueError(f"unsafe archive path for {bundle}/{platform}")
            extra = artifact.get("extra_executables") or {}
            if not isinstance(extra, Mapping):
                raise ValueError(f"invalid extra executables for {bundle}/{platform}")
            for name, spec in extra.items():
                if not _safe_component(name) or not isinstance(spec, Mapping):
                    raise ValueError(
                        f"invalid extra executable for {bundle}/{platform}"
                    )
                if not all(
                    _safe_relative(str(spec.get(path_field, "")))
                    for path_field in ("path_in_archive", "executable_relative")
                ):
                    raise ValueError(
                        f"unsafe extra executable path for {bundle}/{platform}"
                    )
            for digest_field in ("sha256", "exe_sha256"):
                digest = artifact.get(digest_field)
                if digest is not None and (
                    not isinstance(digest, str)
                    or len(digest) != 64
                    or any(char not in "0123456789abcdef" for char in digest)
                ):
                    raise ValueError(f"invalid {digest_field} for {bundle}/{platform}")


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
    except ValueError as error:
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
    """Check the store against the lock without downloading anything.

    Returns `(complete, problems)`; `complete` is False if any attested tool
    for `platform` is missing, mismatched, or the store is stale.
    """
    validate_lock(lock)
    problems: list[str] = []
    for bundle, entry in (lock.get("tools") or {}).items():
        platform_entry = _platform_entry(entry, bundle, platform)
        if isinstance(platform_entry, ProvisionOutcome):
            problems.append(platform_entry.reason)
            continue
        for relative in _relative_scripts(entry, platform):
            relative = relative.format(bundle=bundle)
            outcome = toolchain.resolve(
                f"store:{bundle}/{relative}",
                lock=lock,
                store=store,
                platform=platform,
                repo_root=repo_root,
            )
            if isinstance(outcome, toolchain.BlockedReason):
                problems.append(outcome.reason)
    manifest = toolchain.load_store_manifest(store) or {}
    for cache_name, cache_entry in (lock.get("caches") or {}).items():
        cache_platform = (cache_entry.get("platforms") or {}).get(platform, {})
        expected_digest = cache_platform.get("digest")
        cache_dir = store / "caches" / cache_name / platform
        actual_digest = toolchain_npm_cache.index_digest(cache_dir)
        recorded_cache = (manifest.get("caches") or {}).get(cache_name) or {}
        recorded_platform = (recorded_cache.get("platforms") or {}).get(platform, {})
        if (
            expected_digest is None
            or actual_digest != expected_digest
            or recorded_platform.get("digest") != expected_digest
        ):
            problems.append(
                f"toolchain: {cache_name} cache incomplete or digest mismatch"
            )
    return not problems, problems


def provision(
    lock: Mapping,
    store: Path,
    *,
    platform: str,
    only: frozenset[str] | None = None,
    fetcher: Fetcher | None = None,
    repo_root: Path | None = None,
    env: Mapping[str, str] | None = None,
) -> list[ProvisionOutcome]:
    """Provision every (or `only`-selected) lock tool/cache for `platform`;
    binaries provision first so `python-env`/`node-env`/`caches.*` can
    resolve `uv`/`node`, regardless of the lock's own key order."""
    validate_lock(lock)
    ctx = ProvisionContext(
        store,
        lock,
        platform,
        fetcher or default_fetcher,
        repo_root or Path.cwd(),
        env or {},
    )
    items = sorted(
        (lock.get("tools") or {}).items(),
        key=lambda item: item[1].get("kind") in _ENV_KINDS,
    )
    outcomes: list[ProvisionOutcome] = []
    for bundle, entry in items:
        if only is not None and bundle not in only:
            continue
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
            if entry.get("kind") in _ENV_KINDS:
                outcome = _provision_env_entry(ctx, bundle, entry)
            else:
                outcome = _provision_binary_entry(ctx, bundle, entry)
        except (OSError, ValueError) as error:
            outcome = ProvisionOutcome(
                bundle, "blocked", f"toolchain: {bundle} store mutation failed: {error}"
            )
        outcomes.append(outcome)
    outcomes.extend(  # caches.* (Correction 10 rule 2)
        ProvisionOutcome(bundle, *toolchain_npm_cache.provision(ctx, bundle))
        for bundle in (lock.get("caches") or {})
        if only is None or bundle in only
    )
    return outcomes

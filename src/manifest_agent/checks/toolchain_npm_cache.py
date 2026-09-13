"""Store-provisioned, hash-anchored npm cache for `package.node-runtime`
(phase-3-5-decisions.md Correction 10, rule 2).

`package.node-runtime` installs `plugins/stitch-design/runtime/node`'s own
locked dependencies with `npm ci --offline` (`dependency_checks.py::
_node_runtime`). The runner's per-check cache environment (`toolchain_cache.
cache_environment`, Correction 4/C7d) redirects `npm_config_cache` to a
FRESH, EMPTY per-run temp directory -- correct for keeping a check body from
writing into the candidate, but it means `--offline` has nothing to read
from and the check BLOCKs with `npm error code ENOTCACHED`. The honest fix
is not to go back online, and not to point `npm_config_cache` at the
developer's real `~/.npm` (an unattested, unverifiable, host-specific
source `manifest check` must never trust) -- it is a THIRD npm cache,
populated once by `manifest provision` (network permitted there, and only
there) from exactly `plugins/stitch-design/runtime/node/package-lock.json`,
hash-anchored so a check can verify it before trusting it.

`config/toolchain/package-lock.json` (the ``node-env`` bundle's own lock)
was the source Correction 10's prose named, but `package.node-runtime`
never installs that project -- it installs the stitch-design bundle, whose
lockfile shares only 8 of 71 packages with `node-env`'s. A cache built from
the wrong lockfile would still BLOCK "no store-anchored npm cache" on every
real run, which is not an honest source; this module builds the cache from
the lockfile the check actually installs.

Materialization reuses `npm ci`'s own integrity verification (SHA-512,
package-lock.json's `integrity` fields) rather than re-implementing a
per-package hash check: `npm ci --ignore-scripts` against a disposable
scratch copy of just `package.json`/`package-lock.json`, with
`npm_config_cache` pointed at the store, downloads and verifies every
package as a side effect of populating its own cache. The resulting
attestation digest is the sorted set of npm's own cache-index entries
(`_cacache/index-v5/**`) -- a content fingerprint of what the cache holds,
independent of npm's internal directory sharding.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import tempfile
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from . import toolchain
from .toolchain_provision_store import (
    _with_store_lock,
    _write_manifest,
    staged_directory,
)

CACHE_BUNDLE = "node-cache"
PROJECT_RELATIVE = "plugins/stitch-design/runtime/node"
_INDEX_SUBDIR = Path("_cacache") / "index-v5"
_MATERIALIZE_TIMEOUT_SECONDS = 300.0


class NpmCacheError(RuntimeError):
    """`node-cache` materialization failed (`manifest provision` only)."""


def _frame(hasher, kind: bytes, relative: bytes, payload: bytes) -> None:
    hasher.update(kind)
    hasher.update(len(relative).to_bytes(8, "big"))
    hasher.update(relative)
    hasher.update(len(payload).to_bytes(8, "big"))
    hasher.update(payload)


_VOLATILE_FIELDS = frozenset({"date", "expires", "time"})


def _stable_record(value: object) -> object:
    """Strip only volatile HTTP fields from a decoded cacache index record."""
    if isinstance(value, dict):
        return {
            key: _stable_record(item)
            for key, item in value.items()
            if key not in _VOLATILE_FIELDS
        }
    if isinstance(value, list):
        return [_stable_record(item) for item in value]
    return value


def _semantic_index_bytes(path: Path, index_root: Path) -> tuple[bytes, bytes]:
    """Validate a cacache bucket and return its path plus stable semantics."""
    bucket = path.relative_to(index_root).as_posix().encode()
    records: set[bytes] = set()
    for raw in path.read_bytes().splitlines():
        if not raw:
            continue
        checksum, separator, value = raw.partition(b"\t")
        if (
            not separator
            or len(checksum) != 40
            or any(byte not in b"0123456789abcdef" for byte in checksum)
            or hashlib.sha1(value).hexdigest().encode() != checksum
        ):
            raise NpmCacheError("node-cache: malformed index record")
        try:
            payload = json.loads(value)
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise NpmCacheError("node-cache: malformed index record") from error
        key = payload.get("key") if isinstance(payload, dict) else None
        if not isinstance(key, str):
            raise NpmCacheError("node-cache: malformed index record")
        key_hash = hashlib.sha256(key.encode()).hexdigest()
        expected_bucket = f"{key_hash[:2]}/{key_hash[2:4]}/{key_hash[4:]}".encode()
        if bucket != expected_bucket:
            raise NpmCacheError("node-cache: malformed index record")
        records.add(
            json.dumps(
                _stable_record(payload), sort_keys=True, separators=(",", ":")
            ).encode()
        )
    if not records:
        raise NpmCacheError("node-cache: malformed index record")
    return bucket, b"".join(
        len(value).to_bytes(8, "big") + value for value in sorted(records)
    )


def index_digest(cache_root: Path) -> str | None:
    """Digest canonical index semantics and exact content-v2 bytes."""
    content_root = cache_root / "_cacache" / "content-v2"
    index_root = cache_root / _INDEX_SUBDIR
    if not content_root.is_dir() or not index_root.is_dir():
        return None
    index_entries = sorted(path for path in index_root.rglob("*") if not path.is_dir())
    content_entries = sorted(
        path for path in content_root.rglob("*") if not path.is_dir()
    )
    if not index_entries or not content_entries:
        return None
    hasher = hashlib.sha256()
    hasher.update((len(index_entries) + len(content_entries)).to_bytes(8, "big"))
    for bucket, record in sorted(
        _semantic_index_bytes(path, index_root) for path in index_entries
    ):
        _frame(hasher, b"I", bucket, record)
    for path in content_entries:
        relative = path.relative_to(cache_root).as_posix().encode()
        if path.is_symlink():
            _frame(hasher, b"L", relative, os.readlink(path).encode())
        else:
            _frame(hasher, b"C", relative, path.read_bytes())
    return hasher.hexdigest()


def source_sha256(repo_root: Path) -> str:
    """sha256 of the exact ``package-lock.json`` bytes `package.node-runtime`
    installs from -- the lock's ``caches.node-cache.source_sha256`` anchor,
    and what a candidate's own copy is compared against at check time."""
    path = repo_root / PROJECT_RELATIVE / "package-lock.json"
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _resolve_npm_for_materialize(
    lock: Mapping, store: Path, platform: str, repo_root: Path
) -> toolchain.ResolvedTool:
    """`node` and `npm`, both store-resolved -- `npm-cli.js` runs via a
    `#!/usr/bin/env node` shebang, so `node` must resolve too even though
    only `npm`'s `ResolvedTool` is returned."""
    resolved_node = toolchain.resolve(
        "store:node/bin/node",
        lock=lock,
        store=store,
        platform=platform,
        repo_root=repo_root,
    )
    if isinstance(resolved_node, toolchain.BlockedReason):
        raise NpmCacheError(resolved_node.reason)
    resolved_npm = toolchain.resolve(
        "store:node/bin/npm",
        lock=lock,
        store=store,
        platform=platform,
        repo_root=repo_root,
    )
    if isinstance(resolved_npm, toolchain.BlockedReason):
        raise NpmCacheError(resolved_npm.reason)
    return resolved_npm


def _npm_ci_into_cache(
    *,
    resolved_npm: toolchain.ResolvedTool,
    package_json_bytes: bytes,
    package_lock_bytes: bytes,
    cache_dir: Path,
    env: Mapping[str, str],
) -> None:
    """`npm ci --ignore-scripts` a scratch copy of the two lockfile bytes,
    with `npm_config_cache` pointed at `cache_dir` -- npm's own download and
    SHA-512 integrity verification populates the cache as a side effect."""
    with tempfile.TemporaryDirectory(prefix="manifest-npm-cache-scratch-") as name:
        scratch = Path(name)
        (scratch / "package.json").write_bytes(package_json_bytes)
        (scratch / "package-lock.json").write_bytes(package_lock_bytes)
        run_env = dict(env)
        run_env["PATH"] = os.pathsep.join(
            str(entry) for entry in resolved_npm.path_entries
        )
        run_env["npm_config_cache"] = str(cache_dir)
        try:
            result = subprocess.run(
                [str(resolved_npm.executable), "ci", "--ignore-scripts"],
                cwd=scratch,
                env=run_env,
                capture_output=True,
                text=True,
                timeout=_MATERIALIZE_TIMEOUT_SECONDS,
            )
        except (OSError, subprocess.TimeoutExpired) as error:
            raise NpmCacheError(f"npm ci could not execute: {error}") from error
        if result.returncode != 0:
            raise NpmCacheError(
                f"npm ci exited {result.returncode}: {result.stderr[-2000:]}"
            )


def materialize(
    ctx: _ProvisionContext, *, expected_digest: str | None = None, publish: bool = True
) -> tuple[Path, str]:
    """Materialize a verified npm cache for the complete provision context."""
    resolved_npm = _resolve_npm_for_materialize(
        ctx.lock, ctx.store, ctx.platform, ctx.repo_root
    )
    project = ctx.repo_root / PROJECT_RELATIVE
    try:
        package_json_bytes = (project / "package.json").read_bytes()
        package_lock_bytes = (project / "package-lock.json").read_bytes()
    except OSError as error:
        raise NpmCacheError(f"node-cache source unavailable: {error}") from error
    relative = f"caches/{CACHE_BUNDLE}/{ctx.platform}"
    try:
        with staged_directory(ctx.store, relative) as transaction:
            stage = transaction.path
            _npm_ci_into_cache(
                resolved_npm=resolved_npm,
                package_json_bytes=package_json_bytes,
                package_lock_bytes=package_lock_bytes,
                cache_dir=stage,
                env=ctx.env,
            )
            digest = index_digest(stage)
            if digest is None:
                raise NpmCacheError("node-cache: npm ci produced an empty cache index")
            if expected_digest is not None and digest != expected_digest:
                raise NpmCacheError("node-cache: digest mismatch")
            if publish:
                transaction.commit()
    except (OSError, ValueError) as error:
        raise NpmCacheError(f"node-cache store mutation failed: {error}") from error
    return ctx.store / relative, digest


@dataclass(frozen=True, slots=True)
class ResolvedCache:
    """A verified `node-cache` directory, ready for `npm_config_cache`."""

    directory: Path
    digest: str


def resolve(
    *, repo_root: Path, store: Path, lock: Mapping, platform: str
) -> ResolvedCache | toolchain.BlockedReason:
    """Resolve only a complete cache attested by schema-valid lock records."""
    caches = lock.get("caches")
    if not isinstance(caches, Mapping):
        return toolchain.BlockedReason("toolchain: invalid caches")
    entry = caches.get(CACHE_BUNDLE)
    if not isinstance(entry, Mapping):
        return toolchain.BlockedReason(
            f"toolchain: {CACHE_BUNDLE} unattested for {platform}"
        )
    platforms = entry.get("platforms")
    platform_entry = platforms.get(platform) if isinstance(platforms, Mapping) else None
    if not isinstance(platform_entry, Mapping):
        return toolchain.BlockedReason(
            f"toolchain: {CACHE_BUNDLE} unattested for {platform}"
        )
    attested_digest = platform_entry.get("digest")
    if not isinstance(attested_digest, str):
        return toolchain.BlockedReason(
            f"toolchain: {CACHE_BUNDLE} unattested for {platform}"
        )
    try:
        actual_source = source_sha256(repo_root)
    except OSError as error:
        return toolchain.BlockedReason(
            f"toolchain: {CACHE_BUNDLE} source unavailable: {error}"
        )
    if actual_source != entry.get("source_sha256"):
        return toolchain.BlockedReason(
            f"toolchain: {CACHE_BUNDLE} stale (package-lock.json changed)"
        )
    cache_dir = store / "caches" / CACHE_BUNDLE / platform
    actual_digest = index_digest(cache_dir)
    if actual_digest is None or actual_digest != attested_digest:
        return toolchain.BlockedReason(f"toolchain: {CACHE_BUNDLE} digest mismatch")
    return ResolvedCache(cache_dir, actual_digest)


def resolve_for_check(root: Path) -> ResolvedCache | toolchain.BlockedReason:
    """`resolve()` plus the same lock/store lookup every other project-check
    body does (`analysis_checks.resolve_scanner`, `toolchain_resolve.
    resolve_tool`) -- the one entry point `dependency_checks.py` calls."""
    lock_path = root / "config" / "toolchain.lock.json"
    try:
        lock = toolchain.load_lock_file(lock_path, repo_root=root)
    except (OSError, ValueError) as error:
        return toolchain.BlockedReason(f"toolchain lock unavailable: {error}")
    try:
        store = toolchain.store_root(dict(os.environ), root)
    except toolchain.UnsafeStoreLocationError as error:
        return toolchain.BlockedReason(str(error))
    return resolve(
        repo_root=root, store=store, lock=lock, platform=toolchain.current_platform()
    )


class _ProvisionContext(Protocol):
    """Structural stand-in for `toolchain_provision.ProvisionContext` --
    duck-typed so this module never imports that one back (it already
    imports this one), which would be a cycle. `@property` (read-only), not
    plain attributes: `ProvisionContext` is a frozen dataclass, and a
    protocol with mutable attributes is a structurally NARROWER type a
    read-only frozen field cannot satisfy."""

    @property
    def store(self) -> Path: ...
    @property
    def lock(self) -> Mapping: ...
    @property
    def platform(self) -> str: ...
    @property
    def repo_root(self) -> Path: ...
    @property
    def env(self) -> Mapping[str, str]: ...


def _load_manifest(store: Path, lock: Mapping) -> dict:
    manifest = toolchain.load_store_manifest(store)
    digest = toolchain.lock_digest(lock)
    if manifest is None or manifest.get("lock_digest") != digest:
        return {"schema_version": 1, "lock_digest": digest, "tools": {}}
    return manifest


def _record(ctx: _ProvisionContext, bundle: str, digest: str) -> None:
    """Record `bundle`'s attested digest into the store manifest, under the
    same `fcntl.flock` serialization `toolchain_provision.py` uses for
    every other bundle -- so a `node-cache` write can never interleave with
    a concurrent `manifest provision` writing `manifest.json`."""

    def write() -> dict:
        manifest = _load_manifest(ctx.store, ctx.lock)
        platforms = manifest.setdefault("caches", {}).setdefault(bundle, {})
        platforms.setdefault("platforms", {})[ctx.platform] = {"digest": digest}
        _write_manifest(ctx.store, manifest)
        return manifest

    _with_store_lock(ctx.store, write)


def provision(ctx: _ProvisionContext, bundle: str) -> tuple[str, str, str | None]:
    """Materialize and record a cache, or observe an unpinned cache digest."""
    if bundle != CACHE_BUNDLE:
        return (
            "blocked",
            f"toolchain: {bundle} has no cache materializer",
            None,
        )
    cache_entry = (ctx.lock.get("caches") or {}).get(bundle) or {}
    platform_entry = (cache_entry.get("platforms") or {}).get(ctx.platform, {})
    expected_digest = platform_entry.get("digest")
    expected_source = cache_entry.get("source_sha256")
    try:
        if source_sha256(ctx.repo_root) != expected_source:
            return "blocked", f"toolchain: {bundle} cache is unattested or stale", None
        if expected_digest is None and not ctx.attest_missing:
            return "blocked", f"toolchain: {bundle} cache is unattested or stale", None
        _cache_dir, digest = materialize(
            ctx, expected_digest=expected_digest, publish=expected_digest is not None
        )
        if expected_digest is None:
            return "UNPINNED", f"UNPINNED: toolchain: {bundle} unattested", digest
        _record(ctx, bundle, digest)
    except (NpmCacheError, OSError, ValueError) as error:
        return "blocked", str(error), None
    return "provisioned", "", digest

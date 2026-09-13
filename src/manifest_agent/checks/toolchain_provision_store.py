"""Store manifest recording and environment materialization for provisioning."""

from __future__ import annotations

import fcntl
import json
import os
import subprocess
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from . import toolchain
from . import toolchain_materialize as materialize


def _safe_relative(value: str) -> bool:
    path = Path(value)
    return bool(value) and not path.is_absolute() and ".." not in path.parts

def _with_store_lock(store: Path, body: Callable[[], dict]) -> dict:
    store.mkdir(parents=True, exist_ok=True)
    lock_path = store / ".provision.lock"
    with os.fdopen(
        os.open(lock_path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600), "a"
    ) as stream:
        fcntl.flock(stream, fcntl.LOCK_EX)
        return body()


def _load_manifest(store: Path, lock: Mapping, platform: str) -> dict:
    manifest = toolchain.load_store_manifest(store)
    if (
        manifest is None
        or manifest.get("lock_digest") != toolchain.lock_digest(lock)
        or manifest.get("platform") != platform
    ):
        return {
            "schema_version": 1,
            "lock_digest": toolchain.lock_digest(lock),
            "platform": platform,
            "tools": {},
        }
    return manifest


def _resolved_commit(repo_root: Path) -> str | None:
    result = subprocess.run(
        ("git", "rev-parse", "--verify", "HEAD^{commit}"),
        cwd=repo_root,
        capture_output=True,
        check=False,
        text=True,
    )
    return result.stdout.strip() if result.returncode == 0 else None


def _attestation_metadata(ctx: Any, bundle: str) -> dict[str, str | None]:
    entry = ctx.lock["tools"][bundle]
    platform_entry = entry["platforms"][ctx.platform]
    return {
        "platform": ctx.platform,
        "version": entry["version"],
        "source": platform_entry["url"],
        "resolved_commit": _resolved_commit(ctx.repo_root),
    }


@dataclass(frozen=True)
class BinaryArtifacts:
    """The primary `bin/<bundle>` executable plus any `extra_executables`
    extracted alongside it (e.g. `node`'s `bin/npm`) -- each entry carries
    its OWN `sha256`; `toolchain.resolve()` looks up the one matching the
    relative path it was asked to verify, never the primary tool's."""

    source_sha256: str
    primary_relative: str
    primary_sha256: str
    extra: Mapping[str, tuple[str, str]] = field(default_factory=dict)


def _record_bundle(
    ctx: Any, bundle: str, artifacts: BinaryArtifacts
) -> None:
    def body() -> dict:
        manifest = _load_manifest(ctx.store, ctx.lock, ctx.platform)
        executables = {
            f"bin/{bundle}": {
                "path": artifacts.primary_relative,
                "sha256": artifacts.primary_sha256,
            }
        }
        for name, (extra_relative, extra_sha256) in artifacts.extra.items():
            # `npm-cli.js` (and any future extra executable) runs via a
            # `#!/usr/bin/env node`-style shebang -- it needs the primary
            # `bin/<bundle>` executable (node) on its resolved PATH, exactly
            # like a python-env console script needs its venv interpreter.
            executables[f"bin/{name}"] = {
                "path": extra_relative,
                "sha256": extra_sha256,
                "interpreter": artifacts.primary_relative,
                "interpreter_sha256": artifacts.primary_sha256,
            }
        manifest["tools"][bundle] = {
            **_attestation_metadata(ctx, bundle),
            "source_sha256": artifacts.source_sha256,
            "executables": executables,
        }
        (ctx.store / "manifest.json").write_text(json.dumps(manifest, sort_keys=True))
        return manifest

    _with_store_lock(ctx.store, body)


def _record_env_bundle(
    ctx: Any, bundle: str, source_sha256: str, scripts: Mapping[str, str]
) -> None:
    def body() -> dict:
        manifest = _load_manifest(ctx.store, ctx.lock, ctx.platform)
        manifest["tools"][bundle] = {
            **_attestation_metadata(ctx, bundle),
            "source_sha256": source_sha256,
            # Location metadata for `.pth` normalization (Correction 9).
            "source_checkout": str(ctx.repo_root.resolve()),
            "executables": {
                f"bin/{name}": {"path": relative} for name, relative in scripts.items()
            },
        }
        (ctx.store / "manifest.json").write_text(json.dumps(manifest, sort_keys=True))
        return manifest

    _with_store_lock(ctx.store, body)


class _SourceUnavailable(RuntimeError):
    """A `file://` lock source could not be read; carries the reason text."""


def _read_source_bytes(ctx: Any, url: str) -> bytes:
    """Read a lock-owned source file without letting the URL escape checkout."""
    if not url.startswith("file://"):
        raise _SourceUnavailable(f"source unavailable: unsupported local URL: {url}")
    relative = url.removeprefix("file://")
    if not _safe_relative(relative):
        raise _SourceUnavailable(f"source unavailable: unsafe path: {relative}")
    root = ctx.repo_root.resolve(strict=False)
    try:
        path = (ctx.repo_root / relative).resolve(strict=True)
    except OSError as error:
        raise _SourceUnavailable(f"source unavailable: {relative}: {error}") from error
    if not path.is_relative_to(root) or not path.is_file():
        raise _SourceUnavailable(f"source unavailable: unsafe path: {relative}")
    try:
        return path.read_bytes()
    except OSError as error:
        raise _SourceUnavailable(f"source unavailable: {relative}: {error}") from error


def _materialize_env(
    ctx: Any, bundle: str, entry: Mapping, env_root: Path, names: list[str]
) -> dict[str, str]:
    """Dispatch to the right materializer by bundle name/kind, and return
    its console scripts. `project-env`/`config-env` are the two fixed
    Correction 7 step 1 additions, each with its own real project dir;
    every other `python-env`/`node-env` bundle keeps the original
    kind-only dispatch."""
    ctx_m = materialize.MaterializeContext(
        ctx.lock, ctx.store, ctx.platform, ctx.repo_root, ctx.env
    )
    if bundle == "project-env":
        # The ROOT project's dependency set ONLY -- never installs
        # `manifest_agent` itself (Correction 7 step 1).
        materialize.materialize_project_env(ctx_m, env_root)
        return materialize.python_env_console_scripts(env_root, names)
    if bundle == "config-env":
        # `configs/claude`'s OWN project, installed for real so its
        # `[project.scripts] manifest` entry point exists at `bin/manifest`
        # -- unlike project-env, this env IS meant to carry an installed
        # project (Correction 7 step 1).
        materialize.materialize_python_env(
            ctx_m, env_root, project_relative="configs/claude"
        )
        return materialize.python_env_console_scripts(env_root, names)
    if entry["kind"] == "python-env":
        materialize.materialize_python_env(ctx_m, env_root)
        return materialize.python_env_console_scripts(env_root, names)
    materialize.materialize_node_env(ctx_m, env_root, ctx.fetcher)
    return materialize.node_env_console_scripts(env_root, names)



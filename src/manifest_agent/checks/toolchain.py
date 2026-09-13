"""Resolve hash-verified ``store:`` tool references without network access."""

from __future__ import annotations

import hashlib
import json
import os
import platform as _platform
import re
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from . import (
    toolchain_cache,
    toolchain_env,
    toolchain_fingerprint,
    toolchain_path_prepend,
)
from .secure_input import read_trust_anchor

STORE_ENV_VAR = "MANIFEST_TOOLCHAIN_STORE"
XDG_CACHE_ENV_VAR = "XDG_CACHE_HOME"
DEFAULT_CACHE_RELATIVE = Path(".cache") / "manifest" / "toolchain"

# "Always present" no longer means "found on PATH" (Correction 4): `python3`
# means the interpreter already running `manifest check`, rewritten by
# `resolve_interpreter_argv` to `sys.executable`, never a PATH search; `bash`
# is an OS-baseline-PATH lookup (Correction 17), not `os.defpath`.
ALWAYS_PRESENT_EXECUTABLES = frozenset({"python3", "bash"})

_STORE_EXECUTABLE = re.compile(
    r"^store:(?P<tool>[A-Za-z0-9][A-Za-z0-9._-]*)/(?P<relative>[^\0]+)$"
)


# Re-exported from toolchain_env (moved there to keep this file, and
# _verify_env_exe's helpers, under the Code Constitution's 500-line ceiling
# -- toolchain_env.py is where the rest of the python-env/node-env
# verification logic that needs them already lives).
ResolvedTool = toolchain_env.ResolvedTool
BlockedReason = toolchain_env.BlockedReason


def parse_store_executable(value: str) -> tuple[str, str] | None:
    """Split `"store:<bundle>/<relative>"` into `(bundle, relative)`, else None."""
    match = _STORE_EXECUTABLE.match(value)
    if match is None:
        return None
    return match.group("tool"), match.group("relative")


def is_legal_plain_executable(value: str) -> bool:
    """Whether a non-`store:` executable name is on the always-present allow-list.

    Only interpreters guaranteed present without provisioning (`python3` --
    meaning the runner's OWN interpreter, resolved by `resolve_interpreter_argv`,
    never a `PATH` search; `bash` -- an OS-baseline-PATH lookup, Correction 17)
    or a repository-relative script path may bypass the store; any other bare
    command name (resolved by searching `PATH`) is exactly the trust gap 3a
    closes and must migrate to a `store:` form instead.
    """
    if value in ALWAYS_PRESENT_EXECUTABLES:
        return True
    path = Path(value)
    return not path.is_absolute() and "/" in value and ".." not in path.parts


_MACHINE_ALIASES = {"x86_64": "x64", "amd64": "x64", "aarch64": "arm64"}


def current_platform() -> str:
    """The running `<os>-<arch>` triple, in the lock file's naming convention."""
    system = _platform.system().casefold()
    machine = _MACHINE_ALIASES.get(
        _platform.machine().casefold(), _platform.machine().casefold()
    )
    return f"{system}-{machine}"


class UnsafeStoreLocationError(ValueError):
    """The resolved store location is inside a forbidden root."""


def store_root(env: Mapping[str, str], *forbidden_roots: Path) -> Path:
    """Resolve the toolchain store location, honoring the documented precedence.

    Enforced, not merely documented: the resolved location must not be, or
    be inside, the process's current working directory (the repository
    checkout `manifest check`/`manifest provision` always run from) or any
    caller-supplied `forbidden_roots` (e.g. the disposable candidate).
    """
    override = env.get(STORE_ENV_VAR, "")
    if override:
        resolved = Path(override)
    else:
        xdg_cache = env.get(XDG_CACHE_ENV_VAR, "")
        if xdg_cache:
            resolved = Path(xdg_cache) / "manifest" / "toolchain"
        else:
            home = env.get("HOME", "") or os.path.expanduser("~")
            resolved = Path(home) / DEFAULT_CACHE_RELATIVE
    absolute = Path(resolved).expanduser().resolve(strict=False)
    for forbidden in (Path.cwd(), *forbidden_roots):
        forbidden = Path(forbidden).expanduser().resolve(strict=False)
        if absolute == forbidden or absolute.is_relative_to(forbidden):
            raise UnsafeStoreLocationError(
                f"toolchain store must not resolve inside {forbidden}"
            )
    return absolute


def sha256_file(path: Path) -> str:
    """Return the SHA-256 digest of the complete regular file at `path`."""
    with open(path, "rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def lock_digest(lock: Mapping[str, Any]) -> str:
    """A stable content digest of an in-memory lock document."""
    serialized = json.dumps(
        lock, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode()
    return hashlib.sha256(serialized).hexdigest()


def lock_digest_for_registry(
    document: Mapping[str, Any], registry_path: Path, *, repo_root: Path
) -> dict[str, object]:
    """Load the declared lock from its checkout-owned no-follow descriptor."""
    relative = document.get("toolchain_lock", "") or ""
    digest, lock_document = "", {}
    if relative:
        try:
            raw = read_trust_anchor(repo_root, repo_root / relative)
            digest = hashlib.sha256(raw).hexdigest()
            parsed = json.loads(raw)
            lock_document = parsed if isinstance(parsed, dict) else {}
        except (ValueError, OSError, json.JSONDecodeError) as error:
            raise ValueError(
                f"toolchain lock trust anchor unavailable: {error}"
            ) from error
    return {
        "toolchain_lock": relative,
        "toolchain_lock_digest": digest,
        "toolchain_lock_document": lock_document,
    }


def load_lock_file(path: Path, *, repo_root: Path) -> dict[str, Any]:
    """Load a checkout-owned toolchain lock without following a symlink."""
    try:
        document = json.loads(read_trust_anchor(repo_root, path))
    except (ValueError, json.JSONDecodeError) as error:
        raise ValueError(f"toolchain lock unavailable: {error}") from error
    if not isinstance(document, dict):
        raise ValueError("toolchain lock must be a JSON object")
    return document


def load_store_manifest(store: Path) -> dict[str, Any] | None:
    """Load the store manifest only when its top-level value is an object."""
    manifest_path = store / "manifest.json"
    if not manifest_path.is_file():
        return None
    try:
        document = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return document if isinstance(document, dict) else None


def _safe_relative(value: str) -> bool:
    """A store-manifest-provided relative path is untrusted: reject absolute
    paths and `..` traversal before ever joining it onto the store root."""
    if not value:
        return False
    path = Path(value)
    return not path.is_absolute() and ".." not in path.parts


def _locked_executable(
    lock: Mapping[str, Any], bundle: str, relative: str, platform: str
) -> tuple[Mapping[str, Any], Mapping[str, Any], str] | BlockedReason:
    tools = lock.get("tools")
    entry = tools.get(bundle) if isinstance(tools, Mapping) else None
    platforms = entry.get("platforms") if isinstance(entry, Mapping) else None
    platform_entry = platforms.get(platform) if isinstance(platforms, Mapping) else None
    exe_sha256 = toolchain_env.expected_exe_sha256(bundle, relative, platform_entry)
    if not (
        isinstance(entry, Mapping)
        and isinstance(platform_entry, Mapping)
        and isinstance(exe_sha256, str)
    ):
        return BlockedReason(f"toolchain: {bundle} unattested for {platform}")
    return entry, platform_entry, exe_sha256


def resolve(
    store_reference: str,
    *,
    lock: Mapping[str, Any],
    store: Path,
    platform: str,
    repo_root: Path,
) -> ResolvedTool | BlockedReason:
    """Resolve a store reference only when its executable matches the lock."""
    parsed = parse_store_executable(store_reference)
    if parsed is None:
        raise ValueError(f"not a store executable reference: {store_reference!r}")
    bundle, relative = parsed
    locked = _locked_executable(lock, bundle, relative, platform)
    if isinstance(locked, BlockedReason):
        return locked
    not_provisioned = f"toolchain: {bundle} not provisioned (run manifest provision)"
    entry, platform_entry, exe_sha256 = locked
    manifest = load_store_manifest(store)
    if manifest is None:
        return BlockedReason(not_provisioned)
    if (
        manifest.get("lock_digest") != lock_digest(lock)
        or manifest.get("platform") != platform
    ):
        return BlockedReason("toolchain: store stale (lock or platform changed)")

    executable = _manifest_executable(
        manifest, bundle, relative, entry, platform_entry, platform, not_provisioned
    )
    if isinstance(executable, BlockedReason):
        return executable
    bundle_manifest, exe_info = executable
    if entry.get("kind") in ("python-env", "node-env"):
        inputs = _EnvExeInputs(
            bundle,
            entry,
            exe_info,
            bundle_manifest,
            exe_sha256,
            platform_entry.get("python_provider"),
        )
        return _resolve_env_exe(
            inputs, lock=lock, store=store, platform=platform, repo_root=repo_root
        )
    return _verify_exe(bundle, exe_info, store, exe_sha256)


def _manifest_executable(
    manifest: Mapping,
    bundle: str,
    relative: str,
    entry: Mapping,
    platform_entry: Mapping,
    platform: str,
    not_provisioned: str,
) -> tuple[Mapping, Mapping] | BlockedReason:
    manifest_tools = manifest.get("tools")
    bundle_manifest = (
        manifest_tools.get(bundle) if isinstance(manifest_tools, Mapping) else None
    )
    if not isinstance(bundle_manifest, Mapping):
        return BlockedReason(not_provisioned)
    if (
        bundle_manifest.get("platform") != platform
        or bundle_manifest.get("version") != entry.get("version")
        or bundle_manifest.get("source") != platform_entry.get("url")
    ):
        return BlockedReason("toolchain: store stale (attestation changed)")
    source_sha256 = bundle_manifest.get("source_sha256")
    if source_sha256 is not None and source_sha256 != platform_entry.get("sha256"):
        return BlockedReason("toolchain: store stale (lock changed)")
    executables = bundle_manifest.get("executables")
    exe_info = executables.get(relative) if isinstance(executables, Mapping) else None
    if not isinstance(exe_info, Mapping):
        return BlockedReason(not_provisioned)
    return bundle_manifest, exe_info


@dataclass(frozen=True)
class _EnvExeInputs:
    """The `resolve()` locals its `python-env`/`node-env` branch needs
    together, bundled so `_resolve_env_exe` stays under the parameter
    ceiling -- these five always travel together, never independently."""

    bundle: str
    entry: Mapping
    exe_info: Mapping
    bundle_manifest: Mapping
    exe_sha256: str
    python_provider: Mapping[str, str] | None


def _resolve_env_exe(
    inputs: _EnvExeInputs,
    *,
    lock: Mapping,
    store: Path,
    platform: str,
    repo_root: Path,
):
    """The `python-env`/`node-env` branch of `resolve()`, split out to keep
    `resolve()` itself under the Code Constitution's line ceiling."""
    node_result = None
    if inputs.entry["kind"] == "node-env" and inputs.bundle != "node":
        node_result = resolve(
            "store:node/bin/node",
            lock=lock,
            store=store,
            platform=platform,
            repo_root=repo_root,
        )
    # Repository context is supplied by the caller; cwd is never trust input.
    env_trust = toolchain_env.EnvTrust(store, repo_root.resolve(strict=True))
    executable = toolchain_env.EnvExecutable(
        inputs.bundle,
        inputs.entry["kind"],
        str(inputs.exe_info.get("path", "")),
        inputs.exe_sha256,
        inputs.python_provider,
    )
    return toolchain_env.verify_env_exe(executable, env_trust, node_result)


def _checked_relative_path(store: Path, relative_path: str) -> Path | None:
    return toolchain_env._checked_relative_path(store, relative_path)


def _verify_exe(bundle: str, exe_info: Mapping, store: Path, exe_sha256: str):
    """Re-hash the store's file at the path it claims -- against the lock's
    `exe_sha256`, never the store manifest's own recorded hash."""
    exe_path = _checked_relative_path(store, exe_info.get("path", ""))
    if exe_path is None:
        return toolchain_env._not_provisioned(bundle)
    actual = sha256_file(exe_path)
    if actual != exe_sha256:
        return BlockedReason(f"toolchain: {bundle} digest mismatch")

    interpreter_path = None
    interpreter_relative = exe_info.get("interpreter")
    if interpreter_relative:
        interpreter_path = _checked_relative_path(store, interpreter_relative)
        if interpreter_path is None:
            return toolchain_env._not_provisioned(bundle)
        if sha256_file(interpreter_path) != exe_info.get("interpreter_sha256"):
            return BlockedReason(f"toolchain: {bundle} digest mismatch")

    bin_dirs = (exe_path.parent,)
    if interpreter_path is not None:
        bin_dirs = (exe_path.parent, interpreter_path.parent)
    return ResolvedTool(
        bundle,
        exe_path,
        interpreter_path,
        toolchain_env.with_default_path(bin_dirs),
        actual,
    )


def rewrite_argv(
    argv: tuple[str, ...],
    resolved: ResolvedTool | Mapping[str, ResolvedTool] | None,
) -> tuple[str, ...]:
    """Replace `store:` argv tokens with resolved absolute executable paths.

    A single `ResolvedTool` (the common case: a check's own argv[0]) rewrites
    only argv[0], exactly as before. A `{store_ref: ResolvedTool}` mapping
    (built by `resolve_for_preflight` when a tool's `version_argv` embeds more
    than one distinct `store:` reference -- e.g. a python-env console script
    plus its own venv interpreter) rewrites every matching token, anywhere in
    argv, not only argv[0].
    """
    if resolved is None or not argv:
        return argv
    if isinstance(resolved, Mapping):
        return tuple(
            str(resolved[token].executable) if token in resolved else token
            for token in argv
        )
    if parse_store_executable(argv[0]) is None:
        return argv
    return (str(resolved.executable), *argv[1:])


def resolve_interpreter_argv(argv: tuple[str, ...]) -> tuple[str, ...]:
    """Rewrite every literal `python3` token to `sys.executable` -- the
    interpreter already running `manifest check`, never a `PATH` search
    (Correction 4). `bash` is untouched."""
    if not argv:
        return argv
    return tuple(sys.executable if token == "python3" else token for token in argv)


def resolved_env(env: Mapping[str, str], resolved: ResolvedTool) -> dict[str, str]:
    """Build the child PATH from store bin dirs + the OS baseline PATH (Correction 17) -- never the user PATH."""
    result = dict(env)
    result["PATH"] = os.pathsep.join(str(entry) for entry in resolved.path_entries)
    return result


# Re-exported from toolchain_cache (moved there to keep this file under the

# Fixed OS command baseline used whenever a legal system executable is invoked.
OS_BASELINE_PATH = toolchain_cache.OS_BASELINE_PATH
# Code Constitution's 500-line ceiling -- see that module's docstring).
run_cache_directory = toolchain_cache.run_cache_directory
cache_environment = toolchain_cache.cache_environment
scratch_home_environment = toolchain_cache.scratch_home_environment


# Re-exported from toolchain_fingerprint (moved there to keep this file
# under the Code Constitution's 500-line ceiling); `fingerprint`/
# `fingerprint_for` wrap it with this module's own `sha256_file`/`store_root`
# so callers keep their original signature.
def fingerprint(store: Path, resolved: Mapping[str, ResolvedTool]) -> dict[str, str]:
    """Return file-identity evidence for a resolved store tool set."""
    return toolchain_fingerprint.fingerprint(store, resolved, sha256_file)


def fingerprint_for(
    resolved: ResolvedTool | None, env: Mapping[str, str]
) -> dict[str, str]:
    """Return resolution evidence for one tool under the supplied environment."""
    return toolchain_fingerprint.fingerprint_for(resolved, env, store_root, sha256_file)


integrity_reason = toolchain_fingerprint.integrity_reason


# The caller-side context every toolchain_path_prepend.py function needs,
# built once -- avoids both a circular import (that module cannot import
# this one) and re-threading five parameters through every call.
_PREFLIGHT_CTX = toolchain_path_prepend.Context(
    resolve_fn=resolve,
    parse_fn=parse_store_executable,
    rewrite_argv_fn=rewrite_argv,
    with_default_path_fn=toolchain_env.with_default_path,
    resolved_tool_cls=ResolvedTool,
    blocked_reason_cls=BlockedReason,
)


def resolve_for_preflight(
    tool: Mapping[str, Any],
    env: Mapping[str, str],
    lock: Mapping[str, Any],
    candidate_root: Path,
) -> tuple[ResolvedTool | None, tuple[str, ...], dict[str, str], str | None]:
    """Resolve every `store:` reference a tool's preflight touches.

    `candidate_root` is an enforced forbidden root: the store must not
    resolve inside the disposable candidate the check is running against.
    Returns `(resolved_tool, version_argv, env, blocked_reason)`; plain-name
    tools pass through unchanged (`resolved=None, blocked_reason=None`). A
    `BlockedReason` from resolving ANY distinct ref blocks the whole
    preflight -- a version probe never falls back to searching `PATH` for a
    store engine that failed to resolve.

    `tool["path_prepend"]` (a tuple of `store:<bundle>/bin`-shaped refs, e.g.
    `test.bats`'s `["store:project-env/bin", "store:node/bin"]`) names extra
    bundles whose bin dirs go FIRST on the resolved PATH -- ahead of the
    tool's own bin dir and the OS baseline PATH (Correction 17) -- so a check
    body that shells out to `python3`/`node` from a nested interpreter (bats
    scripts) reaches the store's interpreter, never an ambient impostor.
    """
    refs = toolchain_path_prepend.store_refs(tool, parse_store_executable)
    path_prepend = tuple(tool.get("path_prepend", ()))
    if not refs and not path_prepend:
        version_argv = resolve_interpreter_argv(tuple(tool["version_argv"]))
        return None, version_argv, env, None
    try:
        store = store_root(env, candidate_root)
    except UnsafeStoreLocationError as error:
        return None, (), env, f"toolchain: {error}"
    platform = current_platform()
    inputs = toolchain_path_prepend.ResolutionInputs(
        lock, store, platform, candidate_root
    )
    engine_outcome = toolchain_path_prepend.resolve_engine_refs(
        tool, _PREFLIGHT_CTX, inputs
    )
    if isinstance(engine_outcome, BlockedReason):
        return None, (), env, engine_outcome.reason
    merged, version_argv = engine_outcome
    if path_prepend:
        prepend_outcome = toolchain_path_prepend.resolve_dirs(
            path_prepend, _PREFLIGHT_CTX, inputs
        )
        if isinstance(prepend_outcome, BlockedReason):
            return None, (), env, prepend_outcome.reason
        merged = toolchain_path_prepend.with_prepend(
            merged, prepend_outcome, ResolvedTool
        )
    version_argv = resolve_interpreter_argv(version_argv)
    return merged, version_argv, resolved_env(env, merged), None

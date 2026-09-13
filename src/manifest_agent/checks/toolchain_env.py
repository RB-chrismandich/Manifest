"""Trust-anchor and launcher verification for materialized environments."""

from __future__ import annotations

import os
import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from .toolchain_cache import OS_BASELINE_PATH
from .toolchain_env_digest import (
    distribution_set_digest,
)
from .toolchain_env_digest import (
    external_python_identity as _external_python_identity,
)
from .toolchain_env_digest import (
    is_python_launcher_role as _is_python_launcher_role,
)
from .toolchain_pth import EnvTrust, UntrustedPthError

# UntrustedPthError re-exported: `toolchain.py` and tests import it from
# here rather than reaching into the `.pth`-normalization module directly.


class LauncherError(ValueError):
    """A console script's on-disk shape could not be read or understood."""


@dataclass(frozen=True)
class ResolvedTool:
    """A store-resolved, hash-verified executable ready to run."""

    bundle: str
    executable: Path
    interpreter: Path | None
    path_entries: tuple[Path, ...]
    tool_sha256: str


@dataclass(frozen=True)
class BlockedReason:
    """A distinct, human-readable reason a tool could not be resolved."""

    reason: str


@dataclass(frozen=True)
class LauncherTarget:
    """Where a console script runs from, and whether that path already went
    through real filesystem symlink resolution (`os.path.realpath`) or is
    still the literal path text materialization wrote (a `#!` shebang, or
    the script itself).

    `env_interpreter_name` is set for the `#!/usr/bin/env <name>` shape --
    `npm ci`'s own generated launchers for pure-JS packages use it (e.g.
    `markdownlint-cli2-bin.mjs`) rather than an absolute interpreter path.
    `env` itself resolves `<name>` via `PATH` at run time, so the literal
    shebang text is neither "inside the store" nor "outside" it -- whether
    this is trustworthy depends on what `PATH` the caller puts `<name>` on,
    not on the shebang text itself. `path` is still populated (as
    `/usr/bin/env`, or wherever it literally says) for callers that do not
    special-case this shape."""

    path: Path
    filesystem_resolved: bool
    env_interpreter_name: str | None = None


_ENV_SHEBANG_PREFIXES = ("/usr/bin/env ", "/bin/env ")

# `#!/bin/sh` launchers pip/uv emit when the REAL interpreter's absolute
# path is too long for the OS shebang-line limit (~127 bytes on Linux) --
# a polyglot: valid `sh` (the `'''exec' ... ' '''` re-execs the real
# interpreter) AND valid Python (that same text is a triple-quoted string
# literal the interpreter's own parser skips over). Store paths under a
# deeply nested temp dir (CI runners, `pytest`'s `tmp_path`, some `XDG_*`
# layouts) push `<env_root>/bin/python` past that limit reliably enough
# that this shape is not a corner case -- C7h found it FAILING closed
# (interpreted as a launcher escaping the store, "digest mismatch") the
# first time a `config-env` store happened to live under a long path.
_LONG_SHEBANG_TRAMPOLINE = re.compile(r"""^'''exec' '(?P<path>[^']+)' "\$0" "\$@"$""")


def _trampoline_interpreter(exe_path: Path) -> str | None:
    """The real interpreter path inside a `#!/bin/sh` long-shebang
    trampoline's second line, or `None` if `exe_path` is not that shape."""
    try:
        with open(exe_path, encoding="utf-8", errors="replace") as stream:
            stream.readline()  # the `#!/bin/sh` line itself
            second_line = stream.readline().strip()
    except OSError:
        return None
    match = _LONG_SHEBANG_TRAMPOLINE.match(second_line)
    return match.group("path") if match else None


def launcher_target(exe_path: Path) -> LauncherTarget | None:
    """Where a console script actually runs from: a symlink target, the
    interpreter named on a `#!` shebang line (including the `#!/bin/sh`
    long-shebang trampoline shape above), or -- a self-contained binary
    with neither, e.g. ruff's own compiled executable -- itself. `None` only
    when the file could not be read at all; callers must treat that as
    untrusted, never as "no opinion"."""
    if exe_path.is_symlink():
        return LauncherTarget(Path(os.path.realpath(exe_path)), True)
    try:
        with open(exe_path, "rb") as stream:
            head = stream.read(2)
            if head != b"#!":
                return LauncherTarget(exe_path, False)
            stream.seek(0)
            first_line = stream.readline().decode("utf-8", "replace").strip()
    except OSError:
        return None
    shebang = first_line[2:].strip()
    if shebang in ("/bin/sh", "/bin/bash"):
        trampoline_path = _trampoline_interpreter(exe_path)
        if trampoline_path:
            return LauncherTarget(Path(trampoline_path), False)
    for prefix in _ENV_SHEBANG_PREFIXES:
        if shebang.startswith(prefix):
            name = shebang[len(prefix) :].split()[0] if shebang[len(prefix) :] else ""
            if name:
                return LauncherTarget(Path(prefix.strip()), False, name)
    target = shebang.split()[0] if shebang.split() else ""
    return LauncherTarget(Path(target), False) if target else None


def launcher_inside_store(target: LauncherTarget | None, store: Path) -> bool:
    """Whether a launcher target lives inside `store` -- a launcher pointing
    anywhere else (a system interpreter, a dev checkout, `/usr/bin`) is
    exactly the swap this check exists to catch.

    A real symlink target (`filesystem_resolved`) is compared against the
    filesystem-resolved store, so a store path itself reached through a
    symlinked temp dir (e.g. macOS `/tmp` -> `/private/tmp`) still matches.
    A `#!`-shebang path is compared lexically (`os.path.normpath`, no
    `Path.resolve()`): it is already the literal absolute path
    materialization wrote, e.g. `<env_root>/bin/python`. The `bin/python`
    symlink is separately bound to the current trusted Python provider at
    the path-resolution boundary; resolving this ordinary console script's
    shebang here would instead follow that symlink outward and falsely flag
    every normal script (`ruff`, `pytest`, ...) that merely uses it.
    """
    if target is None:
        return False
    if target.filesystem_resolved:
        resolved_store = Path(os.path.realpath(store))
        return target.path == resolved_store or target.path.is_relative_to(
            resolved_store
        )
    normalized_target = Path(os.path.normpath(str(target.path)))
    normalized_store = Path(os.path.normpath(str(store)))
    return normalized_target == normalized_store or normalized_target.is_relative_to(
        normalized_store
    )


def expected_exe_sha256(
    bundle: str, relative: str, platform_entry: Mapping | None
) -> str | None:
    """The lock's trust anchor for `relative` inside `bundle`.

    The default -- every `python-env`/`node-env` console script, and a
    `binary` kind's own `bin/<bundle>`, plus any fixture that reuses a
    `binary`-shaped lock entry under a non-matching bundle name -- is the
    platform entry's single `exe_sha256`, unchanged. The ONLY divergence: a
    `relative` that names a declared `extra_executables` entry (e.g. `node`'s
    `bin/npm`, never `bin/<bundle>` itself) is verified against THAT entry's
    own `exe_sha256`, never the primary tool's."""
    if platform_entry is None:
        return None
    name = relative.removeprefix("bin/")
    extra = (platform_entry.get("extra_executables") or {}).get(name)
    if extra is not None and relative != f"bin/{bundle}":
        return extra.get("exe_sha256")
    return platform_entry.get("exe_sha256")


def _not_provisioned(bundle: str) -> BlockedReason:
    return BlockedReason(
        f"toolchain: {bundle} not provisioned (run manifest provision)"
    )


def _checked_relative_path(
    store: Path, relative_path: str, *, allow_external_python: bool = False
) -> Path | None:
    """Return a regular store-contained file, resolving links before trust.

    The sole exception is the Python environment's own `bin/python*`
    launcher. A venv deliberately links it to the interpreter executing this
    process; its resolved provider identity is attested here at the first
    path boundary. All other link escapes are rejected.
    """
    if not relative_path or Path(relative_path).is_absolute():
        return None
    if ".." in Path(relative_path).parts:
        return None
    root = store.resolve(strict=False)
    logical_path = store / relative_path
    try:
        candidate = logical_path.resolve(strict=True)
    except OSError:
        return None
    if candidate.is_relative_to(root) and candidate.is_file():
        # Keep the verified logical launcher path: venv `bin/python` and npm's
        # `.bin/*` scripts calculate their environment from this layout.
        return logical_path
    relative_parts = Path(relative_path).parts
    if (
        allow_external_python
        and len(relative_parts) >= 2
        and _is_python_launcher_role("/".join(relative_parts[-2:]))
    ):
        try:
            _external_python_identity(candidate)
        except (OSError, ValueError):
            return None
        return logical_path
    return None


def with_default_path(bin_dirs: tuple[Path, ...]) -> tuple[Path, ...]:
    """De-duplicated bin dirs, plus the OS baseline PATH (Correction 17;
    `/usr/bin`, `/bin`, `/usr/sbin`, `/sbin`) -- never the caller's PATH."""
    path_entries = tuple(dict.fromkeys(bin_dirs))
    return path_entries + tuple(Path(part) for part in OS_BASELINE_PATH)


def _env_digest(
    bundle: str, exe_path: Path, kind: str, exe_sha256: str, env_trust: EnvTrust
):
    """Steps (b): the distribution-set digest, computed and compared. Returns
    the digest on success, or a `BlockedReason`: untrusted `.pth` content
    (Correction 9) is distinct from never-provisioned -- there IS something
    there, it just cannot be trusted -- so it is checked first."""
    # python-env console scripts sit at `<env_root>/bin/NAME` (2 segments);
    # node-env's are npm's own `<env_root>/node_modules/.bin/NAME` (3).
    env_root = (
        exe_path.parent.parent
        if kind == "python-env"
        else exe_path.parent.parent.parent
    )
    try:
        digest = distribution_set_digest(
            env_root,
            kind,
            store=env_trust.store,
            checkout_root=env_trust.repo_root,
        )
    except UntrustedPthError:
        return BlockedReason(f"toolchain: {bundle} untrusted .pth")
    except (OSError, ValueError):
        return _not_provisioned(bundle)
    if digest != exe_sha256:
        return BlockedReason(f"toolchain: {bundle} digest mismatch")
    return digest


def _launcher_ok(kind: str, target, store: Path) -> bool:
    """Validate a console script after its file path has been contained."""
    if kind == "node-env" and target is not None and target.env_interpreter_name:
        return True
    return launcher_inside_store(target, store)


def _is_environment_python_launcher(exe_path: Path) -> bool:
    return _is_python_launcher_role(
        exe_path.relative_to(exe_path.parent.parent).as_posix()
    )


def verify_env_exe(
    bundle: str,
    kind: str,
    exe_info: Mapping,
    env_trust: EnvTrust,
    exe_sha256: str,
    node_result: ResolvedTool | BlockedReason | None,
):
    """`python-env`/`node-env` trust anchor (Correction 3, rule 3): `exe_sha256`
    is the digest of the *installed distribution set*, not of this one
    console script's bytes -- its bytes embed an absolute, store-location-
    dependent interpreter path and can never match a committed lock. Verifies
    (b) the distribution-set digest, (c) the requested console script exists,
    and (d) its launcher resolves to somewhere inside `env_trust.store` -- a
    launcher pointing anywhere else is `digest mismatch`, same as a swapped
    binary.

    Every `node-env` console script gets the store's `store:node/bin/node`
    as its `interpreter`, unconditionally -- most of npm's own generated
    `node_modules/.bin/*` launchers ultimately exec via `#!/usr/bin/env
    node`, which is the OS's shebang mechanism, not something this function
    inspects at rest: without `node`'s bin dir first on the child `PATH`,
    that exec fails with "no such file" regardless of how the launcher
    itself verified. `node_result` is the caller's ALREADY-resolved
    `store:node/bin/node` -- resolving it here would need
    `toolchain.resolve()` itself, which would import this module back and
    create a cycle.
    """
    store = env_trust.store
    exe_path = _checked_relative_path(
        store,
        exe_info.get("path", ""),
        allow_external_python=kind == "python-env",
    )
    if exe_path is None:
        return _not_provisioned(bundle)
    digest = _env_digest(bundle, exe_path, kind, exe_sha256, env_trust)
    if isinstance(digest, BlockedReason):
        return digest
    # The environment's own `bin/python*` launcher is the only allowed
    # external interpreter symlink. `_checked_relative_path()` has already
    # verified it resolves to this process's trusted provider and bound its
    # byte+mode identity before this digest check.
    if kind == "python-env" and _is_environment_python_launcher(exe_path):
        return ResolvedTool(
            bundle, exe_path, None, with_default_path((exe_path.parent,)), digest
        )
    if kind == "node-env" and (
        isinstance(node_result, BlockedReason) or node_result is None
    ):
        return node_result or _not_provisioned("node")
    target = launcher_target(exe_path)
    if not _launcher_ok(kind, target, store):
        return BlockedReason(f"toolchain: {bundle} digest mismatch")
    if kind == "node-env":
        entries = with_default_path((exe_path.parent, node_result.executable.parent))
        return ResolvedTool(bundle, exe_path, node_result.executable, entries, digest)
    return ResolvedTool(
        bundle, exe_path, None, with_default_path((exe_path.parent,)), digest
    )

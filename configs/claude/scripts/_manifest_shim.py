"""Shared exec shim for the retired top-level entry points.

Mirrors the check order in ``manifest-cli.sh``: only what the exec path actually
needs, in dependency order, so the first failure names the real cause. uv is not
required to run an already-synced runtime, so its absence is never fatal here.
"""

import os
import sys
import warnings

HELP_FLAGS = ("-h", "--help", "--version", "-V")


def _runtime_root() -> str:
    """Runtime root, honoring MANIFEST_HOME (non-standard installs, fixtures)."""
    override = os.environ.get("MANIFEST_HOME")
    if override:
        return override
    return os.path.expanduser("~/.claude")


def _bootstrap_hint(root: str) -> str:
    """`re-run <clone>/bootstrap.sh` when a stamp records the deploying clone.

    The state-root stamp is read first because it outlives a deleted ~/.claude —
    exactly when the hint matters most.
    """
    state_root = os.environ.get("MANIFEST_STATE_ROOT") or os.path.expanduser(
        "~/.manifest"
    )
    for stamp in (
        os.path.join(state_root, "runtime.env"),
        os.path.join(root, "config", "deploy_stamp"),
    ):
        try:
            with open(stamp, encoding="utf-8") as fh:
                lines = fh.read().splitlines()
        except OSError:
            continue
        for line in lines:
            if line.startswith("clone_path="):
                clone = line.partition("=")[2].strip()
                if clone and os.path.isdir(clone):
                    return f"re-run {os.path.join(clone, 'bootstrap.sh')}"
    return "re-run ./bootstrap.sh"


def _resolve_runtime(root: str) -> tuple[str | None, str | None]:
    """Return (manifest_bin, error). Exactly one is None."""
    manifest_bin = os.path.join(root, ".venv", "bin", "manifest")
    hint = _bootstrap_hint(root)
    if not os.path.isdir(root):
        return None, f"home runtime not installed — {root} is missing; {hint}"
    if not os.path.exists(manifest_bin):
        if not os.path.isdir(os.path.join(root, ".venv")):
            return (
                None,
                f"home runtime not installed — no venv at "
                f"{os.path.join(root, '.venv')}; {hint}",
            )
        return None, f"home runtime incomplete — {manifest_bin} is missing; {hint}"
    if not os.access(manifest_bin, os.X_OK):
        return (
            None,
            f"home runtime not executable — {manifest_bin} lost its "
            f"executable bit; {hint}",
        )
    return manifest_bin, None


def exec_manifest(subcommand: str, legacy_name: str) -> None:
    warnings.warn(
        f"{legacy_name} is deprecated; use: manifest {subcommand}",
        DeprecationWarning,
        stacklevel=2,
    )
    root = _runtime_root()
    manifest_bin, error = _resolve_runtime(root)

    # --help/--version must succeed before any runtime/dependency check
    # (repo convention: cli-help-before-dependency-checks). Delegate to the home
    # runtime when present; otherwise emit a deprecation+usage note and exit 0
    # rather than failing the help path in a clean environment.
    wants_help = any(a in HELP_FLAGS for a in sys.argv[1:])
    if wants_help and manifest_bin is None:
        print(
            f"{legacy_name} is a deprecated shim for `manifest {subcommand}`. "
            f"Install the home runtime (./bootstrap.sh), then run "
            f"`manifest {subcommand} --help`."
        )
        raise SystemExit(0)

    if manifest_bin is None:
        print(f"{legacy_name}: {error}", file=sys.stderr)
        raise SystemExit(1)

    argv = ["manifest", *subcommand.split(), *sys.argv[1:]]
    try:
        os.execv(manifest_bin, argv)
    except OSError as exc:
        # Reached when the runtime files exist but cannot be run: interpreter
        # upgraded away, venv copied from another home (stale absolute shebang),
        # wrong architecture, noexec mount. A traceback here buries the fix.
        print(
            f"{legacy_name}: could not start the home runtime "
            f"({manifest_bin}): {exc}; {_bootstrap_hint(root)}",
            file=sys.stderr,
        )
        raise SystemExit(1) from exc

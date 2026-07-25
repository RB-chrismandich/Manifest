import os
import shutil
import sys
import warnings


def exec_manifest(subcommand: str, legacy_name: str) -> None:
    warnings.warn(
        f"{legacy_name} is deprecated; use: manifest {subcommand}",
        DeprecationWarning,
        stacklevel=2,
    )
    manifest_bin = os.path.expanduser("~/.claude/.venv/bin/manifest")
    # --help/--version must succeed before any runtime/dependency check
    # (repo convention: cli-help-before-dependency-checks). Delegate to the home
    # runtime when present; otherwise emit a deprecation+usage note and exit 0
    # rather than failing the help path in a clean environment.
    if any(a in ("-h", "--help", "--version", "-V") for a in sys.argv[1:]):
        if os.path.isfile(manifest_bin):
            os.execv(manifest_bin, ["manifest", *subcommand.split(), *sys.argv[1:]])
        print(
            f"Usage: manifest {subcommand} [options]\n\n"
            f"{legacy_name} is a deprecated shim for `manifest {subcommand}`. "
            f"Install the home runtime (./bootstrap.sh), then run "
            f"`manifest {subcommand} --help` for full usage."
        )
        raise SystemExit(0)
    if not shutil.which("uv") and not os.path.isfile(
        os.path.expanduser("~/.local/bin/uv")
    ):
        print(f"{legacy_name}: uv not found — re-run ./bootstrap.sh", file=sys.stderr)
        raise SystemExit(1)
    if not os.path.isfile(manifest_bin):
        print(
            f"{legacy_name}: home runtime not installed — re-run ./bootstrap.sh",
            file=sys.stderr,
        )
        raise SystemExit(1)
    os.execv(manifest_bin, ["manifest", *subcommand.split(), *sys.argv[1:]])

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
    if not shutil.which("uv") and not os.path.isfile(
        os.path.expanduser("~/.local/bin/uv")
    ):
        print("parallel_agent.py: uv not found — re-run ./bootstrap.sh", file=sys.stderr)
        raise SystemExit(1)
    manifest_bin = os.path.expanduser("~/.claude/.venv/bin/manifest")
    if not os.path.isfile(manifest_bin):
        print(f"{legacy_name}: home runtime not installed — re-run ./bootstrap.sh", file=sys.stderr)
        raise SystemExit(1)
    os.execv(manifest_bin, ["manifest", *subcommand.split(), *sys.argv[1:]])

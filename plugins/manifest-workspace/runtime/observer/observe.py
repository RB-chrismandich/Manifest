#!/usr/bin/env python3
"""Validate an installed observer before launching its authorized interpreter."""

from __future__ import annotations

import argparse
import importlib
import os
import subprocess
import sys
from pathlib import Path

sys.dont_write_bytecode = True

resolve_observer_runtime = importlib.import_module(
    "observer_runtime_identity"
).resolve_observer_runtime


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--receipt", type=Path)
    parser.add_argument("--source-root", type=Path)
    args = parser.parse_args(argv)
    receipt = (
        args.receipt
        or Path(os.environ.get("XDG_STATE_HOME") or Path.home() / ".local/state")
        / "manifest/installation.json"
    )
    bundle = Path(__file__).resolve().parents[2]
    try:
        interpreter = resolve_observer_runtime(
            bundle, receipt_path=receipt, environ=os.environ
        )
        command = [
            str(interpreter),
            "-I",
            "-B",
            "-c",
            "from manifest_agent.cli import observe_native; observe_native()",
            "--json",
            "--receipt",
            str(receipt.absolute()),
        ]
        if args.source_root is not None:
            command.extend(("--source-root", str(args.source_root.absolute())))
        completed = subprocess.run(command, check=False, timeout=30)
        return completed.returncode
    except (
        OSError,
        ValueError,
        KeyError,
        TypeError,
        subprocess.SubprocessError,
    ) as error:
        print(
            f"native observer unavailable; run authorized install/update: {error}",
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

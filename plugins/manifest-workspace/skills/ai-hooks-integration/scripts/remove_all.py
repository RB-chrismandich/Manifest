#!/usr/bin/env python3
"""Remove a hook command from Claude/Gemini/Cursor and delete an OpenCode plugin.

Usage:
  remove_all.py --command "<hook-cmd>" --plugin ~/.config/opencode/plugins/<name>.js
"""

import argparse
import subprocess
from pathlib import Path

from runtime.tool_config import get_default_path

ROOT = Path(__file__).resolve().parent
REMOVE = ROOT / "remove_hooks.py"
REMOVE_PLUGIN = ROOT / "remove_opencode_plugin.py"


def run(cmd: list[str]) -> None:
    subprocess.run(cmd, check=True)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--command", required=True)
    ap.add_argument("--plugin", required=True)
    ap.add_argument(
        "--dry-run", action="store_true", help="Print actions without writing"
    )
    args = ap.parse_args()
    dry = ["--dry-run"] if args.dry_run else []
    owner = ["--owner", f"manifest:{Path(args.plugin).stem}"]

    run(
        [
            str(REMOVE),
            "--tool",
            "claude",
            "--path",
            str(get_default_path("claude")),
            "--command",
            args.command,
            *owner,
            *dry,
        ]
    )

    run(
        [
            str(REMOVE),
            "--tool",
            "gemini",
            "--path",
            str(get_default_path("gemini")),
            "--command",
            args.command,
            *owner,
            *dry,
        ]
    )

    run(
        [
            str(REMOVE),
            "--tool",
            "cursor",
            "--path",
            str(get_default_path("cursor")),
            "--command",
            args.command,
            *owner,
            *dry,
        ]
    )

    run([str(REMOVE_PLUGIN), "--path", str(Path(args.plugin).expanduser()), *dry])


if __name__ == "__main__":
    main()

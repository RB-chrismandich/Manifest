#!/usr/bin/env python3
"""Install the same hook command across Claude/Gemini/Cursor and write OpenCode plugin.

Usage:
  install_all.py --command "/abs/path/to/hook" --name my-hook

  # Unified mode (recommended): Uses unified_hook.py with automatic source detection
  install_all.py --unified --handler "/abs/path/to/handler" --name my-hook

Notes:
  - Adds tool-specific suffixes: --claude/--gemini/--cursor
  - Writes OpenCode plugin to ~/.config/opencode/plugins/<name>.js
  - Unified mode automatically detects the actual source tool and filters noise events
"""

import argparse
import subprocess
import sys
from pathlib import Path

from runtime.tool_config import get_default_path

ROOT = Path(__file__).resolve().parent
MERGE = ROOT / "merge_hooks.py"
UNIFIED_HOOK = ROOT / "runtime" / "unified_hook.py"
OPENCODE_INSTALLER = ROOT / "install_opencode_plugin.py"


# The four targets are independent files owned by different tools, so one
# tool's problem must not decide whether the others get their hook. That only
# started to matter once merge_hooks began exiting non-zero on a config it could
# not parse (previously it "succeeded" by truncating the file): a bare
# check=True aborts partway, leaving some tools installed and some not, and
# buries the child's actionable message under a CalledProcessError traceback.
# Every target is attempted; the run then fails once, naming all of them.
_FAILURES: list[str] = []


def run(cmd: list[str], label: str | None = None) -> bool:
    """Attempt one installer step. Records a failure instead of raising."""
    try:
        subprocess.run(cmd, check=True)
    except subprocess.CalledProcessError as exc:
        _FAILURES.append(f"{label or Path(cmd[0]).name} (exit {exc.returncode})")
        return False
    return True


def report_failures() -> None:
    """Exit non-zero naming every target that failed, once all were attempted."""
    if not _FAILURES:
        return
    raise SystemExit(
        "install_all: failed for "
        + ", ".join(_FAILURES)
        + " — see the message printed above each one for the file to fix. "
        "The remaining targets were installed."
    )


def ownership_args(name: str) -> list[str]:
    """Return metadata marking a hook entry as Manifest-owned."""
    return ["--owner", f"manifest:{name}"]


def install_unified(args) -> None:
    """Install unified hook with automatic source detection."""
    dry = ["--dry-run"] if args.dry_run else []
    ownership = ["--owner", f"manifest:{args.name}"]

    # Build the unified hook command.
    # -B is load-bearing, not cosmetic: the runtime lives inside the
    # apm-managed skills tree, so bytecode written next to the source is a file
    # apm did not place. apm then refuses to remove or replace the skill, and a
    # hook that fires every tool call re-creates __pycache__ every session —
    # deleting it does not stick, only not writing it does.
    unified_cmd = f"{sys.executable} -B {UNIFIED_HOOK}"
    if args.handler:
        unified_cmd += f" --handler {args.handler}"

    # Install for Claude (unified hook handles source detection)
    run(
        [
            str(MERGE),
            "--tool",
            "claude",
            "--path",
            str(get_default_path("claude")),
            "--command",
            f"{unified_cmd} --source claude",
            *ownership,
            *dry,
        ],
        "claude",
    )

    # Install for Gemini
    run(
        [
            str(MERGE),
            "--tool",
            "gemini",
            "--path",
            str(get_default_path("gemini")),
            "--command",
            f"{unified_cmd} --source gemini",
            *ownership,
            *dry,
        ],
        "gemini",
    )

    # Install for Cursor
    run(
        [
            str(MERGE),
            "--tool",
            "cursor",
            "--path",
            str(get_default_path("cursor")),
            "--command",
            f"{unified_cmd} --source cursor",
            *ownership,
            *dry,
        ],
        "cursor",
    )

    # Install OpenCode advanced plugin (has its own source detection)
    run(
        [
            str(OPENCODE_INSTALLER),
            "--name",
            args.name,
            "--output",
            str(get_default_path("opencode")),
            "--advanced",
        ]
        + (["--force"] if args.force else [])
        + dry,
        "opencode",
    )


def install_classic(args) -> None:
    """Install classic hooks with tool-specific suffixes."""
    cmd = args.command
    dry = ["--dry-run"] if args.dry_run else []

    run(
        [
            str(MERGE),
            "--tool",
            "claude",
            "--path",
            str(get_default_path("claude")),
            "--command",
            f"{cmd} --claude",
            *ownership_args(args.name),
            *dry,
        ],
        "claude",
    )
    run(
        [
            str(MERGE),
            "--tool",
            "gemini",
            "--path",
            str(get_default_path("gemini")),
            "--command",
            f"{cmd} --gemini",
            *ownership_args(args.name),
            *dry,
        ],
        "gemini",
    )
    run(
        [
            str(MERGE),
            "--tool",
            "cursor",
            "--path",
            str(get_default_path("cursor")),
            "--command",
            f"{cmd} --cursor",
            *ownership_args(args.name),
            *dry,
        ],
        "cursor",
    )

    run(
        [
            str(MERGE),
            "--tool",
            "opencode",
            "--path",
            str(get_default_path("opencode") / f"{args.name}.js"),
            *dry,
        ],
        "opencode",
    )


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Install hooks across all AI tools",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Classic mode (explicit source via suffixes)
  install_all.py --command "/path/to/hook" --name my-hook

  # Unified mode (recommended - automatic source detection)
  install_all.py --unified --handler "/path/to/handler" --name my-hook

  # Unified mode without handler (just normalization and filtering)
  install_all.py --unified --name my-hook
""",
    )
    ap.add_argument("--command", help="Base hook command (classic mode)")
    ap.add_argument(
        "--name", required=True, help="OpenCode plugin filename without extension"
    )
    ap.add_argument(
        "--dry-run", action="store_true", help="Print actions without writing"
    )
    ap.add_argument(
        "--unified",
        action="store_true",
        help="Use unified hook with automatic source detection (recommended)",
    )
    ap.add_argument(
        "--handler",
        help="Handler script path (unified mode only, receives normalized events)",
    )
    ap.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing OpenCode plugin file",
    )
    args = ap.parse_args()

    if args.unified:
        install_unified(args)
    else:
        if not args.command:
            raise SystemExit("--command is required in classic mode (or use --unified)")
        install_classic(args)
    report_failures()


if __name__ == "__main__":
    main()

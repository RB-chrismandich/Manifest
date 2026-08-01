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


def install_unified(args) -> None:
    """Install unified hook with automatic source detection."""
    dry = ["--dry-run"] if args.dry_run else []

    # Build the unified hook command. Skill storage has moved three times in
    # ~5 weeks (bootstrap copy -> apm-managed ~/.manifest/skills -> plugin
    # bundles, PR #685) and each move broke a settings.json hook command that
    # hardcoded THIS script's own install-time absolute path, taking every
    # Bash tool call down (specs/674-plugin-architecture/cutover-plan.md
    # T4.3). Route through the stable dispatcher instead: it lives at
    # ~/.claude/scripts/, deployed by bootstrap.sh and untouched by
    # skill/plugin churn, and resolves the real unified_hook.py + handler
    # locations at fire-time. Only applies to the default (pr-monitor)
    # handler it knows about -- a caller-supplied --handler path is still a
    # raw absolute path today, no more or less fragile than before this fix.
    if args.handler:
        unified_cmd = f"{sys.executable} -B {UNIFIED_HOOK} --handler {args.handler}"
    else:
        unified_cmd = str(Path("~/.claude/scripts/hook_dispatch.py").expanduser())

    # Install for Claude (unified hook handles source detection)
    run(
        [
            str(MERGE),
            "--tool",
            "claude",
            "--path",
            str(Path("~/.claude/settings.json").expanduser()),
            "--command",
            f"{unified_cmd} --source claude",
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
            str(Path("~/.gemini/settings.json").expanduser()),
            "--command",
            f"{unified_cmd} --source gemini",
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
            str(Path("~/.cursor/hooks.json").expanduser()),
            "--command",
            f"{unified_cmd} --source cursor",
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
            str(Path("~/.config/opencode/plugins").expanduser()),
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
            str(Path("~/.claude/settings.json").expanduser()),
            "--command",
            f"{cmd} --claude",
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
            str(Path("~/.gemini/settings.json").expanduser()),
            "--command",
            f"{cmd} --gemini",
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
            str(Path("~/.cursor/hooks.json").expanduser()),
            "--command",
            f"{cmd} --cursor",
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
            str(Path("~/.config/opencode/plugins").expanduser() / f"{args.name}.js"),
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

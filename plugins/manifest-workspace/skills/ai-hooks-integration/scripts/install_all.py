#!/usr/bin/env python3
"""Install the same hook command across Claude/Gemini/Cursor and write OpenCode plugin.

Usage:
  install_all.py --command "/abs/path/to/hook" --name my-hook

  # Unified mode (recommended): Uses unified_hook.py with automatic source detection
  install_all.py --unified --handler "/abs/path/to/handler" --name my-hook

  # Unified mode with the built-in default handler (pr-monitor), routed
  # through the stable dispatcher so the installed command never goes stale:
  install_all.py --unified --default-handler --name pr-monitor

Notes:
  - Adds tool-specific suffixes: --claude/--gemini/--cursor
  - Writes OpenCode plugin to ~/.config/opencode/plugins/<name>.js
  - Unified mode automatically detects the actual source tool and filters noise events
  - --unified with neither --handler nor --default-handler: normalization/filtering
    only, no handler dispatch -- the original unified-mode behavior
"""

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
MERGE = ROOT / "merge_hooks.py"
REMOVE = ROOT / "remove_hooks.py"
UNIFIED_HOOK = ROOT / "runtime" / "unified_hook.py"
OPENCODE_INSTALLER = ROOT / "install_opencode_plugin.py"
DISPATCHER = Path("~/.claude/scripts/hook_dispatch.py").expanduser()
JSON_CONFIG_TARGETS = [
    ("claude", "~/.claude/settings.json"),
    ("gemini", "~/.gemini/settings.json"),
    ("cursor", "~/.cursor/hooks.json"),
]


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


def _merge_json_hook_for_each_tool(command_for, dry: list[str]) -> None:
    """Install `command_for(tool)` into claude/gemini/cursor's hook config."""
    for tool, path in JSON_CONFIG_TARGETS:
        run(
            [
                str(MERGE),
                "--tool",
                tool,
                "--path",
                str(Path(path).expanduser()),
                "--command",
                command_for(tool),
                *dry,
            ],
            tool,
        )


def _strip_legacy_unified_entries(dry: list[str]) -> None:
    """Remove any pre-existing raw unified_hook.py command before installing
    the new one. Skill storage has moved three times in ~5 weeks (bootstrap
    copy -> apm-managed ~/.manifest/skills -> plugin bundles, PR #685), and
    each move broke a settings.json command hardcoding THIS script's own
    install-time absolute path (specs/674-plugin-architecture/cutover-plan.md
    T4.3). Re-running this installer after that fix would otherwise leave the
    old, permanently-broken entry running alongside the new stable one: both
    fire on every matching event, and the dead one alone is enough to block
    the tool call.
    """
    for tool, path in JSON_CONFIG_TARGETS:
        run(
            [
                str(REMOVE),
                "--tool",
                tool,
                "--path",
                str(Path(path).expanduser()),
                "--command",
                "unified_hook.py",
                *dry,
            ],
            f"{tool}-legacy-cleanup",
        )


def _build_unified_command(args) -> str:
    """The command line written into each tool's hook config.

    --default-handler routes through the stable dispatcher at
    ~/.claude/scripts/ (bootstrap-deployed, untouched by skill/plugin churn),
    which resolves the real unified_hook.py + handler locations at fire-time
    instead of baking in an install-time path. It only knows the one
    integration built into it today (pr-monitor) -- a caller-supplied
    --handler path still gets the old self-referential command, no more or
    less fragile than before this fix. Neither flag: original behavior,
    normalization/filtering with no handler at all.
    """
    if args.handler:
        return f"{sys.executable} -B {UNIFIED_HOOK} --handler {args.handler}"
    if not args.default_handler:
        return f"{sys.executable} -B {UNIFIED_HOOK}"
    if not DISPATCHER.is_file():
        raise SystemExit(
            "install_all: --default-handler needs the stable dispatcher at "
            f"{DISPATCHER}, which does not exist yet. Run ./bootstrap.sh first "
            "(it deploys configs/claude/scripts/ to ~/.claude/scripts/), then "
            "re-run this installer -- writing a hook command that points at a "
            "file that doesn't exist would reproduce the exact outage this "
            "fix exists to prevent."
        )
    return str(DISPATCHER)


def install_unified(args) -> None:
    """Install unified hook with automatic source detection."""
    dry = ["--dry-run"] if args.dry_run else []
    _strip_legacy_unified_entries(dry)
    unified_cmd = _build_unified_command(args)

    _merge_json_hook_for_each_tool(lambda tool: f"{unified_cmd} --source {tool}", dry)

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

    _merge_json_hook_for_each_tool(lambda tool: f"{cmd} --{tool}", dry)

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

  # Unified mode with the built-in default handler (pr-monitor), via the
  # stable dispatcher -- never goes stale when skill storage moves
  install_all.py --unified --default-handler --name pr-monitor
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
        "--default-handler",
        action="store_true",
        help=(
            "Unified mode only, mutually exclusive with --handler: install the "
            "built-in default handler (pr-monitor) via the stable dispatcher "
            "at ~/.claude/scripts/hook_dispatch.py, which resolves the real "
            "script locations at fire-time so the installed command never "
            "goes stale when skill storage moves. Fails if the dispatcher "
            "hasn't been deployed yet (run ./bootstrap.sh first)."
        ),
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

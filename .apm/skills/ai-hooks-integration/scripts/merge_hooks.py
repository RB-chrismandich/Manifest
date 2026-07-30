#!/usr/bin/env python3
"""Merge/inject hooks into Claude/Gemini/Cursor JSON configs (and OpenCode plugin).

Usage:
  merge_hooks.py --tool claude  --path ~/.claude/settings.json --command "<hook-cmd> --claude"
  merge_hooks.py --tool gemini  --path ~/.gemini/settings.json --command "<hook-cmd> --gemini"
  merge_hooks.py --tool cursor  --path ~/.cursor/hooks.json     --command "<hook-cmd> --cursor"
  merge_hooks.py --tool opencode --path ~/.config/opencode/plugins/<name>.js

Behavior:
  - Creates missing parents
  - Avoids duplicates (command contains the provided command string)
  - Writes pretty JSON
  - OpenCode writes a generic ES module template
"""

import argparse
from pathlib import Path

from runtime.tool_config import (
    TOOL_CONFIG,
    ConfigUnreadable,
    get_config,
    has_hook,
    load_json,
    save_json,
)

OPENCODE_TEMPLATE = """\
export const PluginHook = async () => {{
  return {{
    "tool.execute.before": async (input, output) => {{
      try {{
        if (input.tool !== "bash") return;
        const command = output?.args?.command ?? input?.args?.command ?? "";
        if (!command) return;

        const {{ exec }} = await import("child_process");
        const {{ promisify }} = await import("util");
        const execAsync = promisify(exec);

        const hookCmd = `{hook_command}`;
        if (hookCmd) {{
          // Provide command as env var to avoid escaping issues
          await execAsync(hookCmd, {{
            env: {{ ...process.env, OPENCODE_INTERCEPTED_CMD: command }}
          }});
        }}
      }} catch (err) {{
        console.error(`[OpenCode Hook Error]: ${{err.message}}`);
        // Rethrow to actually block execution if the hook failed
        throw err;
      }}
    }}
  }};
}};
"""


def write_opencode_plugin(
    path: Path, force: bool, dry_run: bool, command_to_run: str
) -> None:
    if path.exists() and not force:
        return
    if dry_run:
        print(f"[dry-run] write {path}")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(OPENCODE_TEMPLATE.format(hook_command=command_to_run))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tool", choices=TOOL_CONFIG.keys(), required=True)
    ap.add_argument("--path", required=True)
    ap.add_argument("--command", help="Hook command to inject")
    ap.add_argument("--matcher", help="Override matcher for nested hooks")
    ap.add_argument(
        "--force", action="store_true", help="Overwrite existing plugin file (opencode)"
    )
    ap.add_argument(
        "--dry-run", action="store_true", help="Print actions without writing"
    )
    args = ap.parse_args()

    path = Path(args.path).expanduser()

    if not args.command:
        raise SystemExit("--command is required for all tools")

    if args.tool == "opencode":
        write_opencode_plugin(path, args.force, args.dry_run, args.command)
        return

    cfg = get_config(args.tool)
    # Abort rather than merge into a file we could not parse: the write below
    # replaces the whole file, so proceeding on an "empty" read would delete
    # every setting the user has (permissions, env, model, statusLine, ...).
    try:
        data = load_json(path)
    except ConfigUnreadable as exc:
        raise SystemExit(f"merge_hooks: {exc}") from exc

    if args.tool == "cursor" and "version" not in data:
        data["version"] = cfg.get("version", 1)

    hooks = data.setdefault("hooks", {})
    hook_key = cfg["hook_key"]

    if hook_key not in hooks or not isinstance(hooks[hook_key], list):
        hooks[hook_key] = []

    if has_hook(hooks[hook_key], cfg.get("nested", False), args.command):
        save_json(path, data, args.dry_run)
        return

    matcher = args.matcher if args.matcher is not None else cfg.get("default_matcher")

    if cfg.get("nested", False):
        hooks[hook_key].append(
            {
                "matcher": matcher,
                "hooks": [
                    {
                        "type": "command",
                        "command": args.command,
                    }
                ],
            }
        )
    else:
        hooks[hook_key].append({"command": args.command})

    save_json(path, data, args.dry_run)


if __name__ == "__main__":
    main()

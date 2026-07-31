#!/usr/bin/env python3
"""Install an OpenCode plugin into the plugins directory.

Usage:
  install_opencode_plugin.py --name my-plugin --output ~/.config/opencode/plugins
  install_opencode_plugin.py --name my-plugin --output ~/.config/opencode/plugins --force
  install_opencode_plugin.py --name my-plugin --output ~/.config/opencode/plugins --websocket
  install_opencode_plugin.py --name my-plugin --output ~/.config/opencode/plugins --advanced

Notes:
  - Creates a plugin that exports a function (required by OpenCode)
  - Uses correct hook parameter names (sessionID, callID, tool)
  - Optional WebSocket event support for external integrations
  - Advanced mode: WebSocket + HTTP fallback, session management, idle detection
"""

import argparse
from pathlib import Path

# Templates live beside this script (not the caller's cwd) so they travel
# with it when apm copies this skill to ~/.claude/skills/... .
_TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"


def _load_template(filename: str) -> str:
    """Load a plugin template's source text from templates/<filename>.

    Templates use ``.format()``-style placeholders with ``{{``/``}}``
    escaping for literal braces in the generated JavaScript — callers keep
    using ``.format(...)`` on the returned string exactly as before.
    """
    return (_TEMPLATES_DIR / filename).read_text(encoding="utf-8")


# Basic template - just hooks
TEMPLATE_BASIC = _load_template("opencode_basic.js.tmpl")

# WebSocket template - sends events to external server
TEMPLATE_WEBSOCKET = _load_template("opencode_websocket.js.tmpl")

# Advanced template - WebSocket + HTTP fallback, session management, idle detection
TEMPLATE_ADVANCED = _load_template("opencode_advanced.js.tmpl")


def main() -> None:
    ap = argparse.ArgumentParser(description="Install OpenCode plugin")
    ap.add_argument("--name", required=True, help="Plugin file name without extension")
    ap.add_argument("--output", required=True, help="Plugins directory")
    ap.add_argument("--force", action="store_true", help="Overwrite existing file")
    ap.add_argument(
        "--dry-run", action="store_true", help="Print actions without writing"
    )
    ap.add_argument(
        "--export",
        dest="export_name",
        default="PluginHook",
        help="Exported function name",
    )
    ap.add_argument(
        "--websocket", action="store_true", help="Include WebSocket event sending"
    )
    ap.add_argument(
        "--advanced",
        action="store_true",
        help="Advanced mode: WebSocket + HTTP fallback, session management, idle detection",
    )
    args = ap.parse_args()

    out_dir = Path(args.output).expanduser()
    out_dir.mkdir(parents=True, exist_ok=True)

    plugin_path = out_dir / f"{args.name}.js"
    if plugin_path.exists() and not args.force:
        raise SystemExit(f"File exists: {plugin_path} (use --force to overwrite)")

    if args.advanced:
        template = TEMPLATE_ADVANCED
    elif args.websocket:
        template = TEMPLATE_WEBSOCKET
    else:
        template = TEMPLATE_BASIC
    content = template.format(
        plugin_name=args.name.replace("-", " ").title(),
        export_name=args.export_name,
    )

    if args.dry_run:
        print(f"[dry-run] write {plugin_path}")
        print(content)
        return

    plugin_path.write_text(content)
    print(f"Created: {plugin_path}")


if __name__ == "__main__":
    main()

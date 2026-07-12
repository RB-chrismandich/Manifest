#!/usr/bin/env python3
"""Generate configs/cursor/mcp.json from the shared MCP server registry.

configs/claude/config/mcp_servers.yml is the single source of truth for
Manifest-managed MCP servers (spec 2026-07-11 cursor-feature-parity, WS-1).
Every entry with a `url` key is remote-HTTP and Cursor-eligible under Cursor's
`{"mcpServers": {"<name>": {"url": "<url>"}}}` schema, so this script emits
one Cursor entry per registry server, in registry (YAML document) order.

The committed configs/cursor/mcp.json was previously hand-maintained and
drifted (3 of 9 servers present). This generator is the fix: it is invoked
from generate_cursor_rules.sh so a single command keeps rules + mcp.json in
sync, and CI fails on `git status --porcelain configs/cursor/mcp.json`.

CLI:
    generate_cursor_mcp.py            regenerate configs/cursor/mcp.json
    generate_cursor_mcp.py --dry-run  report would-create/would-update; write nothing
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import yaml

PROG = "generate_cursor_mcp.py"

_REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_REGISTRY = _REPO_ROOT / "configs" / "claude" / "config" / "mcp_servers.yml"
DEFAULT_OUTPUT = _REPO_ROOT / "configs" / "cursor" / "mcp.json"


def err(msg: str) -> None:
    print(f"{PROG}: {msg}", file=sys.stderr)


def load_registry(registry_path: Path) -> dict:
    with registry_path.open(encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    servers = data.get("mcp_servers") or {}
    if not isinstance(servers, dict):
        raise ValueError(f"{registry_path}: mcp_servers must be a mapping")
    return servers


def url_servers(servers: dict) -> dict:
    """Registry entries eligible for Cursor's remote-MCP schema (have a url)."""
    return {
        name: {"url": cfg["url"]}
        for name, cfg in servers.items()
        if isinstance(cfg, dict) and "url" in cfg
    }


def render(mcp_servers: dict) -> str:
    """Cursor remote-MCP schema, stable registry order, trailing newline."""
    return json.dumps({"mcpServers": mcp_servers}, indent=2) + "\n"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog=PROG,
        description="Generate configs/cursor/mcp.json from configs/claude/config/mcp_servers.yml.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="report would-create/would-update without writing",
    )
    parser.add_argument(
        "--registry",
        default=str(DEFAULT_REGISTRY),
        help="path to mcp_servers.yml (default: configs/claude/config/mcp_servers.yml)",
    )
    parser.add_argument(
        "--output",
        default=str(DEFAULT_OUTPUT),
        help="path to write mcp.json (default: configs/cursor/mcp.json)",
    )
    args = parser.parse_args(argv)

    registry_path = Path(args.registry)
    output_path = Path(args.output)

    try:
        servers = load_registry(registry_path)
    except FileNotFoundError:
        err(f"{registry_path}: not found")
        return 2
    except (ValueError, yaml.YAMLError) as exc:
        err(f"{registry_path}: {exc}")
        return 2

    mcp_servers = url_servers(servers)
    content = render(mcp_servers)
    existing = output_path.read_text(encoding="utf-8") if output_path.exists() else None

    if existing == content:
        print(f"Cursor mcp.json: unchanged ({len(mcp_servers)} servers)")
        return 0

    verb = "update" if existing is not None else "create"
    if args.dry_run:
        print(f"[DRY-RUN] Would {verb}: {output_path}")
        print(f"Cursor mcp.json: {len(mcp_servers)} servers, not written (--dry-run)")
        return 0

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(content, encoding="utf-8")
    print(f"Cursor mcp.json: {verb}d ({len(mcp_servers)} servers)")
    return 0


if __name__ == "__main__":
    sys.exit(main())

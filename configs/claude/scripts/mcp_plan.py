#!/usr/bin/env python3
"""mcp_plan.py — emit the MCP-server registration plan for bootstrap.

Reads the repo's MCP definitions, plus any server a user stranded in the inert
``settings.local.json``, plus what is already registered in ``~/.claude.json``,
and prints one TSV row per server:

    <name>\t<http|stdio|present>\t<url-or-argv>

``present`` means already registered — the caller counts it as skipped and does
not shell out. Unreadable inputs yield no rows rather than an error, so a
missing or malformed file degrades to "nothing to do" instead of failing a
deploy.

This lives in a FILE rather than a heredoc inside ``deploy.sh`` on purpose. The
previous version embedded this logic as a quoted heredoc feeding a process
substitution; standalone it worked, but once ``deploy.sh`` was sourced by
bootstrap the body stopped being treated as quoted, bash brace-expanded
``{**a, **b}`` inside the Python, and the parser died with a SyntaxError while
the caller saw zero rows and reported "already registered". A real file has no
quoting edge to get wrong.

Inputs are environment variables so no argv quoting is involved either:
    MCP_SRC     repo definitions (configs/claude/config/mcp_user_servers.json)
    MCP_LEGACY  optional; a settings.local.json whose mcpServers to rescue
    MCP_HOME    optional; ~/.claude.json, read for already-registered names
"""

from __future__ import annotations

import json
import os
import sys

PROG = "mcp_plan.py"


def err(*args: object) -> None:
    print(f"{PROG}:", *args, file=sys.stderr)


def usage() -> None:
    print(
        "Usage: mcp_plan.py            (configured entirely by environment)\n"
        "\n"
        "Prints one TSV row per MCP server: <name>\\t<http|stdio|present>\\t<spec>\n"
        "\n"
        "  MCP_SRC     repo MCP definitions JSON (required)\n"
        "  MCP_LEGACY  settings.local.json whose mcpServers to rescue (optional)\n"
        "  MCP_HOME    ~/.claude.json, read for already-registered names (optional)\n"
        "\n"
        "Unreadable inputs print nothing and exit 0."
    )


def load(path: str | None) -> dict:
    if not path:
        return {}
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def main(argv: list[str]) -> int:
    if argv and argv[0] in ("--help", "-h"):
        usage()
        return 0

    servers = dict(load(os.environ.get("MCP_SRC")))
    # A user who added an MCP server to the (inert) settings.local.json got
    # nothing for it. Register those too rather than silently stranding them; a
    # user entry wins over a repo default of the same name.
    legacy = load(os.environ.get("MCP_LEGACY")).get("mcpServers")
    if isinstance(legacy, dict):
        servers.update(legacy)

    registered = load(os.environ.get("MCP_HOME")).get("mcpServers")
    already = set(registered) if isinstance(registered, dict) else set()

    for name, cfg in servers.items():
        if not isinstance(cfg, dict):
            continue
        if name in already:
            print(f"{name}\tpresent\t")
            continue
        if cfg.get("url"):
            print(f"{name}\thttp\t{cfg['url']}")
        elif cfg.get("command"):
            argv_str = " ".join([cfg["command"], *(cfg.get("args") or [])])
            print(f"{name}\tstdio\t{argv_str}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

#!/usr/bin/env python3
"""tracker_registry.py - read-only resolver for tracker_providers.yml.

Usage:
  tracker_registry.py status <provider> <canonical-status>
  tracker_registry.py access <provider>
  tracker_registry.py default-provider
  tracker_registry.py mcp-tool <provider> <operation>
Exit codes: 0 ok, 1 usage, 2 unknown provider/key.
"""

import sys
from pathlib import Path

import yaml

REG = Path(__file__).resolve().parent.parent / "config" / "tracker_providers.yml"


def die(code, msg):
    print(f"tracker-registry: {msg}", file=sys.stderr)
    sys.exit(code)


def main(argv):
    if len(argv) >= 1 and argv[0] in ("--help", "-h"):
        print(__doc__.strip())
        return 0
    if not argv:
        die(1, "missing subcommand (see --help)")
    try:
        data = yaml.safe_load(REG.read_text())
    except OSError as exc:
        die(2, f"cannot read registry {REG}: {exc}")
    cmd, rest = argv[0], argv[1:]
    if cmd == "default-provider":
        print(data["default_provider"])
        return 0
    if cmd in ("status", "access", "mcp-tool"):
        if not rest:
            die(1, f"{cmd}: missing provider")
        provider = rest[0]
        p = data["providers"].get(provider)
        if p is None:
            die(
                2,
                f"unknown provider: {provider} (known: {', '.join(data['providers'])})",
            )
        if cmd == "access":
            print("\n".join(p["access"]))
            return 0
        if len(rest) < 2:
            die(1, f"{cmd}: missing key")
        key = rest[1]
        table = p["status_map"] if cmd == "status" else p.get("mcp_tools", {})
        if key not in table:
            die(2, f"unknown {cmd} key for {provider}: {key}")
        print(table[key])
        return 0
    die(1, f"unknown subcommand: {cmd}")


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

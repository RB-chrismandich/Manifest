#!/usr/bin/env python3
"""Resolve immutable Forge tracker defaults with optional XDG JSON overlays.

Usage:
  tracker_registry.py dump-registry
  tracker_registry.py status <provider> <canonical-status>
  tracker_registry.py access <provider>
  tracker_registry.py default-provider
  tracker_registry.py mcp-tool <provider> <operation>

Exit codes: 0 ok, 1 usage, 2 invalid registry/provider/key.
"""

from __future__ import annotations

import json
import os
import sys
from copy import deepcopy
from pathlib import Path
from typing import Any

RUNTIME_DIR = Path(__file__).resolve().parent.parent
CONFIG_DIR = RUNTIME_DIR / "config"
KNOWN_PROVIDER_TYPES = frozenset({"github", "gitlab", "linear", "jira"})


def _xdg_config_home() -> Path:
    configured = os.environ.get("XDG_CONFIG_HOME")
    if configured:
        return Path(configured)
    return Path(os.environ.get("HOME", "")) / ".config"


def _merge(base: Any, overlay: Any) -> Any:
    if isinstance(base, dict) and isinstance(overlay, dict):
        merged = deepcopy(base)
        for key, value in overlay.items():
            merged[key] = (
                _merge(merged[key], value) if key in merged else deepcopy(value)
            )
        return merged
    return deepcopy(overlay)


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read JSON config {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"config root must be an object: {path}")
    return value


def load_config(name: str) -> dict[str, Any]:
    """Load a bundled JSON document and merge its XDG overlay if present."""
    bundled = CONFIG_DIR / f"{name}.json"
    data = _read_json(bundled)
    overlay = _xdg_config_home() / "manifest" / "forge" / f"{name}.json"
    if overlay.is_file():
        data = _merge(data, _read_json(overlay))
    return data


def load_registry() -> dict[str, Any]:
    data = load_config("tracker_providers")
    providers = data.get("providers")
    if not isinstance(providers, dict) or not providers:
        raise ValueError("tracker registry requires a non-empty providers object")
    for provider_id, provider in providers.items():
        if not isinstance(provider, dict):
            raise ValueError(f"provider {provider_id} must be an object")
        provider_type = provider.get("type", provider_id)
        if provider_type not in KNOWN_PROVIDER_TYPES:
            raise ValueError(
                f"unknown provider type {provider_type!r} for provider {provider_id!r}"
            )
    default = data.get("default_provider")
    if default not in providers:
        raise ValueError(f"default provider {default!r} is not registered")
    return data


def die(code: int, message: str) -> None:
    print(f"tracker-registry: {message}", file=sys.stderr)
    raise SystemExit(code)


def main(argv: list[str]) -> int:
    if argv and argv[0] in ("--help", "-h"):
        print(__doc__.strip())
        return 0
    if not argv:
        die(1, "missing subcommand (see --help)")
    try:
        data = load_registry()
    except ValueError as exc:
        die(2, str(exc))

    command, rest = argv[0], argv[1:]
    if command == "dump-registry":
        print(json.dumps(data, sort_keys=True))
        return 0
    if command == "default-provider":
        print(data["default_provider"])
        return 0
    if command in ("status", "access", "mcp-tool"):
        if not rest:
            die(1, f"{command}: missing provider")
        provider_id = rest[0]
        provider = data["providers"].get(provider_id)
        if provider is None:
            known = ", ".join(data["providers"])
            die(2, f"unknown provider: {provider_id} (known: {known})")
        if command == "access":
            print("\n".join(provider["access"]))
            return 0
        if len(rest) < 2:
            die(1, f"{command}: missing key")
        key = rest[1]
        table = (
            provider["status_map"]
            if command == "status"
            else provider.get("mcp_tools", {})
        )
        if key not in table:
            die(2, f"unknown {command} key for {provider_id}: {key}")
        print(table[key])
        return 0
    die(1, f"unknown subcommand: {command}")


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

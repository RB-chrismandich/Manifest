#!/usr/bin/env python3
"""Install a stored Context7 API key into MCP configs, without printing it."""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import sys
import tempfile
from pathlib import Path

CONTEXT7_URL = "https://mcp.context7.com/mcp"


def load_json(path: Path) -> dict:
    if not path.exists():
        return {}
    with path.open(encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise ValueError(f"{path}: top-level JSON value must be an object")
    return value


def write_private(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(content)
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
    except BaseException:
        with contextlib.suppress(FileNotFoundError):
            os.unlink(temporary)
        raise


def write_json_server(path: Path, entry: dict) -> None:
    config = load_json(path)
    servers = config.setdefault("mcpServers", {})
    if not isinstance(servers, dict):
        raise ValueError(f"{path}: mcpServers must be an object")
    servers["context7"] = entry
    write_private(path, json.dumps(config, indent=2) + "\n")


def replace_codex_server(content: str, block: str) -> str:
    lines = content.splitlines(keepends=True)
    start = next(
        (
            index
            for index, line in enumerate(lines)
            if line.strip() == "[mcp_servers.context7]"
        ),
        None,
    )
    if start is None:
        separator = "" if not content else ("\n" if content.endswith("\n") else "\n\n")
        return content + separator + block

    end = start + 1
    while end < len(lines):
        stripped = lines[end].strip()
        if stripped.startswith("[") and not stripped.startswith(
            "[mcp_servers.context7."
        ):
            break
        end += 1
    before = "".join(lines[:start]).rstrip()
    after = "".join(lines[end:]).lstrip()
    parts = [part for part in (before, block.rstrip(), after.rstrip()) if part]
    return "\n\n".join(parts) + "\n"


def write_codex(path: Path, api_key: str) -> None:
    existing = path.read_text(encoding="utf-8") if path.exists() else ""
    authorization = json.dumps(f"Bearer {api_key}")
    block = (
        "[mcp_servers.context7]\n"
        'type = "http"\n'
        f"url = {json.dumps(CONTEXT7_URL)}\n\n"
        "[mcp_servers.context7.http_headers]\n"
        f"Authorization = {authorization}\n"
    )
    write_private(path, replace_codex_server(existing, block))


def credential_path(home: Path) -> Path:
    config_home = Path(os.environ.get("XDG_CONFIG_HOME", home / ".config"))
    return config_home / "context7" / "credentials.json"


def read_api_key(home: Path) -> str:
    credentials = load_json(credential_path(home))
    key = credentials.get("access_token")
    if (
        not isinstance(key, str)
        or not key.startswith("ctx7sk-")
        or len(key) == len("ctx7sk-")
        or any(ord(character) < 33 or ord(character) > 126 for character in key)
    ):
        raise ValueError(
            "Context7 credential is missing a long-lived API key; run `ctx7 login`"
        )
    return key


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser()
    for target in ("claude", "cursor", "codex", "gemini", "antigravity", "devin"):
        parser.add_argument(f"--{target}", action="store_true")
    args = parser.parse_args(argv)
    home = Path.home()

    try:
        api_key = read_api_key(home)
        bearer = {"Authorization": f"Bearer {api_key}"}
        if args.claude:
            write_json_server(
                home / ".claude.json",
                {"type": "http", "url": CONTEXT7_URL, "headers": bearer},
            )
        if args.cursor:
            write_json_server(
                home / ".cursor" / "mcp.json", {"url": CONTEXT7_URL, "headers": bearer}
            )
        if args.codex:
            write_codex(home / ".codex" / "config.toml", api_key)
        if args.gemini:
            write_json_server(
                home / ".gemini" / "settings.json",
                {"httpUrl": CONTEXT7_URL, "headers": bearer},
            )
        if args.antigravity:
            write_json_server(
                home / ".gemini" / "config" / "mcp_config.json",
                {"serverUrl": CONTEXT7_URL, "headers": bearer},
            )
        if args.devin:
            write_json_server(
                home / ".config" / "devin" / "mcp_config.json",
                {"transport": "http", "url": CONTEXT7_URL, "headers": bearer},
            )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"configure_context7_auth.py: {exc}", file=sys.stderr)
        return 1
    print("Context7 bearer authentication configured")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

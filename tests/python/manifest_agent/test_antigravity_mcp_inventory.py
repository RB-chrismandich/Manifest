"""Antigravity observes the MCP servers already registered in agy."""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path

import pytest

from manifest_agent.adapters.antigravity import AntigravityAdapter
from manifest_agent.adapters.antigravity_evidence import (
    read_antigravity_native_mcp_servers,
)


def _write_agy_mcp_config(home: Path, servers: Mapping[str, object]) -> None:
    config = home / ".gemini" / "config"
    config.mkdir(parents=True)
    (config / "mcp_config.json").write_text(
        json.dumps({"mcpServers": servers}), encoding="utf-8"
    )


def test_live_agy_mcp_registrations_are_read_without_header_values(
    tmp_path: Path,
) -> None:
    _write_agy_mcp_config(
        tmp_path,
        {
            "context7": {
                "serverUrl": "https://mcp.context7.com/mcp",
                "headers": {"Authorization": "secret-value"},
            },
            "stdio-only": {"command": "npx"},
            "malformed": "not-a-mapping",
        },
    )

    servers = read_antigravity_native_mcp_servers({"HOME": str(tmp_path)})

    assert set(servers) == {"context7"}
    assert servers["context7"].url == "https://mcp.context7.com/mcp"
    assert "secret-value" not in repr(servers)


@pytest.mark.parametrize("content", ["{not json", "[]", '{"mcpServers": []}'])
def test_unreadable_agy_mcp_config_yields_no_registrations(
    tmp_path: Path, content: str
) -> None:
    config = tmp_path / ".gemini" / "config"
    config.mkdir(parents=True)
    (config / "mcp_config.json").write_text(content, encoding="utf-8")

    assert read_antigravity_native_mcp_servers({"HOME": str(tmp_path)}) == {}
    assert read_antigravity_native_mcp_servers({"HOME": str(tmp_path / "x")}) == {}


def test_adapter_applies_capabilities_against_live_agy_mcp_registrations(
    tmp_path: Path,
) -> None:
    _write_agy_mcp_config(
        tmp_path, {"context7": {"serverUrl": "https://mcp.context7.com/mcp"}}
    )
    env = {"HOME": str(tmp_path)}

    observed = AntigravityAdapter(env=env)._native_mcp_inventory_for_apply()
    injected = AntigravityAdapter(
        env=env, native_mcp_inventory=("injected",)
    )._native_mcp_inventory_for_apply()

    assert set(observed or ()) == {"context7"}
    assert tuple(injected or ()) == ("injected",)

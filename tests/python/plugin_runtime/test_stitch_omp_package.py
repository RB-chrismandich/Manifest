"""Contract tests for Stitch's OMP package, MCP definition, and assets."""

from __future__ import annotations

import json
from pathlib import Path

import yaml


def test_stitch_bundle_declares_an_installable_omp_package(
    stitch_bundle: Path,
) -> None:
    package_path = stitch_bundle / "package.json"
    assert package_path.is_file()

    package = json.loads(package_path.read_text(encoding="utf-8"))

    assert package["name"] == "stitch-design"
    plugin = json.loads(
        (stitch_bundle / ".claude-plugin/plugin.json").read_text(encoding="utf-8")
    )
    assert package["version"] == plugin["version"]
    assert package["private"] is True
    assert package["omp"] == {"extensions": ["./extensions/ui-delivery-policy.ts"]}


def test_stitch_omp_mcp_definition_is_safe_and_streamable_http(
    stitch_bundle: Path,
) -> None:
    mcp_path = stitch_bundle / ".mcp.json"
    assert mcp_path.is_file()

    definition = json.loads(mcp_path.read_text(encoding="utf-8"))

    assert definition == {
        "$schema": (
            "https://raw.githubusercontent.com/can1357/oh-my-pi/main/"
            "packages/coding-agent/src/config/mcp-schema.json"
        ),
        "mcpServers": {
            "stitch": {
                "type": "http",
                "url": "https://stitch.googleapis.com/mcp",
                "enabled": True,
                "headers": {"X-Goog-Api-Key": "${STITCH_API_KEY}"},
            }
        },
    }


def test_stitch_contract_inventories_omp_delivery_assets(
    stitch_bundle: Path,
) -> None:
    contract_path = stitch_bundle / "manifest-capabilities.yml"
    document = yaml.safe_load(contract_path.read_text(encoding="utf-8"))
    runtime = {item["id"]: item for item in document["components"]["runtime"]}

    assert {
        "stitch-omp-package",
        "stitch-omp-extension",
        "stitch-omp-mcp-definition",
    } <= runtime.keys()
    assert runtime["stitch-omp-package"]["path"] == "package.json"
    assert runtime["stitch-omp-extension"]["path"] == (
        "extensions/ui-delivery-policy.ts"
    )
    assert runtime["stitch-omp-mcp-definition"]["path"] == ".mcp.json"
    extension_inventory = runtime["stitch-omp-extension"]
    compatibility = extension_inventory.get("compatibility")
    assert compatibility is not None
    non_omp_harnesses = {
        "claude",
        "codex",
        "gemini",
        "cursor",
        "antigravity",
        "devin",
    }
    assert set(compatibility) == {*non_omp_harnesses, "omp"}
    assert all(
        compatibility[harness]["mode"] == "not_applicable"
        for harness in non_omp_harnesses
    )
    assert compatibility["omp"]["mode"] == "native"

"""Devin 3000.x plugins info parser and real-contract verification tests."""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path

from manifest_agent.adapters.devin import DevinAdapter
from manifest_agent.adapters.devin_parsing import _parse_info
from manifest_agent.capabilities import McpDefinition
from manifest_agent.contracts import load_addon_contracts, load_domain_contracts
from manifest_agent.models import (
    CommandResult,
    DesiredState,
    MarketplaceSource,
    MarketplaceSourceKind,
)
from manifest_agent.process import CommandRunner


def test_parse_info_extracts_devin_3000_skills_ignoring_headers_and_dividers() -> None:
    raw_output = "\n".join(
        [
            "Plugin: manifest-workspace",
            "  version: 0.7.0",
            "  source: /tmp/release/plugins/manifest-workspace",
            "  description: Workspace configuration and diagnostics.",
            "────────────────────────────────────────",
            "Skills (4):",
            "────────────────────────────────────────",
            "  /plugin:slash-plugin-skill - Slash plugin syntax",
            "      continuation line that must not become a skill",
            "      trailingword",
            "  /manifest-workspace:env-check - Environment probe",
            "  manifest-workspace:deploy-reconcile - Drift reconciliation",
            "  - /acme/tools:bullet-qualified: Colon suffix description",
            "── Agents ──────────────────────────────",
            "  explore",
            "  scout",
            "Hooks",
            "--------",
            "  SessionStart (hooks/hooks.json)",
            "Rules:",
            "========",
            "  guidance/always-on.md * (all)",
            "MCP servers:",
            "  context7 (https://mcp.context7.com/mcp)",
            "  disabled-mcp (https://example.invalid/mcp) (disabled)",
            "Required plugins: (none)",
            "Optional plugins",
            "  (none)",
            "Forbidden plugins: (none)",
        ]
    )

    row, error = _parse_info(raw_output)

    assert error is None
    assert row["name"] == "manifest-workspace"
    assert row["version"] == "0.7.0"
    assert row["source"] == "/tmp/release/plugins/manifest-workspace"
    assert row["skills"] == {
        "slash-plugin-skill",
        "env-check",
        "deploy-reconcile",
        "bullet-qualified",
    }
    assert row["mcp_servers"] == {
        "context7": McpDefinition(
            name="context7", transport="http", url="https://mcp.context7.com/mcp"
        )
    }


def test_parse_info_treats_inline_none_skills_header_as_empty() -> None:
    raw_output = "\n".join(
        [
            "Plugin: manifest-docs",
            "  version: 0.7.0",
            "  source: /tmp/release/plugins/manifest-docs",
            "Skills: (none)",
            "Hooks: (none)",
            "Rules: (none)",
            "Required plugins: (none)",
        ]
    )

    row, error = _parse_info(raw_output)

    assert error is None
    assert row["skills"] == set()


def _real_repo_desired(repo_root: Path) -> DesiredState:
    return DesiredState(
        release_version="0.7.0",
        source_commit="a" * 40,
        source=str(repo_root),
        marketplace_source=MarketplaceSource(
            MarketplaceSourceKind.LOCAL, str(repo_root), None
        ),
        release_root=repo_root,
        repository_url="https://example.invalid/Manifest.git",
        source_dirty=False,
        archive_sha256="b" * 64,
        contracts=load_domain_contracts(repo_root / "plugins"),
        selected_optional=frozenset(),
        requested_harnesses=("devin",),
        addon_contracts=load_addon_contracts(repo_root / "plugins"),
    )


def _real_repo_outputs(desired: DesiredState, repo_root: Path) -> list[CommandResult]:
    listing = "Installed plugins\n" + "\n".join(
        f"{c.name} {c.version}" for c in desired.all_contracts
    )
    outputs = [CommandResult(("devin", "plugins", "list"), 0, listing, "")]
    for contract in desired.all_contracts:
        skills_root = repo_root / "plugins" / contract.name / "skills"
        skill_lines = "\n".join(
            f"  /{contract.name}:{p.parent.name} - Skill"
            for p in sorted(skills_root.glob("*/SKILL.md"))
        )
        info = (
            f"Plugin: {contract.name}\n  version: {contract.version}\n"
            f"  source: {desired.bundle_path(contract.name)}\n"
            f"Skills\n────────\n{skill_lines}\nAgents\n  ignored\n"
        )
        outputs.append(CommandResult(("devin", "plugins", "info"), 0, info, ""))
    return outputs


def _assert_matches_frozen_devin_fixture(
    capabilities: Mapping[str, str], repo_root: Path
) -> None:
    fixture = json.loads(
        (repo_root / "tests/fixtures/plugin_capability_inspection.json").read_text()
    )["harnesses"]["devin"]
    degraded = {
        "manifest-ops:hook:compose-commandments",
        "manifest-ops:hook:version-pin",
    }
    for bundle, entries in fixture["components"].items():
        for entry in entries:
            identity = f"{bundle}:{entry}"
            if identity in degraded:
                assert capabilities[identity] == "degraded"
            elif identity == "manifest-workspace:guidance:workspace-token-economy":
                assert identity not in capabilities
            else:
                assert capabilities[identity] == "verified", identity
    for bundle, entries in fixture["capabilities"].items():
        for entry in entries:
            assert capabilities[f"{bundle}:{entry}"] == "verified"


def test_real_repository_contracts_verify_every_devin_surface(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[3]
    desired = _real_repo_desired(repo_root)
    home = tmp_path / "home"
    rule = home / ".codeium/windsurf/memories/global_rules.md"
    rule.parent.mkdir(parents=True, exist_ok=True)
    rule.write_bytes(
        (repo_root / "plugins/manifest-i-have-adhd/devin/global-rule.md").read_bytes()
    )
    cfg = home / ".config/devin/mcp_config.json"
    cfg.parent.mkdir(parents=True, exist_ok=True)
    cfg.write_text(
        json.dumps(
            {
                "mcpServers": {
                    "context7": {
                        "transport": "http",
                        "url": "https://mcp.context7.com/mcp",
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    outputs = _real_repo_outputs(desired, repo_root)

    class _SeqRunner(CommandRunner):
        def run(self, argv, *, env=None):
            del argv, env
            return outputs.pop(0)

    result = DevinAdapter(
        runner=_SeqRunner(),
        which=lambda name: f"/usr/bin/{name}",
        env={"HOME": str(home), "XDG_CONFIG_HOME": str(home / ".config")},
    ).inspect(desired)

    _assert_matches_frozen_devin_fixture(result.capabilities, repo_root)

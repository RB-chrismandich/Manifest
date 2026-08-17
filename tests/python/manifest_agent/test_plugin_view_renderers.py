"""Harness-specific plugin view rendering invariants."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
import yaml

from manifest_agent.contracts import load_domain_contracts
from manifest_agent.models import CapabilityTier
from tests.python.manifest_agent._plugin_view_fixtures import build_fixture_repo
from tools.generate_plugin_views import render_views

GENERIC_HARNESSES = ("antigravity", "codex", "cursor", "devin")
COMPONENT_FIXTURES = {
    "agents": ("reviewer", "agents/reviewer.md"),
    "hooks": ("preflight", "hooks/preflight.json"),
    "guidance": ("instructions", "guidance/instructions.md"),
    "runtime": ("runner", "runtime/runner.py"),
}


@pytest.fixture
def repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def test_contracts_declare_explicit_capability_tiers(repo_root: Path) -> None:
    expected_path = (
        Path(__file__).resolve().parents[1]
        / "fixtures"
        / "expected_capability_tiers.json"
    )
    expected = json.loads(expected_path.read_text(encoding="utf-8"))
    contracts = {
        contract.name: contract
        for contract in load_domain_contracts(repo_root / "plugins")
    }

    for name, tiers in expected.items():
        contract = contracts[name]
        actual = [list(contract.capabilities.mcp[tier]) for tier in CapabilityTier] + [
            list(contract.capabilities.executables[tier]) for tier in CapabilityTier
        ]
        assert actual == tiers, name


def _configure_component_fixture(fixture_root: Path) -> None:
    docs_bundle = fixture_root / "plugins" / "manifest-docs"
    contract_path = docs_bundle / "manifest-capabilities.yml"
    document = yaml.safe_load(contract_path.read_text(encoding="utf-8"))
    for kind, (component_id, relative_path) in COMPONENT_FIXTURES.items():
        document["components"][kind] = [{"id": component_id, "path": relative_path}]
        asset_path = docs_bundle / relative_path
        asset_path.parent.mkdir(parents=True, exist_ok=True)
        asset_path.write_text("fixture\n", encoding="utf-8")
    document["components"]["runtime"][0]["compatibility"] = {
        "claude": {"mode": "degraded", "reason": "claude fixture runtime"},
        "codex": {"mode": "degraded", "reason": "codex fixture runtime"},
        "gemini": {"mode": "unsupported", "reason": "gemini fixture runtime"},
        "cursor": {"mode": "unsupported", "reason": "cursor fixture runtime"},
        "antigravity": {
            "mode": "degraded",
            "reason": "antigravity fixture runtime",
        },
        "devin": {"mode": "unsupported", "reason": "devin fixture runtime"},
    }
    document["compatibility"]["devin"] = {
        "mode": "degraded",
        "reason": "devin fixture bundle",
    }
    contract_path.write_text(
        yaml.safe_dump(document, sort_keys=False), encoding="utf-8"
    )


def _native_component_keys(view: dict[str, Any]) -> set[tuple[str, str]]:
    keys = {
        (record["component_type"], record["component_id"])
        for records in view.get("compatibility", {}).values()
        for record in records
    }
    for kind, (component_id, relative_path) in COMPONENT_FIXTURES.items():
        for component in view.get(kind, []):
            if component in {relative_path, f"./{relative_path}"} or component == {
                "id": component_id,
                "path": relative_path,
            }:
                keys.add((kind, component_id))
    return keys


def _assert_native_views(views: dict[str, dict[str, Any]]) -> None:
    expected = {
        (kind, component_id)
        for kind, (component_id, _relative_path) in COMPONENT_FIXTURES.items()
    }
    for harness, view in views.items():
        assert expected <= _native_component_keys(view), harness
        runtime = next(
            record
            for record in view["compatibility"]["degraded"]
            if record["component_type"] == "runtime"
        )
        assert runtime["reason"] == f"{harness} fixture runtime"


def _assert_generic_view(generic: dict[str, Any]) -> None:
    assert tuple(sorted(generic["harnesses"])) == GENERIC_HARNESSES
    expected_modes = {
        "antigravity": "imported",
        "codex": "native",
        "cursor": "generated",
        "devin": "degraded",
    }
    runtime_modes = {
        "antigravity": "degraded",
        "codex": "degraded",
        "cursor": "unsupported",
        "devin": "unsupported",
    }
    for harness, expected_mode in expected_modes.items():
        surface = generic["harnesses"][harness]
        assert surface["mode"] == expected_mode
        agent = next(
            record
            for record in surface["compatibility"][expected_mode]
            if record["component_type"] == "agents"
        )
        assert (agent["component_id"], agent["mode"]) == ("reviewer", expected_mode)
        runtime = next(
            record
            for record in surface["compatibility"]["degraded"]
            if record["component_type"] == "runtime"
        )
        assert runtime["reason"] == f"{harness} fixture runtime"
        assert runtime["mode"] == runtime_modes[harness]
    assert generic["harnesses"]["devin"]["reason"] == "devin fixture bundle"


def test_every_component_is_exposed_or_explicitly_degraded(
    repo_root: Path, tmp_path: Path
) -> None:
    fixture_root = tmp_path / "fixture-repo"
    build_fixture_repo(repo_root, fixture_root)
    _configure_component_fixture(fixture_root)
    output_root = tmp_path / "views"
    render_views(fixture_root, output_root=output_root, check=False)
    views = {
        harness: json.loads(
            (
                output_root
                / f"manifest-docs/{'.claude-plugin/plugin.json' if harness == 'claude' else 'gemini-extension.json'}"
            ).read_text()
        )
        for harness in ("claude", "gemini")
    }
    _assert_native_views(views)
    generic = json.loads((output_root / "manifest-docs/plugin.json").read_text())
    _assert_generic_view(generic)

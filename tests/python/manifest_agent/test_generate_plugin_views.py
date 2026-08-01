"""Contract-to-native-view generation invariants."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
import yaml

from manifest_agent.contracts import DOMAIN_BUNDLES, load_domain_contracts
from manifest_agent.models import CapabilityTier
from tools.generate_plugin_views import render_views
from tools.skill_ref import expand, load_bundles


@pytest.fixture
def repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def test_generator_emits_three_native_views_per_domain(
    repo_root: Path, tmp_path: Path
) -> None:
    report = render_views(repo_root, output_root=tmp_path, check=False)

    assert report.bundles == DOMAIN_BUNDLES
    assert (tmp_path / "manifest-docs/.claude-plugin/plugin.json").is_file()
    assert (tmp_path / "manifest-docs/gemini-extension.json").is_file()
    assert (tmp_path / "manifest-docs/plugin.json").is_file()


def test_marketplace_excludes_optional_addon_from_parity_count(
    repo_root: Path,
) -> None:
    contracts = load_domain_contracts(repo_root / "plugins")

    assert {contract.name for contract in contracts} == set(DOMAIN_BUNDLES)


def test_contracts_declare_explicit_capability_tiers(repo_root: Path) -> None:
    contracts = {
        contract.name: contract
        for contract in load_domain_contracts(repo_root / "plugins")
    }
    expected = {
        "manifest-code-quality": (
            (),
            (),
            (),
            ("bash", "git", "python3"),
            (),
            ("browser-use", "playwright", "semgrep"),
        ),
        "manifest-docs": ((), (), (), ("git", "python3"), (), ()),
        "manifest-forge": (
            (),
            (),
            ("atlassian", "github", "linear"),
            ("bash", "git", "python3"),
            (),
            ("gh", "glab"),
        ),
        "manifest-graphify": ((), (), (), ("git",), ("graphify",), ()),
        "manifest-ops": (
            (),
            (),
            ("sentry",),
            ("bash", "git", "python3"),
            (),
            ("docker", "terraform", "tflint", "tofu"),
        ),
        "manifest-security": (
            (),
            (),
            (),
            ("bash", "git", "python3"),
            (),
            ("semgrep",),
        ),
        "manifest-spec-planning": (
            (),
            (),
            (),
            ("bash", "git", "python3"),
            (),
            ("agy",),
        ),
        "manifest-workspace": (
            (),
            ("context7",),
            (),
            ("bash", "git", "python3"),
            (),
            ("pass-cli",),
        ),
        "stitch-design": (
            (),
            (),
            ("stitch",),
            ("bash", "git", "python3"),
            ("node",),
            ("chromium",),
        ),
    }

    for name, tiers in expected.items():
        contract = contracts[name]
        actual = tuple(
            contract.capabilities.mcp[tier] for tier in CapabilityTier
        ) + tuple(contract.capabilities.executables[tier] for tier in CapabilityTier)
        assert actual == tiers, name


def test_generated_lists_are_sorted(repo_root: Path, tmp_path: Path) -> None:
    render_views(repo_root, output_root=tmp_path, check=False)
    claude_view = json.loads(
        (tmp_path / "manifest-code-quality/.claude-plugin/plugin.json").read_text()
    )
    marketplace = json.loads((tmp_path / ".claude-plugin/marketplace.json").read_text())

    assert claude_view["skills"] == sorted(claude_view["skills"])
    domain_names = [
        entry["name"]
        for entry in marketplace["plugins"]
        if entry["name"] in DOMAIN_BUNDLES
    ]
    assert domain_names == sorted(domain_names)


def test_check_reports_all_drift_without_writing(
    repo_root: Path, tmp_path: Path
) -> None:
    render_views(repo_root, output_root=tmp_path, check=False)
    claude_path = tmp_path / "manifest-docs/.claude-plugin/plugin.json"
    gemini_path = tmp_path / "manifest-forge/gemini-extension.json"
    claude_path.write_text("drifted claude\n", encoding="utf-8")
    gemini_path.write_text("drifted gemini\n", encoding="utf-8")

    report = render_views(repo_root, output_root=tmp_path, check=True)

    assert report.drifted_paths == tuple(sorted((claude_path, gemini_path)))
    assert claude_path.read_text(encoding="utf-8") == "drifted claude\n"
    assert gemini_path.read_text(encoding="utf-8") == "drifted gemini\n"


def test_marketplace_preserves_independent_addon_entry(
    repo_root: Path, tmp_path: Path
) -> None:
    source = json.loads((repo_root / ".claude-plugin/marketplace.json").read_text())
    expected = next(
        entry
        for entry in source["plugins"]
        if entry["name"] == "adversarial-design-loop"
    )

    render_views(repo_root, output_root=tmp_path, check=False)
    generated = json.loads((tmp_path / ".claude-plugin/marketplace.json").read_text())
    actual = next(
        entry
        for entry in generated["plugins"]
        if entry["name"] == "adversarial-design-loop"
    )

    assert actual == expected
    assert len(generated["plugins"]) == 10


def test_every_component_is_exposed_or_explicitly_degraded(
    repo_root: Path, tmp_path: Path
) -> None:
    fixture_root = tmp_path / "fixture-repo"
    fixture_plugins = fixture_root / "plugins"
    fixture_marketplace = fixture_root / ".claude-plugin/marketplace.json"
    fixture_marketplace.parent.mkdir(parents=True)
    shutil.copy2(repo_root / ".claude-plugin/marketplace.json", fixture_marketplace)
    for bundle_name in DOMAIN_BUNDLES:
        source_bundle = repo_root / "plugins" / bundle_name
        target_bundle = fixture_plugins / bundle_name
        (target_bundle / "skills/example").mkdir(parents=True)
        shutil.copy2(
            source_bundle / "manifest-capabilities.yml",
            target_bundle / "manifest-capabilities.yml",
        )
        (target_bundle / "skills/example/SKILL.md").write_text(
            "---\nname: example\ndescription: Example fixture skill.\n---\n",
            encoding="utf-8",
        )

    docs_bundle = fixture_plugins / "manifest-docs"
    contract_path = docs_bundle / "manifest-capabilities.yml"
    document = yaml.safe_load(contract_path.read_text(encoding="utf-8"))
    fixtures = {
        "agents": ("reviewer", "agents/reviewer.md"),
        "hooks": ("preflight", "hooks/preflight.json"),
        "guidance": ("instructions", "guidance/instructions.md"),
        "runtime": ("runner", "runtime/runner.py"),
    }
    for kind, (component_id, relative_path) in fixtures.items():
        document["components"][kind] = [{"id": component_id, "path": relative_path}]
        asset_path = docs_bundle / relative_path
        asset_path.parent.mkdir(parents=True, exist_ok=True)
        asset_path.write_text("fixture\n", encoding="utf-8")
    document["components"]["runtime"][0]["compatibility"] = {
        "claude": {"mode": "degraded", "reason": "claude fixture runtime"},
        "codex": {"mode": "native"},
        "gemini": {"mode": "unsupported", "reason": "gemini fixture runtime"},
        "cursor": {"mode": "generated"},
        "antigravity": {"mode": "imported"},
        "devin": {"mode": "native"},
    }
    contract_path.write_text(
        yaml.safe_dump(document, sort_keys=False), encoding="utf-8"
    )

    output_root = tmp_path / "views"
    render_views(fixture_root, output_root=output_root, check=False)

    views = {
        "claude": json.loads(
            (output_root / "manifest-docs/.claude-plugin/plugin.json").read_text()
        ),
        "gemini": json.loads(
            (output_root / "manifest-docs/gemini-extension.json").read_text()
        ),
        "generic": json.loads((output_root / "manifest-docs/plugin.json").read_text()),
    }
    for harness, view in views.items():
        exposed = set()
        for kind, (component_id, relative_path) in fixtures.items():
            for component in view.get(kind, []):
                if (
                    isinstance(component, dict)
                    and component
                    == {
                        "id": component_id,
                        "path": relative_path,
                    }
                ) or component in {relative_path, f"./{relative_path}"}:
                    exposed.add((kind, component_id))
        native = {
            (record["component_type"], record["component_id"])
            for record in view.get("compatibility", {}).get("native", [])
        }
        degraded = {
            (record["component_type"], record["component_id"])
            for record in view.get("compatibility", {}).get("degraded", [])
        }
        expected = {
            (kind, component_id) for kind, (component_id, _) in fixtures.items()
        }
        assert expected <= exposed | native | degraded, harness

    for harness, expected_reason in {
        "claude": "claude fixture runtime",
        "gemini": "gemini fixture runtime",
    }.items():
        runtime_record = next(
            record
            for record in views[harness]["compatibility"]["degraded"]
            if record["component_type"] == "runtime"
        )
        assert runtime_record["reason"] == expected_reason


def test_tools_skill_ref_preserves_qualified_mapping_semantics(
    repo_root: Path,
) -> None:
    bundles = load_bundles(repo_root / "configs/claude/config/skill_policies.yml")

    rewritten, seen, unknown = expand(
        "Run [[skill:project-verify]].", "qualified", bundles
    )

    assert rewritten == "Run /manifest-code-quality:project-verify."
    assert seen == ["project-verify"]
    assert unknown == []

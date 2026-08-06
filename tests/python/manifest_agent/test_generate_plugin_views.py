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

ALL_HARNESSES = (
    "antigravity",
    "claude",
    "codex",
    "cursor",
    "devin",
    "gemini",
)
GENERIC_HARNESSES = ("antigravity", "codex", "cursor", "devin")
EXPECTED_ADDON_ENTRIES = (
    {
        "category": "design",
        "description": (
            "Spec-first UI design loop: colorless screen prompts, faithful render "
            "gates, multi-lens adversarial review with skeptic-verified blockers, "
            "upstream spec amendments."
        ),
        "homepage": "https://github.com/RB-chrismandich/Manifest",
        "keywords": [
            "design",
            "ui",
            "stitch",
            "adversarial-review",
            "design-system",
            "render-verification",
        ],
        "name": "adversarial-design-loop",
        "source": "./plugins/adversarial-design-loop",
        "version": "0.1.0",
    },
    {
        "category": "deployment",
        "description": (
            "The Ten Commandments of docker-compose (DC-001..DC-010): an advisory "
            "save-hook and an on-demand audit for image pinning, secrets, healthchecks, "
            "resource limits, network isolation, volumes, non-root, logging, DRY and "
            "graceful shutdown."
        ),
        "homepage": "https://github.com/ReefBytes-Owner/Manifest",
        "name": "manifest-docker",
        "source": "./plugins/manifest-docker",
        "version": "0.1.0",
    },
)


@pytest.fixture
def repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _build_fixture_repo(repo_root: Path, fixture_root: Path) -> None:
    fixture_plugins = fixture_root / "plugins"
    for bundle_name in DOMAIN_BUNDLES:
        source_bundle = repo_root / "plugins" / bundle_name
        target_bundle = fixture_plugins / bundle_name
        (target_bundle / "skills/example").mkdir(parents=True)
        shutil.copy2(
            source_bundle / "manifest-capabilities.yml",
            target_bundle / "manifest-capabilities.yml",
        )
        contract_document = yaml.safe_load(
            (source_bundle / "manifest-capabilities.yml").read_text(encoding="utf-8")
        )
        for component_type in ("agents", "hooks", "runtime", "guidance"):
            for component in contract_document["components"][component_type]:
                source = source_bundle / component["path"]
                target = target_bundle / component["path"]
                if source.is_dir():
                    target.mkdir(parents=True, exist_ok=True)
                else:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_text("fixture\n", encoding="utf-8")
        (target_bundle / "skills/example/SKILL.md").write_text(
            "---\nname: example\ndescription: Example fixture skill.\n---\n",
            encoding="utf-8",
        )

    marketplace_path = fixture_root / ".claude-plugin/marketplace.json"
    marketplace_path.parent.mkdir(parents=True)
    shutil.copy2(repo_root / ".claude-plugin/marketplace.json", marketplace_path)

    for canonical_source in sorted(
        (repo_root / "plugins").glob("*/.claude-plugin/marketplace-entry.json")
    ):
        addon_source = fixture_plugins / canonical_source.relative_to(
            repo_root / "plugins"
        )
        addon_source.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(canonical_source, addon_source)


def test_generator_emits_three_native_views_per_domain(
    repo_root: Path, tmp_path: Path
) -> None:
    report = render_views(repo_root, output_root=tmp_path, check=False)

    assert report.bundles == DOMAIN_BUNDLES
    assert report.harnesses == ALL_HARNESSES
    assert (tmp_path / "manifest-docs/.claude-plugin/plugin.json").is_file()
    assert (tmp_path / "manifest-docs/gemini-extension.json").is_file()
    generic_path = tmp_path / "manifest-docs/plugin.json"
    assert generic_path.is_file()
    generic = json.loads(generic_path.read_text())
    assert set(report.harnesses) == {"claude", "gemini", *generic["harnesses"]}


def test_generator_emits_release_command_catalog(
    repo_root: Path, tmp_path: Path
) -> None:
    render_views(repo_root, output_root=tmp_path, check=False)
    catalog_path = tmp_path / "manifest-workspace/skills/help/catalog/commands.json"
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))

    assert len(catalog["commands"]) == 108
    assert any(
        command["qualified_name"] == "manifest-workspace:parallel-agent"
        for command in catalog["commands"]
    )


def test_marketplace_excludes_independent_addons_from_parity_count(
    repo_root: Path,
) -> None:
    contracts = load_domain_contracts(repo_root / "plugins")

    assert {contract.name for contract in contracts} == set(DOMAIN_BUNDLES)
    assert "manifest-docker" not in DOMAIN_BUNDLES


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
            ("git", "python3"),
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
            ("curl", "gh", "glab", "gtimeout", "jq", "timeout"),
        ),
        "manifest-ops": (
            (),
            (),
            ("sentry",),
            ("bash", "git", "python3"),
            (),
            ("docker", "shasum", "sha256sum", "terraform", "tflint", "tofu"),
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
            ("agy", "devin", "shasum"),
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
            ("chromium", "curl"),
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


def test_marketplace_preserves_independent_addon_entries(
    repo_root: Path, tmp_path: Path
) -> None:
    canonical_sources = sorted(
        (repo_root / "plugins").glob("*/.claude-plugin/marketplace-entry.json")
    )
    expected = tuple(json.loads(source.read_text()) for source in canonical_sources)
    assert expected == EXPECTED_ADDON_ENTRIES
    for source, entry in zip(canonical_sources, expected, strict=True):
        assert source.read_text() == json.dumps(entry, indent=2, sort_keys=True) + "\n"

    render_views(repo_root, output_root=tmp_path, check=False)
    generated = json.loads((tmp_path / ".claude-plugin/marketplace.json").read_text())
    actual = tuple(
        entry for entry in generated["plugins"] if entry["name"] not in DOMAIN_BUNDLES
    )

    assert actual == expected
    assert len(generated["plugins"]) == len(DOMAIN_BUNDLES) + len(expected)


def test_check_detects_tampered_generated_addon_entry(
    repo_root: Path, tmp_path: Path
) -> None:
    fixture_root = tmp_path / "fixture-repo"
    _build_fixture_repo(repo_root, fixture_root)
    render_views(fixture_root, check=False)
    marketplace_path = fixture_root / ".claude-plugin/marketplace.json"
    marketplace = json.loads(marketplace_path.read_text())
    addon = next(
        entry for entry in marketplace["plugins"] if entry["name"] == "manifest-docker"
    )
    addon["description"] = "tampered generated addon metadata"
    marketplace_path.write_text(json.dumps(marketplace, indent=2) + "\n")

    report = render_views(fixture_root, check=True)

    assert marketplace_path in report.drifted_paths
    assert "tampered" in marketplace_path.read_text()


def test_every_component_is_exposed_or_explicitly_degraded(
    repo_root: Path, tmp_path: Path
) -> None:
    fixture_root = tmp_path / "fixture-repo"
    _build_fixture_repo(repo_root, fixture_root)
    fixture_plugins = fixture_root / "plugins"
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

    output_root = tmp_path / "views"
    render_views(fixture_root, output_root=output_root, check=False)

    views = {
        "claude": json.loads(
            (output_root / "manifest-docs/.claude-plugin/plugin.json").read_text()
        ),
        "gemini": json.loads(
            (output_root / "manifest-docs/gemini-extension.json").read_text()
        ),
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
        represented = {
            (record["component_type"], record["component_id"])
            for mode, records in view.get("compatibility", {}).items()
            if mode != "degraded"
            for record in records
        }
        degraded = {
            (record["component_type"], record["component_id"])
            for record in view.get("compatibility", {}).get("degraded", [])
        }
        expected = {
            (kind, component_id) for kind, (component_id, _) in fixtures.items()
        }
        assert expected <= exposed | represented | degraded, harness

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

    generic = json.loads((output_root / "manifest-docs/plugin.json").read_text())
    assert tuple(sorted(generic["harnesses"])) == GENERIC_HARNESSES
    expected_modes = {
        "antigravity": "imported",
        "codex": "native",
        "cursor": "generated",
        "devin": "degraded",
    }
    for harness, expected_mode in expected_modes.items():
        surface = generic["harnesses"][harness]
        assert surface["mode"] == expected_mode
        agent_record = next(
            record
            for record in surface["compatibility"][expected_mode]
            if record["component_type"] == "agents"
        )
        assert agent_record["component_id"] == "reviewer"
        assert agent_record["mode"] == expected_mode
        runtime_record = next(
            record
            for record in surface["compatibility"]["degraded"]
            if record["component_type"] == "runtime"
        )
        assert runtime_record["reason"] == f"{harness} fixture runtime"
    runtime_modes = {
        "antigravity": "degraded",
        "codex": "degraded",
        "cursor": "unsupported",
        "devin": "unsupported",
    }
    for harness, expected_mode in runtime_modes.items():
        runtime_record = next(
            record
            for record in generic["harnesses"][harness]["compatibility"]["degraded"]
            if record["component_type"] == "runtime"
        )
        assert runtime_record["mode"] == expected_mode
    assert generic["harnesses"]["devin"]["reason"] == "devin fixture bundle"


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

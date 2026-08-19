"""Contract-to-native-view generation invariants."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from manifest_agent.contracts import DOMAIN_BUNDLES, load_domain_contracts
from tests.python.manifest_agent._plugin_view_fixtures import build_fixture_repo
from tools.generate_plugin_views import GenerationError, render_views
from tools.skill_ref import expand, load_bundles

ALL_HARNESSES = (
    "antigravity",
    "claude",
    "codex",
    "cursor",
    "devin",
    "gemini",
)
# Pinned independently of plugins/*/.claude-plugin/marketplace-entry.json — the
# whole point of the assertion is that a change to those canonical files is
# deliberate, so this fixture is hand-maintained and must NOT be regenerated
# from them. Held as data rather than a source literal (CON-004).
EXPECTED_ADDON_ENTRIES = tuple(
    json.loads(
        (
            Path(__file__).resolve().parents[1]
            / "fixtures"
            / "expected_addon_marketplace_entries.json"
        ).read_text()
    )
)
CODEX_IMPLICIT_INVOCATION_ALLOWLIST = {
    "manifest-code-quality:antipattern-detect",
    "manifest-security:code-audit",
    "manifest-workspace:help",
}
CODEX_MANIFEST_STARTUP_BUDGET_BYTES = 4_000
CODEX_INSTALLED_PATH_RESERVE_BYTES = 512


@pytest.fixture
def repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


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


def test_generator_emits_codex_invocation_policy_for_every_skill(
    repo_root: Path, tmp_path: Path
) -> None:
    render_views(repo_root, output_root=tmp_path, check=False)
    source_plugins = repo_root / "plugins"
    actual: dict[str, bool] = {}
    startup_bytes = 0

    for skill_file in sorted(source_plugins.glob("*/skills/*/SKILL.md")):
        relative_skill = skill_file.parent.relative_to(source_plugins)
        qualified_name = f"{relative_skill.parts[0]}:{relative_skill.parts[2]}"
        metadata_path = tmp_path / relative_skill / "agents/openai.yaml"
        metadata = yaml.safe_load(metadata_path.read_text(encoding="utf-8"))
        actual[qualified_name] = metadata["policy"]["allow_implicit_invocation"]
        if actual[qualified_name]:
            frontmatter = yaml.safe_load(
                skill_file.read_text(encoding="utf-8").split("---", 2)[1]
            )
            entry = (
                f"- {qualified_name}: {frontmatter['description']} (file: "
                f"{'x' * CODEX_INSTALLED_PATH_RESERVE_BYTES})\n"
            )
            startup_bytes += len(entry.encode("utf-8"))

    assert {name for name, allowed in actual.items() if allowed} == (
        CODEX_IMPLICIT_INVOCATION_ALLOWLIST
    )
    assert all(isinstance(allowed, bool) for allowed in actual.values())
    assert startup_bytes <= CODEX_MANIFEST_STARTUP_BUDGET_BYTES

    plugin = json.loads(
        (tmp_path / "manifest-code-quality/.claude-plugin/plugin.json").read_text(
            encoding="utf-8"
        )
    )
    assert actual["manifest-code-quality:project-verify"] is False
    assert "./skills/project-verify" in plugin["skills"]


@pytest.mark.parametrize(
    ("policy", "error"),
    (
        ({}, "must declare codex_implicit_invocation_allowlist"),
        (
            {
                "codex_implicit_invocation_allowlist": [
                    "manifest-docs:example",
                    "manifest-docs:example",
                ]
            },
            "duplicate Codex implicit-invocation skill",
        ),
        (
            {"codex_implicit_invocation_allowlist": ["manifest-docs:missing"]},
            "unknown Codex implicit-invocation skill",
        ),
    ),
)
def test_generator_rejects_invalid_codex_implicit_invocation_allowlist(
    repo_root: Path, tmp_path: Path, policy: dict, error: str
) -> None:
    fixture_root = tmp_path / "fixture-repo"
    build_fixture_repo(repo_root, fixture_root)
    policy_path = fixture_root / "configs/claude/config/skill_policies.yml"
    policy_path.write_text(yaml.safe_dump(policy), encoding="utf-8")

    with pytest.raises(GenerationError, match=error):
        render_views(fixture_root, output_root=tmp_path / "views", check=False)


def test_adhd_views_generate_effective_antigravity_and_devin_context(
    repo_root: Path, tmp_path: Path
) -> None:
    render_views(repo_root, output_root=tmp_path, check=False)
    bundle = tmp_path / "manifest-i-have-adhd"
    antigravity = json.loads(
        (bundle / "antigravity-extension.json").read_text(encoding="utf-8")
    )
    guidance = (
        repo_root / "plugins/manifest-i-have-adhd/guidance/always-on.md"
    ).read_text(encoding="utf-8")

    assert antigravity["contextFileName"] == "guidance/always-on.md"
    assert (bundle / "devin/global-rule.md").read_text(encoding="utf-8") == guidance


def test_codex_lifecycle_events_are_independent_native_components(
    repo_root: Path, tmp_path: Path
) -> None:
    render_views(repo_root, output_root=tmp_path, check=False)
    view = json.loads(
        (tmp_path / "manifest-workspace/plugin.json").read_text(encoding="utf-8")
    )["harnesses"]["codex"]
    hooks = {item["id"] for item in view["components"]["hooks"]}

    assert {
        "codex-session-start",
        "codex-stop",
        "codex-permission-request",
    } <= hooks


def test_generator_does_not_vendor_delegate_model_policy_runtime(
    repo_root: Path, tmp_path: Path
) -> None:
    render_views(repo_root, output_root=tmp_path, check=False)
    bundled = tmp_path / "manifest-delegate/manifest_model_policy"

    assert not bundled.exists()


def test_generator_emits_release_command_catalog(
    repo_root: Path, tmp_path: Path
) -> None:
    render_views(repo_root, output_root=tmp_path, check=False)
    catalog_path = tmp_path / "manifest-workspace/skills/help/catalog/commands.json"
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))

    assert len(catalog["commands"]) == 119
    assert any(
        command["qualified_name"] == "manifest-workspace:parallel-agent"
        for command in catalog["commands"]
    )


def test_generator_translates_model_policy_for_every_target_and_agy_alias(
    repo_root: Path, tmp_path: Path
) -> None:
    fixture_root = tmp_path / "fixture-repo"
    build_fixture_repo(repo_root, fixture_root)
    skill = fixture_root / "plugins/manifest-docs/skills/example/SKILL.md"
    skill.write_text(
        "---\n"
        "name: example\n"
        "description: Example fixture skill.\n"
        "models:\n"
        "  codex: [advanced, flash, auto]\n"
        "  gemini: [pro, flash]\n"
        "  cursor: [advanced, auto]\n"
        "  agy: [flash, auto]\n"
        "model_fallback: {mode: auto}\n"
        "---\n",
        encoding="utf-8",
    )

    output_root = tmp_path / "views"
    render_views(fixture_root, output_root=output_root, check=False)
    gemini = json.loads(
        (output_root / "manifest-docs/gemini-extension.json").read_text()
    )
    generic = json.loads((output_root / "manifest-docs/plugin.json").read_text())

    expected = {
        "codex": ["advanced", "flash", "auto"],
        "gemini": ["pro", "flash"],
        "cursor": ["advanced", "auto"],
        "antigravity": ["flash", "auto"],
    }
    records = {
        "gemini": gemini["modelPolicy"][0],
        **{
            harness: generic["harnesses"][harness]["model_policy"][0]
            for harness in ("codex", "cursor", "antigravity")
        },
    }
    for harness, tiers in expected.items():
        record = records[harness]
        assert record["first_tier"] == tiers[0]
        assert record["tiers"] == tiers
        assert record["fallback_mode"] == "auto"
        assert record["launcher"] == (
            "manifest skill-run example "
            f"--harness {harness} --model-chain {','.join(tiers)} "
            "--model-fallback auto"
        )
        guidance = output_root / f"manifest-docs/guidance/model-policy-{harness}.md"
        assert guidance.is_file()
        assert record["launcher"] in guidance.read_text(encoding="utf-8")

    assert gemini["contextFileName"] == "guidance/model-policy-gemini.md"
    for harness in ("codex", "cursor", "antigravity"):
        assert {
            "id": "model-aware-skill-invocation",
            "path": f"guidance/model-policy-{harness}.md",
        } in generic["harnesses"][harness]["components"]["guidance"]


def test_marketplace_excludes_independent_addons_from_parity_count(
    repo_root: Path,
) -> None:
    contracts = load_domain_contracts(repo_root / "plugins")

    assert {contract.name for contract in contracts} == set(DOMAIN_BUNDLES)
    assert "manifest-docker" not in DOMAIN_BUNDLES


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
    build_fixture_repo(repo_root, fixture_root)
    render_views(fixture_root, check=False)
    marketplace_path = fixture_root / ".claude-plugin/marketplace.json"
    marketplace = json.loads(marketplace_path.read_text())
    addon = next(
        entry
        for entry in marketplace["plugins"]
        if entry["name"] == "manifest-delegate"
    )
    addon["description"] = "tampered generated addon metadata"
    marketplace_path.write_text(json.dumps(marketplace, indent=2) + "\n")

    report = render_views(fixture_root, check=True)

    assert marketplace_path in report.drifted_paths
    assert "tampered" in marketplace_path.read_text()


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

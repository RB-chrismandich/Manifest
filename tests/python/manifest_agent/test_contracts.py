from pathlib import Path

import pytest

from manifest_agent.contracts import (
    DOMAIN_BUNDLES,
    ContractError,
    load_contract,
    load_domain_contracts,
)
from manifest_agent.models import CapabilityTier


@pytest.fixture
def fixtures_dir() -> Path:
    return Path(__file__).parents[2] / "fixtures" / "plugin_contracts"


def test_loads_minimal_contract(fixtures_dir: Path) -> None:
    contract = load_contract(fixtures_dir / "minimal-valid.yml")

    assert contract.name == "manifest-docs"
    assert contract.components.skills_root == "skills"
    assert contract.capabilities.executables[CapabilityTier.REQUIRED] == (
        "git",
        "python3",
    )


def test_unknown_capability_tier_fails_closed(fixtures_dir: Path) -> None:
    with pytest.raises(ContractError, match="unknown capability tier"):
        load_contract(fixtures_dir / "unknown-tier.yml")


def test_reports_all_structural_errors(fixtures_dir: Path) -> None:
    with pytest.raises(ContractError) as error:
        load_contract(fixtures_dir / "missing-bundle.yml")

    assert "'bundle' is a required property" in str(error.value)
    assert "'bundle'" in error.value.errors[0]


def test_reports_structural_and_independent_semantic_errors(
    fixtures_dir: Path, tmp_path: Path
) -> None:
    contract_path = tmp_path / "mixed-errors.yml"
    contract_path.write_text(
        (fixtures_dir / "minimal-valid.yml")
        .read_text()
        .replace("schema_version: 1", "schema_version: 2")
        .replace(
            "  executables:\n    required: [git, python3]\n    default: []",
            "  executables:\n    required: [git, python3]\n    default: [git]",
        ),
        encoding="utf-8",
    )

    with pytest.raises(ContractError) as error:
        load_contract(contract_path)

    assert "1 was expected" in str(error.value)
    assert "'git' is declared in both 'required' and 'default' tiers" in str(
        error.value
    )


def test_component_semantic_errors_survive_invalid_capabilities(
    fixtures_dir: Path, tmp_path: Path
) -> None:
    contract_path = tmp_path / "invalid-capabilities.yml"
    contract_path.write_text(
        (fixtures_dir / "minimal-valid.yml")
        .read_text()
        .replace(
            "capabilities:\n  mcp:\n    required: []\n    default: []\n    optional: []\n"
            "  executables:\n    required: [git, python3]\n    default: []\n    optional: []",
            "capabilities: []",
        )
        .replace(
            "agents: []",
            "agents:\n    - id: repeated\n      path: agents/one.py\n"
            "    - id: repeated\n      path: agents/two.py",
        ),
        encoding="utf-8",
    )

    with pytest.raises(ContractError) as error:
        load_contract(contract_path)

    assert "[] is not of type 'object'" in str(error.value)
    assert "duplicate component id 'repeated'" in str(error.value)


def test_component_paths_must_be_normalized(fixtures_dir: Path, tmp_path: Path) -> None:
    contract_path = tmp_path / "not-normalized.yml"
    contract_path.write_text(
        (fixtures_dir / "minimal-valid.yml")
        .read_text()
        .replace(
            "agents: []",
            "agents:\n    - id: duplicate-separator\n      path: agents//run.py",
        ),
        encoding="utf-8",
    )

    with pytest.raises(ContractError, match="does not match"):
        load_contract(contract_path)


def test_skill_include_globs_must_be_safe_relative_patterns(
    fixtures_dir: Path, tmp_path: Path
) -> None:
    contract_path = tmp_path / "unsafe-include.yml"
    contract_path.write_text(
        (fixtures_dir / "minimal-valid.yml")
        .read_text()
        .replace('include: ["*/SKILL.md"]', 'include: ["../../outside/**"]'),
        encoding="utf-8",
    )

    with pytest.raises(ContractError, match="does not match"):
        load_contract(contract_path)


def test_reports_all_semantic_errors(fixtures_dir: Path, tmp_path: Path) -> None:
    contract_path = tmp_path / "semantic-errors.yml"
    contract_path.write_text(
        (fixtures_dir / "minimal-valid.yml")
        .read_text()
        .replace(
            "  executables:\n    required: [git, python3]\n    default: []",
            "  executables:\n    required: [git, python3]\n    default: [git]",
        )
        .replace(
            "agents: []",
            "agents:\n    - id: repeated\n      path: agents/one.py\n"
            "    - id: repeated\n      path: agents/two.py",
        ),
        encoding="utf-8",
    )

    with pytest.raises(ContractError) as error:
        load_contract(contract_path)

    assert "'git' is declared in both 'required' and 'default' tiers" in str(
        error.value
    )
    assert "duplicate component id 'repeated'" in str(error.value)


def test_domain_loader_requires_exact_nine(tmp_path: Path) -> None:
    with pytest.raises(ContractError, match="expected 9 domain contracts"):
        load_domain_contracts(tmp_path)


def test_domain_loader_rejects_paths_outside_bundle(
    fixtures_dir: Path, tmp_path: Path
) -> None:
    bundle = tmp_path / "manifest-docs"
    bundle.mkdir()
    external_assets = tmp_path / "external-assets"
    external_assets.mkdir()
    (bundle / "agents").symlink_to(external_assets, target_is_directory=True)
    (bundle / "manifest-capabilities.yml").write_text(
        (fixtures_dir / "minimal-valid.yml")
        .read_text()
        .replace(
            "agents: []", "agents:\n    - id: escaped\n      path: agents/escaped.py"
        ),
        encoding="utf-8",
    )

    with pytest.raises(ContractError, match="escapes its bundle"):
        load_domain_contracts(tmp_path)


def test_domain_loader_requires_an_existing_skills_directory(
    fixtures_dir: Path, tmp_path: Path
) -> None:
    bundle = tmp_path / "manifest-docs"
    bundle.mkdir()
    (bundle / "manifest-capabilities.yml").write_text(
        (fixtures_dir / "minimal-valid.yml").read_text(), encoding="utf-8"
    )

    with pytest.raises(ContractError, match="must exist and be a directory"):
        load_domain_contracts(tmp_path)


def test_domain_loader_rejects_skill_include_symlink_escapes(
    fixtures_dir: Path, tmp_path: Path
) -> None:
    bundle = tmp_path / "manifest-docs"
    skills_root = bundle / "skills"
    skills_root.mkdir(parents=True)
    external_assets = tmp_path / "external-assets"
    external_assets.mkdir()
    (external_assets / "SKILL.md").write_text("external", encoding="utf-8")
    (skills_root / "linked").symlink_to(external_assets, target_is_directory=True)
    (bundle / "manifest-capabilities.yml").write_text(
        (fixtures_dir / "minimal-valid.yml")
        .read_text()
        .replace('include: ["*/SKILL.md"]', 'include: ["linked/SKILL.md"]'),
        encoding="utf-8",
    )

    with pytest.raises(ContractError, match="expands outside its bundle"):
        load_domain_contracts(tmp_path)


def test_unknown_capability_tiers_each_have_a_diagnostic(
    fixtures_dir: Path, tmp_path: Path
) -> None:
    contract_path = tmp_path / "multiple-unknown-tiers.yml"
    contract_path.write_text(
        (fixtures_dir / "unknown-tier.yml")
        .read_text()
        .replace(
            "    experimental: [docs-mcp]",
            "    experimental: [docs-mcp]\n    preview: [docs-preview]",
        ),
        encoding="utf-8",
    )

    with pytest.raises(ContractError) as error:
        load_contract(contract_path)

    assert (
        error.value.errors.count(
            "capabilities.mcp: unknown capability tier 'experimental'"
        )
        == 1
    )
    assert (
        error.value.errors.count("capabilities.mcp: unknown capability tier 'preview'")
        == 1
    )


def test_domain_bundle_catalog_is_fixed() -> None:
    assert DOMAIN_BUNDLES == (
        "manifest-code-quality",
        "manifest-docs",
        "manifest-forge",
        "manifest-graphify",
        "manifest-ops",
        "manifest-security",
        "manifest-spec-planning",
        "manifest-workspace",
        "stitch-design",
    )

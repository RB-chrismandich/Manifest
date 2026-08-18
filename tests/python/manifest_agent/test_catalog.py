import json
from dataclasses import replace
from pathlib import Path

import pytest

from manifest_agent.catalog import CatalogError, load_catalog
from manifest_agent.contracts import load_addon_contracts
from manifest_agent.service import ManifestService
from manifest_agent.service_state import bundle_checksums


def test_catalog_preserves_complete_marketplace_order() -> None:
    catalog = load_catalog(Path.cwd() / ".claude-plugin/marketplace.json")
    assert catalog[-1].name == "manifest-i-have-adhd"
    assert {row.name for row in catalog} >= {
        "manifest-delegate",
        "manifest-i-have-adhd",
    }


def test_catalog_rejects_duplicate_names(tmp_path: Path) -> None:
    (tmp_path / "plugins/one").mkdir(parents=True)
    path = tmp_path / ".claude-plugin/marketplace.json"
    path.parent.mkdir()
    path.write_text(
        json.dumps(
            {
                "plugins": [
                    {"name": "one", "version": "1.0.0", "source": "./plugins/one"},
                    {"name": "one", "version": "1.0.1", "source": "./plugins/one"},
                ]
            }
        )
    )
    with pytest.raises(CatalogError, match="duplicate"):
        load_catalog(path)


def test_addon_contract_participates_in_desired_identity_and_checksums() -> None:
    service = ManifestService(source=Path.cwd(), harnesses=("codex",))

    desired, error = service._desired_state()

    assert error is None and desired is not None
    assert [contract.name for contract in desired.addon_contracts] == [
        "manifest-i-have-adhd"
    ]
    addon = desired.addon_contracts[0]
    assert {component.id for component in addon.components.hooks} == {
        "adhd-session-start"
    }
    assert {component.id for component in addon.components.runtime} == {
        "adhd-hook-runtime"
    }
    assert "manifest-i-have-adhd" in bundle_checksums(desired)


def test_marketplace_version_must_match_addon_contract() -> None:
    addons = load_addon_contracts(Path.cwd() / "plugins")
    service = ManifestService(
        source=Path.cwd(),
        harnesses=("codex",),
        addon_contract_loader=lambda _root: (replace(addons[0], version="9.9.9"),),
    )

    desired, error = service._desired_state()

    assert desired is None
    assert "manifest-i-have-adhd" in error
    assert "disagrees" in error

"""Codex native catalog verification tests."""

from __future__ import annotations

from dataclasses import replace

from manifest_agent.adapters.codex import CodexAdapter
from manifest_agent.contracts import (
    DOMAIN_BUNDLES,
    Capabilities,
    CompatibilityStatus,
    Component,
    Components,
    Provenance,
)
from manifest_agent.models import (
    BundleContract,
    CapabilityTier,
    CatalogPlugin,
    DesiredState,
    ResultState,
)
from tests.python.manifest_agent._codex_adapter_test_support import (
    QueueRunner,
    command,
    installed_json,
    marketplace_json,
)
from tests.python.manifest_agent._codex_adapter_test_support import (
    desired as desired,
)

ADDON_NAME = "manifest-i-have-adhd"


def _write_addon_components(desired: DesiredState) -> None:
    addon_root = desired.release_root / f"plugins/{ADDON_NAME}"
    for relative in (
        "skills/i-have-adhd/SKILL.md",
        "hooks/hooks.json",
        "hooks/always_on.py",
        "guidance/always-on.md",
    ):
        path = addon_root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("fixture\n", encoding="utf-8")


def _addon_contract() -> BundleContract:
    empty_tiers = {
        CapabilityTier.REQUIRED: (),
        CapabilityTier.DEFAULT: (),
        CapabilityTier.OPTIONAL: (),
    }
    return BundleContract(
        ADDON_NAME,
        "0.1.0",
        "fixture addon",
        "fixture",
        Components(
            "skills",
            ("*/SKILL.md",),
            (),
            (Component("session-start", "hooks/hooks.json"),),
            (Component("runtime", "hooks/always_on.py"),),
            (Component("guidance", "guidance/always-on.md"),),
        ),
        Capabilities(
            empty_tiers,
            {**empty_tiers, CapabilityTier.REQUIRED: ("python3",)},
        ),
        {
            "claude": CompatibilityStatus("native"),
            "codex": CompatibilityStatus("native"),
        },
        Provenance("https://example.invalid", "MIT", "LICENSE", "test"),
    )


def _with_addon(desired: DesiredState) -> DesiredState:
    catalog = (
        *(CatalogPlugin(name, "0.2.0", f"./plugins/{name}") for name in DOMAIN_BUNDLES),
        CatalogPlugin(ADDON_NAME, "0.1.0", f"./plugins/{ADDON_NAME}"),
    )
    return replace(
        desired,
        addon_contracts=(_addon_contract(),),
        catalog_plugins=catalog,
    )


def test_codex_verifies_addon_contract_components_and_executables(
    desired: DesiredState,
) -> None:
    _write_addon_components(desired)
    desired = _with_addon(desired)
    runner = QueueRunner(
        [
            command(
                stdout=marketplace_json(
                    desired.marketplace_source.source,
                    desired.marketplace_source.source,
                )
            ),
            command(
                stdout=installed_json(
                    desired,
                    names=(*DOMAIN_BUNDLES, "manifest-i-have-adhd"),
                )
            ),
        ]
    )

    result = CodexAdapter(runner=runner, which=lambda _name: None).inspect(desired)

    assert result.state is ResultState.BLOCKED
    assert "manifest-i-have-adhd:executable:python3" in " ".join(result.errors)


from manifest_agent.adapters.codex_catalog import installed_manifest_ids
from manifest_agent.adapters.codex_common import MARKETPLACE


def test_installed_manifest_ids_filters_correctly() -> None:
    rows = [
        # Should be included: matches marketplace, installed is True
        {"pluginId": f"manifest-workspace@{MARKETPLACE}", "installed": True},
        # Should be included: matches marketplace, installed is not explicitly False
        {"pluginId": f"manifest-core@{MARKETPLACE}"},
        # Should be excluded: installed is False
        {"pluginId": f"manifest-cli@{MARKETPLACE}", "installed": False},
        # Should be excluded: doesn't match marketplace
        {"pluginId": "some-other-plugin@other"},
        # Should be excluded: missing pluginId
        {"installed": True},
        # Should be excluded: invalid pluginId type
        {"pluginId": 123, "installed": True},
    ]

    result = installed_manifest_ids(rows)

    assert result == {
        f"manifest-workspace@{MARKETPLACE}",
        f"manifest-core@{MARKETPLACE}",
    }


from manifest_agent.adapters.codex_catalog import authenticated_catalog
from manifest_agent.models import HarnessReceipt, OwnedEntry
from manifest_agent.ownership import owned_codex_catalog_entry


def test_authenticated_catalog_success() -> None:
    snapshot = [{"name": "plugin", "version": "1.0", "source": "url"}]
    entry = owned_codex_catalog_entry(snapshot)

    receipt = HarnessReceipt(
        harness="test",
        adapter_version="1",
        native_version="1",
        plugin_ids=("test",),
        owned_entries=(entry,),
        capabilities={},
        verified=True,
    )
    result = authenticated_catalog(receipt, None)
    assert result == snapshot


def test_authenticated_catalog_invalid_ownership() -> None:
    snapshot = [{"name": "plugin", "version": "1.0", "source": "url"}]
    entry = owned_codex_catalog_entry(snapshot)

    invalid_entry = OwnedEntry(
        kind=entry.kind,
        identifier=entry.identifier,
        ownership_marker=entry.ownership_marker,
        previous_checksum="invalid",
    )

    receipt = HarnessReceipt(
        harness="test",
        adapter_version="1",
        native_version="1",
        plugin_ids=("test",),
        owned_entries=(invalid_entry,),
        capabilities={},
        verified=True,
    )
    result = authenticated_catalog(receipt, None)
    assert result is None


def test_authenticated_catalog_multiple_entries() -> None:
    snapshot = [{"name": "plugin", "version": "1.0", "source": "url"}]
    entry = owned_codex_catalog_entry(snapshot)

    receipt = HarnessReceipt(
        harness="test",
        adapter_version="1",
        native_version="1",
        plugin_ids=("test",),
        owned_entries=(entry, entry),
        capabilities={},
        verified=True,
    )
    result = authenticated_catalog(receipt, None)
    assert result is None

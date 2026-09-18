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


from unittest.mock import patch

from manifest_agent.adapters.codex_catalog import observe_restoration
from manifest_agent.models import OwnedEntry


def test_observe_restoration_routing() -> None:
    entry_ambiguous = OwnedEntry(
        kind="unknown", identifier="id", ownership_marker="marker"
    )
    assert observe_restoration(entry_ambiguous) == "ambiguous"

    with patch(
        "manifest_agent.adapters.codex_catalog._observe_skill_restoration"
    ) as mock_skill:
        mock_skill.return_value = "skill_result"
        entry_skill = OwnedEntry(
            kind="codex-skill-source",
            identifier="id",
            ownership_marker="marker",
            target_path="/path/to/skill",
        )
        result = observe_restoration(entry_skill)
        assert result == "skill_result"
        mock_skill.assert_called_once_with(entry_skill)

    with patch(
        "manifest_agent.adapters.codex_catalog._observe_enabled_restoration"
    ) as mock_enabled:
        mock_enabled.return_value = "enabled_result"
        entry_enabled = OwnedEntry(
            kind="plugin-enabled-state",
            identifier="id",
            ownership_marker="marker",
            target_path="/path/to/enabled",
        )
        result = observe_restoration(entry_enabled)
        assert result == "enabled_result"
        mock_enabled.assert_called_once_with(entry_enabled)

    with patch(
        "manifest_agent.adapters.codex_catalog._observe_skill_restoration"
    ) as mock_skill_missing_path:
        entry_skill_missing = OwnedEntry(
            kind="codex-skill-source", identifier="id", ownership_marker="marker"
        )
        result = observe_restoration(entry_skill_missing)
        assert result == "ambiguous"
        mock_skill_missing_path.assert_not_called()

    with patch(
        "manifest_agent.adapters.codex_catalog._observe_enabled_restoration"
    ) as mock_enabled_missing_path:
        entry_enabled_missing = OwnedEntry(
            kind="plugin-enabled-state", identifier="id", ownership_marker="marker"
        )
        result = observe_restoration(entry_enabled_missing)
        assert result == "ambiguous"
        mock_enabled_missing_path.assert_not_called()

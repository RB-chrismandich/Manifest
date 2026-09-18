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


def test_desired_target_identity(desired: DesiredState) -> None:
    from dataclasses import replace
    from pathlib import Path

    from manifest_agent.adapters.codex_catalog import desired_target_identity
    from manifest_agent.models import (
        MarketplaceSourceKind,
    )

    # Create a completely stable fixture since the default 'desired' fixture uses tmp_path
    # inside nested models like marketplace_source and release_root.
    stable_desired = replace(
        desired,
        source="/stable/path",
        release_root=Path("/stable/release_root"),
        repository_url="https://github.com/example/repo",
        marketplace_source=replace(
            desired.marketplace_source,
            source="/stable/marketplace",
            kind=MarketplaceSourceKind.LOCAL,
        ),
    )

    # Note: we need to print the hash to establish the known good baseline once
    # print(f"NEW_HASH: {desired_target_identity(stable_desired)}")

    expected_hash = "c232b13ddc13f0c60a315dd6f181fa46c0aa2758271cc1cb1faac7d9e7eb9198"
    assert desired_target_identity(stable_desired) == expected_hash

"""Shared fixtures for Codex native marketplace adapter tests."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import replace
from pathlib import Path

import pytest

from manifest_agent.adapters.codex import CodexAdapter
from manifest_agent.contracts import (
    DOMAIN_BUNDLES,
    Capabilities,
    CompatibilityStatus,
    Components,
    Provenance,
)
from manifest_agent.models import (
    BundleContract,
    CapabilityTier,
    CatalogPlugin,
    CommandResult,
    DesiredState,
    HarnessReceipt,
    MarketplaceSource,
    MarketplaceSourceKind,
    OwnedEntry,
)
from manifest_agent.ownership import (
    authenticate_codex_receipt,
    owned_codex_catalog_entry,
)
from manifest_agent.process import CommandRunner


def _catalog_entry(names: Sequence[str], state_root: Path) -> OwnedEntry:
    snapshot = [
        {"name": name, "source": f"./plugins/{name}", "version": "0.1.0"}
        for name in names
    ]
    return owned_codex_catalog_entry(
        snapshot,
        marketplace={
            "identifier": "manifest",
            "source_kind": "local",
            "source": str(state_root.resolve()),
            "immutable_ref": None,
            "checkout_root": str(state_root.resolve()),
        },
        env={"XDG_STATE_HOME": str(state_root)},
    )


def _signed_receipt(receipt: HarnessReceipt, state_root: Path) -> HarnessReceipt:
    return authenticate_codex_receipt(receipt, env={"XDG_STATE_HOME": str(state_root)})


def _receipt(state_root: Path, *args, **kwargs) -> HarnessReceipt:
    return _signed_receipt(HarnessReceipt(*args, **kwargs), state_root)


class QueueRunner(CommandRunner):
    def __init__(self, results: Sequence[CommandResult]) -> None:
        self.results = list(results)
        self.log: list[list[str]] = []

    def run(
        self,
        argv: Sequence[str],
        *,
        env: Mapping[str, str] | None = None,
    ) -> CommandResult:
        del env
        self.log.append(list(argv))
        result = self.results.pop(0)
        return CommandResult(
            tuple(argv), result.returncode, result.stdout, result.stderr
        )


def command(
    *, returncode: int = 0, stdout: str = "{}", stderr: str = ""
) -> CommandResult:
    return CommandResult(("fixture",), returncode, stdout, stderr)


@pytest.fixture
def desired(tmp_path: Path) -> DesiredState:
    contracts = []
    for name in DOMAIN_BUNDLES:
        skill = tmp_path / "plugins" / name / "skills" / "help" / "SKILL.md"
        skill.parent.mkdir(parents=True)
        skill.write_text("# Help\n", encoding="utf-8")
        contracts.append(
            BundleContract(
                name,
                "0.2.0",
                "fixture",
                "fixture",
                Components("skills", ("*/SKILL.md",), (), (), (), ()),
                Capabilities(
                    {
                        CapabilityTier.REQUIRED: (),
                        CapabilityTier.DEFAULT: ("context7",)
                        if name == "manifest-workspace"
                        else (),
                        CapabilityTier.OPTIONAL: (),
                    },
                    {
                        CapabilityTier.REQUIRED: ("git",),
                        CapabilityTier.DEFAULT: (),
                        CapabilityTier.OPTIONAL: (),
                    },
                ),
                {
                    "claude": CompatibilityStatus("native"),
                    "codex": CompatibilityStatus("native"),
                },
                Provenance("https://example.invalid", "MIT", "LICENSE", "test"),
            )
        )
    return DesiredState(
        release_version="0.2.0",
        source_commit="a" * 40,
        source=str(tmp_path),
        marketplace_source=MarketplaceSource(
            MarketplaceSourceKind.LOCAL, str(tmp_path), None
        ),
        release_root=tmp_path,
        repository_url="https://example.invalid/Manifest",
        source_dirty=False,
        archive_sha256="b" * 64,
        contracts=tuple(contracts),
        selected_optional=frozenset(),
        requested_harnesses=("codex",),
    )


def marketplace_json(
    source: str, root: Path | str, *, source_type: str = "local"
) -> str:
    return json.dumps(
        {
            "marketplaces": [
                {
                    "name": "manifest",
                    "root": str(root),
                    "marketplaceSource": {
                        "sourceType": source_type,
                        "source": source,
                    },
                }
            ]
        }
    )


def marketplace_add_json(root: Path | str, *, already_added: bool = False) -> str:
    return json.dumps(
        {
            "marketplaceName": "manifest",
            "installedRoot": str(root),
            "alreadyAdded": already_added,
        }
    )


def plugin_add_json(desired: DesiredState, name: str) -> str:
    return json.dumps(
        {
            "pluginId": f"{name}@manifest",
            "name": name,
            "marketplaceName": "manifest",
            "version": "0.2.0",
            "installedPath": str(desired.bundle_path(name)),
        }
    )


def plugin_remove_json(name: str) -> str:
    return json.dumps(
        {
            "pluginId": f"{name}@manifest",
            "name": name,
            "marketplaceName": "manifest",
        }
    )


def mcp_list_json() -> str:
    """Return the complete Codex JSON shape for the catalog context7 server."""
    return json.dumps(
        [
            {
                "name": "context7",
                "enabled": True,
                "transport": {
                    "type": "streamable_http",
                    "url": "https://mcp.context7.com/mcp/oauth",
                },
                "auth_status": "o_auth",
            }
        ]
    )


def installed_json(
    desired: DesiredState,
    version: str = "0.2.0",
    *,
    extra: bool = False,
    enabled: bool = True,
    names: Sequence[str] = DOMAIN_BUNDLES,
) -> str:
    rows = [
        {
            "pluginId": f"{name}@manifest",
            "name": name,
            "marketplaceName": "manifest",
            "version": version,
            "installed": True,
            "enabled": enabled,
            "installedPath": str(desired.bundle_path(name)),
            "source": {
                "source": "local",
                "path": str(desired.bundle_path(name)),
            },
        }
        for name in names
    ]
    if extra:
        rows.append(
            {
                "pluginId": "adversarial-design-loop@manifest",
                "name": "adversarial-design-loop",
                "marketplaceName": "manifest",
                "version": "0.1.0",
                "installed": True,
                "enabled": True,
            }
        )
    return json.dumps({"installed": rows})


def _prepare_reconcile_handle(
    tmp_path: Path, desired: DesiredState, *, marketplace_present: bool = True
) -> tuple[CodexAdapter, object, dict[str, object]]:
    installed = tmp_path / "native-cache/manifest-workspace"
    installed.mkdir(parents=True)
    (installed / "payload.txt").write_text("prior release\n", encoding="utf-8")
    prior_row: dict[str, object] = {
        "pluginId": "manifest-workspace@manifest",
        "version": "0.1.0",
        "enabled": True,
        "installed": True,
        "installedPath": str(installed),
        "source": {"path": str(installed)},
    }
    adapter = CodexAdapter(
        runner=QueueRunner(
            [
                command(
                    stdout=marketplace_json(str(tmp_path), tmp_path)
                    if marketplace_present
                    else '{"marketplaces":[]}'
                ),
                command(stdout=json.dumps({"installed": [prior_row]})),
            ]
        ),
        which=lambda name: name,
        env={"XDG_STATE_HOME": str(tmp_path / "state")},
    )
    prior = replace(
        desired,
        catalog_plugins=(
            CatalogPlugin(
                "manifest-workspace", "0.1.0", "./plugins/manifest-workspace"
            ),
        ),
    )
    handle = adapter.prepare_reconcile(
        HarnessReceipt(
            "codex",
            "1",
            "prior",
            ("manifest-workspace@manifest",),
            (),
            {},
            True,
        ),
        prior,
        desired,
    )
    return adapter, handle, prior_row


def _prepare_prior_only_handle(
    tmp_path: Path, desired: DesiredState
) -> tuple[CodexAdapter, object, dict[str, object], Path]:
    installed = tmp_path / "native-cache/manifest-retired"
    installed.mkdir(parents=True)
    (installed / "payload.txt").write_text("retired release\n", encoding="utf-8")
    prior_row: dict[str, object] = {
        "pluginId": "manifest-retired@manifest",
        "version": "0.1.0",
        "enabled": True,
        "installed": True,
        "installedPath": str(installed),
        "source": {"path": str(installed)},
    }
    adapter = CodexAdapter(
        runner=QueueRunner(
            [
                command(stdout=marketplace_json(str(tmp_path), tmp_path)),
                command(stdout=json.dumps({"installed": [prior_row]})),
            ]
        ),
        which=lambda name: name,
        env={"XDG_STATE_HOME": str(tmp_path / "state")},
    )
    prior = replace(
        desired,
        catalog_plugins=(
            CatalogPlugin("manifest-retired", "0.1.0", "./plugins/manifest-retired"),
        ),
    )
    handle = adapter.prepare_reconcile(
        HarnessReceipt(
            "codex",
            "1",
            "prior",
            ("manifest-retired@manifest",),
            (),
            {},
            True,
        ),
        prior,
        desired,
    )
    return adapter, handle, prior_row, installed

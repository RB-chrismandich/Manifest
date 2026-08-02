"""Installed domain bundles must remain usable after coordinator removal."""

from __future__ import annotations

import os
import shutil
import socket
from pathlib import Path

import pytest

from manifest_agent.contracts import DOMAIN_BUNDLES, load_domain_contracts


@pytest.fixture
def installed_release(tmp_path: Path) -> Path:
    """Copy all domain bundles as a harness adapter would at user scope."""
    source = Path(__file__).resolve().parents[3] / "plugins"
    release = tmp_path / "isolated-release"
    for bundle in DOMAIN_BUNDLES:
        shutil.copytree(source / bundle, release / "plugins" / bundle)
    return release


def test_all_nine_bundle_contracts_load_after_source_and_uv_are_unavailable(
    installed_release: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The portable contracts require only their shipped bundle assets."""
    monkeypatch.setenv("UV_NO_NETWORK", "1")
    monkeypatch.setenv("PATH", "/usr/bin:/bin")
    monkeypatch.setattr(socket, "create_connection", lambda *args, **kwargs: (_ for _ in ()).throw(OSError("network disabled")))

    contracts = load_domain_contracts(installed_release / "plugins")

    assert tuple(contract.name for contract in contracts) == DOMAIN_BUNDLES
    assert all(
        (installed_release / "plugins" / contract.name / contract.components.skills_root).is_dir()
        for contract in contracts
    )
    assert "uvx" not in os.environ["PATH"]


def test_remote_capability_declaration_is_not_mistaken_for_offline_local_runtime(
    installed_release: Path,
) -> None:
    contracts = {contract.name: contract for contract in load_domain_contracts(installed_release / "plugins")}

    graphify = contracts["manifest-graphify"]
    assert graphify.capabilities.executables[next(tier for tier in graphify.capabilities.executables if tier.value == "default")] == ("graphify",)
    assert (installed_release / "plugins/manifest-graphify/runtime/graphify.json").is_file()

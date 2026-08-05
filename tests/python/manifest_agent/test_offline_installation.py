"""Installed domain bundles must remain usable after coordinator removal."""

from __future__ import annotations

import os
import shutil
import socket
import subprocess
import sys
from pathlib import Path

import pytest

from manifest_agent.contracts import DOMAIN_BUNDLES, load_domain_contracts
from manifest_agent.models import HarnessReceipt, HarnessResult, ResultState


class FakeBundleAdapter:
    """Fixture-native adapter that installs only a copied release tree."""

    def __init__(self, name: str, home: Path) -> None:
        self.name = name
        self.home = home
        self.root = home / ".manifest-fixture" / name

    def install(self, release: Path) -> HarnessResult:
        shutil.copytree(release / "plugins", self.root / "plugins")
        return HarnessResult(self.name, ResultState.READY, DOMAIN_BUNDLES, {})

    def list(self) -> tuple[str, ...]:
        return tuple(sorted(path.name for path in (self.root / "plugins").iterdir()))

    def info(self, bundle: str) -> Path:
        return self.root / "plugins" / bundle / "manifest-capabilities.yml"

    def uninstall(self, _receipt: HarnessReceipt) -> HarnessResult:
        shutil.rmtree(self.root)
        return HarnessResult(self.name, ResultState.READY, (), {})

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


def test_all_six_fake_adapters_install_list_info_and_uninstall_offline(
    installed_release: Path, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("UV_NO_NETWORK", "1")
    monkeypatch.setattr(socket, "create_connection", lambda *args, **kwargs: (_ for _ in ()).throw(OSError("network disabled")))
    for harness in ("claude", "codex", "gemini", "cursor", "antigravity", "devin"):
        adapter = FakeBundleAdapter(harness, tmp_path / "homes" / harness)
        installed = adapter.install(installed_release)
        assert installed.state is ResultState.READY
        assert adapter.list() == DOMAIN_BUNDLES
        for bundle in DOMAIN_BUNDLES:
            assert adapter.info(bundle).is_file()
        removed = adapter.uninstall(
            HarnessReceipt(harness, "fixture", "fixture-1", DOMAIN_BUNDLES, (), {}, True)
        )
        assert removed.state is ResultState.READY
        assert not adapter.root.exists()


def test_copied_bundle_local_entry_points_execute_without_coordinator_or_network(
    installed_release: Path, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    adapter = FakeBundleAdapter("claude", tmp_path / "home")
    adapter.install(installed_release)
    installed = adapter.root / "plugins"
    node = shutil.which("node")
    assert node is not None, "stitch's declared default node executable is unavailable"
    network_bin = tmp_path / "network-bin"
    network_bin.mkdir()
    for command in ("curl", "npm", "npx", "uv", "uvx"):
        script = network_bin / command
        script.write_text("#!/bin/sh\necho network disabled >&2\nexit 127\n", encoding="utf-8")
        script.chmod(0o755)
    monkeypatch.setenv("UV_NO_NETWORK", "1")
    monkeypatch.setattr(
        socket,
        "create_connection",
        lambda *args, **kwargs: (_ for _ in ()).throw(OSError("network disabled")),
    )
    shutil.rmtree(installed_release)
    environment = {
        "HOME": str(tmp_path / "home"),
        "PATH": f"{network_bin}:{Path(sys.executable).parent}:{Path(node).parent}:/usr/bin:/bin",
        "UV_NO_NETWORK": "1",
    }
    commands = (
        ("manifest-code-quality", (sys.executable, "skills/code-audit-constitution/scripts/constitution_check.py", "--help")),
        ("manifest-docs", (sys.executable, "runtime/docs_lint.py", "--help")),
        ("manifest-forge", (sys.executable, "runtime/python/tracker_registry.py", "--help")),
        ("manifest-ops", ("/bin/bash", "runtime/bin/version_pin.sh", "--help")),
        ("manifest-security", ("/bin/bash", "runtime/bin/ci_platform.sh", "--help")),
        ("manifest-spec-planning", (sys.executable, "runtime/plan_store.py", "--help")),
        ("manifest-workspace", (sys.executable, "skills/ai-hooks-integration/scripts/runtime/cli_wrapper.py", "--help")),
        ("stitch-design", (node, "runtime/dist/snapshot.mjs", "--help")),
    )
    for bundle, command in commands:
        completed = subprocess.run(
            command,
            cwd=installed / bundle,
            env=environment,
            check=False,
            text=True,
            capture_output=True,
        )
        assert completed.returncode == 0, completed.stderr
    # Graphify is intentionally a remote/default capability: its shipped
    # launcher, rather than a test double, must reject offline execution.
    graphify = subprocess.run(
        ("/bin/bash", "runtime/graphify.sh", "--help"),
        cwd=installed / "manifest-graphify",
        env=environment,
        check=False,
        text=True,
        capture_output=True,
    )
    assert graphify.returncode == 4
    assert graphify.stderr.strip() == "OFFLINE: manifest-graphify:executable:graphify requires network"

"""Filesystem-backed OMP command double; production adapter/service stay real."""

from __future__ import annotations

import json
import shutil
from dataclasses import replace
from pathlib import Path

from manifest_agent.adapters.omp import OmpAdapter
from manifest_agent.contracts import DOMAIN_BUNDLES, Capabilities, Component, Components
from manifest_agent.models import (
    BundleContract,
    CapabilityTier,
    CommandResult,
    DesiredState,
    MarketplaceSource,
    MarketplaceSourceKind,
)
from manifest_agent.release import ResolvedRelease
from manifest_agent.service import ManifestService
from manifest_agent.service_state import with_source_fingerprints


def put_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, sort_keys=True), encoding="utf-8")


def get_json(path, default):
    return json.loads(path.read_text()) if path.exists() else default


def make_desired(path: Path, version="1.0.0", *, git=False):
    names = (*DOMAIN_BUNDLES, "manifest-i-have-adhd")
    contracts, catalog = [], []
    for name in names:
        package_version = "0.2.4" if name == "manifest-i-have-adhd" else version
        bundle = path / "plugins" / name
        skill = bundle / "skills" / f"{name}-skill" / "SKILL.md"
        skill.parent.mkdir(parents=True)
        skill.write_text(f"---\nname: {name}-skill\n---\n{name}\n")
        put_json(
            bundle / ".claude-plugin/plugin.json",
            {"name": name, "version": package_version},
        )
        put_json(
            bundle / "package.json",
            {"name": f"@manifest/{name}", "version": package_version},
        )
        components = Components(
            "skills",
            ("*/SKILL.md",),
            (Component("reviewer", "agents/reviewer.md"),),
            (),
            (),
            (),
        )
        capabilities = Capabilities(
            {CapabilityTier.REQUIRED: ("context7",)},
            {CapabilityTier.REQUIRED: ("git",)},
        )
        contracts.append(
            BundleContract(
                name, package_version, name, "test", components, capabilities, None, None
            )
        )
        catalog.append(
            {
                "name": name,
                "version": package_version,
                "source": f"./plugins/{name}",
            }
        )
    put_json(
        path / ".claude-plugin/marketplace.json",
        {"name": "manifest", "plugins": catalog},
    )
    source = (
        MarketplaceSource(
            MarketplaceSourceKind.GIT,
            "https://example.invalid/Manifest.git",
            "a" * 40,
        )
        if git
        else MarketplaceSource(MarketplaceSourceKind.LOCAL, str(path), None)
    )
    return with_source_fingerprints(
        DesiredState(
            version,
            "a" * 40,
            "fixture",
            source,
            path,
            "https://example.invalid/Manifest",
            False,
            "b" * 64,
            tuple(contracts[:-1]),
            frozenset(),
            ("omp",),
            addon_contracts=(contracts[-1],),
        )
    )


class NativeRunner:
    def __init__(self):
        self.calls = []
        self.contexts = []
        self.failures = {}
        self.callback = None
        self.clock = 0
        self.skill_override = None
        self.last_root = None

    def fail(self, argv, *, after=False):
        self.failures[tuple(argv)] = after

    @property
    def mutations(self):
        return [
            argv
            for argv in self.calls
            if argv[1:3] != ("plugin", "list")
            and argv[1] not in {"--version", "read"}
        ]

    def run(self, argv, *, env=None, cwd=None):
        command = tuple(argv)
        self.calls.append(command)
        self.contexts.append((dict(env or {}), cwd))
        root = Path(env["HOME"]) / ".omp"
        self.last_root = root
        failure = self.failures.pop(command, None)
        if failure is False:
            return CommandResult(command, 1, "", "injected native failure")
        output = self._dispatch(command, root)
        if self.callback is not None:
            self.callback(command, root)
        if failure is True:
            return CommandResult(
                command, 1, output, "injected native failure after mutation"
            )
        return CommandResult(command, 0, output, "")

    def _dispatch(self, command, root):
        if command[1] == "--version":
            return "18.6.1\n"
        registry_path = root / "plugins/installed_plugins.json"
        lock_path = root / "plugins/omp-plugins.lock.json"
        marketplace_path = root / "marketplaces.json"
        registry = get_json(registry_path, {"version": 2, "plugins": {}})
        lock = get_json(lock_path, {"plugins": {}, "settings": {}})
        marketplaces = get_json(marketplace_path, {"version": 1, "marketplaces": []})
        if command[1] == "read":
            skill = command[2].removeprefix("skill://")
            if self.skill_override is not None:
                return f"[Skill file: {self.skill_override}]\n"
            for rows in registry["plugins"].values():
                path = Path(rows[0]["installPath"]) / "skills" / skill / "SKILL.md"
                if path.is_file():
                    return f"[Skill file: {path}]\n" + path.read_text()
            return ""
        action = command[2]
        if action == "list":
            rows = [
                {"id": plugin_id, "scope": "user", "entries": entries}
                for plugin_id, entries in registry["plugins"].items()
                if entries
            ]
            return json.dumps({"marketplace": rows})
        if action == "marketplace":
            if command[3] == "add":
                source = Path(command[4])
                catalog_path = (
                    root / "plugins/cache/marketplaces/manifest/marketplace.json"
                )
                put_json(
                    catalog_path,
                    get_json(source / ".claude-plugin/marketplace.json", {}),
                )
                self.clock += 1
                marketplaces["marketplaces"].append(
                    {
                        "name": "manifest",
                        "sourceType": "local",
                        "sourceUri": str(source),
                        "catalogPath": str(catalog_path),
                        "addedAt": str(self.clock),
                        "updatedAt": str(self.clock),
                    }
                )
            elif command[3] == "remove":
                marketplaces["marketplaces"] = [
                    row
                    for row in marketplaces["marketplaces"]
                    if row["name"] != command[4]
                ]
                shutil.rmtree(root / "plugins/cache/marketplaces" / command[4])
            put_json(marketplace_path, marketplaces)
            return ""
        plugin_id = command[3]
        name, _, marketplace = plugin_id.partition("@")
        old = registry["plugins"].get(plugin_id)
        if action in {"install", "upgrade"}:
            market = next(
                row
                for row in marketplaces["marketplaces"]
                if row["name"] == marketplace
            )
            catalog = get_json(Path(market["catalogPath"]), {})
            entry = next(row for row in catalog["plugins"] if row["name"] == name)
            source = Path(market["sourceUri"]) / entry["source"]
            cache = (
                root
                / "plugins/cache/plugins"
                / f"{marketplace}___{name}___{entry['version']}"
            )
            cache.parent.mkdir(parents=True, exist_ok=True)
            shutil.copytree(source, cache)
            package_name = get_json(cache / "package.json", {}).get("name", name)
            link = root / "plugins/node_modules" / package_name
            link.parent.mkdir(parents=True, exist_ok=True)
            if link.is_symlink():
                link.unlink()
            link.symlink_to(cache)
            prior = lock["plugins"].get(package_name, {})
            enabled = old[0].get("enabled", True) if old else True
            lock["plugins"][package_name] = {
                "version": entry["version"],
                "enabled": enabled,
                "enabledFeatures": prior.get("enabledFeatures"),
            }
            self.clock += 1
            registry["plugins"][plugin_id] = [
                {
                    "scope": "user",
                    "version": entry["version"],
                    "installPath": str(cache),
                    "installedAt": str(self.clock),
                    "enabled": enabled,
                }
            ]
            if old:
                shutil.rmtree(old[0]["installPath"])
        elif action == "uninstall":
            path = Path(old[0]["installPath"])
            # Native OMP reads the package name BEFORE deleting the cache.
            package_name = get_json(path / "package.json", {}).get("name", name)
            shutil.rmtree(path)
            registry["plugins"].pop(plugin_id)
            link = root / "plugins/node_modules" / package_name
            if link.is_symlink():
                link.unlink()
            lock["plugins"].pop(package_name, None)
            lock["settings"].pop(package_name, None)
        put_json(registry_path, registry)
        put_json(lock_path, lock)
        return ""


def make_adapter(tmp_path, runner=None):
    home = tmp_path / "home"
    home.mkdir(exist_ok=True)
    env = {
        "HOME": str(home),
        "XDG_DATA_HOME": "",
        "XDG_CACHE_HOME": str(tmp_path / "cache"),
        "XDG_STATE_HOME": str(tmp_path / "state"),
        "OMP_PROFILE": "",
        "PI_PROFILE": "",
        "PI_CONFIG_DIR": ".omp",
        "PI_CODING_AGENT_DIR": "",
    }
    runner = runner or NativeRunner()
    return (
        OmpAdapter(runner, which=lambda name: "/native/omp", env=env, cwd=tmp_path),
        runner,
    )


def make_service(tmp_path, adapter, desired, *, automatic=False):
    resolved = ResolvedRelease(
        desired.release_version,
        desired.source_commit,
        desired.source,
        desired.marketplace_source,
        desired.release_root,
        desired.repository_url,
        desired.source_dirty,
        desired.archive_sha256,
    )
    return ManifestService(
        source=desired.release_root,
        harnesses=() if automatic else ("omp",),
        adapters={"omp": adapter},
        receipt_path=tmp_path / "custom-authority/installation.json",
        release_resolver=lambda selector: resolved,
        contract_loader=lambda root: desired.contracts,
        addon_contract_loader=lambda root: desired.addon_contracts,
        capability_planner=lambda contracts, selected: object(),
    )


def with_receipt(desired, receipt):
    return replace(desired, prior_harness_receipts=(receipt,))

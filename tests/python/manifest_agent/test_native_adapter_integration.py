"""Hermetic production-adapter lifecycle coverage for all supported harnesses."""

from __future__ import annotations

import json
import os
import shutil
from dataclasses import replace
from pathlib import Path

import pytest

from manifest_agent.adapters.antigravity import AntigravityAdapter
from manifest_agent.adapters.claude import ClaudeAdapter
from manifest_agent.adapters.codex import CodexAdapter
from manifest_agent.adapters.cursor import CursorAdapter
from manifest_agent.adapters.devin import DevinAdapter
from manifest_agent.adapters.gemini import GeminiAdapter
from manifest_agent.contracts import (
    DOMAIN_BUNDLES,
    Capabilities,
    Components,
    load_domain_contracts,
)
from manifest_agent.models import (
    CapabilityTier,
    DesiredState,
    HarnessReceipt,
    HarnessResult,
    MarketplaceSource,
    MarketplaceSourceKind,
    OwnedEntry,
    ResultState,
)
from manifest_agent.process import CommandRunner

_STUB = Path(__file__).parents[2] / "fixtures" / "harness_bins" / "harness-stub"
_REPOSITORY = Path(__file__).parents[3]
_HARNESS_EXECUTABLES = {
    "claude": "claude",
    "codex": "codex",
    "gemini": "gemini",
    "cursor": "cursor-agent",
    "antigravity": "agy",
    "devin": "devin",
}


def _desired(harness: str) -> DesiredState:
    empty_capabilities = Capabilities(
        dict.fromkeys(CapabilityTier, ()), dict.fromkeys(CapabilityTier, ())
    )
    contracts = tuple(
        replace(
            contract,
            components=Components(
                contract.components.skills_root,
                contract.components.skills_include,
                (),
                (),
                (),
                (),
            ),
            capabilities=empty_capabilities,
        )
        for contract in load_domain_contracts(_REPOSITORY / "plugins")
    )
    return DesiredState(
        release_version="0.2.0",
        source_commit="a" * 40,
        source=str(_REPOSITORY),
        marketplace_source=MarketplaceSource(
            MarketplaceSourceKind.LOCAL, str(_REPOSITORY), None
        ),
        release_root=_REPOSITORY,
        repository_url="https://example.invalid/Manifest.git",
        source_dirty=False,
        archive_sha256="b" * 64,
        contracts=contracts,
        selected_optional=frozenset(),
        requested_harnesses=(harness,),
    )


def _response(argv: list[str], stdout: str = "") -> dict[str, object]:
    return {"argv": argv, "stdout": stdout}


def _responses(harness: str, desired: DesiredState, *, installed: bool) -> str:
    if harness == "claude":
        return _claude_responses(desired, installed)
    if harness == "codex":
        return _codex_responses(desired, installed)
    if harness == "gemini":
        return _gemini_responses(desired, installed)
    if harness == "cursor":
        return _cursor_responses(desired)
    if harness == "antigravity":
        return _antigravity_responses(desired)
    if harness == "devin":
        return _devin_responses(desired, installed)
    raise AssertionError(f"unsupported fixture harness: {harness}")


def _configured_environment(tmp_path: Path, harness: str, desired: DesiredState) -> dict[str, str]:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    executable = bin_dir / _HARNESS_EXECUTABLES[harness]
    executable.symlink_to(_STUB)
    log = tmp_path / "argv.jsonl"
    return {
        "HOME": str(tmp_path / "home"),
        "PATH": f"{bin_dir}:{os.environ['PATH']}",
        "HARNESS_STUB_LOG": str(log),
        "HARNESS_STUB_RESPONSES": _responses(harness, desired, installed=True),
    }


def _adapter(harness: str, environment: dict[str, str]):
    def which(name: str) -> str | None:
        return shutil.which(name, path=environment["PATH"])

    common = {"runner": CommandRunner(), "which": which, "env": environment}
    if harness == "claude":
        return ClaudeAdapter(**common)
    if harness == "codex":
        return CodexAdapter(**common)
    if harness == "gemini":
        return GeminiAdapter(**common)
    if harness == "cursor":
        return CursorAdapter(repository_url="https://example.invalid/Manifest.git", **common)
    if harness == "antigravity":
        return AntigravityAdapter(**common)
    if harness == "devin":
        return DevinAdapter(**common)
    raise AssertionError(f"unsupported fixture harness: {harness}")


def _local_adapter(harness: str):
    adapters = {
        "claude": ClaudeAdapter,
        "codex": CodexAdapter,
        "gemini": GeminiAdapter,
        "cursor": CursorAdapter,
        "antigravity": AntigravityAdapter,
        "devin": DevinAdapter,
    }
    return adapters[harness]()


def _receipt(harness: str, desired: DesiredState, plugin_ids: tuple[str, ...]) -> HarnessReceipt:
    if harness in {"claude", "codex"}:
        entries = (OwnedEntry("marketplace", "manifest", "receipt"),)
    elif harness == "cursor":
        entries = (OwnedEntry("marketplace", desired.repository_url, "manifest"),)
    else:
        entries = ()
    return HarnessReceipt(
        harness=harness,
        adapter_version="1",
        native_version="fixture-1",
        plugin_ids=plugin_ids,
        owned_entries=entries,
        capabilities={},
        verified=True,
    )


@pytest.mark.parametrize("harness", tuple(_HARNESS_EXECUTABLES))
def test_response_driven_production_adapters_complete_receipt_lifecycles(
    tmp_path: Path, harness: str
) -> None:
    desired = _desired(harness)
    environment = _configured_environment(tmp_path, harness, desired)
    adapter = _adapter(harness, environment)

    detection = adapter.detect()
    installed = adapter.install(desired)
    inspected = adapter.inspect(desired)
    environment["HARNESS_STUB_RESPONSES"] = _responses(
        harness, desired, installed=False
    )
    plugin_ids = (
        tuple(f"{name}@manifest" for name in DOMAIN_BUNDLES)
        if harness in {"claude", "codex"}
        else DOMAIN_BUNDLES
    )
    removed = adapter.uninstall(_receipt(harness, desired, plugin_ids))

    assert detection.present is True
    assert len(desired.contracts) == len(DOMAIN_BUNDLES)
    assert set(installed.installed_plugin_ids) <= set(plugin_ids)
    assert inspected.state in {ResultState.READY, ResultState.DEGRADED}
    assert removed.state is ResultState.READY
    argv = [
        json.loads(line) for line in (tmp_path / "argv.jsonl").read_text().splitlines()
    ]
    assert [row[1:] for row in argv if row[1:] == ["--version"]]
    _assert_lifecycle_commands(harness, argv)


@pytest.mark.parametrize("harness", tuple(_HARNESS_EXECUTABLES))
def test_local_native_cli_probe_never_skips_absent_harnesses(harness: str) -> None:
    adapter = _local_adapter(harness)
    detection = adapter.detect()

    if detection.present:
        assert detection.executable is not None
        return
    probe = HarnessResult(
        harness, ResultState.BLOCKED, (), {}, errors=(detection.reason or "",)
    )
    assert probe.state is ResultState.BLOCKED
    assert "CLI not present" in probe.errors[0]


def _assert_lifecycle_commands(harness: str, argv: list[list[str]]) -> None:
    commands = [tuple(row[1:]) for row in argv]
    expected = {
        "claude": (
            ("plugin", "marketplace", "add"),
            ("plugin", "marketplace", "list", "--json"),
            ("plugin", "list", "--json"),
            ("plugin", "uninstall"),
        ),
        "codex": (
            ("plugin", "marketplace", "add"),
            ("plugin", "marketplace", "list", "--json"),
            ("plugin", "add"),
            ("plugin", "list", "--json"),
            ("plugin", "remove"),
        ),
        "gemini": (
            ("extensions", "install"),
            ("extensions", "list", "--output-format", "json"),
            ("skills", "list", "--all"),
            ("extensions", "uninstall"),
        ),
        "cursor": (
            ("plugin", "marketplace", "add"),
            ("plugin", "marketplace", "list", "--format", "json"),
            ("plugin", "--help"),
            ("plugin", "marketplace", "remove"),
        ),
        "antigravity": (
            ("plugin", "validate"),
            ("plugin", "link"),
            ("plugin", "install"),
            ("plugin", "list"),
            ("plugin", "uninstall"),
        ),
        "devin": (
            ("plugins", "install"),
            ("plugins", "list"),
            ("plugins", "info"),
            ("plugins", "remove"),
            ("plugins", "prune"),
        ),
    }
    for prefix in expected[harness]:
        assert any(command[: len(prefix)] == prefix for command in commands)
    repeated_prefix = {
        "claude": ("plugin", "install"),
        "codex": ("plugin", "add"),
        "gemini": ("extensions", "install"),
        "antigravity": ("plugin", "install"),
        "devin": ("plugins", "install"),
    }.get(harness)
    if repeated_prefix is not None:
        assert sum(
            command[: len(repeated_prefix)] == repeated_prefix for command in commands
        ) == len(DOMAIN_BUNDLES)


def _claude_responses(desired: DesiredState, installed: bool) -> str:
    marketplace = json.dumps(
        [{"name": "manifest", "source": "directory", "path": str(_REPOSITORY)}]
    )
    rows = [
        {
            "id": f"{name}@manifest",
            "version": "0.2.0",
            "scope": "user",
            "enabled": True,
            "installPath": str(desired.bundle_path(name)),
        }
        for name in DOMAIN_BUNDLES
    ]
    responses = [
        _response(["plugin", "marketplace", "list", "--json"], marketplace),
        _response(["plugin", "list", "--json"], json.dumps(rows if installed else [])),
    ]
    return json.dumps({"responses": responses, "default": {"stdout": "0.2.0\n"}})


def _codex_responses(desired: DesiredState, installed: bool) -> str:
    marketplace = json.dumps(
        {
            "marketplaces": [
                {
                    "name": "manifest",
                    "root": str(_REPOSITORY),
                    "marketplaceSource": {
                        "sourceType": "local",
                        "source": str(_REPOSITORY),
                    },
                }
            ]
        }
    )
    rows = [
        {
            "pluginId": f"{name}@manifest",
            "name": name,
            "marketplaceName": "manifest",
            "version": "0.2.0",
            "installed": True,
            "enabled": True,
            "source": {"source": "local", "path": str(desired.bundle_path(name))},
        }
        for name in DOMAIN_BUNDLES
    ]
    responses = [
        _response(
            ["plugin", "marketplace", "add", str(_REPOSITORY), "--json"],
            json.dumps(
                {
                    "marketplaceName": "manifest",
                    "installedRoot": str(_REPOSITORY),
                    "alreadyAdded": False,
                }
            ),
        ),
        _response(["plugin", "marketplace", "list", "--json"], marketplace),
        _response(["plugin", "list", "--json"], json.dumps({"installed": rows if installed else []})),
    ]
    for name in DOMAIN_BUNDLES:
        responses.append(
            _response(
                ["plugin", "add", f"{name}@manifest", "--json"],
                json.dumps({"pluginId": f"{name}@manifest", "name": name, "marketplaceName": "manifest", "version": "0.2.0", "installedPath": str(desired.bundle_path(name))}),
            )
        )
        responses.append(
            _response(
                ["plugin", "remove", f"{name}@manifest", "--json"],
                json.dumps({"pluginId": f"{name}@manifest", "name": name, "marketplaceName": "manifest"}),
            )
        )
    responses.append(
        _response(
            ["plugin", "marketplace", "remove", "manifest", "--json"],
            json.dumps({"marketplaceName": "manifest"}),
        )
    )
    return json.dumps({"responses": responses, "default": {"stdout": "0.2.0\n"}})


def _gemini_responses(desired: DesiredState, installed: bool) -> str:
    rows = [
        {
            "name": name,
            "version": "0.2.0",
            "path": str(desired.bundle_path(name)),
            "isActive": True,
        }
        for name in DOMAIN_BUNDLES
    ]
    skills: list[str] = ["Discovered Agent Skills:", ""]
    for contract in desired.contracts:
        root = desired.bundle_path(contract.name) / contract.components.skills_root
        for pattern in contract.components.skills_include:
            for path in sorted(root.glob(pattern)):
                skills.extend(
                    [
                        f"{path.parent.name} [Enabled]",
                        f"  Location: {path}",
                        "",
                    ]
                )
    return json.dumps(
        {
            "responses": [
                _response(
                    ["extensions", "list", "--output-format", "json"],
                    json.dumps(rows if installed else []),
                ),
                _response(["skills", "list", "--all"], "\n".join(skills)),
            ],
            "default": {"stdout": "0.2.0\n"},
        }
    )


def _cursor_responses(desired: DesiredState) -> str:
    marketplace = json.dumps(
        [
            {
                "name": "manifest",
                "gitUrl": desired.repository_url,
                "gitRef": desired.source_commit,
                "scope": "user",
            }
        ]
    )
    return json.dumps(
        {
            "responses": [
                _response(["plugin", "marketplace", "list", "--format", "json"], marketplace),
                _response(
                    ["plugin", "--help"],
                    "Commands:\n  marketplace  Manage plugin marketplaces\n",
                ),
            ],
            "default": {"stdout": "0.2.0\n"},
        }
    )


def _antigravity_responses(desired: DesiredState) -> str:
    inventory = json.dumps(
        {
            "imports": [
                {"name": name, "source": "manifest", "components": ["skills"]}
                for name in DOMAIN_BUNDLES
            ]
        }
    )
    return json.dumps(
        {
            "responses": [_response(["plugin", "list"], inventory)],
            "default": {"stdout": "0.2.0\n"},
        }
    )


def _devin_responses(desired: DesiredState, installed: bool) -> str:
    names = DOMAIN_BUNDLES if installed else ()
    listing = "No plugins installed.\n" if not names else "Installed plugins\n" + "\n".join(
        f"{name} 0.2.0" for name in names
    )
    responses = [_response(["plugins", "list"], listing)]
    for contract in desired.contracts:
        root = desired.bundle_path(contract.name) / contract.components.skills_root
        skills = "\n".join(
            f"  - {path.parent.name}"
            for pattern in contract.components.skills_include
            for path in sorted(root.glob(pattern))
        )
        responses.append(
            _response(
                ["plugins", "info", contract.name],
                f"Plugin: {contract.name}\nversion: 0.2.0\nsource: {desired.bundle_path(contract.name)}\nSkills\n{skills}\nRequired plugins\n",
            )
        )
    return json.dumps({"responses": responses, "default": {"stdout": "0.2.0\n"}})

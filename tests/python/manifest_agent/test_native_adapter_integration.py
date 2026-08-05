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


def _response(
    argv: list[str], stdout: str = "", *, returncode: int = 0
) -> dict[str, object]:
    return {"argv": argv, "stdout": stdout, "returncode": returncode}


def _responses(harness: str, desired: DesiredState, phase: str) -> str:
    if harness == "claude":
        return _claude_responses(desired, phase)
    if harness == "codex":
        return _codex_responses(desired, phase)
    if harness == "gemini":
        return _gemini_responses(desired, phase)
    if harness == "cursor":
        return _cursor_responses(desired, phase)
    if harness == "antigravity":
        return _antigravity_responses(desired, phase)
    if harness == "devin":
        return _devin_responses(desired, phase)
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
        "HARNESS_STUB_RESPONSES": _responses(harness, desired, "detect"),
        "HARNESS_STUB_STATE": str(tmp_path / "stub-state.json"),
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
    environment["HARNESS_STUB_RESPONSES"] = _responses(harness, desired, "pre")
    before = adapter.inspect(desired)
    environment["HARNESS_STUB_RESPONSES"] = _responses(
        harness, desired, "installed"
    )
    installed = adapter.install(desired)
    inspected = adapter.inspect(desired)
    environment["HARNESS_STUB_RESPONSES"] = _responses(
        harness, desired, "removed"
    )
    plugin_ids = (
        tuple(f"{name}@manifest" for name in DOMAIN_BUNDLES)
        if harness in {"claude", "codex"}
        else DOMAIN_BUNDLES
    )
    removed = adapter.uninstall(_receipt(harness, desired, plugin_ids))

    assert detection.present is True
    assert len(desired.contracts) == len(DOMAIN_BUNDLES)
    assert before.state is not ResultState.READY
    if harness == "cursor":
        assert installed.state is ResultState.DEGRADED
        assert inspected.state is ResultState.DEGRADED
    else:
        assert installed.state is ResultState.READY
        assert installed.installed_plugin_ids == plugin_ids
        assert inspected.state is ResultState.READY
        assert inspected.installed_plugin_ids == plugin_ids
    assert removed.state is ResultState.READY
    argv = [
        json.loads(line) for line in (tmp_path / "argv.jsonl").read_text().splitlines()
    ]
    assert [row[1:] for row in argv if row[1:] == ["--version"]]
    _assert_lifecycle_commands(harness, desired, argv)


@pytest.mark.native
@pytest.mark.parametrize("harness", tuple(_HARNESS_EXECUTABLES))
def test_local_native_cli_probe_reports_blocked_absence(harness: str) -> None:
    adapter = _local_adapter(harness)
    detection = adapter.detect()

    if detection.present:
        assert detection.executable is not None
        return
    probe = HarnessResult(
        harness, ResultState.BLOCKED, (), {}, errors=(detection.reason or "",)
    )
    assert probe.state is ResultState.BLOCKED
    pytest.fail(f"BLOCKED native probe: {probe.errors[0]}")


def _assert_lifecycle_commands(
    harness: str, desired: DesiredState, argv: list[list[str]]
) -> None:
    commands = [tuple(row[1:]) for row in argv]
    bundle_paths = tuple(str(desired.bundle_path(name)) for name in DOMAIN_BUNDLES)
    expected_installs = {
        "claude": [
            ("plugin", "install", f"{name}@manifest", "--scope", "user")
            for name in DOMAIN_BUNDLES
        ],
        "codex": [
            ("plugin", "add", f"{name}@manifest", "--json")
            for name in DOMAIN_BUNDLES
        ],
        "gemini": [
            ("extensions", "install", path, "--consent", "--skip-settings")
            for path in bundle_paths
        ],
        "cursor": [
            (
                "plugin",
                "marketplace",
                "add",
                desired.repository_url,
                "--git-ref",
                desired.source_commit,
            )
        ],
        "antigravity": [
            ("plugin", "validate", path) for path in bundle_paths
        ]
        + [("plugin", "link", "manifest", str(desired.release_root))]
        + [
            ("plugin", "install", f"{name}@manifest") for name in DOMAIN_BUNDLES
        ],
        "devin": [
            ("plugins", "install", path, "--yes") for path in bundle_paths
        ],
    }
    expected_removals = {
        "claude": [
            ("plugin", "uninstall", f"{name}@manifest") for name in DOMAIN_BUNDLES
        ]
        + [("plugin", "marketplace", "remove", "manifest")],
        "codex": [
            ("plugin", "remove", f"{name}@manifest", "--json")
            for name in DOMAIN_BUNDLES
        ]
        + [("plugin", "marketplace", "remove", "manifest", "--json")],
        "gemini": [("extensions", "uninstall", name) for name in DOMAIN_BUNDLES],
        "cursor": [
            ("plugin", "marketplace", "remove", desired.repository_url)
        ],
        "antigravity": [
            ("plugin", "uninstall", name) for name in DOMAIN_BUNDLES
        ],
        "devin": [("plugins", "remove", name) for name in DOMAIN_BUNDLES]
        + [("plugins", "prune")],
    }
    assert _commands_in_order(commands, expected_installs[harness])
    assert _commands_in_order(commands, expected_removals[harness])


def _commands_in_order(
    commands: list[tuple[str, ...]], expected: list[tuple[str, ...]]
) -> bool:
    """Match each expected exact argv once, while preserving adapter command order."""
    matched = [command for command in commands if command in expected]
    return matched == expected


def _fixture(responses: list[dict[str, object]]) -> str:
    return json.dumps(
        {
            "responses": responses,
            "default": {"stderr": "unconfigured harness argv", "returncode": 97},
        }
    )


def _claude_responses(desired: DesiredState, phase: str) -> str:
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
    inspect_responses = [
        _response(["plugin", "marketplace", "list", "--json"], marketplace),
        _response(["plugin", "list", "--json"], json.dumps(rows)),
    ]
    if phase == "detect":
        return _fixture([_response(["--version"], "0.2.0\n")])
    if phase == "pre":
        return _fixture(
            [inspect_responses[0], _response(["plugin", "list", "--json"], "[]")]
        )
    if phase == "installed":
        responses = [
            _response(
                ["plugin", "marketplace", "add", str(_REPOSITORY), "--scope", "user"]
            ),
            *inspect_responses,
        ]
        responses.extend(
            _response(
                ["plugin", "install", f"{name}@manifest", "--scope", "user"]
            )
            for name in DOMAIN_BUNDLES
        )
        return _fixture(responses)
    if phase == "removed":
        responses = [
            _response(["plugin", "uninstall", f"{name}@manifest"])
            for name in DOMAIN_BUNDLES
        ]
        responses.extend(
            [
                _response(["plugin", "list", "--json"], "[]"),
                _response(["plugin", "marketplace", "remove", "manifest"]),
            ]
        )
        return _fixture(responses)
    raise AssertionError(f"unsupported fixture phase: {phase}")


def _codex_responses(desired: DesiredState, phase: str) -> str:
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
    inspect_responses = [
        _response(["plugin", "marketplace", "list", "--json"], marketplace),
        _response(["plugin", "list", "--json"], json.dumps({"installed": rows})),
    ]
    if phase == "detect":
        return _fixture([_response(["--version"], "0.2.0\n")])
    if phase == "pre":
        return _fixture(
            [
                inspect_responses[0],
                _response(["plugin", "list", "--json"], json.dumps({"installed": []})),
            ]
        )
    if phase == "installed":
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
            *inspect_responses,
        ]
        for name in DOMAIN_BUNDLES:
            responses.append(
            _response(
                ["plugin", "add", f"{name}@manifest", "--json"],
                json.dumps({"pluginId": f"{name}@manifest", "name": name, "marketplaceName": "manifest", "version": "0.2.0", "installedPath": str(desired.bundle_path(name))}),
            )
            )
        return _fixture(responses)
    if phase == "removed":
        responses = [
            _response(
                ["plugin", "remove", f"{name}@manifest", "--json"],
                json.dumps(
                    {
                        "pluginId": f"{name}@manifest",
                        "name": name,
                        "marketplaceName": "manifest",
                    }
                ),
            )
            for name in DOMAIN_BUNDLES
        ]
        responses.extend(
            [
                _response(["plugin", "list", "--json"], json.dumps({"installed": []})),
                _response(
                    ["plugin", "marketplace", "remove", "manifest", "--json"],
                    json.dumps({"marketplaceName": "manifest"}),
                ),
            ]
        )
        return _fixture(responses)
    raise AssertionError(f"unsupported fixture phase: {phase}")


def _gemini_responses(desired: DesiredState, phase: str) -> str:
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
    inspect_responses = [
        _response(
            ["extensions", "list", "--output-format", "json"], json.dumps(rows)
        ),
        _response(["skills", "list", "--all"], "\n".join(skills)),
    ]
    if phase == "detect":
        return _fixture([_response(["--version"], "0.2.0\n")])
    if phase == "pre":
        return _fixture(
            [
                _response(
                    ["extensions", "list", "--output-format", "json"], "[]"
                ),
                inspect_responses[1],
            ]
        )
    if phase == "installed":
        return _fixture(
            [
                *[
                    _response(
                        [
                            "extensions",
                            "install",
                            str(desired.bundle_path(name)),
                            "--consent",
                            "--skip-settings",
                        ]
                    )
                    for name in DOMAIN_BUNDLES
                ],
                *inspect_responses,
            ]
        )
    if phase == "removed":
        return _fixture(
            [
                _response(["extensions", "uninstall", name])
                for name in DOMAIN_BUNDLES
            ]
        )
    raise AssertionError(f"unsupported fixture phase: {phase}")


def _cursor_responses(desired: DesiredState, phase: str) -> str:
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
    if phase == "detect":
        return _fixture([_response(["--version"], "0.2.0\n")])
    if phase == "pre":
        return _fixture(
            [_response(["plugin", "marketplace", "list", "--format", "json"], "[]")]
        )
    if phase == "installed":
        return _fixture(
            [
                _response(
                    [
                        "plugin",
                        "marketplace",
                        "add",
                        desired.repository_url,
                        "--git-ref",
                        desired.source_commit,
                    ]
                ),
                _response(
                    ["plugin", "marketplace", "list", "--format", "json"], marketplace
                ),
                _response(
                    ["plugin", "--help"],
                    "Commands:\n  marketplace  Manage plugin marketplaces\n",
                ),
            ]
        )
    if phase == "removed":
        return _fixture(
            [
                _response(
                    ["plugin", "marketplace", "remove", desired.repository_url]
                )
            ]
        )
    raise AssertionError(f"unsupported fixture phase: {phase}")


def _antigravity_responses(desired: DesiredState, phase: str) -> str:
    inventory = json.dumps(
        {
            "imports": [
                {"name": name, "source": "manifest", "components": ["skills"]}
                for name in DOMAIN_BUNDLES
            ]
        }
    )
    if phase == "detect":
        return _fixture([_response(["--version"], "0.2.0\n")])
    if phase == "pre":
        return _fixture([_response(["plugin", "list"], '{"imports":[]}')])
    if phase == "installed":
        responses = [
            _response(["plugin", "validate", str(desired.bundle_path(name))])
            for name in DOMAIN_BUNDLES
        ]
        responses.append(
            _response(["plugin", "link", "manifest", str(desired.release_root)])
        )
        responses.extend(
            _response(["plugin", "install", f"{name}@manifest"])
            for name in DOMAIN_BUNDLES
        )
        responses.append(_response(["plugin", "list"], inventory))
        return _fixture(responses)
    if phase == "removed":
        return _fixture(
            [_response(["plugin", "uninstall", name]) for name in DOMAIN_BUNDLES]
        )
    raise AssertionError(f"unsupported fixture phase: {phase}")


def _devin_responses(desired: DesiredState, phase: str) -> str:
    installed_listing = "Installed plugins\n" + "\n".join(
        f"{name} 0.2.0" for name in DOMAIN_BUNDLES
    )
    info_responses: list[dict[str, object]] = []
    for contract in desired.contracts:
        root = desired.bundle_path(contract.name) / contract.components.skills_root
        skills = "\n".join(
            f"  - {path.parent.name}"
            for pattern in contract.components.skills_include
            for path in sorted(root.glob(pattern))
        )
        info_responses.append(
            _response(
                ["plugins", "info", contract.name],
                f"Plugin: {contract.name}\nversion: 0.2.0\nsource: {desired.bundle_path(contract.name)}\nSkills\n{skills}\nRequired plugins\n",
            )
        )
    if phase == "detect":
        return _fixture([_response(["--version"], "0.2.0\n")])
    if phase == "pre":
        return _fixture([_response(["plugins", "list"], "No plugins installed.\n"), *info_responses])
    if phase == "installed":
        responses = [
            _response(
                ["plugins", "install", str(desired.bundle_path(name)), "--yes"]
            )
            for name in DOMAIN_BUNDLES
        ]
        responses.extend([_response(["plugins", "list"], installed_listing), *info_responses])
        return _fixture(responses)
    if phase == "removed":
        return _fixture(
            [
                {
                    "argv": ["plugins", "list"],
                    "sequence": [
                        {"stdout": installed_listing},
                        {"stdout": "No plugins installed.\n"},
                        {"stdout": "No plugins installed.\n"},
                    ],
                },
                *[
                    _response(["plugins", "remove", name]) for name in DOMAIN_BUNDLES
                ],
                _response(["plugins", "prune"]),
            ]
        )
    raise AssertionError(f"unsupported fixture phase: {phase}")

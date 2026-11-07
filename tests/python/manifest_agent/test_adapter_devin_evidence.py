"""Devin 3000.x --local install, info parser, and fail-closed evidence tests."""

from __future__ import annotations

import json
import os
import shutil
import stat
from collections.abc import Mapping
from pathlib import Path

import pytest

from manifest_agent.adapters.devin import DevinAdapter
from manifest_agent.capabilities import load_mcp_catalog
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
    DesiredState,
    MarketplaceSource,
    MarketplaceSourceKind,
    ResultState,
)
from manifest_agent.process import CommandRunner

_TARGET_BUNDLE = "manifest-workspace"
_DESIGN_BUNDLE = "stitch-design"


def _rich_components(name: str) -> Components:
    if name != _TARGET_BUNDLE:
        return Components("skills", ("*/SKILL.md",), (), (), (), ())
    return Components(
        "skills",
        ("*/SKILL.md",),
        agents=(Component("reviewer", "agents/reviewer.md"),),
        hooks=(),
        runtime=(
            Component("lint-script", "runtime/lint.py"),
            Component("helper-dir", "runtime/helpers"),
        ),
        guidance=(Component("orchestration", "guidance/orchestration.md"),),
    )


def _rich_capabilities(
    name: str, *, mcp_tier: CapabilityTier = CapabilityTier.REQUIRED
) -> Capabilities:
    mcp = dict.fromkeys(CapabilityTier, ())
    if name == _TARGET_BUNDLE:
        mcp[mcp_tier] = ("context7",)
    if name == _DESIGN_BUNDLE:
        mcp[CapabilityTier.OPTIONAL] = ("stitch",)
    executables = {
        CapabilityTier.REQUIRED: ("python3",),
        CapabilityTier.DEFAULT: (),
        CapabilityTier.OPTIONAL: (),
    }
    return Capabilities(mcp, executables)


def _write_rich_bundle(tmp_path: Path, contract: BundleContract) -> None:
    root = tmp_path / "plugins" / contract.name
    skills = [f"skill-{contract.name}"]
    if contract.name == _TARGET_BUNDLE:
        skills.append("extra-skill")
    for skill_name in skills:
        skill_file = root / "skills" / skill_name / "SKILL.md"
        skill_file.parent.mkdir(parents=True, exist_ok=True)
        skill_file.write_text("# Skill\n", encoding="utf-8")
    declared_components: dict[str, list[dict[str, str]]] = {}
    for attr in ("agents", "hooks", "runtime", "guidance"):
        entries: list[dict[str, str]] = []
        for item in getattr(contract.components, attr):
            entries.append({"id": item.id, "path": item.path})
            asset = root / item.path
            if "." in Path(item.path).name:
                asset.parent.mkdir(parents=True, exist_ok=True)
                asset.write_text("# Component\n", encoding="utf-8")
            else:
                asset.mkdir(parents=True, exist_ok=True)
                (asset / "entry.py").write_text("# Helper\n", encoding="utf-8")
        if entries:
            declared_components[attr] = entries
    skill_paths = sorted(f"skills/{skill_name}" for skill_name in skills)
    devin_surface: dict[str, object] = {"mode": "native", "skills": skill_paths}
    if declared_components:
        devin_surface["components"] = declared_components
    payload = {
        "name": contract.name,
        "version": contract.version,
        "skills": skill_paths,
        "harnesses": {"devin": devin_surface},
    }
    for rel in ("plugin.json", ".devin-plugin/plugin.json"):
        target = root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(payload), encoding="utf-8")


def _build_desired(
    tmp_path: Path,
    *,
    mcp_tier: CapabilityTier = CapabilityTier.REQUIRED,
    selected_optional: frozenset[str] = frozenset(),
) -> DesiredState:
    contracts = []
    for name in DOMAIN_BUNDLES:
        contract = BundleContract(
            name,
            "0.7.0",
            "fixture",
            "fixture",
            _rich_components(name),
            _rich_capabilities(name, mcp_tier=mcp_tier),
            {"devin": CompatibilityStatus("native")},
            Provenance("https://example.invalid", "MIT", "LICENSE", "test"),
        )
        _write_rich_bundle(tmp_path, contract)
        contracts.append(contract)
    return DesiredState(
        release_version="0.7.0",
        source_commit="a" * 40,
        source=str(tmp_path),
        marketplace_source=MarketplaceSource(
            MarketplaceSourceKind.LOCAL, str(tmp_path), None
        ),
        release_root=tmp_path,
        repository_url="https://example.invalid/Manifest.git",
        source_dirty=False,
        archive_sha256="b" * 64,
        contracts=tuple(contracts),
        selected_optional=selected_optional,
        requested_harnesses=("devin",),
    )


def _devin_3000_info_output(desired: DesiredState, name: str) -> str:
    source = desired.bundle_path(name)
    lines = [
        f"Plugin: {name}",
        "  version: 0.7.0",
        f"  source: {source}",
        "  description: Portable Manifest bundle view.",
        "────────────────────────────────────────",
        "Skills",
        "────────────────────────────────────────",
        f"  /{name}:skill-{name} - Primary skill description wrapping onto",
        "      indented continuation words",
    ]
    if name == _TARGET_BUNDLE:
        lines.append(f"  {name}:extra-skill - Colon-qualified bundle skill")
    lines.extend(
        [
            "── Agents ──────────────────────────────",
            "  unverified-header-noise",
            "Hooks: (none)",
            "Rules",
            "--------------------",
            "  guidance/orchestration.md * (all)",
            "MCP servers: (none)",
            "====================",
            "Required plugins: (none)",
            "Optional plugins: (none)",
            "Forbidden plugins: (none)",
        ]
    )
    return "\n".join(lines) + "\n"


def _write_fake_devin_cli(
    tmp_path: Path, desired: DesiredState, *, installed: bool = True
) -> tuple[Path, Path]:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(parents=True, exist_ok=True)
    python_link = bin_dir / "python3"
    if not python_link.exists():
        python_link.symlink_to(Path(os.sys.executable))
    log_path = tmp_path / "devin-argv.jsonl"
    info_map = {
        c.name: _devin_3000_info_output(desired, c.name) for c in desired.all_contracts
    }
    listing = (
        "Installed plugins\n"
        + "\n".join(f"{c.name} {c.version}" for c in desired.all_contracts)
        if installed
        else "No plugins installed."
    )
    (tmp_path / "devin-responses.json").write_text(
        json.dumps({"list": listing, "info": info_map}), encoding="utf-8"
    )
    script = bin_dir / "devin"
    _write_fake_devin_script(script)
    return bin_dir, log_path


def _write_fake_devin_script(script: Path) -> None:
    lines = [
        "#!/usr/bin/env python3",
        "import json, os, pathlib, sys",
        "args = sys.argv[1:]",
        "with open(os.environ['FAKE_DEVIN_LOG'], 'a', encoding='utf-8') as fh:",
        "    fh.write(json.dumps(args) + '\\n')",
        "data = json.loads(pathlib.Path(os.environ['FAKE_DEVIN_DATA']).read_text())",
        "if args == ['--version']: print('devin 3000.10.31 (fake)')",
        "elif args[:2] == ['plugins', 'install']:",
        "    if '--local' not in args: sys.exit(2)",
        "elif args == ['plugins', 'list']: print(data['list'])",
        "elif args[:2] == ['plugins', 'info']: sys.stdout.write(data['info'][args[2]])",
        "elif args[:2] == ['mcp', 'add']:",
        "    cfg = pathlib.Path(os.environ['XDG_CONFIG_HOME']) / 'devin/mcp_config.json'",
        "    cfg.parent.mkdir(parents=True, exist_ok=True)",
        "    cfg.write_text(json.dumps({'mcpServers': {args[-2]: {'transport': 'http', 'url': args[-1]}}}))",
        "else: sys.exit(99)",
    ]
    script.write_text("\n".join(lines) + "\n", encoding="utf-8")
    script.chmod(script.stat().st_mode | stat.S_IXUSR)


def _isolated_env(tmp_path: Path, bin_dir: Path, log_path: Path) -> dict[str, str]:
    home = tmp_path / "home"
    home.mkdir(parents=True, exist_ok=True)
    return {
        "HOME": str(home),
        "XDG_CONFIG_HOME": str(home / ".config"),
        "XDG_DATA_HOME": str(home / ".local/share"),
        "XDG_STATE_HOME": str(home / ".local/state"),
        "XDG_CACHE_HOME": str(home / ".cache"),
        "PATH": str(bin_dir),
        "FAKE_DEVIN_LOG": str(log_path),
        "FAKE_DEVIN_DATA": str(tmp_path / "devin-responses.json"),
    }


def _adapter_for_env(env: Mapping[str, str]) -> DevinAdapter:
    return DevinAdapter(
        runner=CommandRunner(),
        which=lambda binary: shutil.which(binary, path=env["PATH"]),
        env=env,
    )


def _write_mcp_config(env: Mapping[str, str], servers: dict[str, object]) -> Path:
    cfg = Path(env["XDG_CONFIG_HOME"]) / "devin" / "mcp_config.json"
    cfg.parent.mkdir(parents=True, exist_ok=True)
    cfg.write_text(json.dumps({"mcpServers": servers}), encoding="utf-8")
    return cfg


def test_fake_devin_binary_receives_local_flag_and_verifies_all_four_categories(
    tmp_path: Path,
) -> None:
    desired = _build_desired(tmp_path)
    bin_dir, log_path = _write_fake_devin_cli(tmp_path, desired)
    env = _isolated_env(tmp_path, bin_dir, log_path)
    adapter = _adapter_for_env(env)

    installed = adapter.install(desired)
    inspected = adapter.inspect(desired)

    logged = [json.loads(line) for line in log_path.read_text().splitlines()]
    install_calls = [row for row in logged if row[:2] == ["plugins", "install"]]
    assert install_calls == [
        ["plugins", "install", "--local", str(desired.bundle_path(name)), "--yes"]
        for name in DOMAIN_BUNDLES
    ]
    for result in (installed, inspected):
        assert result.state is ResultState.READY
        assert result.errors == ()
        assert result.capabilities[f"{_TARGET_BUNDLE}:agent:reviewer"] == "verified"
        assert (
            result.capabilities[f"{_TARGET_BUNDLE}:runtime:lint-script"] == "verified"
        )
        assert result.capabilities[f"{_TARGET_BUNDLE}:runtime:helper-dir"] == "verified"
        assert (
            result.capabilities[f"{_TARGET_BUNDLE}:guidance:orchestration"]
            == "verified"
        )
        assert result.capabilities[f"{_TARGET_BUNDLE}:mcp:context7"] == "verified"
        assert result.capabilities[f"{_TARGET_BUNDLE}:skill:extra-skill"] == "verified"


@pytest.mark.parametrize(
    ("missing_category", "expected_identity"),
    [
        ("agent", f"{_TARGET_BUNDLE}:agent:reviewer"),
        ("runtime_file", f"{_TARGET_BUNDLE}:runtime:lint-script"),
        ("runtime_empty_dir", f"{_TARGET_BUNDLE}:runtime:helper-dir"),
        ("guidance", f"{_TARGET_BUNDLE}:guidance:orchestration"),
        ("mcp", f"{_TARGET_BUNDLE}:mcp:context7"),
    ],
)
def test_inspect_fails_closed_when_any_evidence_category_is_absent(
    tmp_path: Path, missing_category: str, expected_identity: str
) -> None:
    desired = _build_desired(tmp_path)
    bin_dir, log_path = _write_fake_devin_cli(tmp_path, desired)
    env = _isolated_env(tmp_path, bin_dir, log_path)
    catalog_context7 = load_mcp_catalog()["context7"]
    _write_mcp_config(
        env, {"context7": {"transport": "http", "url": catalog_context7.url}}
    )
    bundle_root = desired.bundle_path(_TARGET_BUNDLE)
    targets = {
        "agent": bundle_root / "agents/reviewer.md",
        "runtime_file": bundle_root / "runtime/lint.py",
        "runtime_empty_dir": bundle_root / "runtime/helpers/entry.py",
        "guidance": bundle_root / "guidance/orchestration.md",
        "mcp": Path(env["XDG_CONFIG_HOME"]) / "devin/mcp_config.json",
    }
    targets[missing_category].unlink()

    result = _adapter_for_env(env).inspect(desired)

    assert result.state is ResultState.BLOCKED
    assert result.capabilities[expected_identity] == "missing"
    assert f"missing adapter evidence: {expected_identity}" in result.errors


@pytest.mark.parametrize(
    "invalid_mcp_entry",
    [
        {"transport": "http", "url": "https://mcp.context7.com/mcp", "disabled": True},
        {"transport": "http", "url": "https://mcp.context7.com/mcp", "enabled": False},
        {"transport": "http", "url": "https://evil.example.invalid/mcp"},
        {"transport": "sse", "url": "https://mcp.context7.com/mcp"},
        {"transport": "stdio", "command": "npx"},
    ],
)
def test_inspect_fails_closed_on_disabled_or_mismatched_devin_mcp_config(
    tmp_path: Path, invalid_mcp_entry: dict[str, object]
) -> None:
    desired = _build_desired(tmp_path, mcp_tier=CapabilityTier.DEFAULT)
    bin_dir, log_path = _write_fake_devin_cli(tmp_path, desired)
    env = _isolated_env(tmp_path, bin_dir, log_path)
    _write_mcp_config(env, {"context7": invalid_mcp_entry})

    result = _adapter_for_env(env).inspect(desired)

    identity = f"{_TARGET_BUNDLE}:mcp:context7"
    assert result.state is ResultState.DEGRADED
    assert result.capabilities[identity] == "missing"
    assert f"missing default capability evidence: {identity}" in result.errors


def test_inspect_fails_closed_when_component_omitted_from_devin_plugin_manifest(
    tmp_path: Path,
) -> None:
    desired = _build_desired(tmp_path)
    bin_dir, log_path = _write_fake_devin_cli(tmp_path, desired)
    env = _isolated_env(tmp_path, bin_dir, log_path)
    _write_mcp_config(
        env, {"context7": {"transport": "http", "url": "https://mcp.context7.com/mcp"}}
    )
    manifest = desired.bundle_path(_TARGET_BUNDLE) / ".devin-plugin/plugin.json"
    document = json.loads(manifest.read_text(encoding="utf-8"))
    document["harnesses"]["devin"]["components"].pop("agents")
    manifest.write_text(json.dumps(document), encoding="utf-8")

    result = _adapter_for_env(env).inspect(desired)

    assert result.state is ResultState.BLOCKED
    assert result.capabilities[f"{_TARGET_BUNDLE}:agent:reviewer"] == "missing"


def test_inspect_verifies_selected_optional_native_existing_mcp_prefix(
    tmp_path: Path,
) -> None:
    desired = _build_desired(
        tmp_path, selected_optional=frozenset({f"{_DESIGN_BUNDLE}:mcp:stitch"})
    )
    bin_dir, log_path = _write_fake_devin_cli(tmp_path, desired)
    env = _isolated_env(tmp_path, bin_dir, log_path)
    _write_mcp_config(
        env,
        {
            "context7": {"transport": "http", "url": "https://mcp.context7.com/mcp"},
            "mcp_stitch_local": {"transport": "stdio", "command": "stitch-mcp"},
        },
    )

    result = _adapter_for_env(env).inspect(desired)

    assert result.state is ResultState.READY
    assert result.capabilities[f"{_DESIGN_BUNDLE}:mcp:stitch"] == "verified"
    assert result.warnings == ()


def test_uninstalled_plugin_never_credits_on_disk_bundle_or_mcp_evidence(
    tmp_path: Path,
) -> None:
    desired = _build_desired(tmp_path)
    bin_dir, log_path = _write_fake_devin_cli(tmp_path, desired, installed=False)
    env = _isolated_env(tmp_path, bin_dir, log_path)
    _write_mcp_config(
        env, {"context7": {"transport": "http", "url": "https://mcp.context7.com/mcp"}}
    )

    result = _adapter_for_env(env).inspect(desired)

    assert result.state is ResultState.BLOCKED
    for suffix in (
        "agent:reviewer",
        "runtime:lint-script",
        "guidance:orchestration",
        "mcp:context7",
    ):
        assert result.capabilities[f"{_TARGET_BUNDLE}:{suffix}"] == "missing"

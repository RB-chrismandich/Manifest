#!/usr/bin/env python3
"""Generate checked harness-native views from portable domain contracts."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from manifest_model_policy import (
    ModelPolicyError,
    SkillModelPolicy,
    parse_skill_model_policy,
)

from manifest_agent.command_catalog import CommandCatalogError, build_command_catalog
from manifest_agent.contracts import (
    DOMAIN_BUNDLES,
    load_contract,
    load_domain_contracts,
)
from manifest_agent.plugin_view_renderers import (
    GenerationError,
)
from manifest_agent.plugin_view_renderers import (
    antigravity_view as _antigravity_view,
)
from manifest_agent.plugin_view_renderers import (
    claude_view as _claude_view,
)
from manifest_agent.plugin_view_renderers import (
    devin_rule as _devin_rule,
)
from manifest_agent.plugin_view_renderers import (
    gemini_view as _gemini_view,
)
from manifest_agent.plugin_view_renderers import (
    generic_view as _generic_view,
)
from manifest_agent.plugin_view_renderers import (
    model_policy_guidance as _model_policy_guidance,
)
from manifest_agent.plugin_view_renderers import (
    validate_component_assets as _validate_component_assets,
)

_ADDON_ENTRY = Path(".claude-plugin/marketplace-entry.json")
_ALL_HARNESSES = (
    "antigravity",
    "claude",
    "codex",
    "cursor",
    "devin",
    "gemini",
)
_GENERIC_HARNESSES = ("antigravity", "codex", "cursor", "devin")
_CODEX_IMPLICIT_ALLOWLIST_KEY = "codex_implicit_invocation_allowlist"


@dataclass(frozen=True)
class GenerationReport:
    """The bundles rendered and any generated paths written or found drifted."""

    bundles: tuple[str, ...]
    harnesses: tuple[str, ...]
    drifted_paths: tuple[Path, ...]
    written_paths: tuple[Path, ...]


def _json(document: dict[str, Any]) -> str:
    return json.dumps(document, indent=2, sort_keys=True) + "\n"


def _codex_skill_metadata(allow_implicit_invocation: bool) -> str:
    return yaml.safe_dump(
        {
            "policy": {
                "allow_implicit_invocation": allow_implicit_invocation,
            }
        },
        sort_keys=False,
    )


def _repository_skills(source_plugins: Path) -> dict[str, Path]:
    skills: dict[str, Path] = {}
    for skill_file in sorted(source_plugins.glob("*/skills/*/SKILL.md")):
        qualified_name = f"{skill_file.parents[2].name}:{skill_file.parent.name}"
        if qualified_name in skills:
            raise GenerationError(f"duplicate qualified skill {qualified_name!r}")
        skills[qualified_name] = skill_file
    return skills


def _codex_implicit_invocation_allowlist(
    repo_root: Path, skills: dict[str, Path]
) -> frozenset[str]:
    policy_path = repo_root / "configs/claude/config/skill_policies.yml"
    try:
        document = yaml.safe_load(policy_path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as error:
        raise GenerationError(
            f"unable to load skill policy {policy_path}: {error}"
        ) from error
    if not isinstance(document, dict) or _CODEX_IMPLICIT_ALLOWLIST_KEY not in document:
        raise GenerationError(
            f"{policy_path} must declare {_CODEX_IMPLICIT_ALLOWLIST_KEY}"
        )
    entries = document[_CODEX_IMPLICIT_ALLOWLIST_KEY]
    if not isinstance(entries, list):
        raise GenerationError(
            f"{policy_path}: {_CODEX_IMPLICIT_ALLOWLIST_KEY} must be a list"
        )

    allowlist: set[str] = set()
    for entry in entries:
        if not isinstance(entry, str) or not entry:
            raise GenerationError(
                f"{policy_path}: Codex implicit-invocation skills must be "
                "non-empty qualified names"
            )
        if entry in allowlist:
            raise GenerationError(
                f"{policy_path}: duplicate Codex implicit-invocation skill {entry!r}"
            )
        allowlist.add(entry)

    unknown = sorted(allowlist - skills.keys())
    if unknown:
        raise GenerationError(
            f"{policy_path}: unknown Codex implicit-invocation skill(s): "
            f"{', '.join(unknown)}"
        )
    return frozenset(allowlist)


def _discover_skills(bundle_path: Path, contract: Any) -> tuple[str, ...]:
    skills_root = bundle_path / contract.components.skills_root
    skill_names: set[str] = set()
    for include_glob in contract.components.skills_include:
        for skill_file in sorted(skills_root.glob(include_glob)):
            if skill_file.is_file():
                skill_names.add(skill_file.parent.name)
    return tuple(sorted(skill_names))


def _skill_policies(bundle_path: Path, contract: Any) -> dict[str, SkillModelPolicy]:
    policies: dict[str, SkillModelPolicy] = {}
    skills_root = bundle_path / contract.components.skills_root
    for include_glob in contract.components.skills_include:
        for skill_file in sorted(skills_root.glob(include_glob)):
            if skill_file.is_file():
                policies[skill_file.parent.name] = parse_skill_model_policy(skill_file)
    return policies


def _addon_entries(repo_root: Path) -> tuple[dict[str, Any], ...]:
    """Load independent marketplace entries from their owning plugin directories."""
    entries: list[dict[str, Any]] = []
    for addon_path in sorted((repo_root / "plugins").glob(f"*/{_ADDON_ENTRY}")):
        try:
            addon = json.loads(addon_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise GenerationError(
                f"unable to load canonical addon metadata from {addon_path}: {error}"
            ) from error
        name = addon.get("name") if isinstance(addon, dict) else None
        if not isinstance(name, str) or not name:
            raise GenerationError(
                f"{addon_path}: marketplace entry must declare a non-empty name"
            )
        if name != addon_path.parent.parent.name:
            raise GenerationError(
                f"{addon_path}: addon name must match its plugin root"
            )
        if name in DOMAIN_BUNDLES:
            raise GenerationError(f"{addon_path}: domain bundles cannot be addons")
        if addon.get("source") != f"./plugins/{name}":
            raise GenerationError(
                f"{addon_path}: addon source must target its plugin root"
            )
        entries.append(addon)
    ordered = tuple(sorted(entries, key=lambda entry: entry["name"]))
    if len({entry["name"] for entry in ordered}) != len(ordered):
        raise GenerationError("independent marketplace addon names must be unique")
    return ordered


def _marketplace(
    contracts: tuple[Any, ...], addons: tuple[dict[str, Any], ...]
) -> dict[str, Any]:
    domain_entries = [
        {
            "category": contract.category,
            "description": contract.description,
            "name": contract.name,
            "source": f"./plugins/{contract.name}",
            "version": contract.version,
        }
        for contract in sorted(contracts, key=lambda item: item.name)
    ]
    return {
        "description": (
            "Manifest agent capabilities partitioned into eight portable domain "
            "bundles, plus independent addons."
        ),
        "name": "manifest",
        "owner": {"name": "ReefBytes"},
        "plugins": [*domain_entries, *addons],
    }


def _emit(
    expected: dict[Path, str], *, check: bool
) -> tuple[tuple[Path, ...], tuple[Path, ...]]:
    drifted: list[Path] = []
    written: list[Path] = []
    for path in sorted(expected):
        try:
            current = path.read_text(encoding="utf-8")
        except FileNotFoundError:
            current = None
        except OSError as error:
            raise GenerationError(
                f"unable to read generated view {path}: {error}"
            ) from error
        if current == expected[path]:
            continue
        drifted.append(path)
        if check:
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            path.write_text(expected[path], encoding="utf-8")
        except OSError as error:
            raise GenerationError(
                f"unable to write generated view {path}: {error}"
            ) from error
        written.append(path)
    return tuple(drifted), tuple(written)


def _bundle_expected_views(
    bundle_path: Path, target: Path, contract: Any
) -> dict[Path, str]:
    _validate_component_assets(bundle_path, contract)
    skills = _discover_skills(bundle_path, contract)
    policies = _skill_policies(bundle_path, contract)
    expected = {
        target / ".claude-plugin" / "plugin.json": _json(
            _claude_view(contract, skills)
        ),
        target / "gemini-extension.json": _json(_gemini_view(contract, policies)),
        target / "plugin.json": _json(_generic_view(contract, skills, policies)),
        target / "antigravity-extension.json": _json(
            _antigravity_view(contract, policies)
        ),
    }
    devin_rule = _devin_rule(contract, bundle_path)
    if devin_rule is not None:
        expected[target / "devin" / "global-rule.md"] = devin_rule
    for harness in ("gemini", *_GENERIC_HARNESSES):
        guidance = _model_policy_guidance(policies, harness)
        if guidance is not None:
            expected[target / "guidance" / f"model-policy-{harness}.md"] = guidance
    return expected


def _load_generation_contracts(
    source_plugins: Path, repository_skills: dict[str, Path]
) -> tuple[Any, ...]:
    for skill_file in repository_skills.values():
        try:
            parse_skill_model_policy(skill_file)
        except ModelPolicyError as error:
            raise GenerationError(f"{skill_file}: {error}") from error
    contracts = load_domain_contracts(source_plugins)
    if tuple(contract.name for contract in contracts) != DOMAIN_BUNDLES:
        raise GenerationError(
            "domain contract loader returned an unexpected bundle order"
        )
    return contracts


def render_views(
    repo_root: Path, check: bool, output_root: Path | None = None
) -> GenerationReport:
    """Render canonical domain contracts without writing when ``check`` is true."""
    repo_root = repo_root.resolve()
    source_plugins = repo_root / "plugins"
    repository_skills = _repository_skills(source_plugins)
    codex_implicit_allowlist = _codex_implicit_invocation_allowlist(
        repo_root, repository_skills
    )
    contracts = _load_generation_contracts(source_plugins, repository_skills)
    bundle_output_root = output_root.resolve() if output_root else source_plugins
    marketplace_output = (
        bundle_output_root / ".claude-plugin" / "marketplace.json"
        if output_root
        else repo_root / ".claude-plugin" / "marketplace.json"
    )
    expected: dict[Path, str] = {}
    for qualified_name, skill_file in repository_skills.items():
        relative_skill = skill_file.parent.relative_to(source_plugins)
        expected[bundle_output_root / relative_skill / "agents/openai.yaml"] = (
            _codex_skill_metadata(qualified_name in codex_implicit_allowlist)
        )
    for contract in contracts:
        bundle_path = source_plugins / contract.name
        target = bundle_output_root / contract.name
        expected.update(_bundle_expected_views(bundle_path, target, contract))

    adhd_path = source_plugins / "manifest-i-have-adhd"
    if (adhd_path / "manifest-capabilities.yml").exists():
        adhd = load_contract(adhd_path / "manifest-capabilities.yml")
        target = bundle_output_root / adhd.name
        expected.update(_bundle_expected_views(adhd_path, target, adhd))

    catalog_target = (
        bundle_output_root / "manifest-workspace/skills/help/catalog/commands.json"
    )
    expected[catalog_target] = _json(build_command_catalog(source_plugins, contracts))

    expected[marketplace_output] = _json(
        _marketplace(contracts, _addon_entries(repo_root))
    )
    drifted, written = _emit(expected, check=check)
    return GenerationReport(
        bundles=tuple(contract.name for contract in contracts),
        harnesses=_ALL_HARNESSES,
        drifted_paths=drifted,
        written_paths=written,
    )


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check", action="store_true", help="report drift without writing files"
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="repository root (defaults to the parent of tools/)",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    try:
        report = render_views(args.repo_root, check=args.check)
    except (CommandCatalogError, GenerationError, ValueError) as error:
        print(f"generate_plugin_views.py: {error}", file=sys.stderr)
        return 2
    if args.check and report.drifted_paths:
        for path in report.drifted_paths:
            try:
                display_path = path.relative_to(args.repo_root.resolve())
            except ValueError:
                display_path = path
            print(display_path)
        return 1
    # A native view and the capability matrix are the two checked release
    # projections of the same contracts.  Keep normal test fixtures focused on
    # native views; the CLI drift gate validates both repository artifacts.
    if args.check:
        from render_plugin_capability_matrix import render

        matrix_path = args.repo_root.resolve() / "docs" / "PLUGIN_CAPABILITY_MATRIX.md"
        inspection_path = (
            args.repo_root.resolve()
            / "tests/fixtures/plugin_capability_inspection.json"
        )
        from render_plugin_capability_matrix import _load_inspection

        if not matrix_path.exists() or matrix_path.read_text(
            encoding="utf-8"
        ) != render(_load_inspection(inspection_path)):
            print("docs/PLUGIN_CAPABILITY_MATRIX.md", file=sys.stderr)
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Generate checked harness-native views from portable domain contracts."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from manifest_agent.command_catalog import CommandCatalogError, build_command_catalog
from manifest_agent.contracts import DOMAIN_BUNDLES, Component, load_domain_contracts

_ADDON_NAME = "adversarial-design-loop"
_ADDON_SOURCE = Path(
    "plugins/adversarial-design-loop/.claude-plugin/marketplace-entry.json"
)
_ALL_HARNESSES = (
    "antigravity",
    "claude",
    "codex",
    "cursor",
    "devin",
    "gemini",
)
_GENERIC_HARNESSES = ("antigravity", "codex", "cursor", "devin")
_COMPONENT_TYPES = ("agents", "guidance", "hooks", "runtime")
_RENDERABLE_MODES = frozenset(("native", "generated", "imported"))


class GenerationError(ValueError):
    """A contract cannot be rendered into complete deterministic views."""


@dataclass(frozen=True)
class GenerationReport:
    """The bundles rendered and any generated paths written or found drifted."""

    bundles: tuple[str, ...]
    harnesses: tuple[str, ...]
    drifted_paths: tuple[Path, ...]
    written_paths: tuple[Path, ...]


def _json(document: dict[str, Any]) -> str:
    return json.dumps(document, indent=2, sort_keys=True) + "\n"


def _discover_skills(bundle_path: Path, contract: Any) -> tuple[str, ...]:
    skills_root = bundle_path / contract.components.skills_root
    skill_names: set[str] = set()
    for include_glob in contract.components.skills_include:
        for skill_file in sorted(skills_root.glob(include_glob)):
            if skill_file.is_file():
                skill_names.add(skill_file.parent.name)
    return tuple(sorted(skill_names))


def _component_record(
    component_type: str, component: Component, mode: str
) -> dict[str, str]:
    return {
        "component_id": component.id,
        "component_type": component_type,
        "mode": mode,
        "path": component.path,
    }


def _components(contract: Any, component_type: str) -> tuple[Component, ...]:
    return tuple(
        sorted(
            getattr(contract.components, component_type),
            key=lambda component: (component.id, component.path),
        )
    )


def _degradation(
    harness: str,
    component_type: str,
    component: Component,
    reason: str | None = None,
    mode: str = "degraded",
) -> dict[str, str]:
    return {
        **_component_record(component_type, component, mode),
        "reason": reason
        or (
            f"{harness} native manifest cannot encode {component_type} component "
            f"{component.id!r} at {component.path!r}"
        ),
    }


def _component_status(contract: Any, harness: str, component: Component) -> Any:
    compatibility = component.compatibility or contract.compatibility
    return compatibility[harness]


def _declared_degradation(
    contract: Any, harness: str, component_type: str, component: Component
) -> dict[str, str] | None:
    status = _component_status(contract, harness, component)
    if status.mode in _RENDERABLE_MODES:
        return None
    return _degradation(
        harness,
        component_type,
        component,
        reason=status.reason,
        mode=status.mode,
    )


def _validate_component_assets(bundle_path: Path, contract: Any) -> None:
    missing = [
        f"{component_type}:{component.id}:{component.path}"
        for component_type in _COMPONENT_TYPES
        for component in _components(contract, component_type)
        if not (bundle_path / component.path).exists()
    ]
    if missing:
        raise GenerationError(
            f"{contract.name}: missing declared component assets: {', '.join(missing)}"
        )


def _add_record(
    records: dict[str, list[dict[str, str]]], mode: str, record: dict[str, str]
) -> None:
    key = mode if mode in _RENDERABLE_MODES else "degraded"
    records.setdefault(key, []).append(record)


def _add_compatibility(
    view: dict[str, Any], records: dict[str, list[dict[str, str]]]
) -> None:
    if not records:
        return
    view["compatibility"] = {
        mode: sorted(
            mode_records,
            key=lambda record: (
                record["component_type"],
                record["component_id"],
                record["path"],
            ),
        )
        for mode, mode_records in sorted(records.items())
        if mode_records
    }


def _claude_view(contract: Any, skills: tuple[str, ...]) -> dict[str, Any]:
    view: dict[str, Any] = {
        "author": {"name": "ReefBytes"},
        "description": contract.description,
        "name": contract.name,
        "skills": [f"./skills/{name}" for name in skills],
        "version": contract.version,
    }
    records: dict[str, list[dict[str, str]]] = {}
    for component_type in _COMPONENT_TYPES:
        components = _components(contract, component_type)
        if not components:
            continue
        exposed: list[Component] = []
        for component in components:
            declared = _declared_degradation(
                contract, "claude", component_type, component
            )
            if declared is not None:
                _add_record(records, declared["mode"], declared)
            elif component_type in {"agents", "hooks"}:
                status = _component_status(contract, "claude", component)
                exposed.append(component)
                _add_record(
                    records,
                    status.mode,
                    _component_record(component_type, component, status.mode),
                )
            else:
                fallback = _degradation("claude", component_type, component)
                _add_record(records, fallback["mode"], fallback)
        if exposed:
            view[component_type] = [f"./{component.path}" for component in exposed]
    _add_compatibility(view, records)
    return view


def _gemini_view(contract: Any) -> dict[str, Any]:
    view: dict[str, Any] = {"name": contract.name, "version": contract.version}
    records: dict[str, list[dict[str, str]]] = {}

    guidance = _components(contract, "guidance")
    if guidance:
        exposed_guidance: list[Component] = []
        for component in guidance:
            declared = _declared_degradation(contract, "gemini", "guidance", component)
            if declared is not None:
                _add_record(records, declared["mode"], declared)
            else:
                status = _component_status(contract, "gemini", component)
                exposed_guidance.append(component)
                _add_record(
                    records,
                    status.mode,
                    _component_record("guidance", component, status.mode),
                )
        paths = [component.path for component in exposed_guidance]
        if paths:
            view["contextFileName"] = paths[0] if len(paths) == 1 else paths

    for component in _components(contract, "agents"):
        declared = _declared_degradation(contract, "gemini", "agents", component)
        if declared is not None:
            _add_record(records, declared["mode"], declared)
        elif component.path.startswith("agents/"):
            status = _component_status(contract, "gemini", component)
            _add_record(
                records,
                status.mode,
                _component_record("agents", component, status.mode),
            )
        else:
            fallback = _degradation("gemini", "agents", component)
            _add_record(records, fallback["mode"], fallback)
    for component in _components(contract, "hooks"):
        declared = _declared_degradation(contract, "gemini", "hooks", component)
        if declared is not None:
            _add_record(records, declared["mode"], declared)
        elif component.path == "hooks/hooks.json":
            status = _component_status(contract, "gemini", component)
            _add_record(
                records,
                status.mode,
                _component_record("hooks", component, status.mode),
            )
        else:
            fallback = _degradation("gemini", "hooks", component)
            _add_record(records, fallback["mode"], fallback)
    for component in _components(contract, "runtime"):
        record = _declared_degradation(contract, "gemini", "runtime", component)
        record = record or _degradation("gemini", "runtime", component)
        _add_record(records, record["mode"], record)
    _add_compatibility(view, records)
    return view


def _generic_harness_surface(
    contract: Any, skills: tuple[str, ...], harness: str
) -> dict[str, Any]:
    bundle_status = contract.compatibility[harness]
    surface: dict[str, Any] = {
        "mode": bundle_status.mode,
        "skills": [f"skills/{name}" for name in skills],
    }
    if bundle_status.reason is not None:
        surface["reason"] = bundle_status.reason
    components_by_type: dict[str, list[dict[str, str]]] = {}
    records: dict[str, list[dict[str, str]]] = {}
    for component_type in _COMPONENT_TYPES:
        for component in _components(contract, component_type):
            status = _component_status(contract, harness, component)
            if status.mode not in _RENDERABLE_MODES:
                record = _degradation(
                    harness,
                    component_type,
                    component,
                    reason=status.reason,
                    mode=status.mode,
                )
                _add_record(records, status.mode, record)
                continue
            components_by_type.setdefault(component_type, []).append(
                {"id": component.id, "path": component.path}
            )
            _add_record(
                records,
                status.mode,
                _component_record(component_type, component, status.mode),
            )
    if components_by_type:
        surface["components"] = components_by_type
    _add_compatibility(surface, records)
    return surface


def _generic_view(contract: Any, skills: tuple[str, ...]) -> dict[str, Any]:
    return {
        "description": contract.description,
        "forbidden": [],
        "harnesses": {
            harness: _generic_harness_surface(contract, skills, harness)
            for harness in _GENERIC_HARNESSES
        },
        "name": contract.name,
        "optional": [],
        "required": [],
        "skills": [f"skills/{name}" for name in skills],
        "version": contract.version,
    }


def _addon_entry(repo_root: Path) -> dict[str, Any]:
    addon_path = repo_root / _ADDON_SOURCE
    try:
        addon = json.loads(addon_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise GenerationError(
            f"unable to load canonical addon metadata from {addon_path}: {error}"
        ) from error
    if not isinstance(addon, dict) or addon.get("name") != _ADDON_NAME:
        raise GenerationError(
            f"{addon_path}: expected one {_ADDON_NAME!r} marketplace entry object"
        )
    if addon.get("source") != f"./plugins/{_ADDON_NAME}":
        raise GenerationError(f"{addon_path}: addon source must target its plugin root")
    return addon


def _marketplace(contracts: tuple[Any, ...], addon: dict[str, Any]) -> dict[str, Any]:
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
            "Manifest agent capabilities partitioned into nine portable domain "
            "bundles, plus the independent adversarial-design-loop addon."
        ),
        "name": "manifest",
        "owner": {"name": "ReefBytes"},
        "plugins": [*domain_entries, addon],
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


def render_views(
    repo_root: Path, check: bool, output_root: Path | None = None
) -> GenerationReport:
    """Render the nine contracts without changing files when ``check`` is true."""
    repo_root = repo_root.resolve()
    source_plugins = repo_root / "plugins"
    contracts = load_domain_contracts(source_plugins)
    if tuple(contract.name for contract in contracts) != DOMAIN_BUNDLES:
        raise GenerationError(
            "domain contract loader returned an unexpected bundle order"
        )

    bundle_output_root = output_root.resolve() if output_root else source_plugins
    marketplace_output = (
        bundle_output_root / ".claude-plugin" / "marketplace.json"
        if output_root
        else repo_root / ".claude-plugin" / "marketplace.json"
    )
    expected: dict[Path, str] = {}
    for contract in contracts:
        bundle_path = source_plugins / contract.name
        _validate_component_assets(bundle_path, contract)
        skills = _discover_skills(bundle_path, contract)
        target = bundle_output_root / contract.name
        expected[target / ".claude-plugin" / "plugin.json"] = _json(
            _claude_view(contract, skills)
        )
        expected[target / "gemini-extension.json"] = _json(_gemini_view(contract))
        expected[target / "plugin.json"] = _json(_generic_view(contract, skills))

    catalog_target = (
        bundle_output_root / "manifest-workspace/skills/help/catalog/commands.json"
    )
    expected[catalog_target] = _json(build_command_catalog(source_plugins, contracts))

    expected[marketplace_output] = _json(
        _marketplace(contracts, _addon_entry(repo_root))
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
        if not matrix_path.exists() or matrix_path.read_text(encoding="utf-8") != render():
            print("docs/PLUGIN_CAPABILITY_MATRIX.md", file=sys.stderr)
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

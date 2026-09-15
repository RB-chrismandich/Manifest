"""Component-evidence extraction for Antigravity generic plugin views."""

import json
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path

from manifest_agent.adapters.base import (
    collect_native_component_evidence,
    normalize_component_identity,
)
from manifest_agent.models import CapabilityTier, DesiredState

_NATIVE_SOURCE = "antigravity"


def _expected_skill_paths(desired: DesiredState, bundle: str) -> tuple[str, ...]:
    contract = next(item for item in desired.all_contracts if item.name == bundle)
    skills_root = desired.bundle_path(bundle) / contract.components.skills_root
    paths = {
        str(path.parent.relative_to(desired.bundle_path(bundle)))
        for pattern in contract.components.skills_include
        for path in skills_root.glob(pattern)
        if path.is_file()
    }
    return tuple(sorted(paths))


def _extension_context(desired: DesiredState, bundle: str):
    extension = desired.bundle_path(bundle) / "antigravity-extension.json"
    try:
        document = json.loads(extension.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return ()
    if not isinstance(document, Mapping):
        return ()
    context = document.get("contextFileName")
    context_paths = (context,) if isinstance(context, str) else context
    return context_paths if isinstance(context_paths, (list, tuple)) else ()


def _declared_surface_evidence(desired, contract, components):
    evidence = {
        normalize_component_identity(contract.name, "skill", Path(skill).name)
        for skill in _expected_skill_paths(desired, contract.name)
    }
    context_paths = _extension_context(desired, contract.name)
    for component in contract.components.guidance:
        if component.path not in context_paths:
            continue
        evidence.add(
            normalize_component_identity(contract.name, "guidance", component.id)
        )
        evidence.update(
            normalize_component_identity(contract.name, "hook", hook.id)
            for hook in contract.components.hooks
        )
        evidence.update(
            normalize_component_identity(contract.name, "runtime", runtime.id)
            for runtime in contract.components.runtime
        )
    for component in components:
        if not isinstance(component, str) or ":" not in component:
            continue
        kind, stable_id = component.split(":", 1)
        if kind in {"guidance", "hook", "runtime"} and stable_id:
            evidence.add(normalize_component_identity(contract.name, kind, stable_id))
    return evidence


def imported_plugin_roots(
    desired: DesiredState, env: Mapping[str, str] | None
) -> dict[str, Path]:
    """Map each bundle to the tree ``agy plugin install`` imported it into.

    Probed against agy 1.2.3 (2026-09-15): `agy plugin install <dir>` copies the
    bundle to ``$HOME/.gemini/config/plugins/<bundle>``. `agy plugin list`
    reports no path, so this location is the only way to inspect what the CLI
    actually imported. A missing tree yields no evidence, never fabricated
    evidence. Falls back to the process home, as the Claude adapter does, so a
    production adapter constructed without an injected env still inspects the
    real import tree instead of silently reporting every component missing.
    """
    values = env or {}
    home = Path(values["HOME"]) if "HOME" in values else Path.home()
    plugins = home / ".gemini" / "config" / "plugins"
    return {
        contract.name: plugins / contract.name for contract in desired.all_contracts
    }


def _component_evidence(
    desired: DesiredState,
    rows: Sequence[Mapping[str, object]],
    which: Callable[[str], str | None],
    plugin_roots: Mapping[str, Path] | None = None,
) -> set[str]:
    """Return only components proven by Antigravity's native inventory."""
    evidence: set[str] = set()
    by_name = {row.get("name"): row for row in rows if isinstance(row.get("name"), str)}
    for contract in desired.all_contracts:
        row = by_name.get(contract.name)
        components = row.get("components") if row is not None else None
        if (
            row is not None
            and row.get("source") == _NATIVE_SOURCE
            and isinstance(components, list)
            and "skills" in components
        ):
            evidence.update(_declared_surface_evidence(desired, contract, components))
        for tier in CapabilityTier:
            evidence.update(
                normalize_component_identity(contract.name, "executable", executable)
                for executable in contract.capabilities.executables[tier]
                if which(executable) is not None
            )
    # `agy plugin list` only ever reports `components: ["skills"]`, so every
    # file-backed component (runtime, hooks, agents, guidance) is proven by the
    # imported tree itself. Crediting it only via a guidance contextFileName
    # match denied evidence to bundles that declare runtime and no guidance.
    if plugin_roots:
        imported = {
            name: root for name, root in plugin_roots.items() if name in by_name
        }
        evidence.update(
            collect_native_component_evidence(desired, imported, {}, lambda _name: None)
        )
    return evidence

"""Render harness-specific plugin documents from portable contracts."""

from __future__ import annotations

from pathlib import Path
from typing import Any

try:
    from manifest_agent._model_policy import ModelFallbackMode, SkillModelPolicy
except ModuleNotFoundError as error:
    if error.name != "manifest_agent._model_policy":
        raise
    from manifest_model_policy import ModelFallbackMode, SkillModelPolicy

from manifest_agent.contracts import Component

_COMPONENT_TYPES = ("agents", "guidance", "hooks", "runtime")
_GENERIC_HARNESSES = ("antigravity", "codex", "cursor", "devin")
_RENDERABLE_MODES = frozenset(("native", "generated", "imported"))


class GenerationError(ValueError):
    """A contract cannot be rendered into complete deterministic views."""


def model_policy_records(
    policies: dict[str, SkillModelPolicy], harness: str
) -> list[dict[str, Any]]:
    """Return deterministic launcher records for one harness."""
    records: list[dict[str, Any]] = []
    for skill_name, policy in sorted(policies.items()):
        tiers = policy.chains.get(harness)
        if not tiers:
            continue
        fallback = policy.fallback_mode or ModelFallbackMode.CONFIRM
        records.append(
            {
                "fallback_mode": fallback.value,
                "first_tier": tiers[0],
                "launcher": (
                    f"manifest skill-run {skill_name} --harness {harness} "
                    f"--model-chain {','.join(tiers)} --model-fallback {fallback.value}"
                ),
                "skill": skill_name,
                "tiers": list(tiers),
            }
        )
    return records


def model_policy_guidance(
    policies: dict[str, SkillModelPolicy], harness: str
) -> str | None:
    """Render installed-launcher guidance when a harness has model policy."""
    records = model_policy_records(policies, harness)
    if not records:
        return None
    lines = [
        "# Model-Aware Skill Invocation",
        "",
        "Use the installed Manifest launcher for these skills. The launcher resolves "
        "the deployed skill catalog; do not construct repository-relative paths.",
        "",
    ]
    lines.extend(f"- `{record['skill']}`: `{record['launcher']}`" for record in records)
    return "\n".join(lines) + "\n"


def components(contract: Any, component_type: str) -> tuple[Component, ...]:
    """Return one component category in deterministic order."""
    return tuple(
        sorted(
            getattr(contract.components, component_type),
            key=lambda component: (component.id, component.path),
        )
    )


def validate_component_assets(bundle_path: Path, contract: Any) -> None:
    """Reject contracts whose declared component paths are missing."""
    missing = [
        f"{component_type}:{component.id}:{component.path}"
        for component_type in _COMPONENT_TYPES
        for component in components(contract, component_type)
        if not (bundle_path / component.path).exists()
    ]
    if missing:
        raise GenerationError(
            f"{contract.name}: missing declared component assets: {', '.join(missing)}"
        )


def _component_record(
    component_type: str, component: Component, mode: str
) -> dict[str, str]:
    return {
        "component_id": component.id,
        "component_type": component_type,
        "mode": mode,
        "path": component.path,
    }


def _component_status(contract: Any, harness: str, component: Component) -> Any:
    compatibility = component.compatibility or contract.compatibility
    return compatibility[harness]


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


def claude_view(contract: Any, skills: tuple[str, ...]) -> dict[str, Any]:
    """Render Claude's native plugin manifest."""
    view: dict[str, Any] = {
        "author": {"name": "ReefBytes"},
        "description": contract.description,
        "name": contract.name,
        "skills": [f"./skills/{name}" for name in skills],
        "version": contract.version,
    }
    records: dict[str, list[dict[str, str]]] = {}
    for component_type in _COMPONENT_TYPES:
        exposed: list[Component] = []
        for component in components(contract, component_type):
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


def _record_gemini_components(
    contract: Any,
    records: dict[str, list[dict[str, str]]],
    component_type: str,
    native_path: str,
) -> None:
    for component in components(contract, component_type):
        declared = _declared_degradation(contract, "gemini", component_type, component)
        if declared is not None:
            _add_record(records, declared["mode"], declared)
        elif component.path == native_path or component.path.startswith(native_path):
            status = _component_status(contract, "gemini", component)
            _add_record(
                records,
                status.mode,
                _component_record(component_type, component, status.mode),
            )
        else:
            fallback = _degradation("gemini", component_type, component)
            _add_record(records, fallback["mode"], fallback)


def _gemini_guidance(
    contract: Any,
    view: dict[str, Any],
    records: dict[str, list[dict[str, str]]],
) -> None:
    exposed: list[Component] = []
    for component in components(contract, "guidance"):
        declared = _declared_degradation(contract, "gemini", "guidance", component)
        if declared is not None:
            _add_record(records, declared["mode"], declared)
            continue
        status = _component_status(contract, "gemini", component)
        exposed.append(component)
        _add_record(
            records,
            status.mode,
            _component_record("guidance", component, status.mode),
        )
    paths = [component.path for component in exposed]
    if paths:
        view["contextFileName"] = paths[0] if len(paths) == 1 else paths


def _append_gemini_model_policy(
    view: dict[str, Any], policies: dict[str, SkillModelPolicy]
) -> None:
    policy = model_policy_records(policies, "gemini")
    if not policy:
        return
    view["modelPolicy"] = policy
    guidance = "guidance/model-policy-gemini.md"
    current = view.get("contextFileName")
    if current is None:
        view["contextFileName"] = guidance
    elif isinstance(current, list):
        view["contextFileName"] = [*current, guidance]
    else:
        view["contextFileName"] = [current, guidance]


def gemini_view(contract: Any, policies: dict[str, SkillModelPolicy]) -> dict[str, Any]:
    """Render Gemini's extension manifest and compatibility evidence."""
    view: dict[str, Any] = {"name": contract.name, "version": contract.version}
    records: dict[str, list[dict[str, str]]] = {}
    _gemini_guidance(contract, view, records)
    _record_gemini_components(contract, records, "agents", "agents/")
    _record_gemini_components(contract, records, "hooks", "hooks/hooks.json")
    for component in components(contract, "runtime"):
        record = _declared_degradation(contract, "gemini", "runtime", component)
        record = record or _degradation("gemini", "runtime", component)
        _add_record(records, record["mode"], record)
    _add_compatibility(view, records)
    _append_gemini_model_policy(view, policies)
    return view


def _generic_harness_surface(
    contract: Any,
    skills: tuple[str, ...],
    harness: str,
    policies: dict[str, SkillModelPolicy],
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
        for component in components(contract, component_type):
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
    policy = model_policy_records(policies, harness)
    if policy:
        surface["model_policy"] = policy
        components_by_type.setdefault("guidance", []).append(
            {
                "id": "model-aware-skill-invocation",
                "path": f"guidance/model-policy-{harness}.md",
            }
        )
        surface["components"] = components_by_type
    return surface


def antigravity_view(
    contract: Any, policies: dict[str, SkillModelPolicy]
) -> dict[str, Any]:
    """Use Antigravity's measured Gemini-extension import surface."""
    return gemini_view(contract, policies)


def devin_rule(contract: Any, bundle_path: Path) -> str | None:
    """Render the one Devin global rule for a generated always-loaded bundle."""
    guidance = [
        component
        for component in components(contract, "guidance")
        if _component_status(contract, "devin", component).mode == "generated"
    ]
    if not guidance:
        return None
    return (bundle_path / guidance[0].path).read_text(encoding="utf-8")


def generic_view(
    contract: Any, skills: tuple[str, ...], policies: dict[str, SkillModelPolicy]
) -> dict[str, Any]:
    """Render the shared Manifest surface for non-Claude harnesses."""
    return {
        "description": contract.description,
        "forbidden": [],
        "harnesses": {
            harness: _generic_harness_surface(contract, skills, harness, policies)
            for harness in _GENERIC_HARNESSES
        },
        "name": contract.name,
        "optional": [],
        "required": [],
        "skills": [f"skills/{name}" for name in skills],
        "version": contract.version,
    }

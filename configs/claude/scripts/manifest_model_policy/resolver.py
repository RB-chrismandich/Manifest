"""Portable tier resolution and fallback precedence."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from .frontmatter import ModelFallbackMode, ModelPolicyError, normalize_harness


@dataclass(frozen=True)
class ResolvedModel:
    tier: str
    model_id: str | None


def resolve_chain(
    config: Mapping, harness: str, tiers: Sequence[str]
) -> tuple[ResolvedModel, ...]:
    normalized = normalize_harness(harness)
    if not tiers or len(tiers) > 4 or len(set(tiers)) != len(tiers):
        raise ModelPolicyError("model chain must contain 1 to 4 unique tiers")
    registry = config.get("model_tiers", {})
    harness_models = (
        registry.get(normalized, {}) if isinstance(registry, Mapping) else {}
    )
    cli_agents = config.get("cli_agents", {})
    agent = cli_agents.get(normalized, {}) if isinstance(cli_agents, Mapping) else {}
    can_omit = isinstance(agent, Mapping) and isinstance(
        agent.get("model_args", []), list
    )
    resolved: list[ResolvedModel] = []
    for index, tier in enumerate(tiers):
        if tier == "auto":
            if index != len(tiers) - 1 or not can_omit:
                raise ModelPolicyError(f"{normalized} cannot use auto in this chain")
            resolved.append(ResolvedModel(tier, None))
            continue
        model_id = (
            harness_models.get(tier) if isinstance(harness_models, Mapping) else None
        )
        if not isinstance(model_id, str) or not model_id:
            raise ModelPolicyError(f"unknown {normalized} model tier {tier!r}")
        resolved.append(ResolvedModel(tier, model_id))
    return tuple(resolved)


def effective_fallback_mode(
    cli_mode: ModelFallbackMode | str | None,
    skill_mode: ModelFallbackMode | str | None,
    global_mode: ModelFallbackMode | str | None,
) -> ModelFallbackMode:
    for value in (cli_mode, skill_mode, global_mode, ModelFallbackMode.CONFIRM):
        if value is not None:
            try:
                return ModelFallbackMode(value)
            except ValueError as error:
                raise ModelPolicyError(f"unknown fallback mode {value!r}") from error
    raise AssertionError("fallback mode default is unreachable")

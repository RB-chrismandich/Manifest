"""Portable model and roster policy helpers for the parallel-agent CLI."""

import argparse
from collections.abc import Mapping

_MODEL_TIER_DEFAULTS = {
    "claude": "sonnet",
    "gemini": "flash",
    "cursor": "flash",
    "codex": "auto",
    "antigravity": "flash",
    "devin": "auto",
}


def _configured_chain(section: object, agent_name: str) -> tuple[str, ...]:
    if not isinstance(section, Mapping):
        return ()
    chain = section.get(agent_name, ())
    if not isinstance(chain, list) or any(
        not isinstance(item, str) or not item for item in chain
    ):
        return ()
    return tuple(chain)


def configured_fallback_tiers(
    config: Mapping, agent_name: str, starting_tier: str
) -> tuple[str, ...]:
    """Select constructor defaults without overriding an explicit model start."""
    fallback = config.get("model_fallback", {})
    chains = fallback.get("chains", {}) if isinstance(fallback, Mapping) else {}
    configured = _configured_chain(chains, agent_name)
    if configured:
        if starting_tier == _MODEL_TIER_DEFAULTS.get(agent_name):
            return configured
        if starting_tier in configured:
            return configured[configured.index(starting_tier) :]
        return (starting_tier,)

    retained = _configured_chain(config.get("credit_fallback", {}), agent_name)
    if starting_tier in retained:
        return retained[retained.index(starting_tier) :]
    return (starting_tier,)


def _dest(name: str) -> str:
    """Match argparse's hyphen-to-underscore destination normalization."""
    return name.replace("-", "_")


def resolve_enabled_agents(
    roster: dict, args: argparse.Namespace, enabled: dict[str, bool]
) -> dict[str, bool]:
    """Apply exclusive and disabling CLI overrides to service configuration."""
    resolved = dict(enabled)
    only_flags = {name: getattr(args, f"{_dest(name)}_only") for name in roster}
    if any(only_flags.values()):
        for agent_name in resolved:
            resolved[agent_name] = only_flags[agent_name]
    for name in roster:
        if getattr(args, f"no_{_dest(name)}"):
            resolved[name] = False
    return resolved


def resolve_cli_models(
    cli_only_providers: list[str], args: argparse.Namespace
) -> dict[str, str]:
    """Resolve model-tier overrides for CLI-only roster agents."""
    return {
        name: getattr(args, f"{_dest(name)}_model")
        or _MODEL_TIER_DEFAULTS.get(name, "auto")
        for name in cli_only_providers
    }


def resolve_requested_model_tiers(
    agent_name: str,
    args: argparse.Namespace,
    skill_chain: tuple[str, ...] = (),
) -> tuple[str, ...]:
    """Resolve portable tier ordering without implicit chain defaults."""
    explicit = getattr(args, f"{_dest(agent_name)}_model")
    appended = tuple(
        item.strip() for item in (args.model_chain or "").split(",") if item.strip()
    )
    if explicit:
        return (explicit, *appended)
    if appended:
        return appended
    return skill_chain


def cli_only_provider_names(roster: dict, sdk_providers: dict) -> list[str]:
    """Return roster providers not handled by an SDK-specific dispatch path."""
    return [name for name in roster if name not in sdk_providers]

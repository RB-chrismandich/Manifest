"""Shared headless CLI provider resolution and invocation.

Used by synthesis, CDDL persona invoke, and SkillClaw evolve so every seam
shares ``cli_agents`` / ``parallel_agent.yml`` configuration.
"""

from __future__ import annotations

import asyncio
import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from agents.config import HAS_ANTHROPIC, Config, Logger

DEFAULT_CLI_PROVIDER_ORDER = (
    "antigravity",
    "cursor",
    "gemini",
    "codex",
    "claude",
)

# Providers whose default headless entry reads the prompt from stdin (large payloads).
STDIN_PROMPT_BINARIES = frozenset({"claude", "gemini"})


@dataclass(frozen=True)
class CliRoute:
    mode: str  # "cli" | "sdk"
    provider: str
    binary_override: str | None = None


def _section_settings(config: Config, section: str) -> dict[str, Any]:
    raw = config.get(section)
    settings = dict(raw) if isinstance(raw, dict) else {}
    if not settings.get("provider_order"):
        synth = config.get("synthesis")
        if isinstance(synth, dict) and synth.get("provider_order"):
            settings.setdefault("provider_order", synth["provider_order"])
    return settings


def _provider_names(config: Config, section: str) -> list[str]:
    settings = _section_settings(config, section)
    order = settings.get("provider_order")
    if isinstance(order, list) and order:
        return [str(name) for name in order]
    agents = config.get("cli_agents") or {}
    if isinstance(agents, dict) and agents:
        return list(agents.keys())
    return list(DEFAULT_CLI_PROVIDER_ORDER)


def _provider_for_cli_env(config: Config, cli: str) -> str | None:
    cli_name = Path(cli).name
    agents = config.get("cli_agents") or {}
    if not isinstance(agents, dict):
        return None
    for name, spec in agents.items():
        if not isinstance(spec, dict):
            continue
        binary = spec.get("binary", "")
        if cli == binary or cli_name == binary:
            return str(name)
    return None


def _binary_on_path(binary: str) -> bool:
    if not binary:
        return False
    if os.path.isabs(binary) or binary.startswith("."):
        return os.path.isfile(binary) and os.access(binary, os.X_OK)
    return bool(shutil.which(binary))


def cli_provider_available(
    config: Config, provider: str, binary_override: str | None = None
) -> bool:
    spec = config.get(f"cli_agents.{provider}")
    if not spec:
        return False
    binary = binary_override or spec.get("binary")
    return _binary_on_path(str(binary or ""))


def claude_sdk_available() -> bool:
    return HAS_ANTHROPIC and bool(os.environ.get("ANTHROPIC_API_KEY"))


def resolve_cli_route(
    config: Config,
    *,
    section: str = "synthesis",
    env_prefix: str = "SYNTH",
    allow_sdk: bool = False,
) -> CliRoute | None:
    """Resolve a headless CLI (or optional Claude SDK) route for *section*."""
    settings = _section_settings(config, section)
    backend = settings.get("backend", config.get(f"{section}.backend", "auto"))
    if backend not in ("auto", "cli", "sdk"):
        backend = "auto"

    provider_cfg = (
        os.environ.get(f"{env_prefix}_PROVIDER")
        or settings.get("provider")
        or config.get(f"{section}.provider")
        or "auto"
    )
    synth_cli = os.environ.get(f"{env_prefix}_CLI")
    binary_override = synth_cli if synth_cli else None

    if provider_cfg == "auto" and synth_cli:
        inferred = _provider_for_cli_env(config, synth_cli)
        if inferred:
            provider_cfg = inferred

    if allow_sdk and (provider_cfg == "sdk" or backend == "sdk"):
        return CliRoute("sdk", "claude") if claude_sdk_available() else None

    if provider_cfg != "auto":
        ov = binary_override if synth_cli else None
        if backend != "sdk" and cli_provider_available(config, str(provider_cfg), ov):
            return CliRoute("cli", str(provider_cfg), binary_override=ov)
        if allow_sdk and str(provider_cfg) == "claude" and backend != "cli":
            return CliRoute("sdk", "claude") if claude_sdk_available() else None
        return None

    if allow_sdk and backend == "sdk":
        return CliRoute("sdk", "claude") if claude_sdk_available() else None

    for name in _provider_names(config, section):
        ov: str | None = None
        if synth_cli and (
            name == _provider_for_cli_env(config, synth_cli)
            or str(provider_cfg) == name
        ):
            ov = synth_cli
        if cli_provider_available(config, name, ov):
            return CliRoute("cli", name, binary_override=ov)

    if allow_sdk and backend == "auto" and claude_sdk_available():
        return CliRoute("sdk", "claude")

    return None


def resolve_role_model_tier(charter_path: str | os.PathLike) -> str:
    """Read ``model:`` from a CDDL role charter frontmatter (default ``sonnet``)."""
    path = Path(charter_path).expanduser()
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return "sonnet"
    if not text.startswith("---"):
        return "sonnet"
    end = text.find("\n---", 3)
    if end < 0:
        return "sonnet"
    for line in text[3:end].splitlines():
        if line.startswith("model:"):
            tier = line.split(":", 1)[1].strip()
            return tier or "sonnet"
    return "sonnet"


def resolve_provider_model(config: Config, provider: str, tier: str) -> str | None:
    if tier == "auto":
        return None
    resolved = config.get(f"model_tiers.{provider}.{tier}")
    return resolved if resolved else tier


async def invoke_cli(
    route: CliRoute,
    prompt: str,
    config: Config,
    *,
    model_tier: str = "sonnet",
    timeout: int = 300,
    logger: Logger | None = None,
) -> str:
    from agents.runners import CLIAgent

    agent = CLIAgent(
        route.provider,
        model=model_tier,
        timeout=timeout,
        config=config,
        logger=logger,
    )
    if route.binary_override:
        agent.binary = route.binary_override

    result = await agent._execute_impl(prompt, "invoke")
    if result.get("status") != "complete":
        raise RuntimeError(result.get("error") or f"{route.provider} invoke failed")
    return result.get("output") or ""


def build_subprocess_argv(
    config: Config,
    route: CliRoute,
    prompt: str,
    *,
    model_tier: str = "sonnet",
) -> tuple[list[str], str | None]:
    """Build argv (+ optional stdin body) for synchronous subprocess runners."""
    spec = config.get(f"cli_agents.{route.provider}") or {}
    binary = route.binary_override or spec.get("binary") or route.provider
    binary_name = Path(str(binary)).name

    if binary_name in STDIN_PROMPT_BINARIES:
        return [str(binary), "-p"], prompt

    from agents.runners import CLIAgent

    agent = CLIAgent(
        route.provider,
        model=model_tier,
        timeout=300,
        config=config,
    )
    if route.binary_override:
        agent.binary = route.binary_override
    output_file = None
    if agent.output_strategy == "file_then_stdout":
        import tempfile

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".txt", delete=False, prefix=f"{route.provider}_out_"
        ) as tmp:
            output_file = tmp.name
    return agent._build_command(prompt, output_file), None


async def invoke_cli_timed(
    route: CliRoute,
    prompt: str,
    config: Config,
    *,
    model_tier: str = "sonnet",
    timeout: int = 300,
    logger: Logger | None = None,
) -> str:
    return await asyncio.wait_for(
        invoke_cli(
            route,
            prompt,
            config,
            model_tier=model_tier,
            timeout=timeout,
            logger=logger,
        ),
        timeout=timeout,
    )

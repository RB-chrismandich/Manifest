"""Runtime assembly and execution for the parallel-agent CLI."""

import argparse
import json
import os
import shutil
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from manifest_model_policy import (
    ModelPolicyError,
    ResolvedModel,
    effective_fallback_mode,
    parse_skill_model_policy,
    resolve_chain,
)

from agents.cli_policy import (
    _MODEL_TIER_DEFAULTS,
    cli_only_provider_names,
    configured_fallback_tiers,
    resolve_cli_models,
    resolve_enabled_agents,
    resolve_requested_model_tiers,
)
from agents.config import (
    HAS_ANTHROPIC,
    HAS_GENAI,
    Config,
    Logger,
    RateLimiter,
    ServiceConfig,
    select_backend,
)
from agents.orchestrator import Orchestrator, check_credits
from agents.runners import ClaudeAgent, CLIAgent, GeminiAgent


@dataclass
class _Runtime:
    args: argparse.Namespace
    config: Config
    services: ServiceConfig
    logger: Logger
    timeout: int
    streaming: bool


def _create_logger(config: Config) -> Logger:
    logger = Logger(config)
    logger.set_correlation_id(
        f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{os.getpid()}"
    )
    return logger


def _run_status_check(args: argparse.Namespace) -> None:
    if not args.status:
        return
    script_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    status_script = os.path.join(script_dir, "check_status.sh")
    if os.path.exists(status_script):
        os.execv("/bin/bash", ["/bin/bash", status_script])
    print(f"Error: {status_script} not found", file=sys.stderr)
    raise SystemExit(1)


async def _run_credit_check(
    args: argparse.Namespace, config: Config, logger: Logger
) -> None:
    if not args.check_credits:
        return
    print("Checking API credits...")
    results = await check_credits(config, logger)
    print(json.dumps(results, indent=2))
    raise SystemExit(0)


def _file_prompt(path_value: str, mode: str, template: str) -> tuple[str, str, None]:
    if not Path(path_value).exists():
        print(f"Error: file not found: {path_value}", file=sys.stderr)
        raise SystemExit(1)
    return mode, template.format(path=path_value), None


def _resolve_mode(
    args: argparse.Namespace, parser: argparse.ArgumentParser
) -> tuple[str, str, None]:
    if args.review:
        return _file_prompt(
            args.review,
            "review",
            "Review this file for code quality, security, and best practices: {path}",
        )
    if args.analyze:
        return _file_prompt(
            args.analyze,
            "analyze",
            "Analyze this file for bugs and security issues: {path}",
        )
    if args.improve:
        return _file_prompt(
            args.improve,
            "improve",
            "Review and improve this observation YAML: {path}",
        )
    if args.prompt:
        return "prompt", args.prompt, None
    parser.print_help()
    raise SystemExit(1)


def _resolve_timeout(args: argparse.Namespace, config: Config, mode: str) -> int:
    if args.timeout is not None:
        return args.timeout
    return {
        "review": config.get("timeouts.review", 600),
        "analyze": config.get("timeouts.analyze", 900),
        "improve": config.get("timeouts.improve", 300),
        "prompt": config.get("timeouts.default", 600),
    }.get(mode, 600)


def _sdk_provider_specs(runtime: _Runtime) -> dict:
    return {
        "claude": {
            "agent_cls": ClaudeAgent,
            "has_sdk": HAS_ANTHROPIC,
            "key_env": "ANTHROPIC_API_KEY",
            "model": runtime.args.claude_model or _MODEL_TIER_DEFAULTS["claude"],
            "limiter": RateLimiter(**runtime.config.get("rate_limits.claude", {})),
        },
        "gemini": {
            "agent_cls": GeminiAgent,
            "has_sdk": HAS_GENAI,
            "key_env": "GOOGLE_API_KEY",
            "model": runtime.args.gemini_model or _MODEL_TIER_DEFAULTS["gemini"],
            "limiter": RateLimiter(**runtime.config.get("rate_limits.gemini", {})),
        },
    }


def _append_sdk_agents(
    runtime: _Runtime, enabled: dict[str, bool], specs: dict, agents: list
) -> None:
    for provider, spec in specs.items():
        if not enabled[provider]:
            continue
        binary = runtime.config.get(f"cli_agents.{provider}.binary", provider)
        selected = select_backend(
            has_sdk=spec["has_sdk"],
            has_key=bool(os.environ.get(spec["key_env"])),
            has_cli=bool(shutil.which(binary)),
        )
        try:
            if selected == "sdk":
                agents.append(
                    spec["agent_cls"](
                        spec["model"],
                        runtime.timeout,
                        spec["limiter"],
                        config=runtime.config,
                        logger=runtime.logger,
                        streaming=runtime.streaming,
                    )
                )
            elif selected == "cli":
                agents.append(
                    CLIAgent(
                        provider,
                        spec["model"],
                        runtime.timeout,
                        spec["limiter"],
                        config=runtime.config,
                        logger=runtime.logger,
                        streaming=runtime.streaming,
                    )
                )
            else:
                message = (
                    f"Warning: skipping {provider} agent: neither the SDK "
                    f"(+{spec['key_env']}) nor the {binary} CLI is available"
                )
                print(message, file=sys.stderr)
                runtime.logger.warning(message)
        # constitution: exempt C-ERR — provider constructors expose third-party failures.
        except Exception as error:
            message = f"Warning: skipping {provider} agent ({selected}): {error}"
            print(message, file=sys.stderr)
            runtime.logger.warning(message.removeprefix("Warning: "))


def _append_cli_agents(
    runtime: _Runtime,
    enabled: dict[str, bool],
    providers: list[str],
    agents: list,
) -> None:
    models = resolve_cli_models(providers, runtime.args)
    for provider in providers:
        if not enabled[provider]:
            continue
        limiter = RateLimiter(**runtime.config.get(f"rate_limits.{provider}", {}))
        try:
            agents.append(
                CLIAgent(
                    provider,
                    models[provider],
                    runtime.timeout,
                    limiter,
                    config=runtime.config,
                    logger=runtime.logger,
                    streaming=runtime.streaming,
                )
            )
        except ValueError as error:
            message = f"Warning: skipping {provider} agent: {error}"
            print(message, file=sys.stderr)
            runtime.logger.warning(message.removeprefix("Warning: "))


def _build_agents(runtime: _Runtime, roster: dict) -> list:
    enabled = resolve_enabled_agents(
        roster,
        runtime.args,
        {name: runtime.services.is_enabled(name) for name in roster},
    )
    specs = _sdk_provider_specs(runtime)
    agents: list = []
    _append_sdk_agents(runtime, enabled, specs, agents)
    _append_cli_agents(
        runtime,
        enabled,
        cli_only_provider_names(roster, specs),
        agents,
    )
    return agents


def _resolve_roster_model_chain(agent, tiers: tuple[str, ...]):
    """Resolve a configured roster extension without widening skill metadata."""
    if not tiers or len(tiers) > 4 or len(set(tiers)) != len(tiers):
        raise ModelPolicyError("model chain must contain 1 to 4 unique tiers")
    resolved = []
    for index, tier in enumerate(tiers):
        model_id = agent._resolve_model(tier)
        if tier == "auto":
            if index != len(tiers) - 1 or model_id is not None:
                raise ModelPolicyError(f"{agent.name} cannot use auto in this chain")
        elif not isinstance(model_id, str) or not model_id:
            raise ModelPolicyError(f"unknown {agent.name} model tier {tier!r}")
        resolved.append(ResolvedModel(tier, model_id))
    return tuple(resolved)


def _apply_model_policy(runtime: _Runtime, agents: list) -> None:
    skill_policy = (
        parse_skill_model_policy(runtime.args.skill_path)
        if runtime.args.skill_path is not None
        else None
    )
    global_mode = runtime.config.get("model_fallback.mode", "confirm")
    for agent in agents:
        skill_chain = skill_policy.chains.get(agent.name, ()) if skill_policy else ()
        tiers = resolve_requested_model_tiers(agent.name, runtime.args, skill_chain)
        if not tiers:
            tiers = configured_fallback_tiers(
                runtime.config.config, agent.name, agent.original_model
            )
        agent.model_chain = (
            resolve_chain(runtime.config.config, agent.name, tiers)
            if agent.name in _MODEL_TIER_DEFAULTS
            else _resolve_roster_model_chain(agent, tiers)
        )
        agent.fallback_mode = effective_fallback_mode(
            runtime.args.model_fallback,
            skill_policy.fallback_mode if skill_policy else None,
            global_mode,
        )
        agent.interactive = not runtime.args.json and sys.stdin.isatty()
        agent.confirm_callback = lambda message: (
            input(f"{message} [y/N] ").strip().lower() in {"y", "yes"}
        )


def _require_agents(runtime: _Runtime, agents: list) -> None:
    warning = runtime.services.check_minimum_agents(len(agents))
    if warning:
        print(warning, file=sys.stderr)
        runtime.logger.warning(warning)
    if agents:
        return
    print(
        "Error: No agents available. Check services.yml or install dependencies.",
        file=sys.stderr,
    )
    runtime.logger.error("No agents available")
    raise SystemExit(1)


async def _execute(
    runtime: _Runtime,
    agents: list,
    prompt: str,
    mode: str,
    command: None,
) -> None:
    orchestrator = Orchestrator(
        agents,
        runtime.config,
        validate=runtime.args.validate,
        logger=runtime.logger,
        enable_synthesis=runtime.args.synthesize,
        streaming=runtime.streaming,
    )
    result = await orchestrator.execute(prompt, mode, command)
    if runtime.args.output or not runtime.args.full_output:
        result["output_files"] = await orchestrator._write_output_files(
            result,
            result["timestamp"],
            custom_output_dir=runtime.args.output,
            full_output=runtime.args.full_output,
        )
    orchestrator.print_results(result, json_output=runtime.args.json)

"""CLI entry point: argument parsing and top-level main() coroutine.

Dependency graph: config + runners + orchestrator → cli (highest fan-in by design).
"""

import argparse
from pathlib import Path

from agents.cli_policy import (
    _MODEL_TIER_DEFAULTS as _MODEL_TIER_DEFAULTS,
)
from agents.cli_policy import (
    cli_only_provider_names as cli_only_provider_names,
)
from agents.cli_policy import (
    resolve_cli_models as resolve_cli_models,
)
from agents.cli_policy import (
    resolve_enabled_agents as resolve_enabled_agents,
)
from agents.cli_policy import (
    resolve_requested_model_tiers as resolve_requested_model_tiers,
)
from agents.cli_runtime import (
    _apply_model_policy,
    _build_agents,
    _create_logger,
    _execute,
    _require_agents,
    _resolve_mode,
    _resolve_timeout,
    _run_credit_check,
    _run_status_check,
    _Runtime,
)
from agents.config import (
    Config,
    ServiceConfig,
    load_agent_roster,
)

# Fallback roster names used only if agent_roster.yml is missing/unreadable
# (load_agent_roster() degrades to {} in that case). Flag generation below
# depends on the roster being non-empty, so this is the cli.py-level safety
# net that keeps the 5 shipped agents' flags alive even on a machine that
# hasn't been re-bootstrapped with agent_roster.yml yet.
#
# devin is deliberately NOT here even though it has a tier default above. With
# no roster file, ServiceConfig.is_enabled() has no `enabled_default` to read
# and falls back to True — so listing devin would put an opt-in, login-gated
# agent into the panel on exactly the machines that never opted in. Its flags
# come back the moment a roster file exists.
_FALLBACK_ROSTER = {
    name: {} for name in ("claude", "gemini", "cursor", "codex", "antigravity")
}

# Historical per-agent flag ordering, pinned so `--help` output stays
# byte-identical to the pre-refactor hardcoded declarations. The --*-model
# and --*-only flags were declared claude/gemini/cursor/codex/antigravity;
# the --no-* flags were declared in a different order
# (claude/cursor/gemini/codex/antigravity) in the original file. Any roster
# agent not in a hint (e.g. a newly added one) is appended in roster order.
_ONLY_ORDER_HINT = ["claude", "gemini", "cursor", "codex", "antigravity"]
_NO_ORDER_HINT = ["claude", "cursor", "gemini", "codex", "antigravity"]


def _ordered(roster: dict, hint: list[str]) -> list[str]:
    ordered = [n for n in hint if n in roster]
    ordered += [n for n in roster if n not in hint]
    return ordered


def _add_common_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("prompt", nargs="?", help="Prompt to send to agents")
    parser.add_argument("--json", action="store_true", help="Output JSON format")
    parser.add_argument("--validate", action="store_true", help="Validate results")
    parser.add_argument("--review", metavar="FILE", help="Code review mode")
    parser.add_argument("--analyze", metavar="FILE", help="Bug/security analysis mode")
    parser.add_argument(
        "--improve", metavar="FILE", help="Improve observation YAML mode"
    )
    parser.add_argument(
        "--check-credits", action="store_true", help="Pre-flight credit check"
    )
    parser.add_argument("--output", metavar="DIR", help="Custom output directory")
    parser.add_argument(
        "--full-output",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Include complete outputs (--no-full-output truncates to 1000 chars)",
    )
    parser.add_argument(
        "--no-stream", action="store_true", help="Disable streaming output"
    )
    parser.add_argument(
        "--synthesize",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Enable synthesis for low consensus (--no-synthesize disables)",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=None,
        help="Timeout per agent (seconds). Defaults: review=600, analyze=900, improve=300, prompt=600",
    )
    parser.add_argument("--skill-path", type=Path, help="SKILL.md model policy")
    parser.add_argument(
        "--model-chain",
        help="comma-separated portable tiers appended after each explicit model",
    )
    parser.add_argument(
        "--model-fallback", choices=("auto", "confirm"), help="fallback authorization"
    )
    parser.add_argument(
        "--status",
        action="store_true",
        help="Check agent status (delegates to check_status.sh)",
    )


def _add_agent_arguments(parser: argparse.ArgumentParser, roster: dict) -> None:
    model_and_only_order = _ordered(roster, _ONLY_ORDER_HINT)
    for name in model_and_only_order:
        parser.add_argument(
            f"--{name}-model",
            default=None,
            help=f"{name.capitalize()} model tier",
        )
    for name in model_and_only_order:
        parser.add_argument(
            f"--{name}-only",
            action="store_true",
            help=f"Run only {name.capitalize()}",
        )

    for name in _ordered(roster, _NO_ORDER_HINT):
        parser.add_argument(
            f"--no-{name}",
            action="store_true",
            help=f"Disable {name.capitalize()} agent",
        )


def build_parser(roster: dict) -> argparse.ArgumentParser:
    """Build global and roster-derived parallel-agent arguments."""
    parser = argparse.ArgumentParser(description="Parallel Agent Orchestrator")
    _add_common_arguments(parser)
    _add_agent_arguments(parser, roster)
    return parser


async def main() -> None:
    """Parse configuration, build available agents, and execute one request."""
    roster = load_agent_roster() or _FALLBACK_ROSTER
    parser = build_parser(roster)
    args = parser.parse_args()
    config = Config()
    runtime = _Runtime(
        args,
        config,
        ServiceConfig(),
        _create_logger(config),
        0,
        not args.no_stream and config.get("streaming.enabled", True),
    )
    _run_status_check(args)
    await _run_credit_check(args, config, runtime.logger)
    mode, prompt, command = _resolve_mode(args, parser)
    runtime.timeout = _resolve_timeout(args, config, mode)
    agents = _build_agents(runtime, roster)
    _apply_model_policy(runtime, agents)
    _require_agents(runtime, agents)
    await _execute(runtime, agents, prompt, mode, command)

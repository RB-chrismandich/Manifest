"""CLI entry point: argument parsing and top-level main() coroutine.

Dependency graph: config + runners + orchestrator → cli (highest fan-in by design).
"""

import argparse
import json
import os
import shutil
import sys
from datetime import datetime
from pathlib import Path

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
from agents.runners import (
    ClaudeAgent,
    CLIAgent,
    GeminiAgent,
)


async def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(description="Parallel Agent Orchestrator")
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
    parser.add_argument("--claude-model", default="sonnet", help="Claude model tier")
    parser.add_argument("--gemini-model", default="flash", help="Gemini model tier")
    parser.add_argument("--cursor-model", default="flash", help="Cursor model tier")
    parser.add_argument("--codex-model", default="auto", help="Codex model tier")
    parser.add_argument(
        "--antigravity-model", default="flash", help="Antigravity model tier"
    )
    parser.add_argument("--claude-only", action="store_true", help="Run only Claude")
    parser.add_argument("--gemini-only", action="store_true", help="Run only Gemini")
    parser.add_argument("--cursor-only", action="store_true", help="Run only Cursor")
    parser.add_argument("--codex-only", action="store_true", help="Run only Codex")
    parser.add_argument(
        "--antigravity-only", action="store_true", help="Run only Antigravity"
    )
    parser.add_argument("--no-claude", action="store_true", help="Disable Claude agent")
    parser.add_argument("--no-cursor", action="store_true", help="Disable Cursor agent")
    parser.add_argument("--no-gemini", action="store_true", help="Disable Gemini agent")
    parser.add_argument("--no-codex", action="store_true", help="Disable Codex agent")
    parser.add_argument(
        "--no-antigravity", action="store_true", help="Disable Antigravity agent"
    )
    parser.add_argument(
        "--status",
        action="store_true",
        help="Check agent status (delegates to check_status.sh)",
    )

    args = parser.parse_args()

    # Load configuration
    config = Config()

    # Load service configuration
    services = ServiceConfig()

    # Create logger
    logger = Logger(config)
    logger.set_correlation_id(
        f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{os.getpid()}"
    )

    # Status check mode — delegate to check_status.sh
    if args.status:
        # Go up one level from agents/ to scripts/ to find sibling scripts
        script_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        status_script = os.path.join(script_dir, "check_status.sh")
        if os.path.exists(status_script):
            os.execv("/bin/bash", ["/bin/bash", status_script])
        else:
            print(f"Error: {status_script} not found", file=sys.stderr)
            sys.exit(1)

    # Credit check mode
    if args.check_credits:
        print("Checking API credits...")
        results = await check_credits(config, logger)
        print(json.dumps(results, indent=2))
        sys.exit(0)

    # Determine mode and prompt
    mode = "prompt"
    command = None

    if args.review:
        if not Path(args.review).exists():
            print(f"Error: file not found: {args.review}", file=sys.stderr)
            sys.exit(1)
        mode = "review"
        prompt = f"Review this file for code quality, security, and best practices: {args.review}"
    elif args.analyze:
        if not Path(args.analyze).exists():
            print(f"Error: file not found: {args.analyze}", file=sys.stderr)
            sys.exit(1)
        mode = "analyze"
        prompt = f"Analyze this file for bugs and security issues: {args.analyze}"
    elif args.improve:
        if not Path(args.improve).exists():
            print(f"Error: file not found: {args.improve}", file=sys.stderr)
            sys.exit(1)
        mode = "improve"
        prompt = f"Review and improve this observation YAML: {args.improve}"
    elif args.prompt:
        mode = "prompt"
        prompt = args.prompt
    else:
        parser.print_help()
        sys.exit(1)

    # Resolve timeout: explicit flag wins, then mode-based default from config
    if args.timeout is not None:
        timeout = args.timeout
    else:
        mode_timeouts = {
            "review": config.get("timeouts.review", 600),
            "analyze": config.get("timeouts.analyze", 900),
            "improve": config.get("timeouts.improve", 300),
            "prompt": config.get("timeouts.default", 600),
        }
        timeout = mode_timeouts.get(mode, 600)

    # Create rate limiters
    claude_limiter = RateLimiter(**config.get("rate_limits.claude", {}))
    gemini_limiter = RateLimiter(**config.get("rate_limits.gemini", {}))
    cursor_limiter = RateLimiter(**config.get("rate_limits.cursor", {}))
    codex_limiter = RateLimiter(**config.get("rate_limits.codex", {}))
    antigravity_limiter = RateLimiter(**config.get("rate_limits.antigravity", {}))

    # Determine streaming mode
    streaming = not args.no_stream and config.get("streaming.enabled", True)

    # --- Agent selection logic ---
    # 1. Start with services.yml enabled state
    enabled = {
        "claude": services.is_enabled("claude"),
        "gemini": services.is_enabled("gemini"),
        "cursor": services.is_enabled("cursor"),
        "codex": services.is_enabled("codex"),
        "antigravity": services.is_enabled("antigravity"),
    }

    # 2. Apply --*-only flags (exclusive: if any set, only those run)
    only_flags = {
        "claude": args.claude_only,
        "gemini": args.gemini_only,
        "cursor": args.cursor_only,
        "codex": args.codex_only,
        "antigravity": args.antigravity_only,
    }
    if any(only_flags.values()):
        for agent_name in enabled:
            enabled[agent_name] = only_flags[agent_name]

    # 3. Apply --no-* overrides (always win)
    if args.no_claude:
        enabled["claude"] = False
    if args.no_gemini:
        enabled["gemini"] = False
    if args.no_cursor:
        enabled["cursor"] = False
    if args.no_codex:
        enabled["codex"] = False
    if args.no_antigravity:
        enabled["antigravity"] = False

    # Build agents list
    agents = []

    sdk_providers = {
        "claude": {
            "agent_cls": ClaudeAgent,
            "has_sdk": HAS_ANTHROPIC,
            "key_env": "ANTHROPIC_API_KEY",
            "model": args.claude_model,
            "limiter": claude_limiter,
        },
        "gemini": {
            "agent_cls": GeminiAgent,
            "has_sdk": HAS_GENAI,
            "key_env": "GOOGLE_API_KEY",
            "model": args.gemini_model,
            "limiter": gemini_limiter,
        },
    }
    for provider, spec in sdk_providers.items():
        if not enabled[provider]:
            continue
        binary = config.get(f"cli_agents.{provider}.binary", provider)
        backend = select_backend(
            has_sdk=spec["has_sdk"],
            has_key=bool(os.environ.get(spec["key_env"])),
            has_cli=bool(shutil.which(binary)),
        )
        try:
            if backend == "sdk":
                agents.append(
                    spec["agent_cls"](
                        spec["model"],
                        timeout,
                        spec["limiter"],
                        config=config,
                        logger=logger,
                        streaming=streaming,
                    )
                )
            elif backend == "cli":
                agents.append(
                    CLIAgent(
                        provider,
                        spec["model"],
                        timeout,
                        spec["limiter"],
                        config=config,
                        logger=logger,
                        streaming=streaming,
                    )
                )
            else:
                msg = (
                    f"Warning: skipping {provider} agent: neither the SDK "
                    f"(+{spec['key_env']}) nor the {binary} CLI is available"
                )
                print(msg, file=sys.stderr)
                logger.warning(msg)
        except Exception as e:
            # SDK construction can raise (missing key, broken auth) and a
            # malformed cli_agents block raises ValueError — degrade to a
            # skipped provider, never a crashed orchestration.
            print(
                f"Warning: skipping {provider} agent ({backend}): {e}",
                file=sys.stderr,
            )
            logger.warning(f"Skipping {provider} agent ({backend}): {e}")

    cli_limiters = {
        "cursor": cursor_limiter,
        "codex": codex_limiter,
        "antigravity": antigravity_limiter,
    }
    cli_models = {
        "cursor": args.cursor_model,
        "codex": args.codex_model,
        "antigravity": args.antigravity_model,
    }
    for provider in ("cursor", "codex", "antigravity"):
        if enabled[provider]:
            try:
                agents.append(
                    CLIAgent(
                        provider,
                        cli_models[provider],
                        timeout,
                        cli_limiters[provider],
                        config=config,
                        logger=logger,
                        streaming=streaming,
                    )
                )
            except ValueError as e:
                print(
                    f"Warning: skipping {provider} agent: {e}",
                    file=sys.stderr,
                )
                logger.warning(f"Skipping {provider} agent: {e}")

    # Check minimum agents
    min_warning = services.check_minimum_agents(len(agents))
    if min_warning:
        print(min_warning, file=sys.stderr)
        logger.warning(min_warning)

    if not agents:
        print(
            "Error: No agents available. Check services.yml or install dependencies.",
            file=sys.stderr,
        )
        logger.error("No agents available")
        sys.exit(1)

    # Create orchestrator and execute
    orchestrator = Orchestrator(
        agents,
        config,
        validate=args.validate,
        logger=logger,
        enable_synthesis=args.synthesize,
        streaming=streaming,
    )

    result = await orchestrator.execute(prompt, mode, command)

    # Write output files (with custom directory if provided)
    if args.output or not args.full_output:
        result["output_files"] = await orchestrator._write_output_files(
            result,
            result["timestamp"],
            custom_output_dir=args.output,
            full_output=args.full_output,
        )

    # Print results
    orchestrator.print_results(result, json_output=args.json)

#!/usr/bin/env python3
# help-coverage: exempt — interceptor wrapper; argv IS the wrapped command being
# intercepted, so --help is forwarded to the child rather than handled here.
"""BudgetBroker Command Interceptor Wrapper.

Intercepts outgoing CLI agent execution calls, estimates token spend, tracks costs,
and handles credit/quota fallbacks dynamically.
"""

import subprocess
import sys
from pathlib import Path

BUDGET_LOG = Path("~/.claude/.agent_outputs/budget.log").expanduser()


def estimate_tokens(prompt: str) -> int:
    """Rough character-to-token heuristic (4 chars per token)."""
    return len(prompt) // 4


def log_budget(msg: str):
    """Log budget event to the log file."""
    BUDGET_LOG.parent.mkdir(parents=True, exist_ok=True)
    with open(BUDGET_LOG, "a") as f:
        f.write(f"{msg}\n")


def is_quota_error(output: str) -> bool:
    """Detect quota, rate limit, or credit exhaustion errors."""
    indicators = [
        "quota exceeded",
        "rate limit",
        "insufficient credits",
        "credit exhaustion",
        "spend limit",
        "429",
    ]
    return any(ind in output.lower() for ind in indicators)


# The wrapper is invoked as the CLI binary; parallel_agent.yml is keyed by
# provider. This is the only mapping that has to live here, and it mirrors
# `cli_agents.<provider>.binary`.
BINARY_TO_PROVIDER = {
    "claude": "claude",
    "gemini": "gemini",
    "cursor-agent": "cursor",
    "codex": "codex",
    "agy": "antigravity",
}


def fallback_chain(binary: str) -> list[str]:
    """Concrete models a provider falls through, cheapest last.

    Resolved from parallel_agent.yml rather than restated here. This module
    used to carry its own copy and it had already drifted: it still named
    claude-opus-4-8 and an entire pre-grok cursor ladder while every other
    consumer had moved on (CON-003).
    """
    provider = BINARY_TO_PROVIDER.get(binary)
    if provider is None:
        return []
    from agents.config import Config

    config = Config()
    tier_map = config.get(f"model_tiers.{provider}", {}) or {}
    tiers = config.get(f"credit_fallback.{provider}", []) or []
    return [tier_map[tier] for tier in tiers if tier in tier_map]


def get_fallback_model(binary: str, current_model: str) -> str | None:
    """Return the next fallback model for a provider, or None at the bottom."""
    chain = fallback_chain(binary)
    if not chain:
        return None
    try:
        idx = chain.index(current_model)
    except ValueError:
        # An unrecognized model means "start at the bottom", not an error.
        return chain[-1]
    return chain[idx + 1] if idx + 1 < len(chain) else None


def run_command(cmd: list[str]) -> subprocess.CompletedProcess:
    """Run the command subprocess."""
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
    )


def main():
    if len(sys.argv) < 2:
        print("Usage: budget_broker.py <binary> [args...]", file=sys.stderr)
        sys.exit(2)

    cmd = sys.argv[1:]
    binary = cmd[0]

    # Find the prompt in args to estimate tokens
    prompt = ""
    for arg in cmd:
        if len(arg) > 50:  # Heuristic for the prompt string
            prompt = arg
            break

    tokens = estimate_tokens(prompt)
    log_budget(
        f"[BUDGET_BROKER] Executing: {' '.join(cmd)} | Est. Input Tokens: {tokens}"
    )

    # Initial execution
    res = run_command(cmd)

    # Check for quota errors
    combined_output = res.stdout + "\n" + res.stderr
    if res.returncode != 0 and is_quota_error(combined_output):
        log_budget(
            "[BUDGET_BROKER] Quota/Rate limit error detected. Attempting fallback..."
        )

        # Extract current model from command line args
        current_model = None
        model_flag_idx = -1
        for i, arg in enumerate(cmd):
            if arg in ("--model", "-m"):
                model_flag_idx = i
                if i + 1 < len(cmd):
                    current_model = cmd[i + 1]
                break

        if current_model:
            fallback = get_fallback_model(binary, current_model)
            if fallback:
                cmd[model_flag_idx + 1] = fallback
                log_budget(f"[BUDGET_BROKER] Retrying command with model: {fallback}")
                res = run_command(cmd)

    # Output original streams
    sys.stdout.write(res.stdout)
    sys.stderr.write(res.stderr)
    sys.exit(res.returncode)


if __name__ == "__main__":
    main()

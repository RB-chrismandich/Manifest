#!/usr/bin/env python3
"""Acceptance test for Task 24: config-only CLI-agent extensibility.

A CLI-only agent that exists *only* in agent_roster.yml (not in
parallel_agent.yml's cli_agents block, and with no dedicated Python class)
must still produce a working CLIAgent runner with the correct binary/args.
This is the test that proves the roster refactor is real config-only
extensibility, not just a rename of the existing generic CLIAgent class.
"""

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
SCRIPTS_DIR = str(REPO_ROOT / "configs" / "claude" / "scripts")
sys.path.insert(0, SCRIPTS_DIR)

from agents.config import Config, RateLimiter
from agents.runners import CLIAgent

# The 5 real agents plus a 6th synthetic "widget" agent that exists nowhere
# else in the codebase — not in parallel_agent.yml, not in config.py's
# _default_config(), and with no dedicated runner class.
SYNTHETIC_ROSTER = """
agents:
  claude:
    name: claude
    binary: claude
    home_dir: ~/.claude
    prompt_args: ["-p", "{prompt}"]
    model_args: ["--model", "{model}"]
    auth_check: "claude auth status"
    enabled_default: true
  gemini:
    name: gemini
    binary: gemini
    home_dir: ~/.gemini
    prompt_args: ["-p", "{prompt}"]
    model_args: ["-m", "{model}"]
    auth_check: "gemini auth status"
    enabled_default: true
  cursor:
    name: cursor
    binary: cursor-agent
    home_dir: ~/.cursor
    prompt_args: ["{prompt}"]
    model_args: ["--model", "{model}"]
    auth_check: "cursor-agent --version"
    enabled_default: true
  codex:
    name: codex
    binary: codex
    home_dir: ~/.codex
    prompt_args: ["{prompt}"]
    model_args: ["--model", "{model}"]
    auth_check: "codex login status"
    enabled_default: true
  antigravity:
    name: antigravity
    binary: agy
    home_dir: ~/.antigravity
    prompt_args: ["--print", "{prompt}"]
    model_args: ["--model", "{model}"]
    auth_check: "agy models"
    enabled_default: true
  widget:
    name: widget
    binary: widget-cli
    home_dir: ~/.widget
    prompt_args: ["--ask", "{prompt}"]
    model_args: ["--model", "{model}"]
    auth_check: "widget-cli whoami"
    enabled_default: true
"""


def _make_config(tmp_path):
    roster_file = tmp_path / "agent_roster.yml"
    roster_file.write_text(SYNTHETIC_ROSTER)
    return Config(
        config_path=str(tmp_path / "none.yml"),
        roster_path=str(roster_file),
    )


def _make_limiter():
    return RateLimiter(requests_per_minute=1000, burst_size=100)


class TestSixthSyntheticRosterAgent:
    def test_generic_cli_agent_builds_command_for_roster_only_provider(self, tmp_path):
        """`widget` has no cli_agents entry anywhere — only the roster
        fixture. CLIAgent must still assemble a correct command."""
        config = _make_config(tmp_path)
        agent = CLIAgent(
            "widget",
            model="widget-model-1",
            rate_limiter=_make_limiter(),
            config=config,
        )
        cmd = agent._build_command("hello")
        assert cmd == ["widget-cli", "--model", "widget-model-1", "--ask", "hello"]

    def test_no_new_subclass_required(self, tmp_path):
        """The roster-driven agent is a plain CLIAgent instance — config-only
        extensibility, not a per-provider subclass."""
        config = _make_config(tmp_path)
        agent = CLIAgent(
            "widget",
            model="auto",
            rate_limiter=_make_limiter(),
            config=config,
        )
        assert type(agent) is CLIAgent

    def test_roster_only_provider_missing_binary_still_raises(self, tmp_path):
        """A malformed roster entry (no binary) must fail the same way a
        malformed cli_agents entry does, not silently build a broken argv."""
        roster_file = tmp_path / "agent_roster.yml"
        roster_file.write_text("agents:\n  broken:\n    name: broken\n")
        config = Config(
            config_path=str(tmp_path / "none.yml"),
            roster_path=str(roster_file),
        )
        with pytest.raises(ValueError, match="binary is required"):
            CLIAgent(
                "broken", model="flash", rate_limiter=_make_limiter(), config=config
            )

    def test_known_providers_still_use_cli_agents_not_roster_fallback(self, tmp_path):
        """cursor has a real cli_agents entry (via _default_config, which
        mirrors parallel_agent.yml) — its base_args (headless + read-only
        flags) must keep coming from there, not the roster fallback, which
        would silently drop them."""
        config = _make_config(tmp_path)
        agent = CLIAgent(
            "cursor",
            model="flash",
            rate_limiter=_make_limiter(),
            config=config,
        )
        cmd = agent._build_command("hello")
        assert "--print" in cmd
        assert cmd[cmd.index("--mode") + 1] == "ask"

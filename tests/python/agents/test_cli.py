#!/usr/bin/env python3
"""Per-module unit tests for agents.cli.

Tests CLI argument parsing in isolation via subprocess — no live agents required.
"""

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
ENTRY_POINT = str(REPO_ROOT / "configs" / "claude" / "scripts" / "parallel_agent.py")


def _run(*args, **kwargs):
    """Run the entry point with given args and return CompletedProcess."""
    return subprocess.run(
        [sys.executable, ENTRY_POINT, *args],
        capture_output=True,
        text=True,
        **kwargs,
    )


class TestCLIArgParsing:
    def test_help_exits_zero(self):
        result = _run("--help")
        assert result.returncode == 0

    def test_help_contains_json_flag(self):
        result = _run("--help")
        assert "--json" in result.stdout

    def test_help_contains_validate_flag(self):
        result = _run("--help")
        assert "--validate" in result.stdout

    def test_help_contains_review_flag(self):
        result = _run("--help")
        assert "--review" in result.stdout

    def test_help_contains_analyze_flag(self):
        result = _run("--help")
        assert "--analyze" in result.stdout

    def test_help_contains_timeout_flag(self):
        result = _run("--help")
        assert "--timeout" in result.stdout

    def test_help_contains_claude_only_flag(self):
        result = _run("--help")
        assert "--claude-only" in result.stdout

    def test_no_args_exits_nonzero(self):
        result = _run()
        assert result.returncode != 0

    def test_review_nonexistent_file_exits_nonzero(self):
        result = _run("--review", "/nonexistent/path/file.py")
        assert result.returncode != 0

    def test_review_nonexistent_file_prints_error(self):
        result = _run("--review", "/nonexistent/path/file.py")
        assert "error" in result.stderr.lower() or "not found" in result.stderr.lower()

    def test_analyze_nonexistent_file_exits_nonzero(self):
        result = _run("--analyze", "/nonexistent/path/file.py")
        assert result.returncode != 0

    def test_improve_nonexistent_file_exits_nonzero(self):
        result = _run("--improve", "/nonexistent/path/file.py")
        assert result.returncode != 0


# ---------------------------------------------------------------------------
# select_backend — SDK vs CLI fallback decision (claude, gemini)
# ---------------------------------------------------------------------------

SCRIPTS_DIR = str(REPO_ROOT / "configs" / "claude" / "scripts")
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

from agents.config import select_backend


class TestSelectBackend:
    """The OAuth-only machine case (no API key, authenticated CLI on PATH)
    must select "cli" — that gap left only the Antigravity path runnable."""

    def test_sdk_preferred_when_package_and_key_present(self):
        assert select_backend(has_sdk=True, has_key=True, has_cli=True) == "sdk"

    def test_sdk_with_key_wins_even_without_cli(self):
        assert select_backend(has_sdk=True, has_key=True, has_cli=False) == "sdk"

    def test_cli_fallback_when_key_missing(self):
        # OAuth-only machine: SDK installed but no API key, CLI on PATH
        assert select_backend(has_sdk=True, has_key=False, has_cli=True) == "cli"

    def test_cli_fallback_when_sdk_missing(self):
        # No SDK at all, CLI on PATH (the state that motivated this fallback)
        assert select_backend(has_sdk=False, has_key=False, has_cli=True) == "cli"

    def test_sdk_last_resort_for_own_auth(self):
        # SDK present, no key, no CLI: let the SDK try its own auth (ADC/OAuth)
        assert select_backend(has_sdk=True, has_key=False, has_cli=False) == "sdk"

    def test_none_when_nothing_available(self):
        assert select_backend(has_sdk=False, has_key=False, has_cli=False) is None

    def test_key_alone_is_not_enough_for_sdk(self):
        # Key set but package missing: CLI if present, else nothing
        assert select_backend(has_sdk=False, has_key=True, has_cli=True) == "cli"
        assert select_backend(has_sdk=False, has_key=True, has_cli=False) is None


# ---------------------------------------------------------------------------
# Roster-driven flags/dispatch — a 6th synthetic CLI-only agent ("beta", no
# sdk_providers entry) must get working flags and reach CLIAgent construction
# with zero changes to cli.py, proving build_parser()/cli_only_provider_names()
# are genuinely roster-driven rather than hardcoded to the 5 shipped agents.
# ---------------------------------------------------------------------------

import yaml

from agents.cli import (
    build_parser,
    cli_only_provider_names,
    resolve_cli_models,
    resolve_enabled_agents,
)
from agents.config import Config, RateLimiter
from agents.runners import CLIAgent

# Mirrors agent_roster.yml's key order (claude, gemini, cursor, codex,
# antigravity) plus a synthetic 6th CLI-only agent appended at the end.
ROSTER_WITH_BETA = {
    "claude": {},
    "gemini": {},
    "cursor": {},
    "codex": {},
    "antigravity": {},
    "beta": {},
}

# claude/gemini go through the SDK-selection path (untouched by this task);
# everything else — including the synthetic "beta" — is CLI-only dispatch.
FAKE_SDK_PROVIDERS = {"claude": {}, "gemini": {}}


class TestRosterDrivenSixthAgent:
    def test_beta_only_flag_parses(self):
        parser = build_parser(ROSTER_WITH_BETA)
        args = parser.parse_args(["--beta-only"])
        assert args.beta_only is True

    def test_no_beta_flag_parses(self):
        parser = build_parser(ROSTER_WITH_BETA)
        args = parser.parse_args(["--no-beta"])
        assert args.no_beta is True

    def test_beta_model_flag_parses_with_generic_default(self):
        parser = build_parser(ROSTER_WITH_BETA)
        args = parser.parse_args([])
        # "beta" has no entry in _MODEL_TIER_DEFAULTS (not in
        # agent_roster.yml's schema) — falls back to the generic "auto".
        assert args.beta_model == "auto"

    def test_beta_model_flag_accepts_override(self):
        parser = build_parser(ROSTER_WITH_BETA)
        args = parser.parse_args(["--beta-model", "advanced"])
        assert args.beta_model == "advanced"

    def test_help_shows_beta_flags(self):
        parser = build_parser(ROSTER_WITH_BETA)
        help_text = parser.format_help()
        assert "--beta-only" in help_text
        assert "--no-beta" in help_text
        assert "--beta-model" in help_text

    def test_beta_is_in_cli_only_dispatch_set(self):
        names = cli_only_provider_names(ROSTER_WITH_BETA, FAKE_SDK_PROVIDERS)
        assert names == ["cursor", "codex", "antigravity", "beta"]

    def test_claude_and_gemini_excluded_from_cli_only_dispatch(self):
        names = cli_only_provider_names(ROSTER_WITH_BETA, FAKE_SDK_PROVIDERS)
        assert "claude" not in names
        assert "gemini" not in names

    def test_cliagent_beta_constructs_through_roster_fallback(self, tmp_path):
        """Reachability proof: a CLIAgent("beta", ...) construction succeeds
        via the same Config.get_cli_agent_spec() roster-fallback path that
        cursor/codex/antigravity use, when "beta" has no cli_agents entry in
        parallel_agent.yml but does have a roster entry."""
        roster_file = tmp_path / "agent_roster.yml"
        roster_file.write_text(
            yaml.dump(
                {
                    "agents": {
                        "beta": {
                            "name": "beta",
                            "binary": "echo",
                            "home_dir": "~/.beta",
                            "prompt_args": ["{prompt}"],
                            "model_args": ["--model", "{model}"],
                            "auth_check": "echo ok",
                            "enabled_default": True,
                        }
                    }
                }
            )
        )
        config = Config(
            config_path=str(tmp_path / "nonexistent_parallel_agent.yml"),
            roster_path=str(roster_file),
        )
        limiter = RateLimiter(requests_per_minute=1000, burst_size=100)
        agent = CLIAgent(
            "beta",
            "auto",
            30,
            limiter,
            config=config,
        )
        assert agent.binary == "echo"
        assert agent.name == "beta"


# ---------------------------------------------------------------------------
# Hyphenated roster agent name — argparse mangles a flag's dest by replacing
# '-' with '_' (e.g. "--gemini-pro-only" -> args.gemini_pro_only), so any
# getattr(args, f"{name}_only") lookup that reuses the *raw* roster name
# (still hyphenated) raises AttributeError. That AttributeError fires
# unconditionally during startup arg processing for EVERY invocation, not
# just ones targeting the hyphenated agent — so this is a regression test
# for a full-script crash, not a per-agent edge case. Uses the same
# fresh-fixture pattern as TestRosterDrivenSixthAgent above.
# ---------------------------------------------------------------------------

ROSTER_WITH_HYPHENATED_NAME = {
    "claude": {},
    "gemini": {},
    "gemini-pro": {},
}

FAKE_SDK_PROVIDERS_HYPHEN = {"claude": {}, "gemini": {}}


class TestHyphenatedRosterAgentName:
    def test_hyphenated_flags_present_in_help(self):
        parser = build_parser(ROSTER_WITH_HYPHENATED_NAME)
        help_text = parser.format_help()
        assert "--gemini-pro-only" in help_text
        assert "--no-gemini-pro" in help_text
        assert "--gemini-pro-model" in help_text

    def test_gemini_pro_only_flag_mangles_to_underscored_dest(self):
        # Confirms argparse's own behavior: the flag is hyphenated but the
        # dest attribute is underscored. This is the ground truth that
        # downstream getattr(args, ...) lookups must match.
        parser = build_parser(ROSTER_WITH_HYPHENATED_NAME)
        args = parser.parse_args(["--gemini-pro-only"])
        assert args.gemini_pro_only is True
        assert not hasattr(args, "gemini-pro_only")

    def test_resolve_enabled_agents_does_not_raise_for_hyphenated_name(self):
        """This is the exact code path that crashed the entire script for
        ALL agents (not just the hyphenated one) before the fix: main()
        calls this unconditionally during startup, before any agent
        dispatch. Reproducing it directly (no subprocess) proves the fix
        without needing live agent binaries/keys."""
        parser = build_parser(ROSTER_WITH_HYPHENATED_NAME)
        args = parser.parse_args(["--claude-only", "ping"])
        enabled = resolve_enabled_agents(
            ROSTER_WITH_HYPHENATED_NAME,
            args,
            {"claude": True, "gemini": True, "gemini-pro": True},
        )
        # --claude-only is exclusive: only claude stays enabled.
        assert enabled == {"claude": True, "gemini": False, "gemini-pro": False}

    def test_gemini_pro_only_flag_resolves_correctly(self):
        parser = build_parser(ROSTER_WITH_HYPHENATED_NAME)
        args = parser.parse_args(["--gemini-pro-only"])
        enabled = resolve_enabled_agents(
            ROSTER_WITH_HYPHENATED_NAME,
            args,
            {"claude": True, "gemini": True, "gemini-pro": True},
        )
        assert enabled == {"claude": False, "gemini": False, "gemini-pro": True}

    def test_no_gemini_pro_flag_always_wins(self):
        parser = build_parser(ROSTER_WITH_HYPHENATED_NAME)
        args = parser.parse_args(["--no-gemini-pro"])
        enabled = resolve_enabled_agents(
            ROSTER_WITH_HYPHENATED_NAME,
            args,
            {"claude": True, "gemini": True, "gemini-pro": True},
        )
        assert enabled == {"claude": True, "gemini": True, "gemini-pro": False}

    def test_gemini_pro_model_flag_resolves_via_cli_only_dispatch(self):
        parser = build_parser(ROSTER_WITH_HYPHENATED_NAME)
        args = parser.parse_args(["--gemini-pro-model", "advanced"])
        cli_only = cli_only_provider_names(
            ROSTER_WITH_HYPHENATED_NAME, FAKE_SDK_PROVIDERS_HYPHEN
        )
        assert cli_only == ["gemini-pro"]
        cli_models = resolve_cli_models(cli_only, args)
        assert cli_models == {"gemini-pro": "advanced"}

    def test_default_gemini_pro_model_resolves_without_override(self):
        parser = build_parser(ROSTER_WITH_HYPHENATED_NAME)
        args = parser.parse_args([])
        cli_only = cli_only_provider_names(
            ROSTER_WITH_HYPHENATED_NAME, FAKE_SDK_PROVIDERS_HYPHEN
        )
        cli_models = resolve_cli_models(cli_only, args)
        # "gemini-pro" has no entry in _MODEL_TIER_DEFAULTS -> generic "auto".
        assert cli_models == {"gemini-pro": "auto"}

#!/usr/bin/env python3
"""Per-module unit tests for agents.cli.

Tests CLI argument parsing in isolation via subprocess — no live agents required.
"""

import os
import subprocess
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
ENTRY_POINT = str(REPO_ROOT / "configs" / "claude" / "scripts" / "parallel_agent.py")

# Tests below that assert on the actual `manifest parallel-agent --help`/error
# surface need the project venv built (`uv sync --project configs/claude`, as
# CI's Test job and _stub_home_runtime() below both do). Without it, the
# parallel_agent.py shim can't resolve a manifest binary and instead prints a
# generic deprecation notice -- a real, different code path, not a failure of
# the thing being tested. Skip cleanly rather than asserting against that
# notice's text.
_MANIFEST_RUNTIME_AVAILABLE = (
    REPO_ROOT / "configs" / "claude" / ".venv" / "bin" / "manifest"
).exists()
_REQUIRES_MANIFEST_RUNTIME = pytest.mark.skipif(
    not _MANIFEST_RUNTIME_AVAILABLE,
    reason=(
        "requires the manifest home runtime built at "
        "configs/claude/.venv/bin/manifest -- run "
        "`uv sync --project configs/claude` (see .github/workflows/ci.yml)"
    ),
)

_STUB_HOME: str | None = None


def _stub_home_runtime() -> str:
    """A HOME whose ~/.claude/.venv points at the repo's project venv so the
    parallel_agent.py deprecation shim resolves the `manifest` home runtime
    (mirrors the bats stub_home_manifest_runtime helper). The venv is built by
    `uv sync --project configs/claude`, as CI's Test job does. Cached per run."""
    global _STUB_HOME
    if _STUB_HOME is not None:
        return _STUB_HOME
    manifest = REPO_ROOT / "configs" / "claude" / ".venv" / "bin" / "manifest"
    home = Path(tempfile.mkdtemp(prefix="manifest_home_"))
    if manifest.exists():
        venv_bin = home / ".claude" / ".venv" / "bin"
        venv_bin.mkdir(parents=True, exist_ok=True)
        (venv_bin / "manifest").symlink_to(manifest)
        local_bin = home / ".local" / "bin"
        local_bin.mkdir(parents=True, exist_ok=True)
        uv = local_bin / "uv"
        uv.write_text("#!/bin/sh\nexit 0\n")
        uv.chmod(0o755)
    _STUB_HOME = str(home)
    return _STUB_HOME


def _run(*args, **kwargs):
    """Run the entry point with given args and return CompletedProcess."""
    env = {**os.environ, "HOME": _stub_home_runtime()}
    return subprocess.run(
        [sys.executable, ENTRY_POINT, *args],
        capture_output=True,
        text=True,
        env=env,
        **kwargs,
    )


class TestCLIArgParsing:
    def test_help_exits_zero(self):
        result = _run("--help")
        assert result.returncode == 0

    @_REQUIRES_MANIFEST_RUNTIME
    def test_help_contains_json_flag(self):
        result = _run("--help")
        assert "--json" in result.stdout

    @_REQUIRES_MANIFEST_RUNTIME
    def test_help_contains_validate_flag(self):
        result = _run("--help")
        assert "--validate" in result.stdout

    @_REQUIRES_MANIFEST_RUNTIME
    def test_help_contains_review_flag(self):
        result = _run("--help")
        assert "--review" in result.stdout

    @_REQUIRES_MANIFEST_RUNTIME
    def test_help_contains_analyze_flag(self):
        result = _run("--help")
        assert "--analyze" in result.stdout

    @_REQUIRES_MANIFEST_RUNTIME
    def test_help_contains_timeout_flag(self):
        result = _run("--help")
        assert "--timeout" in result.stdout

    @_REQUIRES_MANIFEST_RUNTIME
    def test_help_contains_claude_only_flag(self):
        result = _run("--help")
        assert "--claude-only" in result.stdout

    def test_no_args_exits_nonzero(self):
        result = _run()
        assert result.returncode != 0

    def test_review_nonexistent_file_exits_nonzero(self):
        result = _run("--review", "/nonexistent/path/file.py")
        assert result.returncode != 0

    @_REQUIRES_MANIFEST_RUNTIME
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
    _MODEL_TIER_DEFAULTS,
    _apply_model_policy,
    _Runtime,
    build_parser,
    cli_only_provider_names,
    resolve_cli_models,
    resolve_requested_model_tiers,
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
        assert args.beta_model is None
        assert resolve_cli_models(["beta"], args) == {"beta": "auto"}

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

    @pytest.mark.parametrize("agent_name", ("beta", "test-agent"))
    def test_model_policy_accepts_roster_only_agents(self, tmp_path, agent_name):
        roster = {
            agent_name: {
                "name": agent_name,
                "binary": "echo",
                "home_dir": f"~/.{agent_name}",
                "prompt_args": ["{prompt}"],
                "model_args": ["--model", "{model}"],
                "auth_check": "echo ok",
                "enabled_default": True,
            }
        }
        roster_file = tmp_path / "agent_roster.yml"
        roster_file.write_text(yaml.dump({"agents": roster}))
        config = Config(
            config_path=str(tmp_path / "nonexistent_parallel_agent.yml"),
            roster_path=str(roster_file),
        )
        args = build_parser(roster).parse_args([f"--{agent_name}-only", "ping"])
        runtime = _Runtime(args, config, None, None, 30, False)
        agent = CLIAgent(
            agent_name,
            "auto",
            30,
            RateLimiter(requests_per_minute=1000, burst_size=100),
            config=config,
        )

        _apply_model_policy(runtime, [agent])

        assert tuple((item.tier, item.model_id) for item in agent.model_chain) == (
            ("auto", None),
        )


class TestModelChainOrdering:
    @pytest.mark.parametrize(
        ("agent_name", "starting_tier", "expected"),
        (
            ("codex", "auto", ("advanced", "flash", "mini", "auto")),
            ("claude", "sonnet", ("sonnet", "haiku")),
        ),
    )
    def test_ordinary_invocation_applies_configured_fallback_chain(
        self, tmp_path, agent_name, starting_tier, expected
    ):
        roster = {name: {} for name in _MODEL_TIER_DEFAULTS}
        args = build_parser(roster).parse_args(["ordinary task"])
        config = Config(
            config_path=str(tmp_path / "missing.yml"),
            roster_path=str(tmp_path / "missing-roster.yml"),
        )
        runtime = _Runtime(args, config, None, None, 120, False)
        agent = SimpleNamespace(
            name=agent_name,
            original_model=starting_tier,
            model_chain=None,
            fallback_mode=None,
            interactive=False,
            confirm_callback=None,
        )

        _apply_model_policy(runtime, [agent])

        assert tuple(item.tier for item in agent.model_chain) == expected

    @pytest.mark.parametrize(
        "agent_name", ("claude", "gemini", "cursor", "codex", "antigravity", "devin")
    )
    def test_chain_only_is_exactly_the_supplied_chain(self, agent_name):
        roster = {name: {} for name in _MODEL_TIER_DEFAULTS}
        args = build_parser(roster).parse_args(["--model-chain", "flash,auto"])

        assert resolve_requested_model_tiers(agent_name, args) == ("flash", "auto")

    @pytest.mark.parametrize(
        "agent_name", ("claude", "gemini", "cursor", "codex", "antigravity", "devin")
    )
    def test_explicit_agent_model_precedes_supplied_chain(self, agent_name):
        roster = {name: {} for name in _MODEL_TIER_DEFAULTS}
        args = build_parser(roster).parse_args(
            [f"--{agent_name}-model", "advanced", "--model-chain", "flash,auto"]
        )

        assert resolve_requested_model_tiers(agent_name, args) == (
            "advanced",
            "flash",
            "auto",
        )

    @pytest.mark.parametrize(
        "agent_name", ("claude", "gemini", "cursor", "codex", "antigravity", "devin")
    )
    def test_explicit_agent_model_overrides_skill_chain(self, agent_name):
        roster = {name: {} for name in _MODEL_TIER_DEFAULTS}
        args = build_parser(roster).parse_args([f"--{agent_name}-model", "advanced"])

        assert resolve_requested_model_tiers(agent_name, args, ("flash", "auto")) == (
            "advanced",
        )


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

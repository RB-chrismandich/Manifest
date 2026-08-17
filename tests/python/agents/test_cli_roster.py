#!/usr/bin/env python3
"""Per-module unit tests for agents.cli.

Tests CLI argument parsing in isolation via subprocess — no live agents required.
"""

import os
import subprocess
import sys
import tempfile
from pathlib import Path

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


from agents.cli import (
    _MODEL_TIER_DEFAULTS,
    build_parser,
    cli_only_provider_names,
    resolve_cli_models,
    resolve_enabled_agents,
)

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


# ---------------------------------------------------------------------------
# Drift guard (goal-task-E, Part 2): cli.py's own hardcoded-default copies --
# _FALLBACK_ROSTER (used only when agent_roster.yml is missing/unreadable,
# see cli.py's module comment) and _MODEL_TIER_DEFAULTS (model-tier defaults;
# NOT part of agent_roster.yml's schema by design -- see agent_roster.yml's
# header) -- are two of several independent hardcoded-default copies this
# goal's work created (see also reconcile_core.py's _DEFAULT_ROOT_TAGS in
# test_reconcile_policy.py, and check_status.sh's/sync-skills.sh's tier-3
# arrays in tests/bats/agent_roster_drift_guard.bats). Neither dict carries
# binary/home_dir/auth_check values to compare -- only names -- so the guard
# here is name-SET equality against the REAL agent_roster.yml (read live,
# not a hardcoded expectation), so a future agent rename/removal not
# mirrored into cli.py's fallbacks fails here instead of shipping a stale
# copy that silently drops (or never grows) flags for the known fleet.
# ---------------------------------------------------------------------------


class TestCliFallbackDriftGuard:
    def test_fallback_roster_names_match_real_default_on_registry_agents(self):
        """The no-roster-file fallback carries the DEFAULT-ON agents only.

        With no registry, ServiceConfig.is_enabled() has no `enabled_default`
        to consult and returns True, so an opt-in agent listed here would join
        the panel on precisely the machines that never opted in.
        """
        import yaml
        from agents.cli import _FALLBACK_ROSTER

        roster_path = REPO_ROOT / "configs" / "claude" / "config" / "agent_roster.yml"
        with open(roster_path, encoding="utf-8") as fh:
            agents = yaml.safe_load(fh)["agents"]
        default_on = {n for n, e in agents.items() if e["enabled_default"]}
        assert set(_FALLBACK_ROSTER) == default_on

    def test_opt_in_agent_is_absent_from_the_no_registry_fallback(self):
        from agents.cli import _FALLBACK_ROSTER

        assert "devin" not in _FALLBACK_ROSTER

    def test_model_tier_defaults_names_match_real_registry(self):
        import yaml

        roster_path = REPO_ROOT / "configs" / "claude" / "config" / "agent_roster.yml"
        with open(roster_path, encoding="utf-8") as fh:
            real_names = set(yaml.safe_load(fh)["agents"])
        assert set(_MODEL_TIER_DEFAULTS) == real_names

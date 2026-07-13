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

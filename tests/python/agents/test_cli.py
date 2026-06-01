#!/usr/bin/env python3
"""Per-module unit tests for agents.cli.

Tests CLI argument parsing in isolation via subprocess — no live agents required.
"""

import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
ENTRY_POINT = str(
    REPO_ROOT / "configs" / "claude" / "scripts" / "parallel_agent.py"
)


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

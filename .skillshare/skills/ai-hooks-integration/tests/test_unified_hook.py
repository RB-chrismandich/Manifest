#!/usr/bin/env python3
"""Tests for unified hook script."""

import json
import os
import subprocess
import sys
import unittest

# Add scripts directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

from runtime.unified_hook import (
    allow_response,
    deny_response,
    extract_command,
    extract_cwd,
    normalize_event,
    should_drop_event,
)


class TestExtractCwd(unittest.TestCase):
    """Test cwd extraction from various payload formats."""

    def test_direct_cwd(self):
        """Should extract cwd from direct field."""
        payload = {"cwd": "/path/to/project"}
        self.assertEqual(extract_cwd(payload), "/path/to/project")

    def test_working_directory(self):
        """Should extract from working_directory (Gemini format)."""
        payload = {"working_directory": "/path/to/project"}
        self.assertEqual(extract_cwd(payload), "/path/to/project")

    def test_nested_tool_input(self):
        """Should extract from tool_input.cwd."""
        payload = {"tool_input": {"cwd": "/path/to/project"}}
        self.assertEqual(extract_cwd(payload), "/path/to/project")

    def test_empty_payload(self):
        """Should return empty string for empty payload."""
        self.assertEqual(extract_cwd({}), "")

    def test_priority_direct_over_nested(self):
        """Direct cwd should take priority over nested."""
        payload = {"cwd": "/direct", "tool_input": {"cwd": "/nested"}}
        self.assertEqual(extract_cwd(payload), "/direct")


class TestExtractCommand(unittest.TestCase):
    """Test command extraction from various payload formats."""

    def test_tool_input_command(self):
        """Should extract from tool_input.command (Claude/Gemini)."""
        payload = {"tool_input": {"command": "npm test"}}
        self.assertEqual(extract_command(payload), "npm test")

    def test_args_command(self):
        """Should extract from args.command (Cursor)."""
        payload = {"args": {"command": "git status"}}
        self.assertEqual(extract_command(payload), "git status")

    def test_empty_payload(self):
        """Should return empty string for empty payload."""
        self.assertEqual(extract_command({}), "")

    def test_priority_tool_input_over_args(self):
        """tool_input.command should take priority."""
        payload = {
            "tool_input": {"command": "from_tool_input"},
            "args": {"command": "from_args"},
        }
        self.assertEqual(extract_command(payload), "from_tool_input")


class TestShouldDropEvent(unittest.TestCase):
    """Test event filtering logic."""

    def test_drop_opencode_events(self):
        """OpenCode events should be dropped (handled by plugin)."""
        should_drop, reason = should_drop_event("opencode", {})
        self.assertTrue(should_drop)
        self.assertIn("dedicated plugin", reason)

    def test_drop_cursor_reading_claude_dir(self):
        """Cursor reading .claude/ directory should be dropped."""
        payload = {"cwd": "/Users/user/.claude/settings"}
        should_drop, reason = should_drop_event("cursor", payload)
        self.assertTrue(should_drop)
        self.assertIn(".claude", reason)

    def test_drop_cursor_command_accessing_claude(self):
        """Cursor command accessing .claude should be dropped."""
        payload = {"tool_input": {"command": "cat ~/.claude/settings.json"}}
        should_drop, reason = should_drop_event("cursor", payload)
        self.assertTrue(should_drop)
        self.assertIn(".claude", reason)

    def test_allow_cursor_normal_events(self):
        """Normal Cursor events should be allowed."""
        payload = {"cwd": "/Users/user/project", "tool_input": {"command": "npm test"}}
        should_drop, reason = should_drop_event("cursor", payload)
        self.assertFalse(should_drop)
        self.assertEqual(reason, "")

    def test_allow_claude_events(self):
        """Claude events should be allowed."""
        should_drop, _ = should_drop_event("claude", {})
        self.assertFalse(should_drop)

    def test_allow_gemini_events(self):
        """Gemini events should be allowed."""
        should_drop, _ = should_drop_event("gemini", {})
        self.assertFalse(should_drop)


class TestNormalizeEvent(unittest.TestCase):
    """Test event normalization."""

    def test_claude_payload(self):
        """Should normalize Claude payload."""
        payload = {
            "tool_name": "Bash",
            "tool_input": {"command": "npm test"},
            "cwd": "/path/to/project",
            "session_id": "abc123",
            "timestamp": "2025-01-15T10:30:00Z",
        }

        event = normalize_event("claude", payload, "PreToolUse")

        self.assertEqual(event["event_type"], "PreToolUse")
        self.assertEqual(event["source"], "claude")
        self.assertEqual(event["session_id"], "abc123")
        self.assertEqual(event["cwd"], "/path/to/project")
        self.assertEqual(event["tool_name"], "Bash")
        self.assertEqual(event["tool_input"], {"command": "npm test"})
        self.assertEqual(event["timestamp"], "2025-01-15T10:30:00Z")
        self.assertEqual(event["raw_payload"], payload)

    def test_gemini_payload(self):
        """Should normalize Gemini payload (different field names)."""
        payload = {
            "tool": "run_shell_command",
            "args": {"command": "git status"},
            "working_directory": "/path/to/project",
        }

        event = normalize_event("gemini", payload, "PreToolUse")

        self.assertEqual(event["source"], "gemini")
        self.assertEqual(event["tool_name"], "run_shell_command")
        self.assertEqual(event["tool_input"], {"command": "git status"})
        self.assertEqual(event["cwd"], "/path/to/project")

    def test_missing_fields(self):
        """Should handle missing fields gracefully."""
        payload = {"tool_name": "Bash"}

        event = normalize_event("claude", payload)

        self.assertEqual(event["tool_name"], "Bash")
        self.assertEqual(event["session_id"], "")
        self.assertEqual(event["cwd"], "")
        self.assertEqual(event["timestamp"], "")


class TestResponses(unittest.TestCase):
    """Test response generation."""

    def test_allow_response(self):
        """Should generate valid allow response."""
        response = allow_response()
        self.assertEqual(response["hookSpecificOutput"]["permissionDecision"], "allow")
        self.assertTrue(response["continue"])

    def test_deny_response(self):
        """Should generate valid deny response with reason."""
        response = deny_response("Too dangerous")
        self.assertEqual(response["hookSpecificOutput"]["permissionDecision"], "deny")
        self.assertEqual(
            response["hookSpecificOutput"]["permissionDecisionReason"],
            "Too dangerous",
        )
        self.assertFalse(response["continue"])

    def test_responses_include_hook_event_name(self):
        """hookSpecificOutput must carry hookEventName (Claude Code requires it)."""
        # Defaults to PreToolUse.
        self.assertEqual(
            allow_response()["hookSpecificOutput"]["hookEventName"], "PreToolUse"
        )
        self.assertEqual(
            deny_response("x")["hookSpecificOutput"]["hookEventName"], "PreToolUse"
        )

    def test_event_type_threads_into_hook_event_name(self):
        """An explicit event type must propagate to hookEventName."""
        self.assertEqual(
            allow_response("PostToolUse")["hookSpecificOutput"]["hookEventName"],
            "PostToolUse",
        )
        self.assertEqual(
            deny_response("x", "PostToolUse")["hookSpecificOutput"]["hookEventName"],
            "PostToolUse",
        )


class TestResponseFormat(unittest.TestCase):
    """Test that responses are valid JSON."""

    def test_allow_response_is_valid_json(self):
        """Allow response should be valid JSON."""
        response = allow_response()
        # Should not raise
        json.dumps(response)

    def test_deny_response_is_valid_json(self):
        """Deny response should be valid JSON."""
        response = deny_response("reason")
        # Should not raise
        json.dumps(response)


class TestMainStdinFailOpen(unittest.TestCase):
    """main() must fail open (exit 0, valid allow JSON) for ANY non-object stdin.

    Regression: a JSON array payload passed the (dict, list) validation but then
    crashed in normalize_event via payload.get() -> AttributeError, exit 1,
    violating the fail-open contract.
    """

    SCRIPT = os.path.join(
        os.path.dirname(__file__), "..", "scripts", "runtime", "unified_hook.py"
    )

    def _run(self, stdin_text):
        return subprocess.run(
            [sys.executable, self.SCRIPT, "--source", "claude", "--no-detect"],
            input=stdin_text,
            capture_output=True,
            text=True,
        )

    def _assert_fail_open(self, stdin_text, label):
        proc = self._run(stdin_text)
        self.assertEqual(
            proc.returncode,
            0,
            f"{label}: expected exit 0, got {proc.returncode}\n{proc.stderr}",
        )
        self.assertNotIn("Traceback", proc.stderr, f"{label}: crashed:\n{proc.stderr}")
        parsed = json.loads(proc.stdout)
        self.assertEqual(
            parsed["hookSpecificOutput"]["permissionDecision"], "allow", label
        )

    def test_array_payload_fails_open(self):
        """A JSON array on stdin must coerce to a fail-open allow, not crash."""
        self._assert_fail_open("[1, 2, 3]", "array")

    def test_primitive_payload_fails_open(self):
        """A JSON number/string on stdin must fail open (already worked)."""
        self._assert_fail_open("42", "number")
        self._assert_fail_open('"hello"', "string")

    def test_object_payload_allows(self):
        """A normal object payload still produces an allow response."""
        self._assert_fail_open(
            '{"tool_name": "Bash", "tool_input": {"command": "ls"}}', "object"
        )


if __name__ == "__main__":
    unittest.main()

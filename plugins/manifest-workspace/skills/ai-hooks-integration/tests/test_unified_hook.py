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

    def test_cursor_payload_is_not_rerouted_through_claude_storage(self):
        """A Cursor-native hook keeps its declared source and payload."""
        payload = {"cwd": "/Users/user/.claude/settings"}
        should_drop, reason = should_drop_event("cursor", payload)
        self.assertFalse(should_drop)
        self.assertEqual(reason, "")

    def test_cursor_command_is_not_used_for_source_inference(self):
        """Command text never changes the selected native harness."""
        payload = {"tool_input": {"command": "cat ~/.claude/settings.json"}}
        should_drop, reason = should_drop_event("cursor", payload)
        self.assertFalse(should_drop)
        self.assertEqual(reason, "")

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

    def test_gemini_responses_use_decision_contract(self):
        """Gemini BeforeTool hooks consume decision/reason, not Claude output."""
        self.assertEqual(allow_response("BeforeTool", "gemini"), {"decision": "allow"})
        self.assertEqual(
            deny_response("blocked", "BeforeTool", "gemini"),
            {"decision": "deny", "reason": "blocked"},
        )

    def test_cursor_responses_use_permission_contract(self):
        """Cursor shell hooks consume permission and optional messages."""
        self.assertEqual(
            allow_response("beforeShellExecution", "cursor"),
            {"permission": "allow"},
        )
        self.assertEqual(
            deny_response("blocked", "beforeShellExecution", "cursor"),
            {
                "permission": "deny",
                "user_message": "blocked",
                "agent_message": "blocked",
            },
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


class TestNoBytecodeInSkillDirs(unittest.TestCase):
    """Hook execution must not write __pycache__ into a skill directory.

    Regression: handlers and the runtime live under the apm-managed skills tree.
    Any sibling module they import leaves a .pyc there — a file apm did not
    place — after which apm refuses to remove or replace that skill. Deleting
    the directory does not stick; only never writing it does.

    Asserted behaviourally (run it, look for the directory) rather than by
    grepping for "-B", so the test still fails if the flag is dropped anywhere
    along the spawn path.
    """

    def test_run_handler_leaves_no_pycache(self):
        """A handler importing a sibling must not litter its own directory."""
        import tempfile
        from pathlib import Path

        from runtime.unified_hook import run_handler

        with tempfile.TemporaryDirectory() as tmp:
            skill_dir = Path(tmp)
            (skill_dir / "sibling_module.py").write_text("VALUE = 1\n")
            handler = skill_dir / "handler.py"
            handler.write_text(
                "import json, sys\n"
                "import sibling_module\n"  # the import that creates the .pyc
                "sys.stdin.read()\n"
                'print(json.dumps({"decision": "allow"}))\n'
            )

            run_handler(str(handler), {"event_type": "PreToolUse"})

            leftovers = list(skill_dir.rglob("__pycache__"))
            self.assertEqual(
                leftovers,
                [],
                f"handler spawn wrote bytecode into the skill dir: {leftovers}",
            )

    def test_installer_emits_no_bytecode_flag(self):
        """install_all.py must build a hook command that suppresses bytecode."""
        installer = os.path.join(
            os.path.dirname(__file__), "..", "scripts", "install_all.py"
        )
        with open(installer, encoding="utf-8") as fh:
            source = fh.read()
        self.assertIn(
            "-B {UNIFIED_HOOK}",
            source,
            "the installed hook command must pass -B; without it every hook "
            "fire can re-lock the skill against apm",
        )


if __name__ == "__main__":
    unittest.main()

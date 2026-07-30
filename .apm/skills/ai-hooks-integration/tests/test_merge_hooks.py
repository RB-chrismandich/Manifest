#!/usr/bin/env python3
"""Tests for hook merging logic."""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

# Add scripts directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

from merge_hooks import TOOL_CONFIG, has_hook, load_json, save_json


class TestToolConfig(unittest.TestCase):
    """Test tool configuration."""

    def test_all_tools_configured(self):
        """All supported tools should be configured."""
        expected = {"claude", "gemini", "cursor", "opencode"}
        self.assertEqual(set(TOOL_CONFIG.keys()), expected)

    def test_claude_config(self):
        """Claude config should have correct structure."""
        cfg = TOOL_CONFIG["claude"]
        self.assertEqual(cfg["hook_key"], "PreToolUse")
        self.assertEqual(cfg["default_matcher"], "Bash")
        self.assertTrue(cfg["nested"])

    def test_gemini_config(self):
        """Gemini config should have correct structure."""
        cfg = TOOL_CONFIG["gemini"]
        self.assertEqual(cfg["hook_key"], "BeforeTool")
        self.assertEqual(cfg["default_matcher"], "run_shell_command")
        self.assertTrue(cfg["nested"])

    def test_cursor_config(self):
        """Cursor config should have flat structure."""
        cfg = TOOL_CONFIG["cursor"]
        self.assertEqual(cfg["hook_key"], "beforeShellExecution")
        self.assertIsNone(cfg["default_matcher"])
        self.assertFalse(cfg["nested"])


class TestLoadJson(unittest.TestCase):
    """Test JSON loading."""

    def test_load_existing_file(self):
        """Should load existing JSON file."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump({"key": "value"}, f)
            f.flush()

            data = load_json(Path(f.name))
            self.assertEqual(data, {"key": "value"})

            os.unlink(f.name)

    def test_load_nonexistent_file(self):
        """Should return empty dict for nonexistent file."""
        data = load_json(Path("/nonexistent/path/file.json"))
        self.assertEqual(data, {})


class TestSaveJson(unittest.TestCase):
    """Test JSON saving."""

    def test_save_creates_parents(self):
        """Should create parent directories."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "nested" / "dir" / "file.json"

            save_json(path, {"key": "value"}, dry_run=False)

            self.assertTrue(path.exists())
            with open(path) as f:
                data = json.load(f)
            self.assertEqual(data, {"key": "value"})

    def test_save_dry_run(self):
        """Dry run should not write file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "file.json"

            save_json(path, {"key": "value"}, dry_run=True)

            self.assertFalse(path.exists())

    def test_save_pretty_prints(self):
        """Should save with indentation."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "file.json"

            save_json(path, {"key": "value"}, dry_run=False)

            content = path.read_text()
            # Should have newlines (pretty printed)
            self.assertIn("\n", content)


class TestHasHook(unittest.TestCase):
    """Test hook existence checking."""

    def test_empty_list(self):
        """Empty list should have no hooks."""
        self.assertFalse(has_hook([], nested=True, command="/path/to/hook"))
        self.assertFalse(has_hook([], nested=False, command="/path/to/hook"))

    def test_nested_hook_exists(self):
        """Should find nested hook."""
        hooks = [{"matcher": "Bash", "hooks": [{"command": "/path/to/hook --claude"}]}]
        self.assertTrue(has_hook(hooks, nested=True, command="/path/to/hook"))

    def test_nested_hook_not_exists(self):
        """Should not find missing nested hook."""
        hooks = [{"matcher": "Bash", "hooks": [{"command": "/other/hook"}]}]
        self.assertFalse(has_hook(hooks, nested=True, command="/path/to/hook"))

    def test_flat_hook_exists(self):
        """Should find flat hook."""
        hooks = [{"command": "/path/to/hook --cursor"}]
        self.assertTrue(has_hook(hooks, nested=False, command="/path/to/hook"))

    def test_flat_hook_not_exists(self):
        """Should not find missing flat hook."""
        hooks = [{"command": "/other/hook"}]
        self.assertFalse(has_hook(hooks, nested=False, command="/path/to/hook"))

    def test_partial_match(self):
        """Should match partial command string."""
        hooks = [{"command": "/path/to/hook --flag --other"}]
        self.assertTrue(has_hook(hooks, nested=False, command="/path/to/hook"))

    def test_non_list_returns_false(self):
        """Non-list should return False."""
        self.assertFalse(has_hook(None, nested=True, command="cmd"))
        self.assertFalse(has_hook("string", nested=True, command="cmd"))
        self.assertFalse(has_hook({}, nested=True, command="cmd"))


class TestIdempotency(unittest.TestCase):
    """Test that hook merging is idempotent."""

    def test_repeated_merge_no_duplicates(self):
        """Running merge multiple times should not create duplicates."""
        # This is more of an integration test, but important for the spec
        hooks = []
        command = "/path/to/hook"

        # Simulate first merge
        if not has_hook(hooks, nested=False, command=command):
            hooks.append({"command": command})

        # Simulate second merge (should not add)
        if not has_hook(hooks, nested=False, command=command):
            hooks.append({"command": command})

        self.assertEqual(len(hooks), 1)


class TestUnreadableConfigIsNeverOverwritten(unittest.TestCase):
    """A present-but-unparseable config must survive, not be replaced.

    Regression: load_json returned {} for an unparseable file (and, for valid
    JSON that was not an object, returned {} with no warning at all). Callers
    read -> mutate -> write the WHOLE file, so an "empty" read meant the file was
    rewritten containing only the hook block. Measured before the fix: a
    settings.json holding model/statusLine/env/permissions plus a user hook went
    309 bytes -> 256 bytes, exit 0. Uninstall shared the same path.
    """

    SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"

    REALISTIC = """{
  "model": "opus",
  "statusLine": {"type": "command", "command": "~/bin/statusline"},
  "env": {"FOO": "bar"},
  "permissions": {"allow": ["Bash(ls:*)"]},
  "hooks": {"PreToolUse": [{"matcher": "Bash", "hooks": [
      {"type": "command", "command": "~/mine.py"}]}]},
}"""  # note the trailing comma — a realistic hand-edit typo

    def _run(self, script, path):
        return subprocess.run(
            [
                sys.executable,
                str(self.SCRIPTS / script),
                "--tool",
                "claude",
                "--path",
                str(path),
                "--command",
                "/tmp/new-hook.py",
            ],
            capture_output=True,
            text=True,
            cwd=str(self.SCRIPTS),
        )

    def _assert_preserved(self, script, content):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "settings.json"
            path.write_text(content)
            before = path.read_bytes()

            proc = self._run(script, path)

            self.assertNotEqual(proc.returncode, 0, f"{script} must refuse, not exit 0")
            self.assertEqual(
                path.read_bytes(), before, f"{script} rewrote an unreadable file"
            )
            self.assertIn("efusing to overwrite", proc.stderr + proc.stdout)

    def test_merge_refuses_malformed_json(self):
        self._assert_preserved("merge_hooks.py", self.REALISTIC)

    def test_remove_refuses_malformed_json(self):
        self._assert_preserved("remove_hooks.py", self.REALISTIC)

    def test_merge_refuses_valid_json_that_is_not_an_object(self):
        # Previously the quietest data-loss path: no warning whatsoever.
        self._assert_preserved("merge_hooks.py", '["a", "b"]')

    def test_absent_file_is_still_created(self):
        """The refusal must not break the legitimate create-from-nothing path."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "settings.json"
            proc = self._run("merge_hooks.py", path)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertIn("PreToolUse", json.loads(path.read_text())["hooks"])

    def test_empty_file_is_treated_as_absent(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "settings.json"
            path.write_text("   \n")
            proc = self._run("merge_hooks.py", path)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertIn("PreToolUse", json.loads(path.read_text())["hooks"])

    def test_unrelated_settings_survive_a_successful_merge(self):
        """The whole point: adding a hook must not drop anything else."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "settings.json"
            path.write_text(
                json.dumps({"model": "opus", "env": {"A": "1"}, "permissions": {}})
            )
            proc = self._run("merge_hooks.py", path)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            data = json.loads(path.read_text())
            self.assertEqual(data["model"], "opus")
            self.assertEqual(data["env"], {"A": "1"})
            self.assertIn("hooks", data)


class TestSaveJsonDurability(unittest.TestCase):
    def test_backup_is_written_before_overwrite(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "settings.json"
            path.write_text(json.dumps({"original": True}))
            save_json(path, {"replaced": True}, dry_run=False)
            backup = path.with_suffix(path.suffix + ".bak")
            self.assertTrue(backup.exists(), "no .bak written")
            self.assertEqual(json.loads(backup.read_text()), {"original": True})
            self.assertEqual(json.loads(path.read_text()), {"replaced": True})

    def test_no_temp_files_left_behind(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "settings.json"
            save_json(path, {"a": 1}, dry_run=False)
            leftovers = [p.name for p in Path(tmpdir).iterdir() if p.suffix == ".tmp"]
            self.assertEqual(leftovers, [])

    def test_symlinked_config_is_updated_at_its_target(self):
        """A symlinked dotfile must stay a symlink, not become a regular file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            real = Path(tmpdir) / "real.json"
            real.write_text(json.dumps({"original": True}))
            link = Path(tmpdir) / "settings.json"
            link.symlink_to(real)

            save_json(link, {"replaced": True}, dry_run=False)

            self.assertTrue(link.is_symlink(), "symlink was replaced by a file")
            self.assertEqual(json.loads(real.read_text()), {"replaced": True})


if __name__ == "__main__":
    unittest.main()

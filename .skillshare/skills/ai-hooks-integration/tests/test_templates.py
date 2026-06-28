#!/usr/bin/env python3
"""Tests for generated JavaScript templates."""

import os
import re
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

try:
    from install_opencode_plugin import TEMPLATE_ADVANCED, TEMPLATE_BASIC, TEMPLATE_WEBSOCKET
except ImportError:
    TEMPLATE_BASIC = ""
    TEMPLATE_WEBSOCKET = ""
    TEMPLATE_ADVANCED = ""

try:
    from merge_hooks import OPENCODE_PLUGIN_TEMPLATE
except ImportError:
    OPENCODE_PLUGIN_TEMPLATE = ""

class TestTemplates(unittest.TestCase):
    def test_no_empty_catch_bindings(self):
        """Ensure all catch blocks explicitly capture exceptions (e.g. catch (e))."""
        templates = [
            ("TEMPLATE_BASIC", TEMPLATE_BASIC),
            ("TEMPLATE_WEBSOCKET", TEMPLATE_WEBSOCKET),
            ("TEMPLATE_ADVANCED", TEMPLATE_ADVANCED),
            ("OPENCODE_PLUGIN_TEMPLATE", OPENCODE_PLUGIN_TEMPLATE),
        ]

        bindingless_pattern = re.compile(r'catch\s*\{')
        empty_pattern = re.compile(r'catch\s*\([^)]+\)\s*\{\s*\}')
        empty_pattern_escaped = re.compile(r'catch\s*\([^)]+\)\s*\{\{\s*\}\}')

        for name, content in templates:
            if not content:
                continue

            matches = bindingless_pattern.findall(content)
            self.assertEqual(len(matches), 0, f"Template {name} contains bindingless catch blocks.")

            matches_empty = empty_pattern.findall(content)
            matches_escaped = empty_pattern_escaped.findall(content)
            self.assertEqual(len(matches_empty) + len(matches_escaped), 0, f"Template {name} contains empty catch blocks.")

if __name__ == "__main__":
    unittest.main()

"""Input validation and record-size boundaries for the audit logger."""

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(__file__))

from _audit_logger_test_support import AuditLoggerTestCase


class AuditLoggerTests(AuditLoggerTestCase):
    """Pin accepted input and record size limits."""

    def test_input_and_record_size_boundaries(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td).resolve()
            input_path = root / "input-boundary"
            exact_input = b'{"x":1}' + b" " * (65536 - len(b'{"x":1}'))
            result = self.invoke(input_path, exact_input)
            self.assertEqual(result.returncode, 0, result.stderr)
            original = input_path.read_bytes()
            result = self.invoke(input_path, exact_input + b" ")
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(input_path.read_bytes(), original)

            base_record = json.dumps(
                {"timestamp": 1700000000.0, "event": {"x": ""}},
                ensure_ascii=True,
                separators=(",", ":"),
            ).encode("ascii")
            value_size = 16383 - len(base_record)
            boundary_event = json.dumps({"x": "a" * value_size}).encode()
            accepted_path = root / "record-at-boundary"
            result = self.invoke_with_frozen_clock(accepted_path, boundary_event)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(len(accepted_path.read_bytes()), 16384)
            too_large = root / "record-too-large"
            oversized_event = json.dumps({"x": "a" * (value_size + 1)}).encode()
            result = self.invoke_with_frozen_clock(too_large, oversized_event)
            self.assertNotEqual(result.returncode, 0)
            self.assertFalse(too_large.exists())


if __name__ == "__main__":
    unittest.main()

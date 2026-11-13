#!/usr/bin/env python3
"""Credential redaction coverage for audit records."""

import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(__file__))

from _audit_logger_test_support import AuditLoggerTestCase


class AuditLoggerRedactionTests(AuditLoggerTestCase):
    def test_redacts_full_argv_assignment_and_indented_continuation(self):
        with tempfile.TemporaryDirectory() as td:
            log = Path(td).resolve() / "audit.jsonl"
            payload = {
                "deep": [
                    "Bearer abc123",
                    "--password secret",
                    "--token=xyz",
                    "API_TOKEN=hidden",
                    "https://user:pass@example.test/",
                    'client --password "prefix\\"secret-value"',
                    'API_TOKEN="prefix\\"token-value"',
                    r"client --password prefix\ secret-space",
                    r"API_TOKEN=prefix\ token-space",
                    r"client --password ''concat-secret",
                    r"API_TOKEN=''concat-token",
                    "client --password \\\ncontinued-secret",
                    "API_TOKEN=\\\ncontinued-token",
                    "line\nbreak",
                ],
                "args": [
                    "--password",
                    "split-password",
                    "--token",
                    "split-token",
                    "--token=first second-secret",
                    "--password=first second-password",
                    "API_TOKEN=first second-secret",
                ],
            }
            result = self.invoke(log, json.dumps(payload).encode())
            self.assertEqual(result.stdout, b"")
            self.assertEqual(result.returncode, 0, result.stderr)
            lines = log.read_bytes().splitlines()
            self.assertEqual(len(lines), 1)
            self.assertLessEqual(len(lines[0]), 16384)
            self.assertNotIn(b"abc123", lines[0])
            self.assertNotIn(b"secret", lines[0])
            self.assertNotIn(b"hidden", lines[0])
            self.assertNotIn(b"user:pass", lines[0])
            self.assertNotIn(b"split-password", lines[0])
            self.assertNotIn(b"split-token", lines[0])
            self.assertNotIn(b"xyz", lines[0])
            self.assertNotIn(b"secret-value", lines[0])
            self.assertNotIn(b"token-value", lines[0])
            self.assertNotIn(b"secret-space", lines[0])
            self.assertNotIn(b"concat-secret", lines[0])
            self.assertNotIn(b"concat-token", lines[0])
            self.assertNotIn(b"token-space", lines[0])
            self.assertNotIn(b"continued-secret", lines[0])
            self.assertNotIn(b"continued-token", lines[0])
            self.assertNotIn(b"second-secret", lines[0])
            self.assertNotIn(b"second-password", lines[0])
            json.loads(lines[0])
            event = json.loads(lines[0])["event"]
            self.assertEqual(len(event["deep"]), 14)
            self.assertEqual(len(event["args"]), 7)

    def test_url_userinfo_redacts_through_last_at_delimiter(self):
        with tempfile.TemporaryDirectory() as td:
            log = Path(td).resolve() / "audit.jsonl"
            payload = {
                "nested": {
                    "command": "curl https://alice:first@second@example.test/path"
                }
            }
            result = self.invoke(log, json.dumps(payload).encode())
            self.assertEqual(result.returncode, 0, result.stderr)
            record = log.read_bytes()
            self.assertNotIn(b"alice", record)
            self.assertNotIn(b"first", record)
            self.assertNotIn(b"second", record)
            self.assertIn(b"example.test", record)
            self.assertEqual(
                json.loads(record)["event"]["nested"]["command"],
                "curl https://[REDACTED]@example.test/path",
            )

            self.assertEqual(log.stat().st_mode & 0o777, 0o600)

    def test_redacts_quoted_flag_and_backslash_newline_option(self):
        with tempfile.TemporaryDirectory() as td:
            log = Path(td).resolve() / "audit.jsonl"
            payload = {
                "nested": {
                    "command": 'client "--token" quoted-secret',
                    "continued": "client --token\\\n continued-secret",
                }
            }
            result = self.invoke(log, json.dumps(payload).encode())
            self.assertEqual(result.returncode, 0, result.stderr)
            record = log.read_bytes()
            self.assertNotIn(b"quoted-secret", record)
            self.assertNotIn(b"continued-secret", record)
            self.assertEqual(
                json.loads(record)["event"]["nested"]["continued"],
                "client --token [REDACTED]",
            )

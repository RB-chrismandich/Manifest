#!/usr/bin/env python3
"""Filesystem validation and failure behavior for audit records."""

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(__file__))

from _audit_logger_test_support import LOGGER, AuditLoggerTestCase


class AuditLoggerFilesystemTests(AuditLoggerTestCase):
    def test_missing_fcntl_fails_closed_with_generic_diagnostic(self):
        with tempfile.TemporaryDirectory() as td:
            log = Path(td).resolve() / "audit.jsonl"
            code = (
                "import runpy,sys; sys.modules['fcntl']=None; "
                f"sys.argv={[str(LOGGER), '--path', str(log)]!r}; "
                f"runpy.run_path({str(LOGGER)!r}, run_name='__main__')"
            )
            proc = subprocess.run(
                [sys.executable, "-c", code],
                input=b'{"secret":"do-not-disclose"}',
                capture_output=True,
            )
            self.assertNotEqual(proc.returncode, 0)
            self.assertEqual(proc.stderr.strip(), b"audit logger failed")
            self.assertNotIn(b"do-not-disclose", proc.stdout + proc.stderr)
            self.assertFalse(log.exists())

    def test_missing_directory_open_flags_fail_closed(self):
        for flag in ("O_DIRECTORY", "O_NOFOLLOW"):
            with self.subTest(flag=flag), tempfile.TemporaryDirectory() as td:
                log = Path(td).resolve() / "audit.jsonl"
                code = (
                    "import os,runpy,sys; "
                    f"delattr(os, {flag!r}); "
                    f"sys.argv={[str(LOGGER), '--path', str(log)]!r}; "
                    f"runpy.run_path({str(LOGGER)!r}, run_name='__main__')"
                )
                proc = subprocess.run(
                    [sys.executable, "-c", code],
                    input=b'{"secret":"do-not-disclose"}',
                    capture_output=True,
                )
                self.assertNotEqual(proc.returncode, 0)
                self.assertEqual(proc.stderr.strip(), b"audit logger failed")
                self.assertNotIn(b"do-not-disclose", proc.stdout + proc.stderr)
                self.assertFalse(log.exists())

    def test_rejects_malformed_oversized_and_unsafe_destinations(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td).resolve()
            log = root / "audit.jsonl"
            for data in (
                b"not json",
                b"\xff",
                b"[]",
                b" " * 65537,
                json.dumps({"x": "z" * 17000}).encode(),
            ):
                result = self.invoke(log, data)
                self.assertNotEqual(result.returncode, 0)
                self.assertNotIn(b"secret", result.stderr)
            target = root / "target"
            target.write_text("unchanged")
            link = root / "link"
            link.symlink_to(target)
            result = self.invoke(link, b"{}")
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(target.read_text(), "unchanged")
            fifo = root / "pipe"
            os.mkfifo(fifo)
            result = subprocess.run(
                [sys.executable, str(LOGGER), "--path", str(fifo)],
                input=b"{}",
                capture_output=True,
                timeout=2,
            )
            self.assertNotEqual(result.returncode, 0)
            result = self.invoke(log, b'{"x":1e999}')
            self.assertNotEqual(result.returncode, 0)
            self.assertFalse(log.exists())
            unsafe_parent = root / "unsafe-parent"
            unsafe_parent.mkdir()
            unsafe_parent.chmod(0o770)
            rejected_path = unsafe_parent / "events.jsonl"
            result = self.invoke(rejected_path, b"{}")
            self.assertNotEqual(result.returncode, 0)
            self.assertFalse(rejected_path.exists())
            unsafe_parent.chmod(0o700)

    def test_rejects_hardlink_and_permissive_leaf_without_modification(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td).resolve()
            original = root / "original"
            original.write_bytes(b"existing\n")
            original.chmod(0o600)
            hardlink = root / "hardlink"
            os.link(original, hardlink)
            result = self.invoke(original, b"{}")
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(original.read_bytes(), b"existing\n")
            self.assertEqual(hardlink.read_bytes(), b"existing\n")

            permissive = root / "permissive"
            permissive.write_bytes(b"existing\n")
            permissive.chmod(0o644)
            result = self.invoke(permissive, b"{}")
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(permissive.read_bytes(), b"existing\n")

            target_dir = root / "real-parent"
            target_dir.mkdir()
            symlink_parent = root / "linked-parent"
            symlink_parent.symlink_to(target_dir, target_is_directory=True)
            linked_file = symlink_parent / "events.jsonl"
            result = self.invoke(linked_file, b"{}")
            self.assertNotEqual(result.returncode, 0)
            self.assertFalse((target_dir / "events.jsonl").exists())

    def test_rejects_wrong_owner_when_running_with_chown_capability(self):
        if os.geteuid() != 0:
            self.skipTest("wrong-owner fixture requires effective uid 0")
        with tempfile.TemporaryDirectory() as td:
            path = Path(td).resolve() / "wrong-owner"
            path.write_bytes(b"existing\n")
            path.chmod(0o600)
            os.chown(path, 65534, os.stat(path).st_gid)
            result = self.invoke(path, b"{}")
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(path.read_bytes(), b"existing\n")

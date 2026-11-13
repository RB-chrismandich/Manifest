#!/usr/bin/env python3
"""Append rollback, locking, and concurrency coverage for audit records."""

import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(__file__))

from _audit_logger_test_support import LOGGER, AuditLoggerTestCase


class AuditLoggerAppendTests(AuditLoggerTestCase):
    def test_short_append_rolls_back_partial_record(self):
        spec = importlib.util.spec_from_file_location("audit_logger", LOGGER)
        logger = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(logger)
        with tempfile.TemporaryDirectory() as td:
            log = Path(td).resolve() / "audit.jsonl"
            log.write_bytes(b"prior\n")
            log.chmod(0o600)
            real_write = os.write

            def partial_write(fd, data):
                real_write(fd, data[: max(1, len(data) // 2)])
                return max(1, len(data) // 2)

            with patch.object(
                logger.os, "write", side_effect=partial_write
            ) as write_mock:
                with self.assertRaises(OSError):
                    logger.append(str(log), b'{"event":"new"}')
                write_mock.assert_called_once()
            self.assertEqual(log.read_bytes(), b"prior\n")

    def test_writers_contend_while_another_writer_holds_lock(self):
        spec = importlib.util.spec_from_file_location("audit_logger", LOGGER)
        logger = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(logger)
        with tempfile.TemporaryDirectory() as td:
            log = Path(td).resolve() / "audit.jsonl"
            first_has_lock = threading.Event()
            second_is_blocked = threading.Event()
            release_first = threading.Event()
            first_claimed = False
            real_flock = logger.fcntl.flock

            def coordinated_flock(fd, operation):
                nonlocal first_claimed
                if operation == logger.fcntl.LOCK_UN:
                    return real_flock(fd, operation)
                if operation != logger.fcntl.LOCK_EX:
                    raise AssertionError(
                        f"append requested unexpected lock mode: {operation}"
                    )
                is_first = not first_claimed
                first_claimed = True
                if is_first:
                    real_flock(fd, operation)
                    first_has_lock.set()
                    if not release_first.wait(timeout=5):
                        raise TimeoutError("test did not release first writer")
                    return
                try:
                    real_flock(fd, operation | logger.fcntl.LOCK_NB)
                except BlockingIOError:
                    second_is_blocked.set()
                else:
                    raise AssertionError(
                        "second writer acquired lock while first held it"
                    )
                real_flock(fd, operation)

            with (
                patch.object(logger.fcntl, "flock", side_effect=coordinated_flock),
                ThreadPoolExecutor(max_workers=2) as pool,
            ):
                first = pool.submit(logger.append, str(log), b'{"writer":"first"}')
                self.assertTrue(first_has_lock.wait(timeout=5))
                second = pool.submit(logger.append, str(log), b'{"writer":"second"}')
                self.assertTrue(second_is_blocked.wait(timeout=5))
                release_first.set()
                first.result(timeout=5)
                second.result(timeout=5)
            records = [json.loads(line) for line in log.read_bytes().splitlines()]
            self.assertEqual(
                {record["writer"] for record in records}, {"first", "second"}
            )

    def test_concurrent_appends_remain_valid_jsonl(self):
        with tempfile.TemporaryDirectory() as td:
            log = Path(td).resolve() / "audit.jsonl"
            payload = json.dumps({"v": "x" * 1000}).encode()
            procs = [
                subprocess.Popen(
                    [sys.executable, str(LOGGER), "--path", str(log)],
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                )
                for _ in range(8)
            ]
            for proc in procs:
                proc.stdin.write(payload)
                proc.stdin.close()
            for proc in procs:
                returncode = proc.wait(timeout=10)
                stderr = proc.stderr.read().decode("utf-8", errors="replace")
                self.assertEqual(returncode, 0, stderr)
                proc.stdout.close()
                proc.stderr.close()
            lines = log.read_bytes().splitlines()
            self.assertEqual(len(lines), 8)
            for line in lines:
                json.loads(line)

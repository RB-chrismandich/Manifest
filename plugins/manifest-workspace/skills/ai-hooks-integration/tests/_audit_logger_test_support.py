#!/usr/bin/env python3
"""Shared subprocess fixtures for the audit logger test modules."""

import subprocess
import sys
import unittest
from pathlib import Path

LOGGER = Path(__file__).parents[1] / "scripts/runtime/audit_logger.py"


class AuditLoggerTestCase(unittest.TestCase):
    """Provide stable audit-logger subprocess invocation helpers."""

    def invoke(self, path: Path, data: bytes) -> subprocess.CompletedProcess[bytes]:
        """Invoke the logger with bounded input and capture its result."""
        return subprocess.run(
            [sys.executable, str(LOGGER), "--path", str(path)],
            input=data,
            capture_output=True,
        )

    def invoke_with_frozen_clock(
        self, path: Path, data: bytes
    ) -> subprocess.CompletedProcess[bytes]:
        """Invoke the logger with a deterministic timestamp."""
        runner = (
            "import runpy,sys,time; "
            "logger=sys.argv.pop(1); "
            "time.time=lambda:1700000000.0; "
            "runpy.run_path(logger,run_name='__main__')"
        )
        return subprocess.run(
            [sys.executable, "-c", runner, str(LOGGER), "--path", str(path)],
            input=data,
            capture_output=True,
        )

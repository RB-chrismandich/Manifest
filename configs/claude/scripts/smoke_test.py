#!/usr/bin/env python3
"""Thin executable entry point for the smoke-test orchestrator.

Dispatches to ``smoke_orchestrator.cli``. Running this file directly puts its own
directory (``configs/claude/scripts``, or the deployed ``~/.claude/scripts``) on
``sys.path`` so the sibling ``smoke_orchestrator`` package imports cleanly.

``--help`` and argument parsing succeed before any runtime dependency (PyYAML /
Playwright) is touched — those are imported lazily inside each subcommand handler
(repo convention: cli-help-before-dependency-checks).
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from smoke_orchestrator.cli import main

if __name__ == "__main__":
    raise SystemExit(main())

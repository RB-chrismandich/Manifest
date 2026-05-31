#!/usr/bin/env python3
"""Parallel Agent Orchestrator — entry point shim.

All logic lives in the agents/ package. This file exists solely for backward
compatibility so existing callers (CI scripts, shell wrappers, ~/.claude/scripts/)
continue to work unchanged.

Usage:
    python parallel_agent.py "Your prompt here"
    python parallel_agent.py --json --validate "Your prompt"
    python parallel_agent.py --review /path/to/file
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from agents.cli import main  # noqa: E402

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nInterrupted by user", file=sys.stderr)
        sys.exit(130)

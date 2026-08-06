#!/usr/bin/env python3
"""Bundle-local entry point for parallel agent orchestration."""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parents[1]
os.environ.setdefault(
    "MANIFEST_PARALLEL_CONFIG", str(SKILL_ROOT / "config/parallel_agent.json")
)
os.environ.setdefault(
    "MANIFEST_VALIDATION_CRITERIA",
    str(SKILL_ROOT / "config/validation_criteria.json"),
)
os.environ.setdefault(
    "MANIFEST_SYNTHESIS_TEMPLATE", str(SKILL_ROOT / "prompts/synthesis.md")
)


def _print_bootstrap_free_help() -> None:
    print(
        """usage: parallel_agent.py [-h] [--json] [--validate]
                         [--review FILE | --analyze FILE | --improve FILE]
                         [--timeout SECONDS] [--output DIR] [prompt]

Run installed agent harness CLIs concurrently using only files in this skill.
The command never installs harnesses and writes run artifacts below XDG state.
"""
    )


def main() -> int:
    if any(arg in {"-h", "--help"} for arg in sys.argv[1:]):
        _print_bootstrap_free_help()
        return 0

    scripts = Path(__file__).resolve().parent
    sys.path.insert(0, str(scripts))
    from agents.cli import main as agents_main

    asyncio.run(agents_main())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

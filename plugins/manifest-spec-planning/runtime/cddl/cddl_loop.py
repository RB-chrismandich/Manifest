#!/usr/bin/env python3
"""CDDL scripted orchestrator retired — use /spec-implement-loop (sub-agents)."""

from __future__ import annotations

import sys

_RETIRED = (
    "cddl_loop.py: removed — CDDL orchestration is the /spec-implement-loop skill "
    "(native sub-agents). Role prompts are packaged beside this executable."
)


def main(argv: list[str] | None = None) -> int:
    args = list(argv if argv is not None else sys.argv[1:])
    if not args or args[0] in ("-h", "--help"):
        print(f"Usage: {_RETIRED}")
        return 0
    print(_RETIRED, file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())

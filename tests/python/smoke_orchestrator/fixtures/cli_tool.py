#!/usr/bin/env python3
"""Trivial CLI target for smoke-orchestrator executor tests (``cli`` step type).

Subcommands exercise the runner's contract without any external dependency:

* ``ok``            -> prints ``ok``,        exits 0   (happy path)
* ``fail [code]``   -> prints to stderr,     exits code (default 1)
* ``emit [id]``     -> prints ``invoice_id=<id>``       (regex capture source)
* ``echo <args...>``-> prints the args joined            (proves a chained value arrived)
* ``expect <w> <a>``-> exit 0 iff ``w == a``             (in-band chaining assertion)
* ``slow [secs]``   -> sleeps then prints ``done``       (timeout path)

Kept deliberately tiny and stdlib-only so it runs identically in CI and locally.
"""

from __future__ import annotations

import sys
import time


def main(argv: list[str]) -> int:
    if not argv:
        print("usage: cli_tool.py <ok|fail|emit|echo|slow> [args]", file=sys.stderr)
        return 2
    cmd, rest = argv[0], argv[1:]
    if cmd == "ok":
        print("ok")
        return 0
    if cmd == "fail":
        code = int(rest[0]) if rest else 1
        print("boom", file=sys.stderr)
        return code
    if cmd == "emit":
        print(f"invoice_id={rest[0] if rest else '42'}")
        return 0
    if cmd == "echo":
        print(" ".join(rest))
        return 0
    if cmd == "expect":
        # expect <wanted> <actual> -> exit 0 iff equal; proves a chained value arrived.
        wanted, actual = (rest + ["", ""])[:2]
        if wanted != actual:
            print(f"expected {wanted!r}, got {actual!r}", file=sys.stderr)
            return 1
        print("match")
        return 0
    if cmd == "slow":
        time.sleep(float(rest[0]) if rest else 5.0)
        print("done")
        return 0
    print(f"unknown subcommand: {cmd}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

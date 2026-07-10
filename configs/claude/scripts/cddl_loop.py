#!/usr/bin/env python3
"""cddl_loop.py — Critic-Driven Development Loop entry shim (feature 482).

Owns --help (fast path: no config/state/dependency lookup, repo convention
specs/003 R6) and the stable exit-code contract; delegates everything else to
the cddl package (contracts/cli-interface.md).
"""

import sys
from pathlib import Path

USAGE = """\
Usage: cddl_loop.py <start|answer|status> [options]

  start <target>                        Pre-flight + clarification gate + loop
  answer --run <id> --answers-file <f>  Resume a parked run with answers
  status [--run <id>]                   Show a run's state summary

Options (start): --spec/--plan <path>  --verify-cmd '<cmd>'  --max-rounds N
  --max-iterations N  --invoke-timeout S  --run-timeout S  --allow-dirty
  --state-root <dir>
Env: CDDL_CLI CDDL_MAX_ROUNDS CDDL_MAX_ITERATIONS CDDL_INVOKE_TIMEOUT
  CDDL_RUN_TIMEOUT CDDL_AUDIT_FILE MANIFEST_STATE_ROOT
Exit: 0 success | 2 usage | 3 questions-pending | 4 gate-failure
  5 ceiling-failure | 6 pre-flight failure | 7 aborted
"""


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] in ("-h", "--help"):
        print(USAGE, end="")
        return 0
    if not argv:
        print(USAGE, end="", file=sys.stderr)
        print("cddl-loop: a subcommand is required", file=sys.stderr)
        return 2
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from cddl.cli import main as cli_main

    return cli_main(argv)


if __name__ == "__main__":
    sys.exit(main())

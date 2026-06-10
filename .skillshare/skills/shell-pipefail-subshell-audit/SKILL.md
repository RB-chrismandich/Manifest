---
name: shell-pipefail-subshell-audit
description: Audit bash scripts using set -euo pipefail for silent-abort risks in $() command substitutions that parse empty or malformed input
---
# Shell Pipefail Subshell Audit

1. Read the whole script; confirm `set -e`, `set -u`, and/or `pipefail` are active (any subset changes the failure semantics).
2. List every `var="$(cmd)"` assignment whose `cmd` consumes external/upstream input — parses JSON, reads a file, or captures another script's stdout.
3. For each, run `cmd` by hand against three inputs: empty string, malformed/partial text, and a crashed-upstream traceback. Note the exit code — under `set -e` a non-zero subshell aborts the whole script.
4. Confirm a guard exists on the assignment line: `var="$(cmd)" || { err "..."; exit 1; }`. A bare assignment with no guard dies silently with no user-facing message.
5. For `echo "$x" | program` stages, check `pipefail`: a failing right-hand side aborts even though `echo` succeeded.
6. Harden parsers against missing keys — e.g. Python `json.load(...).get("dropped", [])` rather than `[...]["dropped"]` — so empty/partial JSON degrades instead of throwing.
7. Verify each guard's error text names the failing step (not a generic "error").
8. Confirm reachability of any warning/branch that must fire on the empty case (e.g. a "candidates rejected" warning placed before an early `exit 0` when the work list is empty).
9. Run `shellcheck` and the script's test suite; report each unguarded substitution whose realistic failure path silently aborts.

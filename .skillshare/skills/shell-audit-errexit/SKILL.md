---
name: shell-audit-errexit
description: Use when a bash script under `set -euo pipefail` aborts in production but passes tests — audit helpers and sourced libs for non-`$()` control-flow triggers (trailing `&&`, stdin-drain, SIGPIPE, `((i++))`). Complements shell-audit-pipefail.
---
# Audit Shell Helpers for Production-Only Aborts Tests Miss

Four control-flow hazards that pass small fixtures and abort in production. Same family as `shell-audit-pipefail`, but
the trigger is control flow, not `$()` parsing.

1. **Recognize the signature.** Script exits non-zero (1, or 141 for SIGPIPE) right after a benign step (a "Deployed
   files" listing, a cleanup), with no error output, skipping everything after it — or a loop processes only its first
   item. Tests pass because fixtures are small, the file exists, or there's no real subprocess. The failing statement is
   often three files deep in a sourced helper that "can't fail."
2. **Trailing-conditional return.** Scan every function and sourced script for a LAST statement of the form `[[ cond ]]
   && action` or `cmd && action`. When the guard is false the `&&` list returns non-zero, becomes the function's exit
   status, and under `set -e` in the caller aborts the whole script. This was a launchd-cleanup `[[ -f "$plist" ]] &&
   {...}` that killed every bootstrap run silently. Fix: end on explicit `return 0`/`true`, guard with `|| true`, or
   rewrite as `if ... then ... fi`.
3. **Subprocess draining a while-read loop's stdin.** Scan for `… | while IFS=… read …; do … <cmd> …; done` where
   `<cmd>` is a subprocess that reads stdin (ssh, an LLM/agent CLI, ffmpeg). It consumes the loop's piped stdin, so only
   the first iteration runs. Fix: redirect the inner command — `cmd </dev/null` — or read on a separate FD. Reproduce
   with a fake binary that does `cat >/dev/null` and assert every item is processed.
4. **SIGPIPE from head-truncated pipelines.** `producer | head -N | while …` — when `head` exits after N lines,
   `producer` dies of SIGPIPE (141). Harmless under bare `set -e`, fatal once `pipefail` is added. Buffer through a
   guarded command substitution, or, if pipefail isn't set, label it defensive — don't claim it's the active bug.
5. **`((i++))` / `let` returns 1 when the result is 0.** A post-increment counter — `((count++))` with `count=0` —
   evaluates to the OLD value `0`, so the arithmetic command returns exit 1 and `set -e` aborts mid-loop, silently,
   right after the thing you counted. It is **CI-only**: bash 3.2 (macOS default `/bin/bash`) does not trip errexit on
   `((...))`, bash ≥4 (Linux runners) does — green on your Mac, red in CI. Confirm with `bash -c 'set -e; v=0; ((v++));
   echo ok'` on `/bin/bash` vs a bash-5. Fix to an always-success form: `var=$((var + 1))` (shellcheck-clean), or `:
   $((var++))` / `((var++)) || true`. Sweep: `grep -rnE '\(\([a-zA-Z_]+(\+\+|--)\)\)' scripts/`.
6. **Audit the whole sourced chain.** A top-level `set -e` propagates into every sourced lib; check the last statement
   of each helper, not just the entrypoint.
7. **Prove each fix red-first.** Write the failing test reproducing the production condition (absent file, large input,
   stdin-draining subprocess), then fix, then green. State the real mechanism in the test comment — never encode a
   disproven first hypothesis (e.g. "SIGPIPE under set -e" when it's actually only fatal under pipefail).

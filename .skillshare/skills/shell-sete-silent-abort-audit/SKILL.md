---
name: shell-sete-silent-abort-audit
description: Use when a bash script under `set -e` (or `set -euo pipefail`) aborts, exits non-zero, or misbehaves in production but passes tests and small inputs — audit helper functions and sourced libs for three non-`$()` triggers. Complements shell-pipefail-subshell-audit (which covers `$()` parsing empty input).
---
# Audit Shell Helpers for Production-Only Aborts Tests Miss

Three control-flow hazards that pass small fixtures and abort in production. Same family as `shell-pipefail-subshell-audit`, but the trigger is control flow, not `$()` parsing.

1. **Recognize the signature.** Script exits non-zero (1, or 141 for SIGPIPE) right after a benign step (a "Deployed files" listing, a cleanup), with no error output, skipping everything after it — or a loop processes only its first item. Tests pass because fixtures are small, the file exists, or there's no real subprocess. The failing statement is often three files deep in a sourced helper that "can't fail."
2. **Trailing-conditional return.** Scan every function and sourced script for a LAST statement of the form `[[ cond ]] && action` or `cmd && action`. When the guard is false the `&&` list returns non-zero, becomes the function's exit status, and under `set -e` in the caller aborts the whole script. This was a launchd-cleanup `[[ -f "$plist" ]] && {...}` that killed every bootstrap run silently. Fix: end on explicit `return 0`/`true`, guard with `|| true`, or rewrite as `if ... then ... fi`.
3. **Subprocess draining a while-read loop's stdin.** Scan for `… | while IFS=… read …; do … <cmd> …; done` where `<cmd>` is a subprocess that reads stdin (ssh, an LLM/agent CLI, ffmpeg). It consumes the loop's piped stdin, so only the first iteration runs. Fix: redirect the inner command — `cmd </dev/null` — or read on a separate FD. Reproduce with a fake binary that does `cat >/dev/null` and assert every item is processed.
4. **SIGPIPE from head-truncated pipelines.** `producer | head -N | while …` — when `head` exits after N lines, `producer` dies of SIGPIPE (141). Harmless under bare `set -e`, fatal once `pipefail` is added. Buffer through a guarded command substitution, or, if pipefail isn't set, label it defensive — don't claim it's the active bug.
5. **Audit the whole sourced chain.** A top-level `set -e` propagates into every sourced lib; check the last statement of each helper, not just the entrypoint.
6. **Prove each fix red-first.** Write the failing test reproducing the production condition (absent file, large input, stdin-draining subprocess), then fix, then green. State the real mechanism in the test comment — never encode a disproven first hypothesis (e.g. "SIGPIPE under set -e" when it's actually only fatal under pipefail).

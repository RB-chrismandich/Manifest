---
name: errexit-safe-shell-counters
description: Use when writing or debugging bash under `set -e` that increments counters with `((var++))`/`((n--))` — the arithmetic command returns exit 1 when its result is 0, silently aborting the script on the first increment from zero (and only on bash ≥4, so macOS bash 3.2 hides it until CI).
---
# Errexit-Safe Shell Counters

Distinct from `shell-pipefail-subshell-audit` (pipefail + `$()` parsing empty input). This is the `((...))`-returns-1-on-zero trap that passes locally and dies in CI.

1. **Know the trap.** In bash, `((expr))` and `let` return exit status 1 whenever the arithmetic result is `0`. `((count++))` is *post*-increment — it evaluates to the OLD value — so the very first `((count++))` when `count=0` evaluates to 0 and returns 1.
2. **See why it aborts.** Under `set -e`/`set -euo pipefail`, that nonzero status kills the script — usually mid-loop, right after the action you just counted — giving a baffling silent exit with no error message.
3. **Understand why it's CI-only.** bash 3.2 (default macOS `/bin/bash`) does NOT trip errexit on `((...))`; bash ≥4 (Linux, GitHub/GitLab runners) does. The suite is green on your Mac and red in CI.
4. **Confirm empirically before touching code.** Run `bash -c 'set -e; v=0; ((v++)); echo survived; echo $?'` on `/bin/bash` AND a bash-5 (`/opt/homebrew/bin/bash`, or `brew install bash`). Divergent exit codes prove this bug.
5. **Fix to an always-success form.** Replace `((var++))` with `var=$((var + 1))` (clearest, shellcheck-clean). Alternatives: `: $((var++))` or `((var++)) || true`.
6. **Sweep, don't spot-fix.** `grep -rnE '\(\([a-zA-Z_]+(\+\+|--)\)\)' path/to/scripts/*.sh` — one zero-start counter anywhere is a latent abort. Fix every site.
7. **Re-verify under bash ≥4 with errexit active**, run the affected tests, and consider a repo lint guard (sibling to any array-expansion guard) so the pattern can't return.
